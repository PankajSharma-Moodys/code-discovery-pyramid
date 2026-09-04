#!/usr/bin/env bash
# Mechanically enforces ground rules 1, 2 and 6 (RESEARCH.md §11). See PLAN.md D2/§4a.
set -eu

for d in code_scanner/render code_scanner/languages/defs code_scanner; do
  [ -d "$d" ] || { echo "FAIL: $d missing — check is vacuous"; exit 1; }
done

# Rule 2: renderers read JSON only, never import parse/ or analyze/.
if /usr/bin/grep -rE "(from|import).*\b(parse|analyze)\b" code_scanner/render/; then
  echo "FAIL: rule 2 — render/ imports parse or analyze"
  exit 1
fi

# Rule 1: languages/defs/ is data only — no def/if/for/while.
if /usr/bin/grep -rE "^[[:space:]]*(def|if|for|while) " code_scanner/languages/defs/; then
  echo "FAIL: rule 1 — languages/defs/ contains logic"
  exit 1
fi

# Rule 6: no framework names outside packs/ (packs/ is the one tree §6 L4 authorises).
# "nest" is word-bounded: the bare substring also matches "nesting"/"max_nesting", a
# legitimate metric name, so an unbounded match would fail this check vacuously-wrong.
if /usr/bin/grep -rilE "spring|fastapi|django|rails|\bnestjs\b|\bnest\b" \
      code_scanner/ --exclude-dir=packs --exclude-dir=__pycache__; then
  echo "FAIL: rule 6 — framework name outside packs/"
  exit 1
fi

echo "check_rules: OK"
