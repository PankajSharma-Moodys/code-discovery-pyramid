"""Phase 1 — inventory (§5.1).

Built from `git ls-files`, never from a filesystem walk. On the validation
target that is the difference between 391 files and 2,065: the worst offender,
`sql-pool-api-client`, holds 372 files on disk and 2 in git because its Java is
generated from an OpenAPI spec at build time. A walk would spend more context on
that one generated module than on the eight authored ones combined, and would
report generated boilerplate as if it were design.

The 5.3x ratio is reported as a first-class fact rather than a diagnostic. A
repository where most files on disk are invisible to version control is telling
you something about itself.

Nothing here records a timestamp. `inventory.json` must be byte-identical across
two runs at the same commit, and a `generated_at` field would quietly fail that
gate at every phase. Wall-clock lives in `manifest.json`, which the
reproducibility check excludes for exactly this reason.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .lang import classify_role, get_extractor, is_manifest
from .util import (
    CdpError,
    count_disk_files,
    git_head,
    git_ls_files,
    is_binary_path,
    is_git_repo,
    read_lines,
    walk_files,
)

ROOT_MODULE = "(root)"


def build_inventory(repo: Path) -> Dict:
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise CdpError("not a directory: %s" % repo)

    source = "git"
    paths = git_ls_files(repo) if is_git_repo(repo) else None
    if paths is None:
        source = "walk"
        paths = walk_files(repo)

    manifests = sorted(p for p in paths if is_manifest(p))
    module_roots = _module_roots(paths, manifests)

    files: List[Dict] = []
    for rel in paths:
        extractor = get_extractor(rel)
        binary = is_binary_path(rel)
        loc = 0
        size = 0
        full = repo / rel
        try:
            size = full.stat().st_size
        except OSError:
            size = 0
        if not binary and size < 4_000_000:
            loc = len(read_lines(full))
        files.append(
            {
                "path": rel,
                "module": _module_for(rel, module_roots),
                "language": extractor.language if extractor.language != "build" else _build_language(rel),
                "role": classify_role(rel, extractor),
                "loc": loc,
                "bytes": size,
                "binary": binary,
            }
        )

    modules = _module_summaries(repo, files, module_roots, manifests)
    on_disk = count_disk_files(repo)
    tracked = len(files)

    return {
        "repo": str(repo),
        "repo_name": repo.name,
        "head": git_head(repo) or "unpinned",
        "source": source,
        "counts": {
            "tracked": tracked,
            "on_disk": on_disk,
            "ratio": round(on_disk / tracked, 2) if tracked else 0.0,
        },
        "by_language": _tally(files, "language"),
        "by_role": _tally(files, "role"),
        "modules": modules,
        "files": files,
    }


# ----------------------------------------------------------------- modules


def _module_roots(paths: List[str], manifests: List[str]) -> List[str]:
    """Directories that are module roots, deepest-first for prefix matching.

    A directory holding a build manifest is a module. This is the one rule that
    makes module detection portable across ecosystems — gradle, maven, npm,
    go, cargo and poetry all mark their module roots this way — and it needs no
    knowledge of any particular repository's layout.

    A manifest at the repository root does not create a module; the root is the
    root scope (§3.3), which exists precisely to own the files no module claims.
    """
    dirs = set()
    for manifest in manifests:
        parent = manifest.rsplit("/", 1)[0] if "/" in manifest else ""
        if parent:
            dirs.add(parent)

    if not dirs:
        # No sub-manifests: fall back to top-level directories that hold files.
        for path in paths:
            if "/" in path:
                dirs.add(path.split("/", 1)[0])
    return sorted(dirs, key=lambda d: (-d.count("/"), d))


def _module_for(rel: str, module_roots: List[str]) -> str:
    for root in module_roots:  # deepest first
        if rel == root or rel.startswith(root + "/"):
            return root
    return ROOT_MODULE


def _build_language(rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    if name.startswith(("build.gradle", "settings.gradle")) or rel.endswith(".gradle"):
        return "gradle"
    if name == "pom.xml":
        return "maven"
    if name == "package.json":
        return "npm"
    if name == "go.mod":
        return "gomod"
    return "build"


def _module_summaries(
    repo: Path, files: List[Dict], module_roots: List[str], manifests: List[str]
) -> List[Dict]:
    names = sorted(set(f["module"] for f in files))
    manifest_by_dir: Dict[str, List[str]] = {}
    for m in manifests:
        parent = m.rsplit("/", 1)[0] if "/" in m else ROOT_MODULE
        manifest_by_dir.setdefault(parent, []).append(m)

    out = []
    for name in names:
        owned = [f for f in files if f["module"] == name]
        path = "" if name == ROOT_MODULE else name
        disk = count_disk_files(repo / path) if path else 0
        entry = {
            "name": name,
            "path": path,
            "manifests": sorted(manifest_by_dir.get(name, [])),
            "files": len(owned),
            "loc": sum(f["loc"] for f in owned),
            "by_language": _tally(owned, "language"),
            "by_role": _tally(owned, "role"),
        }
        if path:
            entry["on_disk"] = disk
            entry["disk_ratio"] = round(disk / len(owned), 2) if owned else 0.0
            # A module whose tracked count is a rounding error against its disk
            # count is generated, and §6.7 requires describing it by its
            # contract rather than reading it.
            entry["generated_suspect"] = bool(owned) and disk >= 20 * len(owned)
        out.append(entry)
    return out


def _tally(files: List[Dict], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for f in files:
        counts[f[key]] = counts.get(f[key], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def summarise(inventory: Dict) -> List[str]:
    """Terse human summary for the CLI and for `manifest.json`'s headline."""
    counts = inventory["counts"]
    lines = [
        "repo      %s @ %s" % (inventory["repo_name"], inventory["head"][:12]),
        "census    %d tracked / %d on disk (%.1fx)  [%s]"
        % (counts["tracked"], counts["on_disk"], counts["ratio"], inventory["source"]),
        "languages " + ", ".join("%s %d" % (k, v) for k, v in list(inventory["by_language"].items())[:8]),
        "modules   %d" % len(inventory["modules"]),
    ]
    for m in sorted(inventory["modules"], key=lambda m: -m["files"]):
        flag = "  <- generated?" if m.get("generated_suspect") else ""
        lines.append(
            "  %-28s %4d files %7d loc  (disk %s)%s"
            % (m["name"], m["files"], m["loc"], m.get("on_disk", "-"), flag)
        )
    return lines
