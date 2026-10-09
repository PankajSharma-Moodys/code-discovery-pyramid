# Plan: "Open folder…" in the Atlas repo picker

Budget: ≤100 lines. Spec: the in-chat design approved 2026-10-08 (option C:
scan on pick, deep `cdp run` only on explicit click). No separate spec file.

## Global Constraints

- The scan endpoint ALWAYS writes to `<folder>/.cdp`. It must never write to
  the server's `CDP_STORE` store or a registry-resolved store (the live server
  runs with `CDP_STORE=/Users/sethis7/cdp-demo/.cdp`; overwriting it is data loss).
- Mutating routes use the existing `require_mutation_auth` dependency
  (`web/api/auth.py`, header `X-CDP-Web-Token`), same as `POST /api/run`.
- Never hand-edit `web/client/schema.ts`; regenerate with
  `cd web/client && npm run generate`.
- No new runtime or dev dependencies.
- Backend tests: `.venv/bin/python -m unittest discover -s web/tests -t .`
  (pytest is not installed). Registry isolation: patch
  `cdp.store.registry.REGISTRY_PATH` as `web/tests/test_repos_endpoint.py` does.
- Match surrounding style: docstrings that explain *why*; frontend uses the
  `atlas-card` class and `var(--atlas-*)` CSS variables.
- Out of scope: graph/canvas changes, deleting/unregistering repos, cancelling scans.

## Task 1: `GET /api/fs/list` — read-only folder browser endpoint

In `web/api/app.py` + models in `web/api/models.py`. No auth (read-only, like other GETs).
- Query `path: Optional[str]`; default `Path.home()`. `expanduser().resolve()`.
- 404 if not an existing directory; 403 if listing it raises `PermissionError`.
- Response `FsListResponse`: `path: str`, `parent: Optional[str]` (None at `/`),
  `is_git: bool`, `has_scan: bool` (for `path` itself), and
  `entries: List[FsEntry]` with `name, path, is_git, has_scan`.
- `is_git` = `<dir>/.git` exists; `has_scan` = `<dir>/.cdp/index.db` is a file.
- Entries: subdirectories only, skip names starting with `.`, skip entries whose
  stat raises `OSError`, sort case-insensitively by name. Never return file contents.
- Tests `web/tests/test_fs_list.py` on a temp tree: listing/sorting/hidden-skip,
  git + scan flags, default path is home, missing path → 404, file path → 404.

## Task 2: `POST /api/scan` + job log tail + regenerate client

- `POST /api/scan?repo=<folder>` with `dependencies=[Depends(require_mutation_auth)]`.
  Resolve `repo`; 404 if not a directory. `state_dir = repo / ".cdp"` — do NOT
  call `resolve_state_dir`. Register `registry_mod.repo_identity(repo) -> state_dir`
  via `cdp.store.registry.register` (explicit `--state-dir` makes `cmd_scan`
  skip registration, so the endpoint does it). Spawn with
  `jobs_mod.spawn_or_join("scan", str(repo), str(state_dir), [])`; return `JobResponse`.
- Add `log_tail: Optional[str]` to `JobStatusResponse`: last 20 lines of the
  job's log file once the job is no longer running (None while running).
- Tests `web/tests/test_scan_endpoint.py`: copy `tests/fixtures/minirepo` into a
  temp dir and `git init` + commit it there (never scan the fixture in place);
  run with env `CDP_STORE` = a separate empty temp dir; poll `GET /api/job/{id}`
  until done. Assert: returncode 0; `<copy>/.cdp/index.db` exists; the `CDP_STORE`
  dir is still empty; `/api/repos` lists a row with that state dir and no error;
  missing token → 403 (mirror how existing tests exercise `/api/run` auth);
  non-directory → 404; finished job has non-empty `log_tail`.
- Regenerate the TS client (`npm run generate`) and commit `web/openapi.json` + `schema.ts`.

## Task 3: Frontend — folder browser in RepoPicker

- Hooks (new `web/frontend/src/api/folderHooks.ts`, patterned on
  `controlRoomHooks.ts`): `useFsList(path)`, `useScanMutation()` (uses
  `useControlRoomStore` `authToken` + `mutationClient` + `raiseAuthOr`),
  `useJob(jobId)` polling every 1500 ms while `running`.
- New `web/frontend/src/panels/FolderBrowser.tsx`, shown inside the RepoPicker
  dropdown via an "Open folder…" footer button. Shows: breadcrumb/parent link,
  a typed-path input with Go, the folder list with `git` / `scanned` badges.
- Header action for the current folder: `has_scan` → **Open**; else **Scan this folder**.
  Without a token, render the existing `TokenGate` instead of the scan button.
- While scanning: "scanning… Ns". On returncode 0: invalidate the `repos` query,
  `setRepo({ repo: path, stateDir: path + "/.cdp", repoId })` (repoId = matching
  `/api/repos` row's id if present, else the path), then show
  **Run deep analysis →** which calls `useViewStore`'s `setView("control-room")`.
  Nonzero exit: show "scan failed (exit N)" plus `log_tail` in a `<pre>`.
- **Open** calls the same `setRepo`. RepoPicker label fix: if no `/api/repos` row
  matches the store's `repoId`, show that `repoId` instead of falling back to `repos[0]`.
- Verify: the frontend's typecheck/build and existing unit tests pass
  (use scripts in `web/frontend/package.json`).
