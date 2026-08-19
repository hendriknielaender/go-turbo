# Using pprof

Capturing and reading CPU and memory profiles, including which endpoint answers
which question.

## Use pprof

For a service, expose profiles on a separately protected listener. Never expose
them directly to untrusted networks; profiles and handlers can reveal sensitive
data and consume substantial resources.

```go
import (
	"log"
	"net/http"
	_ "net/http/pprof"
)

func serveProfiles() {
	server := &http.Server{
		Addr:              "127.0.0.1:6060",
		ReadHeaderTimeout: 2 * time.Second,
	}
	log.Print(server.ListenAndServe())
}
```

Capture under the workload that exhibits the problem:

```sh
curl -o cpu.out 'http://127.0.0.1:6060/debug/pprof/profile?seconds=30'
curl -o heap.out 'http://127.0.0.1:6060/debug/pprof/heap'
curl -o allocs.out 'http://127.0.0.1:6060/debug/pprof/allocs'
go tool pprof -http=:0 cpu.out
```

Use profile differences when the baseline is meaningful:

```sh
go tool pprof -base=before.out after.out
```

Sampling changes what can be seen. Short profiles miss rare work; heap sampling
can underrepresent small allocations. Increase duration or sampling only with a
clear need and account for overhead.

## Read CPU and memory profiles

In CPU profiles, **flat** time is time attributed to a function itself;
**cumulative** time includes callees. Descend from high-cumulative/low-flat
callers before naming the bottleneck.

Common clues are starting points, not conclusions:

- allocator and GC frames: inspect their callers and an allocation profile;
- `runtime.growslice`: check capacity knowledge and append volume;
- map hashing/access: reduce lookups or reconsider the key/index;
- copying/memory movement: inspect conversions, growth, and ownership transfers;
- syscall frames: measure operation size and boundary frequency;
- semaphore/lock frames: use mutex and block profiles;
- stack growth: inspect recursion, large frames, and goroutine lifetime.

Use allocation and heap profiles for different questions:

- `allocs`: cumulative churn; identify what drives allocation rate and GC work;
- `heap`: live objects at capture; identify retention and live-set growth.

For a leak, capture two heap profiles after comparable warmup and offered load,
then diff them. Profiles attribute bytes to allocation sites, not to the code
that later retained the object; follow ownership from the allocation.
