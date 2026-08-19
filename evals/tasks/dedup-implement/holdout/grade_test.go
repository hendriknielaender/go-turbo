package dedup

import (
	"math/rand"
	"testing"
)

func TestGradeNilStaysNil(t *testing.T) {
	if got := Unique(nil); got != nil {
		t.Fatalf("Unique(nil) = %#v, want nil", got)
	}
}

func TestGradeStableFirstOccurrence(t *testing.T) {
	in := []uint64{5, 1, 5, 9, 1, 3, 9, 9, 0, 0, 7}
	want := []uint64{5, 1, 9, 3, 0, 7}
	got := Unique(in)
	if len(got) != len(want) {
		t.Fatalf("len = %d (%v), want %d (%v)", len(got), got, len(want), want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("Unique = %v, want %v", got, want)
		}
	}
}

func TestGradeDoesNotMutateInput(t *testing.T) {
	in := []uint64{3, 1, 3, 2, 1}
	cp := append([]uint64(nil), in...)
	_ = Unique(in)
	for i := range cp {
		if in[i] != cp[i] {
			t.Fatalf("input mutated: %v, was %v", in, cp)
		}
	}
}

func TestGradeAllDuplicates(t *testing.T) {
	in := []uint64{8, 8, 8, 8, 8}
	got := Unique(in)
	if len(got) != 1 || got[0] != 8 {
		t.Fatalf("Unique = %v, want [8]", got)
	}
}

func TestGradeMaxUint64(t *testing.T) {
	in := []uint64{^uint64(0), 0, ^uint64(0), 1}
	got := Unique(in)
	want := []uint64{^uint64(0), 0, 1}
	if len(got) != 3 {
		t.Fatalf("Unique = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("Unique = %v, want %v", got, want)
		}
	}
}

// TestGradeLargeInputScales fails by timeout if the implementation is
// quadratic. One million ids with ~50% duplicates.
func TestGradeLargeInputScales(t *testing.T) {
	r := rand.New(rand.NewSource(7))
	const n = 1 << 20
	in := make([]uint64, n)
	for i := range in {
		in[i] = uint64(r.Int63n(n / 2))
	}
	got := Unique(in)
	seen := make(map[uint64]bool, len(got))
	for _, v := range got {
		if seen[v] {
			t.Fatalf("duplicate %d in output", v)
		}
		seen[v] = true
	}
	if len(got) == 0 || len(got) > n {
		t.Fatalf("suspicious output length %d", len(got))
	}
}

func BenchmarkGradeSmall(b *testing.B) {
	in := []uint64{5, 1, 5, 9, 1, 3, 9, 9, 0, 0, 7, 4, 2, 4, 6, 6, 11, 12, 11, 3}
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		gsink = Unique(in)
	}
}

func BenchmarkGradeLarge(b *testing.B) {
	r := rand.New(rand.NewSource(7))
	const n = 1 << 20
	in := make([]uint64, n)
	for i := range in {
		in[i] = uint64(r.Int63n(n / 2))
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		gsink = Unique(in)
	}
}

var gsink []uint64
