# UDP Datagrams

No delivery, no ordering, no congestion control — you supply whichever of those
the application actually needs.

UDP preserves datagram boundaries but supplies no delivery, ordering,
deduplication, congestion, or session semantics. A successful write means the
local stack accepted the packet, not that a peer processed it. Design message
IDs, expiry, duplicate handling, authentication, and retry policy when the
application needs them.

Set an application datagram maximum that stays within the deployment path's
effective MTU when possible. IP fragmentation magnifies loss and middlebox
failure. A receive buffer smaller than a datagram can truncate it; choose a
buffer that covers the protocol limit and use APIs that expose truncation when
the platform and implementation allow it. Reject, do not parse, a truncated
message.

Connected UDP narrows the peer and can simplify error delivery, but it does
not become a stream or a reliable connection. For a shared packet socket,
validate source addresses and never let one sender monopolize a single
unbounded processing queue.

Use UDP directly for telemetry or discovery only when occasional loss and
reordering are acceptable by contract. Building reliable transport on UDP is
a protocol project; prefer a reviewed transport rather than growing ad hoc
ACK, retransmission, congestion-control, and crypto layers.
