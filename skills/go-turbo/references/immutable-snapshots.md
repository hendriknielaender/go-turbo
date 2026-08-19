# Immutable Snapshots and Lazy Init

Publish a snapshot readers never mutate, and initialise once without paying a
lock on every read.

## Immutable snapshots

Read-mostly state such as configuration or routing rules can remove locks from
the read path by publishing a fully built snapshot.

```go
type Config struct {
	timeout  time.Duration
	features map[string]bool
}

func newConfig(timeout time.Duration, features map[string]bool) *Config {
	cloned := make(map[string]bool, len(features))
	maps.Copy(cloned, features)
	return &Config{timeout: timeout, features: cloned}
}

var current atomic.Pointer[Config]

func reload(raw []byte) error {
	timeout, features, err := parseConfig(raw)
	if err != nil {
		return err
	}
	current.Store(newConfig(timeout, features))
	return nil
}

func serve() error {
	cfg := current.Load() // one version for the whole operation
	if cfg == nil {
		return errors.New("configuration is not initialized")
	}
	return use(cfg)
}
```

Immutability must be deep. Clone maps, slices, and pointed-to objects before
publication, keep mutable fields unexported, and do not return aliases that a
caller can modify. Load the pointer once per logical operation so fields cannot
come from different versions. Rebuild only affected immutable segments if a
complete rebuild is measured as too expensive.

## Lazy initialization

Use the standard once helpers for initialization that may be called
concurrently:

```go
var client = sync.OnceValue(func() *Client {
	return newClient()
})

var configuration = sync.OnceValues(func() (*Config, error) {
	return loadConfig()
})
```

They invoke the function once and replay its result. If the function panics,
subsequent calls panic with the same value. That behavior is not a retry
policy. Use an explicit state machine under a mutex when initialization must be
retryable, refreshable, or cancellable.

Do not publish a `ready` flag before assigning the object. Reimplementing
`sync.Once` with atomics requires a correct in-progress state, waiter behavior,
panic behavior, and memory publication; it is almost never a worthwhile hot
path.
