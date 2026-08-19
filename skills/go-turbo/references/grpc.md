# gRPC

Unary and streaming calls, and where the generated layer's costs land.

Unary RPC gives one request and one response with a generated typed contract.
It is usually the clearest default. Set deadlines, maximum message sizes, and
status mappings; a schema does not protect a server from an enormous repeated
field or a client that never finishes sending.

Server streaming fits one request followed by a sequence of results. Client
streaming fits incremental upload or aggregation. Bidirectional streaming is
for truly independent message flows, not merely to avoid repeated unary-call
overhead. Every open stream retains protocol, flow-control, and application
state until completion or cancellation. Goroutine retention depends on the
selected gRPC implementation and handler design; do not assume either zero or
exactly one goroutine per open stream. Confirm it with goroutine and heap
profiles under representative stream counts.

Streaming changes failure semantics. Define whether partial results are
committed, how a client resumes, and whether messages have sequence IDs.
Propagate cancellation to producers, and stop work promptly when a send fails.
Do not assume concurrent sends on one stream are safe unless the selected API
documents it.

Generated message reuse and codec pooling are paid optimizations. They are
unsafe if ownership crosses calls or asynchronous sends retain memory. Profile
allocations, document lifetime, and race-test any reuse.
