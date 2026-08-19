#!/usr/bin/env bash
# Shared helpers for script graders.
#
# Verdicts are encoded with json.dumps rather than printf. Grader detail text
# is compiler and test output, which routinely contains quotes, backslashes,
# newlines, and percent signs; hand-rolled JSON escaping gets this wrong and
# turns a legitimate task failure into an unparsable verdict, which the harness
# cannot tell apart from a broken grader.

# emit <score> <passed:true|false> <metrics-json> <detail>
emit() {
  SCORE="$1" PASSED="$2" METRICS="$3" DETAIL="$4" python3 -c '
import json, os
try:
    metrics = json.loads(os.environ["METRICS"] or "{}")
except json.JSONDecodeError:
    metrics = {"metrics_encoding_error": os.environ["METRICS"][:200]}
print(json.dumps({
    "score": float(os.environ["SCORE"]),
    "passed": os.environ["PASSED"] == "true",
    "metrics": metrics,
    "detail": os.environ["DETAIL"][:2000],
}))'
}

# fail <detail>  -> zero score, exit cleanly so the harness records the reason
fail() {
  emit 0.0 false '{}' "$1"
  exit 0
}

# clip <file> — first N chars of a log, for use as detail text
clip() {
  head -c "${2:-600}" "$1" 2>/dev/null || true
}
