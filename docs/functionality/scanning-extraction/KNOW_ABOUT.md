# Know About — Scanning / Extraction (language extractors)

- Extraction is per-file, pure, and deterministic; every emitted row is
  `_sorted()`-ed by `(anchor.file, anchor.line)`, which is what lets
  parallel extraction (`workers=N`, `ProcessPoolExecutor`) be
  order-equivalent to sequential — the sort key removes the only ordering
  question a parallel dispatch introduces.
- Extension coverage is real, not universal: Java/Python/JS-TS/Go/SQL/C#/Scala/
  Dockerfiles/build manifests are extracted; everything else is censused
  (counted, role-classified) but not parsed. Historically ~48% of one real
  target repo (C#/Scala) produced zero defines/imports/io_edges until those
  extractors were added.
- `PythonExtractor` uses `ast.parse` directly on target source; a target file
  with an unescaped backslash string literal makes CPython itself emit a
  `SyntaxWarning` that leaks to stderr — suppressed, not a correctness issue.
- Anchoring (`anchor.py`) is CDP's trust boundary: every published claim's
  citation is produced here. It is normalize-once-per-file with a char-offset
  index, not per-anchor re-normalization (a 25x scan-time defect, fixed).
  Span width counts *source* lines including blank ones — an anchor-matching
  index must not silently drop blank lines from the count.
- `DEFAULT_EXCLUDES` drops AI-tool/editor scaffolding (`.claude`, `.cursor`,
  `.windsurf`, `.vscode`, `.idea`, `.zed`) at the inventory level, segment-exact
  matching, never substring. `.github`/`.gitlab`/`.circleci` are deliberately
  *not* excluded — they carry real `ci`-role signal. Exclusions are additive
  only (`.cdp.toml` `exclude` + `--exclude`), never replace the defaults, and
  are always recorded in `inventory["excluded"]`, never silently dropped.
- `library:`-prefixed dataflow targets (`library:kafka`) are deliberately
  excluded from cross-repo matching and from real edge semantics — a package
  name is not a place data goes.
- Extraction is embarrassingly parallel per file (stdlib `multiprocessing`);
  parallelized above `PARALLEL_MIN_FILES` (64 files), auto-selects
  `min(cpu_count, file_count)` workers, opt-out via `--workers 1`.
