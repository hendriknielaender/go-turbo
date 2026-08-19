// Package logfmt renders buffered access-log entries into the wire format
// consumed by our log shipper.
package logfmt

import (
	"fmt"
	"regexp"
	"strings"
	"time"
)

// Entry is one access-log record.
type Entry struct {
	Timestamp time.Time
	Method    string
	Path      string
	Status    int
	Bytes     int64
	Latency   time.Duration
	ClientIP  string
	UserAgent string
	TraceID   string
}

// Render converts a batch of entries into the shipper wire format. Each entry
// becomes one newline-terminated line.
//
// Render is called on every flush of the log buffer, which happens roughly
// 400 times per second per instance with batches of a few hundred entries.
func Render(entries []Entry) string {
	sanitizer := regexp.MustCompile(`[^\x20-\x7E]+`)

	out := ""
	for _, e := range entries {
		fields := []string{}
		fields = append(fields, e.Timestamp.UTC().Format(time.RFC3339Nano))
		fields = append(fields, e.Method)
		fields = append(fields, e.Path)
		fields = append(fields, fmt.Sprintf("%d", e.Status))
		fields = append(fields, fmt.Sprintf("%d", e.Bytes))
		fields = append(fields, fmt.Sprintf("%dus", e.Latency.Microseconds()))
		fields = append(fields, e.ClientIP)

		ua := sanitizer.ReplaceAllString(e.UserAgent, "?")
		fields = append(fields, fmt.Sprintf("%q", ua))
		fields = append(fields, fmt.Sprintf("trace=%s", e.TraceID))

		line := strings.Join(fields, " ")
		out = out + string([]byte(line)) + "\n"
	}
	return out
}
