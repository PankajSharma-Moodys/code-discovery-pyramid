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

from pathlib import Path
from typing import Dict, List, Optional

from .lang import extract_file
from .util import read_lines

# Files above this size are censused but not parsed. A 4 MB generated source
# file is not a design document, and reading it would blow the budget it was
# excluded from git to protect.
MAX_PARSE_BYTES = 2_000_000


def run_extract(repo: Path, inventory: Dict, progress=None) -> Dict:
    repo = Path(repo)
    defines: List[Dict] = []
    uses: List[Dict] = []
    io_edges: List[Dict] = []
    imports: List[Dict] = []
    per_file: Dict[str, Dict] = {}
    declared: Dict[str, List[str]] = {}
    module_notes: Dict[str, List[str]] = {}

    for entry in inventory["files"]:
        rel = entry["path"]
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
            "language": facts.language,
            "package": facts.package,
            "primary": facts.primary,
            "loc": facts.loc,
            "signals": facts.signals,
            "defines": len(facts.defines),
            "imports": len(facts.imports),
            "io_edges": len(facts.io_edges),
        }
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
