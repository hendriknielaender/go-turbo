---
description: Performance review of a Go diff — one line per finding
argument-hint: "[diff, PR, or files]"
---

Run the `go-turbo-review` skill on: $ARGUMENTS

Review for performance only. One line per finding: `L<line>: <tag> <what>. <fix>.` Flag added allocations and unbounded concurrency, and equally flag premature optimizations that cost readability or safety for an unmeasured win. Judge whether each path is actually hot; say so when you can't tell. End with the net estimate.
