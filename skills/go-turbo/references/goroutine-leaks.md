# Goroutine Lifetime and Leaks

Every goroutine needs an owner and an exit path. A leak is a goroutine whose
lifetime nobody wrote down.

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

## Version compatibility

The examples target current Go. For an older module, preserve its minimum
version unless the task explicitly changes it: use `ctx.Err()` instead of
`context.Cause` before Go 1.20; use `sync.Once` instead of `OnceValue` or
`OnceValues` and clone maps manually before Go 1.21; and bind a per-iteration
copy before a goroutine when the module uses pre-1.22 range semantics. Check
the exact dependency version for `errgroup.SetLimit`. Compile and race-test
with the repository's oldest supported toolchain, not only the developer's
newest one.
