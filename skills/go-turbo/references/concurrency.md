# Concurrency

Go makes concurrency cheap enough that the failure mode is rarely "not
concurrent enough." It is almost always unbounded concurrency, contention on
a shared structure, or a goroutine that never exits.

## Contents

- [Worker pools and bounded concurrency](#worker-pools-and-bounded-concurrency)
- [Sizing the pool](#sizing-the-pool)
- [Atomics vs mutexes](#atomics-vs-mutexes)
- [Sharding a contended structure](#sharding-a-contended-structure)
- [Immutable snapshot publishing](#immutable-snapshot-publishing)
- [Lazy initialization](#lazy-initialization)
- [Channels](#channels)
- [Context](#context)
- [Goroutine leaks](#goroutine-leaks)
- [Backpressure](#backpressure)

## Worker pools and bounded concurrency

`go handleItem(x)` in a loop over unbounded input is the most common
performance bug in Go services. It works beautifully in testing and falls
over in production: memory spikes with goroutine stacks and in-flight
buffers, the scheduler thrashes, and downstream systems get a stampede.

The simplest fix is a semaphore, which keeps the code shape you already have:

```go
sem := make(chan struct{}, 32)
var wg sync.WaitGroup

for _, item := range items {
    wg.Add(1)
    sem <- struct{}{}
    go func() {
        defer wg.Done()
        defer func() { <-sem }()
        handle(item)
    }()
}
wg.Wait()
```

A fixed pool avoids the per-item goroutine entirely and is better when items
are small and numerous:

```go
func Process(items []Item, workers int) []Result {
    jobs := make(chan Item)
    results := make(chan Result, len(items))

    var wg sync.WaitGroup
    for range workers {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for it := range jobs {
                results <- handle(it)
            }
        }()
    }

    for _, it := range items {
        jobs <- it
    }
    close(jobs)
    wg.Wait()
    close(results)

    out := make([]Result, 0, len(items))
    for r := range results {
        out = append(out, r)
    }
    return out
}
```

For anything with error handling or cancellation, `errgroup` with
`SetLimit` is less code and gets the edge cases right:

```go
g, ctx := errgroup.WithContext(ctx)
g.SetLimit(32)
for _, item := range items {
    g.Go(func() error { return handle(ctx, item) })
}
err := g.Wait()
```

**When not to pool.** Small bounded workloads (spawn directly — a pool is
overhead), and latency-critical single tasks where queueing delay is worse
than the concurrency risk.

## Sizing the pool

The right size depends on what the work is waiting for:

- **CPU-bound** (hashing, parsing, compression, serialization):
  `runtime.GOMAXPROCS(0)`, or slightly less if the process shares the machine.
  More workers than Ps just adds context switches and cache thrashing.
- **I/O-bound** (network calls, DB queries, disk): substantially more than
  the core count, because workers spend most of their time parked. The real
  bound is the downstream resource — DB connection pool size, rate limit,
  target service capacity. Size to that, not to your CPU count.
- **Mixed**: split into two pools with different sizes rather than picking a
  compromise that's wrong for both.

Symptoms of too many workers: throughput flat or falling as you add workers,
rising p99 latency, growing GC activity, high `sched` latency in
`go tool trace`. Ramp the count in a load test and take the knee of the
curve.

## Atomics vs mutexes

`sync/atomic` operates on single words with hardware instructions — no lock
queue, no scheduler involvement. For a counter or a flag it is meaningfully
faster than a mutex, and the gap widens sharply under contention because
mutex waiters get parked and rescheduled.

```go
type Stats struct {
    requests atomic.Int64
    errors   atomic.Int64
}

func (s *Stats) Record(err error) {
    s.requests.Add(1)
    if err != nil {
        s.errors.Add(1)
    }
}
```

The typed atomics (`atomic.Int64`, `atomic.Pointer[T]`, `atomic.Bool`,
Go 1.19+) are the ones to use — they can't be accidentally accessed
non-atomically, and they carry alignment guarantees the bare functions do
not.

Go's atomics are sequentially consistent. There is no relaxed/acquire/release
ordering as in C++ or Rust, which is a deliberate simplification: you cannot
tune the fences, and you also cannot get the memory-ordering bugs.

**Use atomics for:** counters, flags, a single pointer swapped wholesale,
CAS-based fast paths.

**Use a mutex for:** anything needing more than one word changed
consistently, multi-step invariants, or any critical section you would
struggle to reason about as a CAS loop. A mutex you understand beats a
lock-free structure you don't.

The atomic-gated fast path is a useful hybrid — but only when the atomic is
a genuine read-only signal:

```go
if !enabled.Load() {
    return    // no lock in the common case
}
mu.Lock()
defer mu.Unlock()
// ...
```

If the same goroutine also *sets* the flag, load-then-lock races. Use
`CompareAndSwap` so the check and the claim are one operation:

```go
if !started.CompareAndSwap(false, true) {
    return    // someone else already claimed it
}
```

`sync.RWMutex` is worth a specific caution: it is a win for genuinely
read-heavy workloads with long read sections, and a loss for short ones,
where the extra bookkeeping costs more than the mutex it replaced. Measure
before swapping `Mutex` for `RWMutex`.

## Sharding a contended structure

When a single lock is hot, splitting it beats widening it. Shard by key hash
so unrelated keys never touch the same lock:

```go
const shards = 64

type Map struct {
    s [shards]struct {
        mu sync.Mutex
        m  map[string]Value
        _  [40]byte   // keep each shard's lock on its own cache line
    }
}

func (m *Map) shard(k string) int {
    return int(maphash.String(seed, k) % shards)
}

func (m *Map) Get(k string) (Value, bool) {
    s := &m.s[m.shard(k)]
    s.mu.Lock()
    defer s.mu.Unlock()
    v, ok := s.m[k]
    return v, ok
}
```

The padding matters here: without it, adjacent shard mutexes share a cache
line and you get false sharing between shards that were supposed to be
independent.

`sync.Map` is a narrower tool than its name suggests. It is optimized for two
specific patterns: keys written once and read many times, and disjoint key
sets per goroutine. For a general read-write map it is usually slower than a
sharded plain map. Reach for it when it matches those patterns; otherwise
shard.

## Immutable snapshot publishing

For read-heavy, write-rare data — config, routing tables, feature flags,
compiled rulesets — publishing an immutable snapshot behind an atomic pointer
removes locking from the read path entirely.

```go
var current atomic.Pointer[Config]

func Get() *Config { return current.Load() }   // no lock, no contention

func Reload(raw []byte) error {
    cfg, err := parse(raw)
    if err != nil {
        return err     // old config stays live; a bad reload changes nothing
    }
    current.Store(cfg)
    return nil
}
```

Two properties make this work, and both are easy to break:

**Deep immutability.** Go's maps and slices are reference types. A snapshot
containing a map that someone else can still mutate is not immutable. Copy on
construction and never hand out the interior:

```go
func NewConfig(features map[string]bool) *Config {
    f := make(map[string]bool, len(features))
    maps.Copy(f, features)
    return &Config{Features: f}
}
```

**Consistent reads.** Load once per operation, not per field — otherwise
you can read half the old snapshot and half the new one:

```go
cfg := Get()                    // one load
if cfg.Features["beta"] && cfg.Timeout > 0 { ... }
```

Readers see either the old snapshot or the new one, never a mix, and a reader
holding the old pointer keeps it valid until it's done. That's eventual
consistency by design: updates aren't instantly visible. If you need
transactional multi-key updates, this isn't the pattern.

For large structures where rebuilding everything per update is too expensive,
segment it — a map of independently-swappable sub-snapshots — so an update
only rebuilds the segment it touches.

## Lazy initialization

```go
var getClient = sync.OnceValue(func() *Client {
    return newClient()
})
```

`sync.OnceValue` and `sync.OnceValues` (Go 1.21+) are the default. They are
shorter than `sync.Once` with a package-level variable, and there's no way to
accidentally read the value before it's set.

```go
var loadConfig = sync.OnceValues(func() (*Config, error) {
    return parse("config.yml")
})
```

`sync.Once` remains right when initialization has no return value or when
you need the flexibility of a raw block.

Hand-rolled atomic initialization is almost never worth it. The naive version
is wrong in a way that's easy to miss:

```go
// BROKEN: publishes the flag before the resource is ready.
if !ready.Load() {
    if ready.CompareAndSwap(false, true) {
        resource = expensiveInit()
    }
}
return resource   // another goroutine can get nil or a half-built resource
```

Getting it right requires a three-state protocol (uninitialized /
in-progress / done) plus a spin-with-`runtime.Gosched()` for the losers — and
if the initializer panics, the losers spin forever. `sync.OnceValue` handles
all of this, including re-panicking on subsequent calls. Only reach past it
if a profile shows the once-check itself is hot, which is rare.

## Channels

Channels are for coordination. They are not the fastest way to move data, and
using them as a queue in a hot path is a common mistake — every send/receive
is a lock plus potentially a goroutine park and reschedule.

- **Unbuffered** — a synchronization point. The sender blocks until a
  receiver is ready. Use when you want that rendezvous.
- **Buffered** — absorbs bursts. Size it deliberately: capacity is memory you
  will hold at peak, and an over-large buffer hides backpressure until it
  becomes an OOM.
- **`close`** is a broadcast to all receivers. Only the sender closes.

For high-frequency counters, prefer atomics over a channel to a collector
goroutine. For passing large values, send a pointer — a channel of large
structs copies the whole value twice.

`select` with a `default` gives a non-blocking try, which is the right shape
for "drop on overflow" metrics paths:

```go
select {
case metrics <- sample:
default:      // drop rather than block the request path
}
```

## Context

`context.Context` is how cancellation propagates. Its performance value is
negative work avoided: a request whose client disconnected shouldn't still be
querying the database.

```go
func handler(w http.ResponseWriter, r *http.Request) {
    ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
    defer cancel()

    rows, err := db.QueryContext(ctx, q)
    // ...
}
```

- Pass it as the first parameter, explicitly. Never store one in a struct
  field.
- `defer cancel()` always — a leaked `WithTimeout` context leaks a timer and
  keeps the parent's child list growing.
- Check `ctx.Err()` to distinguish `context.Canceled` (client went away, not
  your problem) from `context.DeadlineExceeded` (you were too slow — that's a
  metric worth having).
- `context.WithValue` is for request-scoped metadata only, and lookup is a
  linear walk up the chain. Don't put hot data in it; don't put business
  state in it at all.
- In long loops, check `ctx.Done()` between iterations rather than only at
  the top.

## Goroutine leaks

A leaked goroutine holds its stack, everything its stack references, and
whatever it has open. At scale this reads as a slow memory leak with no
obvious allocation site.

The three shapes that cause almost all of them:

```go
// 1. Send on a channel nobody will ever receive from.
func leak() {
    ch := make(chan int)      // unbuffered
    go func() { ch <- work() }()
    return                    // goroutine blocks forever
}

// 2. Range over a channel that is never closed.
for v := range ch { ... }     // producer died without close(ch)

// 3. Blocking network read with no deadline and no cancellation.
conn.Read(buf)                // peer vanished; this never returns
```

Fixes, in order of preference: give the goroutine a `ctx.Done()` case in a
`select`; set deadlines on all network I/O; buffer the result channel so the
sender can always complete; make ownership explicit so exactly one side
closes.

Detection:

```sh
curl http://localhost:6060/debug/pprof/goroutine?debug=1   # grouped by stack
```

Take two snapshots minutes apart under steady load and diff the counts. Any
stack whose count grows monotonically is your leak. `go.uber.org/goleak` in
tests catches most of these before they ship. Go 1.26 also has an
experimental goroutine leak profile
(`GOEXPERIMENT=goroutineleakprofile`, exposed at
`/debug/pprof/goroutineleak`) that identifies goroutines blocked on
primitives that can never be unblocked.

## Backpressure

When input arrives faster than you process it, something has to give. If you
don't choose what, the answer is memory, and the failure is an OOM at 3am.

The three viable answers:

1. **Block the producer.** A bounded channel or semaphore does this for free
   — a full buffer stalls the sender, which stalls its caller, propagating
   pressure back to the source. This is the default and usually right.
2. **Shed load.** Drop, or reject with a 429/`ResourceExhausted`. Right for
   metrics, telemetry, and anything where stale data is worthless. Use
   `select`/`default`.
3. **Buffer to durable storage.** Right when the data matters and the spike
   is bounded. It's a queue, with all a queue's operational weight.

What is never right is an unbounded in-memory queue. It doesn't remove the
pressure, it just delays the failure and converts it into an OOM.

For TCP specifically, the kernel already implements backpressure: if you stop
reading, the receive window closes and the peer's writes block. Small buffers
and prompt flushing push pressure back to the kernel and keep your memory
flat — but flushing aggressively means more, smaller segments, more syscalls,
and worse throughput on high-latency links. And TCP-level backpressure has no
application context: one slow client in a fan-out can stall a shared write
path. At scale, combine kernel backpressure with bounded per-client queues
and write deadlines so a single slow consumer can be dropped instead of
blocking everyone.
