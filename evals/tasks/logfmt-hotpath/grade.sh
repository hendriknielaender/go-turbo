#!/usr/bin/env bash
# Score logfmt-hotpath.
#
# The baseline is re-measured here, back-to-back with the candidate on the same
# machine in the same grading pass, rather than compared against a number
# recorded earlier. Benchmark figures taken under different machine load are
# not comparable, and a stored baseline silently rewards or punishes runs for
# how busy the host happened to be. This task is marked "exclusive" in
# task.json so the harness grades it serially.
#
# Correctness is a gate: the held-out contract test has already been copied
# over the agent's tree, so an agent that relaxed the wire format to go faster
# scores zero regardless of its timings.
set -uo pipefail
. "$TASK_DIR/../_lib.sh"

median() { sort -n | awk '{a[NR]=$1} END{if(NR==0){print 0} else if(NR%2){print a[(NR+1)/2]} else {print (a[NR/2]+a[NR/2+1])/2}}'; }

command -v go >/dev/null 2>&1 || fail "go toolchain not found"
: "${TASK_DIR:?TASK_DIR not set by harness}"

if ! go vet ./... >vet.log 2>&1; then
  fail "go vet failed: $(clip vet.log)"
fi

# Correctness gate against the held-out contract test.
if ! go test -count=1 -timeout 300s ./... >test.log 2>&1; then
  fail "held-out contract test failed: $(clip test.log 800)"
fi

# A rewrite that introduced shared mutable state should not pass silently.
RACE_OK=true
go test -count=1 -race -timeout 300s ./... >race.log 2>&1 || RACE_OK=false

# One benchmark invocation per tree; ns/op and allocs/op are both read from the
# same output. Benchmarking twice would double the wall cost of every grade for
# no extra information, and would not even sample the same runs.
bench_run() { ( cd "$1" && go test -count=5 -run='^$' -bench=BenchmarkRender -benchmem ./... 2>/dev/null ) >"$2"; }

BASE_DIR=$(mktemp -d)
trap 'rm -rf "$BASE_DIR"' EXIT
cp "$TASK_DIR"/baseline/*.go "$TASK_DIR"/baseline/go.mod "$BASE_DIR"/ 2>/dev/null || fail "baseline sources missing"

bench_run . cand.bench
bench_run "$BASE_DIR" base.bench

CAND_NS=$(awk '/^BenchmarkRender/{print $3}' cand.bench | median)
BASE_NS=$(awk '/^BenchmarkRender/{print $3}' base.bench | median)
CAND_ALLOC=$(awk '/^BenchmarkRender/{print $7}' cand.bench | median)
BASE_ALLOC=$(awk '/^BenchmarkRender/{print $7}' base.bench | median)

if [ -z "$CAND_NS" ] || [ "$CAND_NS" = "0" ] || [ -z "$BASE_NS" ] || [ "$BASE_NS" = "0" ]; then
  fail "benchmark produced no usable ns/op (candidate=$CAND_NS baseline=$BASE_NS)"
fi

TARGET=$(python3 -c 'import json,os;print(json.load(open(os.environ["TASK_DIR"]+"/task.json"))["grader"]["target_speedup"])')

read -r SPEEDUP SCORE <<<"$(awk -v b="$BASE_NS" -v c="$CAND_NS" -v t="$TARGET" 'BEGIN{
  s = b / c;
  if (s <= 1) { sc = 0 } else { sc = log(s) / log(t); if (sc > 1) sc = 1; if (sc < 0) sc = 0 }
  printf "%.3f %.4f", s, sc;
}')"

emit "$SCORE" true \
  "{\"speedup\":$SPEEDUP,\"baseline_ns_op\":$BASE_NS,\"candidate_ns_op\":$CAND_NS,\"baseline_allocs_op\":${BASE_ALLOC:-null},\"candidate_allocs_op\":${CAND_ALLOC:-null},\"race_clean\":$RACE_OK}" \
  "speedup ${SPEEDUP}x vs target ${TARGET}x"
