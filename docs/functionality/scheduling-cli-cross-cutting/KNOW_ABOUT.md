# Know About — Scheduling / CLI Cross-Cutting Concerns

- `--repo` silently defaulting to the process's cwd is a recurring, dangerous
  failure class (F16): if cwd isn't the repo being operated on, anchor
  verification runs against unrelated file content, producing an
  all-anchors-failed signature that looks exactly like a bad model run, not
  an operator mistake. `_check_repo_matches_manifest` guards the five/six
  commands that read `--repo`'s file content; `cmd_scan` is exempt (it's the
  writer of the record).
- Backend construction can have filesystem side effects merely from being
  opened (`SqliteStore` creates its db file and parent dir on construction) —
  any "has this been scanned yet" check must be a pure filesystem probe
  (`store.has_scanned`), never construct a backend speculatively, or a
  file-watching hook litters `.cdp/index.db` at every unrelated directory it
  probes.
