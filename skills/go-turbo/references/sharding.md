# Sharding Contended State

Splitting one lock into N is a measured fix for a measured contention problem,
and it changes what you can atomically observe.

When one map lock is measured as hot, split keys across independent locks. Use
a power-of-two shard count only if the hash has useful low bits.

```go
const shardCount = 64

type mapShard struct {
	mu sync.Mutex
	m  map[string]Value
}

type ShardedMap struct {
	seed   maphash.Seed
	shards [shardCount]mapShard
}

func NewShardedMap() *ShardedMap {
	m := &ShardedMap{seed: maphash.MakeSeed()}
	for i := range m.shards {
		m.shards[i].m = make(map[string]Value)
	}
	return m
}

func (m *ShardedMap) shard(key string) *mapShard {
	h := maphash.String(m.seed, key)
	return &m.shards[h&(shardCount-1)]
}

func (m *ShardedMap) Load(key string) (Value, bool) {
	s := m.shard(key)
	s.mu.Lock()
	v, ok := s.m[key]
	s.mu.Unlock()
	return v, ok
}
```

Benchmark shard count and skew with real keys. Sharding adds hashing and makes
whole-map operations more complicated. `sync.Map` is a specialized option for
entries written once and read many times, or disjoint key sets updated by
different goroutines; a typed map plus a lock is the normal choice elsewhere.

Do not append a guessed byte array to a shard and call it cache-line safe. The
size of a mutex is not an API, cache-line size varies by architecture, and
padding after the map does not isolate the lock at the start of the next
element. Padding is a paid optimization after a false-sharing benchmark. If it
is justified, define a target-specific separation constant in build-tagged
files and surround only the measured hot word:

```go
// turbo: isolates a measured false-sharing hotspot at the cost of footprint;
// cacheLinePad is defined per supported GOARCH and validated on deployment
// hardware because Go has no public portable cache-line alignment constant.
type isolatedCounter struct {
	_ [cacheLinePad]byte
	n atomic.Uint64
	_ [cacheLinePad]byte
}
```

The two-sided separation prevents adjacent hot counters from sharing a line
when the target assumption is correct; it does not create a general Go
alignment guarantee. Keep this code and its benchmark together.
