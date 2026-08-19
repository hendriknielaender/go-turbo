#!/usr/bin/env bash
# Score dedup-implement.
#
# Held-out tests have already been copied over the agent's tree by the harness,
# so an agent that deleted or weakened its own tests is still graded against
# the originals. The 1M-element scaling test is the performance gate: a
# quadratic implementation does not finish inside the timeout.
set -uo pipefail
. "$TASK_DIR/../_lib.sh"

command -v go >/dev/null 2>&1 || fail "go toolchain not found"

UNFORMATTED=$(gofmt -l . 2>/dev/null | tr '\n' ' ')

if ! go vet ./... >vet.log 2>&1; then
  fail "go vet failed: $(clip vet.log)"
fi

# Score only the held-out tests. The agent's own tests stay in the tree so the
# package still builds the way it wrote it, but they must not count toward the
# score: an agent that adds twenty trivially-passing tests would otherwise
# dilute a real held-out failure. Names are read from the holdout sources
# rather than hardcoded, so adding a held-out case needs no change here.
HOLDOUT_TESTS=$(grep -ho '^func Test[A-Za-z0-9_]*' "$TASK_DIR"/holdout/*.go 2>/dev/null \
  | awk '{print $2}' | paste -sd'|' -)
[ -n "$HOLDOUT_TESTS" ] || fail "no held-out test functions found in \$TASK_DIR/holdout"
EXPECTED=$(printf '%s' "$HOLDOUT_TESTS" | awk -F'|' '{print NF}')

# -count=1 defeats the test cache; the scaling test must actually execute.
go test -count=1 -timeout 300s -v -run "^(${HOLDOUT_TESTS})\$" ./... >test.log 2>&1
PASSED=$(grep -c '^--- PASS' test.log || true)
FAILED=$(grep -c '^--- FAIL' test.log || true)
TOTAL=$((PASSED + FAILED))

if [ "$TOTAL" -ne "$EXPECTED" ]; then
  fail "expected $EXPECTED held-out tests, $TOTAL ran (build failure or panic): $(clip test.log)"
fi

SCORE=$(awk -v p="$PASSED" -v t="$TOTAL" 'BEGIN{printf "%.4f", p/t}')
PASSFLAG=$([ "$FAILED" -eq 0 ] && echo true || echo false)

SMALL_NS=null; LARGE_NS=null
if [ "$FAILED" -eq 0 ]; then
  go test -count=3 -run='^$' -bench='BenchmarkGrade' -benchmem ./... >bench.log 2>&1 || true
  SMALL_NS=$(awk '/BenchmarkGradeSmall/{s+=$3;n++} END{if(n)printf "%.1f",s/n; else print "null"}' bench.log)
  LARGE_NS=$(awk '/BenchmarkGradeLarge/{s+=$3;n++} END{if(n)printf "%.1f",s/n; else print "null"}' bench.log)
fi

FAILNAMES=$(grep '^--- FAIL' test.log | awk '{print $3}' | tr '\n' ' ')

emit "$SCORE" "$PASSFLAG" \
  "{\"tests_passed\":$PASSED,\"tests_total\":$TOTAL,\"small_ns_op\":$SMALL_NS,\"large_ns_op\":$LARGE_NS,\"unformatted\":\"$UNFORMATTED\"}" \
  "failed: ${FAILNAMES:-none}"
