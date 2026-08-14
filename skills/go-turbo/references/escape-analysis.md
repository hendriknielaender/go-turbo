# Escape Analysis

Escape analysis is the compiler pass that decides whether a value lives on
the stack or the heap. A stack value is freed for nothing when the function
returns; a heap value costs an allocation and then GC work forever after.

The compiler is conservative by necessity: if it cannot prove a value stops
being referenced when the function returns, the value escapes. Most escapes
are correct and necessary. The ones worth fixing are the ones caused by
incidental code shape rather than actual lifetime requirements.

## Contents

- [Reading the diagnostics](#reading-the-diagnostics)
- [What forces a heap allocation](#what-forces-a-heap-allocation)
- [Restructuring to avoid escape](#restructuring-to-avoid-escape)
- [When escaping is the right answer](#when-escaping-is-the-right-answer)
- [Inlining and its interaction with escape](#inlining-and-its-interaction-with-escape)

## Reading the diagnostics

```sh
go build -gcflags=-m ./...          # escape + inlining decisions
go build -gcflags='-m -m' ./...     # with the reasoning chain
go build -gcflags='-m' ./pkg 2>&1 | grep -E 'escapes to heap|moved to heap'
```

The lines that cost you allocations:

```
./main.go:12:2:  moved to heap: buf
./main.go:20:13: ... argument does not escape
./main.go:24:16: &User{...} escapes to heap
./main.go:31:6:  can inline process
./main.go:33:9:  inlining call to process
```

- `moved to heap: x` — a declared variable that must outlive its frame.
- `escapes to heap` — an expression whose result is heap-allocated.
- `does not escape` — good news; the value stayed on the stack.
- `can inline` / `inlining call to` — inlining decisions, which feed back
  into escape analysis (see below).

Two practical notes. First, `-gcflags=-m` on its own applies to the packages
you name; use `-gcflags=all=-m` to see dependencies too, though the output
gets large. Second, escape analysis output is *not* a benchmark. It tells you
where allocations come from. Whether they matter is a separate question that
a profile answers.

## What forces a heap allocation

**Returning a pointer to a local.**

```go
func New() *Config {
    c := Config{}
    return &c        // moved to heap: c
}
```

Correct and idiomatic — a constructor has to do this. Listed because it will
dominate your `-m` output and you should recognize it as noise.

**Storing into something that outlives the frame** — a global, a struct field
reachable from outside, a slice element that escapes, a channel send:

```go
var cache *Entry

func set() {
    e := Entry{}
    cache = &e       // moved to heap: e
}
```

**Closures that capture by reference.** A captured variable escapes if the
closure outlives the frame:

```go
func counter() func() int {
    n := 0
    return func() int { n++; return n }  // moved to heap: n
}
```

A closure that does *not* outlive the frame — passed to `sync.Once.Do`, to a
`range` callback, to `sort.Slice` — generally does not force an escape.

**Interface conversion where the compiler can't see through the call.** The
classic offender is variadic `any`:

```go
fmt.Fprintf(w, "id=%d", id)   // id escapes: boxed into any
```

`fmt` verbs take `...any`, so every argument is boxed. That's fine in
error paths and startup; it's an allocation per call in a hot loop. In a hot
path, use `strconv.AppendInt` into a reused buffer, or `w.WriteString`.

**Values whose size isn't known at compile time.** `make([]byte, n)` with a
runtime `n` historically escaped; Go 1.26 stack-allocates the backing store
in more cases, but a large or unbounded `n` still goes to the heap. There is
a stack-frame size limit — very large fixed-size arrays escape too.

**Anything reachable from an escaped value.** Escape is transitive: if a
struct escapes, so does everything its pointer fields point at.

**Taking the address of a loop variable and storing it.** Since Go 1.22 each
iteration has its own variable, so this is now correct — but it is n
allocations, one per iteration.

## Restructuring to avoid escape

**Pass a destination instead of returning a new one.** This is the highest-
value refactor in the list and it reads fine:

```go
// Allocates per call.
func Format(v Value) []byte

// Caller controls the memory; often no allocation at all.
func AppendFormat(dst []byte, v Value) []byte
```

The standard library uses this shape everywhere — `strconv.AppendInt`,
`time.Time.AppendFormat`, `append`-style APIs generally. Callers reuse one
buffer across a whole loop.

**Return values, not pointers, for small structs.** A 16- or 32-byte struct
returned by value copies a few words and stays on the stack. Returned by
pointer, it allocates and adds an indirection on every field access. Pointers
earn their keep for large structs, for mutation, and when nil is meaningful —
not by default.

**Give the compiler a fixed size when you can.**

```go
var scratch [64]byte
b := scratch[:0]           // stack-backed, no allocation
b = strconv.AppendInt(b, n, 10)
```

A useful pattern for small, bounded work: a fixed array in the frame, sliced
to zero length, appended into. It stays on the stack as long as `b` doesn't
escape.

**Keep the concrete type at hot boundaries.** Accepting `io.Writer` is right
almost everywhere; accepting `*bufio.Writer` in one internal hot function
lets the compiler inline the call and skip the boxing.

**Hoist the allocation out of the loop.**

```go
for _, item := range items {
    buf := make([]byte, 0, 64)     // n allocations
    process(append(buf, item...))
}

buf := make([]byte, 0, 64)         // one
for _, item := range items {
    buf = buf[:0]
    process(append(buf, item...))
}
```

## When escaping is the right answer

Do not contort code to defeat escape analysis. Escape is correct and should
be left alone when:

- **It's a constructor.** `func New() *T` returning a heap pointer is
  idiomatic Go. Do not force callers to pass in a `*T` to save one allocation
  on a call that happens once.
- **The object genuinely outlives the call** — stored in a struct, sent on a
  channel, captured by a goroutine, put in a cache. That's not a leak, that's
  the design.
- **It's not hot.** One allocation on a path taken once per request, in a
  service doing thousands of other things per request, is invisible. A
  profile will tell you; `-gcflags=-m` will not.
- **Avoiding it would hurt readability more than the allocation costs.**
  Threading a scratch buffer through five call frames to save one 24-byte
  allocation off a cold path is a net loss.

The rule of thumb: fix escapes that are *incidental* (caused by code shape,
fixable without changing the API's meaning), leave escapes that are
*intentional* (the value really does need to outlive the frame).

## Inlining and its interaction with escape

Inlining and escape analysis are coupled: when a call is inlined, the
compiler can see the callee's use of an argument, and often proves it doesn't
escape. When the call isn't inlined, arguments passed by pointer are assumed
to escape.

```sh
go build -gcflags='-m' ./... 2>&1 | grep -E 'can inline|cannot inline'
```

Common inlining blockers (the budget is roughly 80 "nodes" of AST):

- the function is too big
- it contains a `defer`, a `select`, a `range` over a channel, or a `go`
  statement
- it makes a call through an interface or a function value
- it recurses

The practical move is to split a hot function into a small inlinable
fast path and a `//go:noinline`-eligible slow path — the shape the standard
library uses in `sync.Mutex.Lock` and `strings.Index`:

```go
func (c *Cache) Get(k string) (V, bool) {
    if v, ok := c.fast[k]; ok {   // small enough to inline
        return v, true
    }
    return c.slowGet(k)           // the bulk lives here
}
```

Don't chase inlining generally. Chase it when a profile shows call overhead
in a function called millions of times, and confirm with a benchmark — the
`-m` output tells you what the compiler did, not whether it helped.
