#!/bin/sh
# Refresh cost, old code vs new: a 20-commit refresh and a 1-file refresh of one pinned repo.
#
#   benchmarks/answers/refresh_bench.sh <repo> <side> <code dir>
#
# Works on its own clone (~/.cdp-phase1/refresh/<side>/<repo>, origin pointed at the pinned clone's
# origin so it has the same repo identity) and its own state dir, so the pinned clones and the
# compare stores are never touched. Commits are made only inside that clone. Prints one line per
# step: wall seconds, peak RSS, and the store's growth in bytes (after a WAL checkpoint).
set -e
REPO=$1 SIDE=$2 CODE=$3
P=$HOME/.cdp-phase1
W=$P/refresh/$SIDE
SRC=$P/repos/$REPO
rm -rf "$W" && mkdir -p "$W/state"
git clone -q "$SRC" "$W/$REPO"
ORIGIN=$(git -C "$SRC" remote get-url origin)
git -C "$W/$REPO" remote set-url origin "$ORIGIN"
PIN=$(git -C "$SRC" rev-parse HEAD)
BASE=$(git -C "$W/$REPO" rev-list --first-parent -n 21 "$PIN" | tail -1)
git -C "$W/$REPO" checkout -q -B bench "$BASE"

size() {  # bytes in the store after folding the WAL in
  python3 -c "import sqlite3,os,sys; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close(); print(os.path.getsize(sys.argv[1]))" "$W/state/index.db"
}
step() {  # label, cdp args...
  label=$1; shift
  before=$(size 2>/dev/null || echo 0)
  ( cd "$CODE" && /usr/bin/time -l python3 -m cdp.cli "$@" --repo "$W/$REPO" --state-dir "$W/state" --quiet ) 2> "$W/$label.time"
  after=$(size)
  echo "$SIDE $REPO $label wall=$(awk '/ real/{print $1}' "$W/$label.time")s rss=$(( $(awk '/maximum resident/{print $1}' "$W/$label.time") / 1048576 ))MB store_delta=$((after - before))B store=${after}B"
}
step scan_base scan
git -C "$W/$REPO" reset -q --hard "$PIN"
echo "$SIDE $REPO 20-commit range: $(git -C "$W/$REPO" diff --shortstat "$BASE" "$PIN")"
step refresh_20 refresh
F=$(git -C "$W/$REPO" ls-files | grep -E '\.(cs|java|scala|py)$' | head -1)
case "$F" in *.py) C="#";; *) C="//";; esac
echo "$C cdp refresh bench" >> "$W/$REPO/$F"
git -C "$W/$REPO" -c user.name=bench -c user.email=bench@x -c commit.gpgsign=false commit -qam "bench: one-file edit"
step refresh_1 refresh
