# Backpressure

When the consumer cannot keep up, the producer has to find out. Backpressure is
how that signal travels.

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
