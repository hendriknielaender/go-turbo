# Choosing a Data Structure

Choose from the operation mix, the size distribution, and the access pattern —
not from what reads as sophisticated.

## Choose by workload, not fashion

Write down the operation mix and its bounds before choosing a representation:

- input size and its high percentile, not only its average;
- read, insert, delete, and iteration frequency;
- whether stable ordering is part of the contract;
- ownership, aliasing, and concurrent access;
- maximum retained memory and acceptable rejection behavior.

Big-O notation predicts scaling, not the winner for every size. Hashing,
indirection, cache misses, and allocation can make an asymptotically better
structure slower for a tiny bounded set. Conversely, a fast linear scan at
eight elements becomes an incident if an attacker can supply eight million.
Enforce the bound at the trust boundary when the choice depends on it.

Prefer a direct algorithmic fix when profiles show repeated work: index data
once instead of rescanning it, aggregate in one pass instead of sorting only
to count, and stop parsing once the answer is known. Preserve correctness for
duplicates, empty inputs, integer overflow, and adversarial ordering.

## Measurement and review gates

For an algorithm or representation change:

1. Add property or differential tests covering empty, duplicate, maximum,
   and adversarial inputs.
2. Benchmark representative sizes, including the bound that triggers the
   design choice, with allocation reporting and repeated samples.
3. Profile the complete caller; a faster lookup is irrelevant if parsing or
   I/O dominates.
4. Inspect live memory, not only bytes allocated per operation. Retention can
   worsen while microbenchmark allocations improve.
5. Run the race detector for any ownership or synchronization change.

Keep the simpler structure when results overlap within noise. Complexity is
a production cost too, especially when an invariant must survive future edits.
