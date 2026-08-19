# Backing-Store Retention

A small sub-slice can hold a large array alive. This is the leak shape that
looks like normal code.

A short slice or substring keeps its complete backing allocation reachable.
When a small result will outlive a large input, detach it:

```go
func retainFrame(readBuffer []byte, n int) []byte {
	return bytes.Clone(readBuffer[:n])
}

func retainName(record string, start, end int) string {
	return strings.Clone(record[start:end])
}
```

Limiting a slice's capacity does not release its backing array. Cloning does.
The same retention occurs in queues that repeatedly reslice from the front;
clear removed pointer elements and compact or replace the backing store when
retained capacity becomes material.

**Use when:** heap profiles show a large owner retained by small live views, or
the view crosses an ownership boundary. **Backfires when:** the view is
short-lived, most of the input remains useful, or the copy adds more churn
than the retained bytes cost. Decide from retained-heap profiles, not length
alone.
