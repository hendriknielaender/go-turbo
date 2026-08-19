# Sorting

Sort once and query many times; a repeated sort inside a loop is a complexity
bug wearing a library call.

## Sort once, query many times

Sorting costs `O(n log n)`, after which binary searches cost `O(log n)`.
That is attractive when a snapshot receives many queries. It is wasteful for
one query, and repeated insertion into the middle of a slice remains `O(n)`.
For mutable workloads, compare a map or a purpose-built tree rather than
silently paying copy costs.

Keep the comparator consistent with equality. Floating-point NaNs, locale
rules, and case folding can violate assumptions unless the domain defines an
ordering. When sorting shared data, copy it or transfer ownership; in-place
sorting is an observable mutation.
