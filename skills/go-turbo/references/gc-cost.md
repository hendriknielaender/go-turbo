# Collector Cost

What the collector actually spends, and which part of your program decides it.

Go 1.26 uses a concurrent, tracing, non-generational mark-and-sweep collector.
Short stop-the-world phases establish and finish a cycle; marking runs mostly
with the application, using write barriers and mutator assists to preserve the
object graph while it changes.

The Green Tea marking implementation is enabled by default in Go 1.26. It
batches scan work for better locality, but it does not change the operational
model: roots and reachable pointer-bearing memory must still be scanned, and
allocation still drives new cycles. A build with
`GOEXPERIMENT=nogreenteagc` is useful only as a controlled comparison when a
toolchain upgrade changes a measured workload.

Reason about three quantities:

1. **Allocation rate.** More heap bytes and objects per second consume
   allocator work and reach the next collection sooner.
2. **Live heap and roots.** Reachable heap objects, goroutine stacks, and
   globals determine mark work and the next heap goal.
3. **Scannable bytes.** Pointer-free data is cheaper for the collector to scan
   than a pointer-dense graph, though it still consumes memory, bandwidth, and
   reclamation work.

Do not assume that a short-lived heap object is free because it dies quickly;
the collector remains non-generational. Also do not replace compact values
with pointer graphs merely to reduce copying: that can increase allocations,
retention, cache misses, and scan work simultaneously.

**Optimize the model when:** profiles show allocator or GC CPU, assist time,
or memory pressure. **Backfires when:** code becomes pooled, pointer-free, or
manually packed without a workload-level improvement. Collector internals and
pause distributions change across releases; benchmark the deployed toolchain.
