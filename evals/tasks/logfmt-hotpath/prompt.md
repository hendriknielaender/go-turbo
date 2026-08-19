Our CPU profile from production shows logfmt.Render is the single hottest
function in the log shipper: 18% of process CPU, and the allocation profile
attributes 31% of bytes allocated to it. Flushes happen ~400x/sec per instance
with batches of a few hundred entries.

Make Render faster. The output format is a wire contract with the shipper and
must not change; logfmt_test.go pins it and must keep passing.
