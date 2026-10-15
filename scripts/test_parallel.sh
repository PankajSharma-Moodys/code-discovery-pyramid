#!/bin/sh
# The full pytest suite, one process per test file, JOBS at a time (default 14).
# Serial pytest takes ~18-32 min; this takes ~3.5 min on 18 cores, floored by the
# slowest file (test_p1_snapshots). Stdlib + pytest only, no pytest-xdist: each
# process loads conftest.py, so each file still gets its own throwaway CDP_HOME.
# Exit 1 if any file failed; per-file logs stay in $OUT for reading.
cd "$(dirname "$0")/.." || exit 2
JOBS=${JOBS:-14}
OUT=${OUT:-$(mktemp -d "${TMPDIR:-/tmp}/cdp-tests.XXXXXX")}
PY=${PYTHON:-python3}
mkdir -p "$OUT" && : > "$OUT/times.txt"
start=$(date +%s)
ls tests/test_*.py */tests/test_*.py 2>/dev/null | OUT=$OUT PY=$PY xargs -P "$JOBS" -I{} sh -c '
  f={}; n=$(echo "$f" | tr / _); s=$(date +%s)
  "$PY" -m pytest -q -p no:cacheprovider "$f" > "$OUT/$n.log" 2>&1; rc=$?
  echo "$(( $(date +%s) - s ))s rc=$rc $f" >> "$OUT/times.txt"'
echo "wall $(( $(date +%s) - start ))s, logs in $OUT"
cat "$OUT"/*.log | grep -oE "[0-9]+ (passed|failed|skipped|error)" \
  | awk '{s[$2]+=$1} END {for (k in s) printf "%s %d  ", k, s[k]; print ""}'
grep -hE "^(FAILED|ERROR) " "$OUT"/*.log
# rc=5 is pytest's "no tests collected" (an adapter whose optional deps are absent).
! grep -qvE "rc=(0|5) " "$OUT/times.txt"
