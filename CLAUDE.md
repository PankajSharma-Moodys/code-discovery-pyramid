# code-scanner — ground rules

See `RESEARCH.md` §11 for the rationale behind each rule, and `PLAN.md` for the defect
register and build order. `scripts/check_rules.sh` mechanically enforces rules 1, 2 and 6.

1. **Languages are data.** Adding a language means a `LanguageProfile` record
   (`code_scanner/languages/defs/`) and a golden fixture. Never `if language == "…"` in an
   analyzer — that means a missing profile field.
2. **Renderers read JSON only.** Nothing under `code_scanner/render/` imports `parse` or
   `analyze`. If the HTML needs a number, that number belongs in the JSON.
3. **Degrade, never lie.** Parse failures produce `parse_status: degraded|unparsed`, are
   excluded from the score, and are surfaced in `scan.files_degraded`/`files_unparsed`.
   Never a crash, never a silent zero.
4. **Thresholds are config.** Every threshold, weight and severity lives in
   `.codescanner.toml` (see `code_scanner/config.py: DEFAULTS`). No magic numbers in
   analyzer code.
5. **Every number states its scope.** Anything scored records what it was computed over
   (`scope.roles`, `scope.files`, `scope.population`). A metric that cannot name its
   denominator does not ship.
6. **No framework names in the analyzers.** Framework knowledge lives in `packs/*.toml`
   or nowhere. A pack may only suppress findings, never create them.

Run `bash scripts/check_rules.sh` and `pytest` before considering a milestone done.
