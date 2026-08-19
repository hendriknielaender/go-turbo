package logfmt

import (
	"math/rand"
	"strings"
	"testing"
	"time"
)

func TestRenderEmpty(t *testing.T) {
	if got := Render(nil); got != "" {
		t.Fatalf("Render(nil) = %q, want empty", got)
	}
	if got := Render([]Entry{}); got != "" {
		t.Fatalf("Render(empty) = %q, want empty", got)
	}
}

func TestRenderSingle(t *testing.T) {
	e := Entry{
		Timestamp: time.Date(2024, 3, 7, 12, 0, 0, 123456789, time.UTC),
		Method:    "GET",
		Path:      "/v1/items?page=2",
		Status:    200,
		Bytes:     4096,
		Latency:   1500 * time.Microsecond,
		ClientIP:  "10.0.0.7",
		UserAgent: "curl/8.4.0",
		TraceID:   "abc123",
	}
	want := `2024-03-07T12:00:00.123456789Z GET /v1/items?page=2 200 4096 1500us 10.0.0.7 "curl/8.4.0" trace=abc123` + "\n"
	if got := Render([]Entry{e}); got != want {
		t.Fatalf("Render mismatch\n got: %q\nwant: %q", got, want)
	}
}

func TestRenderSanitizesUserAgent(t *testing.T) {
	e := Entry{
		Timestamp: time.Date(2024, 3, 7, 12, 0, 0, 0, time.UTC),
		Method:    "POST",
		Path:      "/v1/events",
		Status:    500,
		Bytes:     0,
		Latency:   0,
		ClientIP:  "::1",
		UserAgent: "bad\x00\x01agent\ttailé",
		TraceID:   "t-1",
	}
	want := `2024-03-07T12:00:00Z POST /v1/events 500 0 0us ::1 "bad?agent?tail?" trace=t-1` + "\n"
	if got := Render([]Entry{e}); got != want {
		t.Fatalf("Render mismatch\n got: %q\nwant: %q", got, want)
	}
}

func TestRenderQuotesAndEscapes(t *testing.T) {
	e := Entry{
		Timestamp: time.Date(2024, 1, 2, 3, 4, 5, 0, time.UTC),
		Method:    "GET",
		Path:      "/",
		Status:    301,
		Bytes:     -1,
		Latency:   -2 * time.Microsecond,
		ClientIP:  "1.2.3.4",
		UserAgent: `weird "quoted" \ slash`,
		TraceID:   "",
	}
	want := `2024-01-02T03:04:05Z GET / 301 -1 -2us 1.2.3.4 "weird \"quoted\" \\ slash" trace=` + "\n"
	if got := Render([]Entry{e}); got != want {
		t.Fatalf("Render mismatch\n got: %q\nwant: %q", got, want)
	}
}

func TestRenderNonUTCTimestampNormalized(t *testing.T) {
	zone := time.FixedZone("UTC+5", 5*60*60)
	e := Entry{
		Timestamp: time.Date(2024, 6, 1, 15, 0, 0, 0, zone),
		Method:    "HEAD",
		Path:      "/health",
		Status:    204,
		Latency:   999 * time.Nanosecond,
		ClientIP:  "127.0.0.1",
		UserAgent: "kube-probe/1.29",
		TraceID:   "z",
	}
	want := `2024-06-01T10:00:00Z HEAD /health 204 0 0us 127.0.0.1 "kube-probe/1.29" trace=z` + "\n"
	if got := Render([]Entry{e}); got != want {
		t.Fatalf("Render mismatch\n got: %q\nwant: %q", got, want)
	}
}

func TestRenderMultipleLines(t *testing.T) {
	batch := sampleBatch(37)
	got := Render(batch)
	if n := strings.Count(got, "\n"); n != 37 {
		t.Fatalf("line count = %d, want 37", n)
	}
	for i, e := range batch {
		one := Render([]Entry{e})
		if !strings.Contains(got, one) {
			t.Fatalf("batch output missing line %d: %q", i, one)
		}
	}
}

func sampleBatch(n int) []Entry {
	r := rand.New(rand.NewSource(1))
	methods := []string{"GET", "POST", "PUT", "DELETE"}
	paths := []string{"/v1/items", "/v1/items/42", "/v1/search?q=widget&page=3", "/health", "/v2/orders/9c1f/lines"}
	agents := []string{
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
		"curl/8.4.0",
		"kube-probe/1.29",
		"Go-http-client/2.0",
		"bad\x00client\x1b[0m",
	}
	base := time.Date(2024, 3, 7, 12, 0, 0, 0, time.UTC)

	out := make([]Entry, n)
	for i := range out {
		out[i] = Entry{
			Timestamp: base.Add(time.Duration(r.Int63n(1e12))),
			Method:    methods[r.Intn(len(methods))],
			Path:      paths[r.Intn(len(paths))],
			Status:    []int{200, 201, 204, 301, 404, 500}[r.Intn(6)],
			Bytes:     r.Int63n(1 << 20),
			Latency:   time.Duration(r.Int63n(int64(250 * time.Millisecond))),
			ClientIP:  "10.0.0.7",
			UserAgent: agents[r.Intn(len(agents))],
			TraceID:   "0123456789abcdef0123456789abcdef",
		}
	}
	return out
}

func BenchmarkRender(b *testing.B) {
	batch := sampleBatch(300)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		sink = Render(batch)
	}
}

var sink string
