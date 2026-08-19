# DNS

Resolution sits in front of every new connection. Cache behaviour and resolver
choice matter most when connection churn is already high.

Name resolution is platform- and configuration-dependent. On Unix, Go may use
its built-in resolver or the native resolver through cgo. Diagnose the actual
choice in a staging or diagnostic run:

```sh
GODEBUG=netdns=1 ./service
GODEBUG=netdns=go+1 ./service
GODEBUG=netdns=cgo+1 ./service
```

The first prints the resolver decision; the latter two force a resolver and
print diagnostics. A forced choice can change compatibility with the host's
name-service configuration, so it is an experiment, not a blanket production
optimization. `net.Resolver.PreferGo` scopes the preference to one resolver.

Attach `httptrace` DNS and connect hooks to measure lookup count, duration,
addresses, and errors. A trace callback may occur more than once because of
address fallback. Reused transport connections perform no lookup, so DNS
metrics must be interpreted alongside reuse and dial metrics.

`net.Resolver` does not promise an application-level TTL cache. A native
resolver may benefit from operating-system caching, while the built-in path may
query configured resolvers. If lookups dominate after connection reuse is
healthy, prefer a well-operated local caching resolver. An in-process cache
must honor positive and negative TTLs, coalesce concurrent misses, rotate
addresses, bound memory, and define stale/failure behavior. Pinning one resolved
IP can defeat load balancing and failover.

Long-lived connections naturally outlive DNS answers. Decide whether endpoint
changes are adopted through server-driven drain, bounded connection lifetime,
idle eviction, or an address-aware dial policy. Dialing every request solely to
refresh DNS trades the problem for handshake and port cost.
