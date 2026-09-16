"""Phase 3 -- incremental extract (0.11, M3.2) and `cdp refresh` (3.1, M3.3).

Graph, xref and dataflow are always recomputed in full: partition assignment
and manifest-declared edges are global properties of the whole file set, so a
cached graph after one file moves is a wrong graph, not an optimisation
deferred (`PHASE/phase_3_plan.md` M3.2). Only per-file extraction
(`defines`/`uses`/`io_edges`) is incremental, because `extract_file` is already
pure per file (`extract.py`).

Rename-awareness (`git diff -M`) is threaded through `state.fold` /
`verify.verify_all` rather than applied by mutating a patch already in the log
(R5, immutable patches): `classify_changes` below is the one place that reads
git history, and its output is a same-turn argument to `fold`, never persisted
back into `patches/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .extract import MAX_PARSE_BYTES, _sorted
from .lang import extract_file
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
    out = run_git(repo, "diff", "--name-status", "-M", prev_sha, new_sha)
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


def classify_changes(
    repo: Path, prev_sha: str, new_sha: str
) -> Tuple[Dict[str, str], Set[str], Set[str], Set[str]]:
    """`(rename_map, edited_files, added_files, deleted_files)`.

    `rename_map` (old path -> new path) covers every rename, pure or edited,
    since both need an anchor's recorded `file` rewritten before verification.
    `edited_files` (new paths) is R9's set: real content edits. A pure rename
    (`R100`) is excluded outright; a same-path or renamed-and-edited change is
    excluded too when the pre- and post-image are identical once every line is
    `normalise_ws`'d and blank lines dropped -- a reformat, not an edit.
    """
    rename_map: Dict[str, str] = {}
    edited: Set[str] = set()
    added: Set[str] = set()
    deleted: Set[str] = set()

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
        pre_text = run_git(repo, "show", "%s:%s" % (prev_sha, old_path or path))
        pre_lines = pre_text.splitlines() if pre_text is not None else None
        post_lines = read_lines(repo / path)
        if pre_lines is not None and _normalised_body(pre_lines) == _normalised_body(post_lines):
            continue
        edited.add(path)

    return rename_map, edited, added, deleted


def incremental_extract(
    repo: Path, inventory: Dict, prior_extraction: Dict, changed_files: Set[str]
) -> Dict:
    """Re-extract every file in a module that touched a changed file; carry
    every other module's rows forward untouched.

    Module granularity, not file granularity: `declared_deps`/`module_notes`
    are aggregated per module with no per-file attribution kept in the stored
    artifact, so carrying a module forward while re-deriving only one of its
    files would silently drop the rest. Re-deriving the whole module whenever
    any of its files changed is what makes this byte-identical to a full
    `run_extract` -- the equivalence the milestone's acceptance test checks.
    """
    repo = Path(repo)
    entries = inventory["files"]
    entry_by_path = {e["path"]: e for e in entries}
    changed_modules = {entry_by_path[p]["module"] for p in changed_files if p in entry_by_path}
    stale = {e["path"] for e in entries if e["module"] in changed_modules}
    carried_paths = {e["path"] for e in entries if e["path"] not in stale}

    prior_files = prior_extraction.get("files", {})
    defines = [r for r in prior_extraction.get("defines", []) if r.get("file") in carried_paths]
    uses = [r for r in prior_extraction.get("uses", []) if r.get("file") in carried_paths]
    io_edges = [r for r in prior_extraction.get("io_edges", []) if r.get("file") in carried_paths]
    imports = [r for r in prior_extraction.get("imports", []) if r.get("file") in carried_paths]
    per_file: Dict[str, Dict] = {p: prior_files[p] for p in carried_paths if p in prior_files}
    declared = {
        m: list(v) for m, v in (prior_extraction.get("declared_deps") or {}).items()
        if m not in changed_modules
    }
    module_notes = {
        m: list(v) for m, v in (prior_extraction.get("module_notes") or {}).items()
        if m not in changed_modules
    }

    for entry in entries:
        rel = entry["path"]
        if rel not in stale:
            continue
        if entry["binary"] or entry["bytes"] > MAX_PARSE_BYTES:
            continue
        lines = read_lines(repo / rel)
        if not lines:
            continue
        facts = extract_file(rel, lines, entry["module"])
        module = entry["module"]
        for row in facts.defines:
            row = dict(row)
            row["file"] = rel
            row["module"] = module
            defines.append(row)
        for row in facts.uses:
            row = dict(row)
            row["file"] = rel
            row["module"] = module
            row["scope_package"] = facts.package
            uses.append(row)
        for row in facts.io_edges:
            row = dict(row)
            row["file"] = rel
            row["module"] = module
            io_edges.append(row)
        for row in facts.imports:
            imports.append({"file": rel, "module": module, "fqn": row["fqn"],
                            "line": row["line"], "anchor": row["anchor"]})
        if facts.declared_deps:
            declared.setdefault(module, []).extend(facts.declared_deps)
        if facts.notes:
            module_notes.setdefault(module, []).extend(facts.notes)
        per_file[rel] = {
            "language": facts.language, "package": facts.package, "primary": facts.primary,
            "loc": facts.loc, "signals": facts.signals, "defines": len(facts.defines),
            "imports": len(facts.imports), "io_edges": len(facts.io_edges),
        }

    return {
        "head": inventory["head"],
        "files": per_file,
        "defines": _sorted(defines, ("fqn", "file", "kind")),
        "uses": _sorted(uses, ("fqn", "file")),
        "io_edges": _sorted(io_edges, ("source", "target", "channel", "file")),
        "imports": _sorted(imports, ("file", "fqn")),
        "declared_deps": {k: sorted(set(v)) for k, v in sorted(declared.items())},
        "module_notes": {k: sorted(set(v)) for k, v in sorted(module_notes.items())},
        "totals": {
            "parsed_files": len(per_file),
            "defines": len(defines),
            "uses": len(uses),
            "io_edges": len(io_edges),
            "imports": len(imports),
        },
    }
