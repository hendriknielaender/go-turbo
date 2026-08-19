# Load Testing

Open-loop load, coordinated omission, and why a closed-loop harness flatters the
system under test.

## Load-test systems

Choose the generator by the question:

- use an open-loop fixed-rate generator for latency at a known offered load;
- use a closed-loop/high-throughput generator to find a saturation ceiling;
- use scripted scenarios for realistic multi-step behavior;
- use protocol-specific tools for raw TCP, HTTP/2, gRPC, or QUIC and assert the
  protocol actually negotiated.

Closed-loop clients pause submissions while the service is slow and can hide
the requests that would have arrived during the stall. Call out coordinated
omission whenever reporting latency from such a test.

Test a rate curve rather than one point: below expected load, at target, near
saturation, and beyond saturation. Report offered rate, achieved throughput,
errors/rejections, p50/p95/p99/max latency, CPU, memory, GC, queue depth, open
connections, and downstream saturation.

Separate warm and cold connection-pool/TLS-session tests. For high connection
churn, watch the load generator's file descriptors, CPU, ephemeral ports, and
`TIME_WAIT`; a saturated generator can make a healthy server appear slow.

Capture profiles during the steady portion of the load test, not during idle
startup or uncontrolled ramp-up.
