"""Phase 2 driver — run the registered extractors over the inventory.

This is the phase that implements PLAN.md's central decision: **Python owns
structure, the LLM owns meaning.** `defines[]`, `uses[]` and `io_edges[]` are
produced here, deterministically, from the source text. Leaf agents never emit
them; they emit only `claims[]` and `unknowns[]` over structure they are handed.

Two consequences the plan calls out and this file inherits:

- `xref.json` becomes fully reproducible, so the determinism harness measures
  only what was genuinely stochastic rather than scoring a regex.
- Detector bugs become silent recall loss. That risk is owned by the `minirepo`
  golden test, which asserts hand-written expected output byte for byte.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .lang import extract_file
from .lang.base import FileFacts
from .util import read_lines

# Files above this size are censused but not parsed. A 4 MB generated source
# file is not a design document, and reading it would blow the budget it was
# excluded from git to protect.
MAX_PARSE_BYTES = 2_000_000

# Below this many parseable files, a process pool's own startup cost (each
# worker forks/spawns an interpreter) is not worth paying -- every existing
# test and the `minirepo` fixture sit well under it, so they run the
# sequential path unchanged and untimed by this change at all (F9, "worth a
# further 4-8x", was deliberately not implemented until the ordering claim
# below was verified against real files, not just argued).
PARALLEL_MIN_FILES = 64


def _extract_worker(payload: Tuple[str, str, str]) -> Tuple[str, str, Optional[FileFacts]]:
    """Runs in a worker process: read one file and extract it, standalone.

    Must stay a module-level function (not a closure) -- `ProcessPoolExecutor`
    pickles the callable and its argument to hand off to the worker, and a
    closure over `run_extract`'s locals is not picklable.
    """
    repo_str, rel, module = payload
    lines = read_lines(Path(repo_str) / rel)
    if not lines:
        return (rel, module, None)
    return (rel, module, extract_file(rel, lines, module))


def _absorb(rel: str, module: str, facts: FileFacts, defines, uses, io_edges,
            imports, per_file, declared, module_notes) -> None:
    """One file's `FileFacts` into the accumulators. Used by both the
    sequential and parallel paths so there is exactly one copy of this
    logic to keep in sync with the schema."""
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
        "language": facts.language,
        "package": facts.package,
        "primary": facts.primary,
        "loc": facts.loc,
        "signals": facts.signals,
        "defines": len(facts.defines),
        "imports": len(facts.imports),
        "io_edges": len(facts.io_edges),
    }


def run_extract(repo: Path, inventory: Dict, progress=None,
                 workers: Optional[int] = None) -> Dict:
    """Extract every parseable file in `inventory`, in parallel above
    `PARALLEL_MIN_FILES` files.

    Safe to parallelise across *files* only because of what happens after
    this function collects the pieces: every list returned below goes
    through `_sorted()`, whose key ends in `(anchor.file, anchor.line)` --
    so the final order never depends on which file's rows were appended
    first. A tie in that key can only happen between two rows from the
    *same* file (`file` is part of every sort key), and one file's own row
    order comes entirely from a single `extract_file()` call running start
    to finish inside one worker -- parallelism changes which files interleave
    before the sort, never the order of rows a single file produced. There is
    therefore nothing left for cross-file ordering to get wrong, but that is
    a claim, not a hope: `tests/test_extract_parallel.py` checks it directly
    against real files (fixture and, opt-in, `$TARGET_REPO`), not just this
    docstring's argument.

    `workers=None` (default) auto-selects: sequential below
    `PARALLEL_MIN_FILES` parseable files, `min(cpu_count, file_count)` above
    it. An explicit `workers=` always wins, so a caller (the differential
    test) can force real parallel execution on a small repo.
    """
    repo = Path(repo)
    defines: List[Dict] = []
    uses: List[Dict] = []
    io_edges: List[Dict] = []
    imports: List[Dict] = []
    per_file: Dict[str, Dict] = {}
    declared: Dict[str, List[str]] = {}
    module_notes: Dict[str, List[str]] = {}

    candidates: List[Tuple[str, str]] = [
        (entry["path"], entry["module"]) for entry in inventory["files"]
        if not entry["binary"] and entry["bytes"] <= MAX_PARSE_BYTES
    ]

    if workers is None:
        workers = (min(os.cpu_count() or 1, len(candidates))
                   if len(candidates) >= PARALLEL_MIN_FILES else 1)

    if workers <= 1:
        for rel, module in candidates:
            lines = read_lines(repo / rel)
            if not lines:
                continue
            facts = extract_file(rel, lines, module)
            _absorb(rel, module, facts, defines, uses, io_edges, imports,
                    per_file, declared, module_notes)
            if progress:
                progress(rel)
    else:
        payloads = [(str(repo), rel, module) for rel, module in candidates]
        # `Executor.map()` is a generator that, internally, kicks off every
        # future up front and then yields `futures[i].result()` in dispatch
        # order -- `i=0`'s result is yielded before `i=1`'s regardless of
        # which worker process actually finishes first, blocking on `i=0` if
        # it is still running when `i=1` completes. So this loop absorbs
        # results in exactly `candidates`' order, identical to the sequential
        # branch above, even though the underlying work happened out of order
        # across processes.
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for rel, module, facts in pool.map(_extract_worker, payloads):
                if facts is None:
                    continue
                _absorb(rel, module, facts, defines, uses, io_edges, imports,
                        per_file, declared, module_notes)
                if progress:
                    progress(rel)

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


def _sorted(rows: List[Dict], keys) -> List[Dict]:
    """Total order over rows, so two runs write byte-identical JSON.

    Sorting on the anchor line as the final key matters: two `persist` edges
    from the same class to the same table differ only by where they were seen,
    and without the line in the key their relative order would depend on dict
    iteration rather than on the file.
    """

    def key(row: Dict):
        primary = tuple(str(row.get(k) or "") for k in keys)
        anchor = row.get("anchor") or {}
        return primary + (str(anchor.get("file") or ""), int(anchor.get("line") or 0))

    return sorted(rows, key=key)


def signals_index(extraction: Dict) -> Dict[str, List[str]]:
    """signal -> files carrying it. Feeds the module documents and §6.6's
    framework-managed exclusion list."""
    index: Dict[str, List[str]] = {}
    for rel, info in extraction["files"].items():
        for signal in info.get("signals", []):
            index.setdefault(signal, []).append(rel)
    return {k: sorted(v) for k, v in sorted(index.items())}
