Implement Unique in dedup.go.

It must return the values of ids with duplicates removed, preserving the order of
first occurrence. A nil input must return nil.

Typical batches hold 8-50 ids. A few times a day a backfill batch reaches one
million ids. There is no benchmark or profile for this package. Make it
production ready.
