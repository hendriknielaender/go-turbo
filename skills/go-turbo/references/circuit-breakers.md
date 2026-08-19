# Circuit Breakers

A breaker exists to stop paying for calls already known to fail. Its states and
thresholds are the whole design.

Use a maintained, tested circuit-breaker implementation when a breaker is
warranted. A plausible-looking bespoke breaker often races transitions,
admits too many probes, counts caller cancellations as dependency failures, or
flaps on sparse traffic. Configure and test these state semantics explicitly:

- **Closed:** requests pass. Only eligible dependency outcomes enter a rolling
  failure calculation, and a minimum sample volume prevents one failure from
  opening a quiet service.
- **Open:** requests fail fast until a monotonic-time recovery interval ends.
  The open result should be distinguishable from an attempted call.
- **Half-open:** a strictly bounded number of probes enter. Sufficient success
  closes the breaker; an eligible failure reopens it. All other calls reject.

One authority must perform each transition. Reset rolling state deliberately
on transitions, and define how concurrent completions from the previous state
are classified. Timeouts, transport failures, overload responses, application
errors, caller cancellation, and validation failures are different signals;
count only outcomes that indicate the protected dependency is unhealthy.

A breaker is not a concurrency limit. Requests admitted just before opening
can still pile up, and a healthy but saturated dependency can time out without
failing quickly. Pair the breaker with deadlines, admission control, and a
retry budget. Test state transitions with a controllable clock and concurrent
probes, then load-test recovery without a synchronized stampede.
