# The Netpoller

It already does the event loop. Rebuilding it is a measured decision, rarely a
win.

For pollable network descriptors, the runtime integrates platform readiness
mechanisms such as epoll, kqueue, and IOCP. A goroutine waiting for socket
readiness can park without dedicating an OS thread; readiness makes it
runnable again. This makes straightforward blocking-style network code scale
well when deadlines, buffer ownership, and admission are controlled.

Not every operation follows this path. Regular file I/O on common Unix
systems, cgo calls, some name-resolution paths, device I/O, and arbitrary
syscalls may block an OS thread. TLS, compression, parsing, and application
work consume CPU after readiness. Confirm actual blocking and thread behavior
with goroutine profiles and execution traces.

**Keep goroutine-based I/O when:** standard network APIs meet throughput and
tail-latency goals. **Consider a custom event loop only when:** profiles prove
runtime scheduling or per-connection state is the remaining bottleneck and a
benchmark includes cancellation, backpressure, partial I/O, and failures.
Custom loops backfire through portability loss, complex ownership, starvation,
and duplicated runtime behavior. Never remove deadlines or cancellation for
speed.
