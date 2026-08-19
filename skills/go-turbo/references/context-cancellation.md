# Context and Cancellation

Every wait needs a cancellation path, and cancellation only works if it is
propagated all the way down.

`context.Context` prevents obsolete work from consuming capacity. Pass it as
the first parameter, do not store it in a long-lived struct, and call every
returned cancel function so timers and parent-child links are released.

```go
func lookup(ctx context.Context, db *sql.DB, id string) (Record, error) {
	queryCtx, cancel := context.WithTimeout(ctx, 750*time.Millisecond)
	defer cancel()

	var out Record
	err := db.QueryRowContext(queryCtx, query, id).Scan(&out.ID, &out.Name)
	return out, err
}
```

Downstream code must use context-aware APIs and select on `ctx.Done()` around
blocking channel operations. In a CPU loop, check cancellation at a cadence
that bounds wasted work without placing a channel check in every tiny
iteration. `context.Cause` preserves a domain-specific cancellation cause when
the caller used a cause-aware constructor.

Context values are only for request-scoped metadata that crosses API
boundaries. Use an unexported, typed key plus accessors; strings can collide
between packages.

```go
type requestIDKey struct{}

func WithRequestID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, requestIDKey{}, id)
}

func RequestID(ctx context.Context) (string, bool) {
	id, ok := ctx.Value(requestIDKey{}).(string)
	return id, ok
}
```

Do not use values for dependencies, optional parameters, or mutable business
state. Value lookup walks a context chain; frequently accessed hot data belongs
in an explicit parameter.
