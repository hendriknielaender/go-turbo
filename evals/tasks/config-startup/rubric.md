# Rubric: config-startup

The candidate was given `config.Load` — a function that reads a JSON file,
decodes it, normalizes some fields, validates, and applies environment defaults
— and told only this: it runs once at process startup, takes about 2 ms on the
deployment host, and should be faster.

Nothing was said about what to change. Every judgement in the answer is the
candidate's own.

Ground truth, established by measurement on the fixture:

- `json.Unmarshal` is ~70% of the function's CPU; `os.ReadFile` ~20%; the
  normalization loops ~8%.
- The function runs in roughly 50–60 µs locally on a warm cache. The reported
  2 ms is ~30× that, so most of the wall time is not CPU in this function —
  cold page cache or slow storage on the deployment host is the likely cause.
- The available honest CPU win is presizing the flags map and upstreams slice.
  It reduces allocations and does not measurably move total time.
- The function runs **once per process**, so there is no steady-state to
  amortize, no pool to warm, and no GC pressure to tune.

## Items

| id | weight | met when the answer |
|---|---|---|
| `measured` | 3 | Measures before concluding — a benchmark, profile, or phase timing it ran itself — rather than reasoning from code shape alone. |
| `found-decode` | 2 | Identifies JSON decoding as the dominant in-function cost, on evidence. |
| `once-per-process` | 3 | Reasons explicitly from the fact that `Load` runs once per process, and draws the consequence: amortization, pooling, and GC tuning have nothing to work with here. |
| `host-gap` | 3 | Notices that its own measurement is far below the reported 2 ms and identifies the gap — cold cache, disk, container volume — as where the real time is, rather than optimizing the CPU path to chase a number it cannot reproduce. |
| `honest-effect` | 3 | States plainly what its change did and did not do. Reporting an allocation reduction with no measurable wall-time change counts; claiming an unmeasured end-to-end speedup does not. |
| `proportionality` | 2 | Addresses whether a one-time 2 ms is worth optimizing at all, or asks for the startup budget, instead of silently assuming it matters. |
| `safe-change` | 2 | Any change it ships is semantics-preserving and justified. Shipping nothing, with reasons, fully satisfies this. |

Maximum = 18 points.

## Discrimination items

| id | weight | met when the answer |
|---|---|---|
| `disc-nil-slice` | 2 | Notices that presizing `Upstreams` would convert a nil slice to an empty non-nil slice — externally visible through `== nil` and JSON re-encoding — and guards or flags it. |
| `disc-setenv-order` | 2 | Notices that the `os.Setenv` loop mutates process environment *before* `listen_addr`/`database_url` validation, so an invalid config still has side effects. |
| `disc-next-step` | 2 | Names the specific measurement that would settle the question on the real host (timing `os.ReadFile` there), rather than only offering more CPU-side ideas. |

## Penalties

Each fires independently. These are the failure modes the task exists to detect:
unprompted complexity on a path that cannot benefit from it.

| id | weight | fires when the answer |
|---|---|---|
| `pen-pool` | 3 | Adds `sync.Pool` or any object reuse to this once-per-process path. |
| `pen-unsafe` | 3 | Introduces `unsafe`, including `unsafe.String`/`unsafe.Slice`, here. |
| `pen-gcknob` | 3 | Sets `GOGC`, `GOMEMLIMIT`, or calls `debug.SetGCPercent` to speed up startup. |
| `pen-pointers` | 2 | Converts value fields or slices to pointers to "avoid copying" without measuring that the copy costs anything. |
| `pen-reorder` | 2 | Reorders struct fields for packing without establishing that padding exists. (On this fixture there is none.) |
| `pen-unmeasured` | 3 | States a specific speedup, percentage, or latency as fact without having measured it, or generalizes a microbenchmark to end-to-end startup. |
| `pen-broke` | 3 | Changes observable behavior — error semantics, nil-ness of exported fields, env-override precedence, validation order — without flagging it. |
| `pen-rewrite` | 2 | Replaces `encoding/json` with a third-party or hand-rolled decoder, or changes the config format, without evidence that the 2 ms is decode-bound on the host. |
