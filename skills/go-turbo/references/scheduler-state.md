# Scheduler Pressure

Read G-M-P state before changing a knob. Latency that does not track CPU is a
scheduling symptom.

The scheduler coordinates:

- **G:** a goroutine and its stack/state;
- **M:** an OS thread;
- **P:** the execution resources required to run Go code.

There are exactly `GOMAXPROCS` Ps. Each P has local runnable work; the runtime
also uses global queues and work stealing. When a goroutine blocks in a system
call, its M can release the P so another M runs Go work. Blocking cgo calls,
system calls, and `runtime.LockOSThread` may still grow the OS-thread count.

Take a bounded scheduler snapshot:

```sh
GODEBUG=schedtrace=1000 ./service
GODEBUG=schedtrace=1000,scheddetail=1 ./service
```

Interpret trends, not one line:

- runnable work with no idle Ps indicates CPU demand or long non-preempted
  work; adding goroutines cannot create CPU capacity;
- rising thread count far above Ps points to blocking calls, cgo, or locked
  threads;
- many waiting goroutines can be healthy I/O concurrency or a leak; classify
  wait reasons in profiles and traces.

`debug.SetMaxThreads` is a crash-before-system-exhaustion safety limit, not a
throughput control. Lowering it without accounting for worst-case syscall,
cgo, and locked-thread demand can crash the process.

**Tune scheduler-facing concurrency when:** traces and load tests show runnable
delay, blocking, or oversubscription. **Backfires when:** worker pools are
sized only from core count despite I/O waits, more goroutines amplify queues
and memory, or scheduler debug output is left enabled without measuring its
diagnostic overhead.
