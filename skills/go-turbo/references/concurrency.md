# Concurrency

Concurrency is a capacity tool, not a throughput guarantee. Start by removing
work and choosing the right algorithm. Then bound in-flight work, make
ownership explicit, and measure contention before reaching for atomics or
cache-line tricks.

## Contents

- [Bound every source of concurrency](#bound-every-source-of-concurrency)
- [Choose the bound from the bottleneck](#choose-the-bound-from-the-bottleneck)
- [Mutexes, atomics, and ownership](#mutexes-atomics-and-ownership)
- [Sharding contended state](#sharding-contended-state)
- [Immutable snapshots](#immutable-snapshots)
- [Lazy initialization](#lazy-initialization)
- [Channels and value ownership](#channels-and-value-ownership)
- [Context and cancellation](#context-and-cancellation)
- [Process signals and graceful shutdown](#process-signals-and-graceful-shutdown)
- [Goroutine lifetime](#goroutine-lifetime)
- [Backpressure](#backpressure)
- [Version compatibility](#version-compatibility)

## Bound every source of concurrency

One goroutine per independent operation is idiomatic when the operation count
is already bounded. It is unsafe when input is unbounded: each goroutine adds
live state, queued work, and pressure on downstream services.

For cancellable work that can fail, a limited `errgroup` is a compact default:

```go
func process(ctx context.Context, items []Item, limit int) error {
	if limit < 1 {
		return fmt.Errorf("worker limit must be positive: %d", limit)
	}

	g, groupCtx := errgroup.WithContext(ctx)
	g.SetLimit(limit)
	for _, item := range items {
		if err := groupCtx.Err(); err != nil {
			break
		}
		g.Go(func() error {
			return handle(groupCtx, item)
		})
	}
	if err := g.Wait(); err != nil {
		return err
	}
	return ctx.Err()
}
```

Every operation called by `handle` must honor `groupCtx`; a concurrency limit
cannot rescue an uninterruptible worker. `SetLimit` must not be changed while
workers are active. Use `TryGo` only when rejection or a fallback path is part
of the contract.

A fixed worker pool is useful for a long-lived stream. Give it one owner that
closes the jobs channel, make result delivery cancellable, and wait for every
worker during shutdown. A semaphore is useful when preserving the existing
call shape matters. Both are capacity bounds, not reasons to keep an
unnecessary pipeline.

Avoid nested independent pools. If an outer request fan-out of 32 invokes an
inner fan-out of 32, the real bound is 1,024. Prefer one shared budget for the
scarce resource.

## Choose the bound from the bottleneck

- CPU work usually starts near `runtime.GOMAXPROCS(0)`. Increase the count only
  when a benchmark shows useful overlap rather than scheduler and cache cost.
- I/O work is bounded by the dependency: connection-pool capacity, rate limit,
  file descriptors, memory per operation, or the peer's tested concurrency.
- Mixed stages deserve separate budgets. A large I/O queue should not multiply
  CPU-heavy parsing behind it.

Sweep the limit under representative load. Watch throughput, tail latency,
queue depth, allocation rate, blocked time, downstream errors, and scheduler
latency. Select the knee of the curve with headroom; the largest number that
survived one test is not a capacity plan.

`GOMAXPROCS` is not a worker-pool size for I/O. Current Go runtimes derive and
periodically update the default from available CPUs, affinity, and supported
container limits. Override it only for an operational reason backed by data.
`runtime.LockOSThread` is for APIs that require thread affinity, not a general
scheduler optimization. OS CPU affinity is likewise deployment policy: it can
reduce migration in a controlled workload or strand the scheduler on the wrong
CPUs, so keep it behind a repeatable system benchmark.

## Mutexes, atomics, and ownership

The cheapest synchronization is exclusive ownership: keep mutable state in one
goroutine or partition it so concurrent workers never touch the same object.
When sharing is required, choose the simplest primitive that preserves the
invariant.

- `sync.Mutex`: multiple fields or a multi-step invariant.
- `sync.RWMutex`: only after a benchmark demonstrates that parallel, long
  reads outweigh its additional bookkeeping. It cannot be upgraded or
  downgraded.
- typed `sync/atomic` values: one independent word such as a counter, flag, or
  immutable pointer.
- channels: coordination and ownership transfer, not a faster mutex.

Go's atomic operations are sequentially consistent. An atomic flag does not
make adjacent non-atomic state safe. Publish an entire immutable object through
an `atomic.Pointer[T]`, or protect the complete invariant with a lock.

```go
type Counters struct {
	requests atomic.Uint64
	failures atomic.Uint64
}

func (c *Counters) Record(err error) {
	c.requests.Add(1)
	if err != nil {
		c.failures.Add(1)
	}
}
```

Typed atomic values and lock types must not be copied after first use. A single
heavily updated atomic can itself become a cache-coherence bottleneck; shard or
aggregate per worker only after contention is visible in measurements.

Use `CompareAndSwap` when the operation is a claim, not a separate observation
and update:

```go
if !started.CompareAndSwap(false, true) {
	return
}
startOnce()
```

Do not turn a multi-state protocol into a clever CAS loop without tests for
all transitions, cancellation, and ABA/lifetime hazards. A clear mutex is
usually faster to maintain and often fast enough to run.

## Sharding contended state

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

## Immutable snapshots

Read-mostly state such as configuration or routing rules can remove locks from
the read path by publishing a fully built snapshot.

```go
type Config struct {
	timeout  time.Duration
	features map[string]bool
}

func newConfig(timeout time.Duration, features map[string]bool) *Config {
	cloned := make(map[string]bool, len(features))
	maps.Copy(cloned, features)
	return &Config{timeout: timeout, features: cloned}
}

var current atomic.Pointer[Config]

func reload(raw []byte) error {
	timeout, features, err := parseConfig(raw)
	if err != nil {
		return err
	}
	current.Store(newConfig(timeout, features))
	return nil
}

func serve() error {
	cfg := current.Load() // one version for the whole operation
	if cfg == nil {
		return errors.New("configuration is not initialized")
	}
	return use(cfg)
}
```

Immutability must be deep. Clone maps, slices, and pointed-to objects before
publication, keep mutable fields unexported, and do not return aliases that a
caller can modify. Load the pointer once per logical operation so fields cannot
come from different versions. Rebuild only affected immutable segments if a
complete rebuild is measured as too expensive.

## Lazy initialization

Use the standard once helpers for initialization that may be called
concurrently:

```go
var client = sync.OnceValue(func() *Client {
	return newClient()
})

var configuration = sync.OnceValues(func() (*Config, error) {
	return loadConfig()
})
```

They invoke the function once and replay its result. If the function panics,
subsequent calls panic with the same value. That behavior is not a retry
policy. Use an explicit state machine under a mutex when initialization must be
retryable, refreshable, or cancellable.

Do not publish a `ready` flag before assigning the object. Reimplementing
`sync.Once` with atomics requires a correct in-progress state, waiter behavior,
panic behavior, and memory publication; it is almost never a worthwhile hot
path.

## Channels and value ownership

Choose channel capacity from semantics:

- unbuffered channels require sender and receiver to rendezvous;
- bounded buffers absorb a known burst and then apply backpressure;
- closing is a sender-owned broadcast that no more values will arrive.

Capacity is retained memory, not free throughput. An oversized channel hides
overload until latency and memory have already grown. An unbounded queue built
around a slice merely moves the eventual failure.

A channel transfers its element by value. Large structs enlarge buffered
channel storage and can make copying material. A pointer is not an automatic
fix: it can force an escape, adds GC-visible indirection, extends the object's
lifetime, and can introduce a race if sender and receiver both mutate it.
Prefer a small immutable value, an identifier, or an explicit ownership token.
Send a pointer when the object already has a suitable lifetime and ownership is
unambiguous, then benchmark. Never return a pooled object until the receiver is
finished with it.

Non-blocking sends are appropriate only when loss is intentional and counted:

```go
select {
case samples <- sample:
default:
	dropped.Add(1)
}
```

For a hot counter, an atomic is normally cheaper than sending every increment
to a collector goroutine. For a queue, include cancellation in both send and
receive paths.

## Context and cancellation

`context.Context` prevents obsolete work from consuming capacity. Pass it as
the first parameter, do not store it in a long-lived struct, and call every
returned cancel function so timers and parent-child links are released.

```go
func lookup(ctx context.Context, db *sql.DB, id string) (Record, error) {
	queryCtx, cancel := context.WithTimeout(ctx, 750*time.Millisecond)
	defer cancel()

	var out Record
	err := db.QueryRowContext(queryCtx, query, id).Scan(&out.ID, &out.Name)
	return out, err
}
```

Downstream code must use context-aware APIs and select on `ctx.Done()` around
blocking channel operations. In a CPU loop, check cancellation at a cadence
that bounds wasted work without placing a channel check in every tiny
iteration. `context.Cause` preserves a domain-specific cancellation cause when
the caller used a cause-aware constructor.

Context values are only for request-scoped metadata that crosses API
boundaries. Use an unexported, typed key plus accessors; strings can collide
between packages.

```go
type requestIDKey struct{}

func WithRequestID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, requestIDKey{}, id)
}

func RequestID(ctx context.Context) (string, bool) {
	id, ok := ctx.Value(requestIDKey{}).(string)
	return id, ok
}
```

Do not use values for dependencies, optional parameters, or mutable business
state. Value lookup walks a context chain; frequently accessed hot data belongs
in an explicit parameter.

## Process signals and graceful shutdown

`signal.NotifyContext` gives the process one cancellation root and a stop
function that unregisters signal handling. Graceful shutdown needs a fresh,
bounded context because the signal-derived context is already canceled.

```go
func run(parent context.Context, srv *http.Server) error {
	runCtx, stop := signal.NotifyContext(
		parent,
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	serveErr := make(chan error, 1)
	go func() {
		serveErr <- srv.ListenAndServe()
	}()

	select {
	case err := <-serveErr:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	case <-runCtx.Done():
	}
	stop() // restore normal signal handling while the bounded drain runs

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	shutdownErr := srv.Shutdown(shutdownCtx)
	if shutdownErr != nil {
		shutdownErr = errors.Join(shutdownErr, srv.Close())
	}

	err := <-serveErr
	if errors.Is(err, http.ErrServerClosed) {
		err = nil
	}
	return errors.Join(shutdownErr, err)
}
```

`Server.Shutdown` closes listeners, closes idle connections, and waits for
active HTTP connections to become idle. It does not wait for hijacked
connections such as WebSockets. Track those separately, signal their protocol
shutdown from `RegisterOnShutdown`, and wait for their owners within the same
shutdown budget. Stop accepting work first, and keep dependencies available
until admitted work has drained.

## Goroutine lifetime

Every goroutine needs an owner, an exit condition, and a join point. Common
leaks are a send with no receiver, a range over a channel no owner closes, a
timer or ticker never stopped, and network I/O with neither deadline nor a
close on cancellation.

On ordinary platforms, Go begins with a 2 KiB minimum stack model at process
startup; stacks grow and can shrink, and current runtimes may adapt the
starting size for later goroutines from observed stack use. Goroutines are
inexpensive, not free: stacks, referenced buffers, queued values, timers, and
descriptors all multiply with concurrency.

Cancellation does not interrupt an arbitrary blocking `Read`. For a
`net.Conn`, the cancellation owner should close the connection or set a
deadline; `Close` unblocks pending reads and writes. For a channel operation,
select on both the channel and `ctx.Done()`.

Compare goroutine profiles under steady load rather than relying on one count:

```sh
curl -sS http://127.0.0.1:6060/debug/pprof/goroutine?debug=1
```

Growing groups with the same blocked stack are leak candidates. Add tests that
cancel, force errors, and shut down every pipeline; run `go test -race` for any
concurrency change. Block and mutex profiles plus `go tool trace` distinguish
queueing, lock contention, and scheduler delay. Keep diagnostic endpoints on a
protected listener. Go 1.26 also offers the experimental
`GOEXPERIMENT=goroutineleakprofile` build option and `goroutineleak` pprof
profile; treat its format and availability as experimental.

## Backpressure

When arrival rate exceeds service rate, select an explicit outcome:

1. block the producer with a bounded queue or concurrency gate;
2. reject or shed work with an observable error;
3. persist it to a durable queue with a finite retention policy.

Define the bound in bytes as well as items when item sizes vary. Include queued
work in the request deadline; otherwise an operation can consume its entire
budget before it starts. Report queue depth, wait duration, rejection count,
and oldest-item age.

TCP flow control is useful but incomplete application backpressure. Stopping
reads eventually closes the receive window, yet one slow consumer can still
fill an application queue or block a shared fan-out. Bound per-connection
state, use write deadlines, and disconnect a lagging peer according to the
protocol contract.

Optimization stops when throughput and tail latency meet the target without
unsafe ownership or unbounded state. Atomics, padding, and lock-free structures
need a contention profile and a benchmark that keeps race freedom intact.

## Version compatibility

The examples target current Go. For an older module, preserve its minimum
version unless the task explicitly changes it: use `ctx.Err()` instead of
`context.Cause` before Go 1.20; use `sync.Once` instead of `OnceValue` or
`OnceValues` and clone maps manually before Go 1.21; and bind a per-iteration
copy before a goroutine when the module uses pre-1.22 range semantics. Check
the exact dependency version for `errgroup.SetLimit`. Compile and race-test
with the repository's oldest supported toolchain, not only the developer's
newest one.
