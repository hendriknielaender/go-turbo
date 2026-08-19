package config

import (
	"encoding/json"
	"os"
	"testing"
)

// BenchmarkLoad measures the full Load path end to end, as it runs once at
// process startup.
func BenchmarkLoad(b *testing.B) {
	for i := 0; i < b.N; i++ {
		clearTestEnv()
		if _, err := Load("testdata/config.json"); err != nil {
			b.Fatal(err)
		}
	}
}

// BenchmarkReadFile isolates the disk-read portion of Load.
func BenchmarkReadFile(b *testing.B) {
	for i := 0; i < b.N; i++ {
		if _, err := os.ReadFile("testdata/config.json"); err != nil {
			b.Fatal(err)
		}
	}
}

// BenchmarkUnmarshal isolates the JSON decode portion of Load using
// pre-read bytes, so file I/O is not counted.
func BenchmarkUnmarshal(b *testing.B) {
	data, err := os.ReadFile("testdata/config.json")
	if err != nil {
		b.Fatal(err)
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var raw rawConfig
		if err := json.Unmarshal(data, &raw); err != nil {
			b.Fatal(err)
		}
	}
}

func clearTestEnv() {
	os.Unsetenv("APP_ENV")
	os.Unsetenv("LOG_LEVEL")
	os.Unsetenv("TRACING_ENABLED")
	os.Unsetenv("REGION_OVERRIDE")
}
