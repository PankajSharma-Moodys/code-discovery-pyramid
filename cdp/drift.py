"""What changed between two commits, as `fold` needs it (rename map, real edits).

`state.fold` derives this itself, per claim, from the claim's own `claim_reviewed_at` commit and the
repo's HEAD, so the materialized state is a function of the log, the xref and the repo -- never of
what one `refresh` happened to pass in. `refresh` uses the same classification to choose what to
re-extract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional, Set, Tuple

from .util import normalise_ws, read_lines, run_git


class HistoryUnavailable(Exception):
    """`<prev>` fell out of reachable history (rebase, force-push) or out of a
    shallow clone's window. Callers must fall back to a full re-extract with
    every claim's staleness reported as unknown, never as "not stale"."""


def diff_status(repo: Path, prev_sha: str, new_sha: str) -> List[Tuple[str, str, Optional[str]]]:
    """`(status, path, old_path)` triples from `git diff --name-status -M`.

    `status` is `A`, `M`, `D`, or git's own rename-similarity tag (`R100` for a
    byte-identical move, `R87` for renamed-and-edited). Raises
    `HistoryUnavailable` when the range cannot be walked at all.
    """
    # `--relative -- .`: paths relative to the scanned folder and limited to it, whether that
    # is the git root or a subfolder of it.
    out = run_git(repo, "diff", "--name-status", "-M", "--relative", prev_sha, new_sha, "--", ".")
    if out is None:
        raise HistoryUnavailable("git diff --name-status -M %s %s failed" % (prev_sha, new_sha))
    rows: List[Tuple[str, str, Optional[str]]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) == 3:
            rows.append((status, parts[2], parts[1]))
        else:
            rows.append((status, parts[1], None))
    return rows


def _normalised_body(lines: List[str]) -> List[str]:
    return [normalise_ws(l) for l in lines if normalise_ws(l)]


def classify_full(
    repo: Path, prev_sha: str, new_sha: str
) -> Tuple[Dict[str, str], Set[str], Set[str], Set[str], Set[str]]:
    """`(rename_map, edited_files, added_files, deleted_files, reformatted_files)`.

    `rename_map` (old path -> new path) covers every rename, pure or edited,
    since both need an anchor's recorded `file` rewritten before verification.
    `edited_files` (new paths) is R9's set: real content edits. A pure rename
    (`R100`) is excluded outright; a same-path or renamed-and-edited change is
    excluded too when the pre- and post-image are identical once every line is
    `normalise_ws`'d and blank lines dropped -- a reformat, not an edit. Those go to
    `reformatted_files`: they do not invalidate a review, but every line number in them
    may have moved, so they are re-extracted all the same.
    """
    rename_map: Dict[str, str] = {}
    edited: Set[str] = set()
    added: Set[str] = set()
    deleted: Set[str] = set()
    reformatted: Set[str] = set()

    for status, path, old_path in diff_status(repo, prev_sha, new_sha):
        if status == "D":
            deleted.add(path)
            continue
        if status == "A":
            added.add(path)
            continue
        if old_path is not None:
            rename_map[old_path] = path
            if status == "R100":
                continue
        pre_text = run_git(repo, "show", "%s:./%s" % (prev_sha, old_path or path))
        pre_lines = pre_text.splitlines() if pre_text is not None else None
        post_lines = read_lines(repo / path)
        if pre_lines is not None and _normalised_body(pre_lines) == _normalised_body(post_lines):
            if pre_lines != post_lines:
                reformatted.add(path)
            continue
        edited.add(path)

    return rename_map, edited, added, deleted, reformatted


def classify_changes(
    repo: Path, prev_sha: str, new_sha: str
) -> Tuple[Dict[str, str], Set[str], Set[str], Set[str]]:
    """`classify_full` without the reformatted set: `(rename_map, edited, added, deleted)`."""
    return classify_full(repo, prev_sha, new_sha)[:4]


Drift = Tuple[Dict[str, str], FrozenSet[str]]


def drift_provider(repo: Path, head_sha: Optional[str]) -> Callable[[Optional[str]], Drift]:
    """`base sha -> (rename_map, edited_files)` for `base..HEAD`, memoised. A claim with no base,
    a base equal to HEAD, or a base git cannot walk (rebase, shallow clone) has no drift: its
    anchors are checked where they were recorded."""
    cache: Dict[str, Drift] = {}

    def drift(base: Optional[str]) -> Drift:
        if not base or not head_sha or base == head_sha:
            return {}, frozenset()
        if base not in cache:
            try:
                rename_map, edited, _a, _d, _r = classify_full(Path(repo), base, head_sha)
                cache[base] = (rename_map, frozenset(edited))
            except HistoryUnavailable:
                cache[base] = ({}, frozenset())
        return cache[base]

    return drift
