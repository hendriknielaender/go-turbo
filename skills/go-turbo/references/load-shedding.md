# Load Shedding

Passive and active shedding, and the response codes that tell a caller to back
off rather than retry immediately.

## Passive and active load shedding

Passive shedding lets an existing bound apply backpressure: a full queue
rejects, a semaphore declines admission, or a deadline expires. It is simple
and tied directly to a resource, but may react only after latency is already
high.

Active shedding rejects earlier using signals such as inflight work, queue
age, CPU saturation, dependency latency, or a concurrency controller. Use a
signal causally related to capacity. Process-wide CPU can be misleading when
the real bottleneck is one database pool; error rate can rise because shedding
already works.

Add hysteresis: enter shedding at a high watermark sustained for a short
window, and exit only below a lower watermark for a recovery window. Separate
thresholds prevent rapid on/off oscillation. Rate-limit state-change logs and
export current mode, trigger, duration, and rejection reason.

Never make readiness fail merely because the instance is shedding ordinary
load unless removal is the intended recovery. Ejecting every overloaded
instance transfers its traffic to the remainder and can collapse the fleet.

## HTTP overload responses

Use `503 Service Unavailable` when temporary capacity prevents service. Include
`Retry-After` only when the server has a meaningful estimate; the value is an
HTTP date or integer seconds. Clients still need jitter and a budget.

```go
package overload

import (
	"net/http"
	"strconv"
	"time"
)

func Reject(w http.ResponseWriter, retryAfter time.Duration) {
	if retryAfter > 0 {
		seconds := int64(retryAfter / time.Second)
		if retryAfter%time.Second != 0 {
			seconds++
		}
		if seconds < 1 {
			seconds = 1
		}
		w.Header().Set("Retry-After", strconv.FormatInt(seconds, 10))
	}
	http.Error(w, "temporarily unavailable", http.StatusServiceUnavailable)
}
```

Use `429 Too Many Requests` for a caller-specific rate limit when that is the
actual condition. Emit a low-cardinality machine-readable reason in headers or
the response schema without exposing internal capacity details.
