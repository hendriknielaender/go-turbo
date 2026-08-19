# QUIC

Streams, flow control, and connection migration in one transport, with handshake
and congestion behaviour that differ from TCP in ways that change tuning.

QUIC is an encrypted, multiplexed transport carried over UDP. It integrates
cryptographic handshake state with transport state and can support connection
migration. Streams are ordered within themselves. Missing data on one stream
does not create a transport-ordering requirement for data on another, although
shared connection limits can still reduce both streams' progress.

There are two flow-control budgets: each stream and the connection as a whole.
If the receiver stops consuming, the sender eventually blocks even when the
network is writable. If one application component hoards the connection-level
window, other streams can stall. Bound concurrent streams and bytes in flight,
and keep consuming or cancel streams that are no longer needed.

Zero-round-trip data can reduce setup latency for a resumed relationship, but
it may be replayed. Use it only when the operation's application-level
semantics are inherently replay-safe or idempotent without relying on the
early-data transport to deduplicate it. Anti-replay windows, single-use
tickets, and idempotency keys are defense in depth; they are not permission to
put a non-idempotent mutation in early data. Authentication alone also does
not make a mutation replay-safe. Never place an unconditional charge, grant,
or destructive update in early data.

Loss recovery operates on QUIC packets and retransmittable frame data. One
packet can contain frames for multiple streams as well as connection-control
frames. When loss detection declares that packet lost, data that is still
needed is scheduled in new packets; the original UDP datagram is not replayed
wholesale. Acknowledged or obsolete data need not be sent again. Independent
stream ordering limits the delivery dependency, while the shared congestion
controller and connection flow-control budget can still slow otherwise
unaffected streams.

Connection migration preserves a logical connection across address changes;
it does not guarantee every middlebox accepts the traffic or that application
authorization remains valid for the new path. Log stable connection identity
without treating an IP address as identity.
