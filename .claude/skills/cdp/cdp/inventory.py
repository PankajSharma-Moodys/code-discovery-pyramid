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

from .lang import classify_role, extract_file, get_extractor, is_manifest
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
    root_module = _root_module(repo, paths, manifests)
    root_name = root_module["name"] or ROOT_MODULE
    module_roots = [] if root_module["is_module"] else _module_roots(paths, manifests)

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
                "module": _module_for(rel, module_roots, root_name),
                "language": extractor.language if extractor.language != "build" else _build_language(rel),
                "role": classify_role(rel, extractor),
                "loc": loc,
                "bytes": size,
                "binary": binary,
            }
        )

    modules = _module_summaries(repo, files, module_roots, manifests, root_name)
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
        "root_module": root_module,
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

    A manifest at the repository root does not, by itself, create a module: in a
    monorepo whose root manifest is an aggregator, the root is the root scope
    (§3.3), which exists precisely to own the files no module claims. That case
    is decided by `_root_module` before this function is called; reaching here
    means the root is not a module, so only sub-manifests are considered.

    The last resort — a module per top-level directory — applies only when the
    repository holds no manifest anywhere. It is a guess, and it is why pointing
    `--repo` at a single module used to produce a bogus `src`.
    """
    dirs = set()
    for manifest in manifests:
        parent = manifest.rsplit("/", 1)[0] if "/" in manifest else ""
        if parent:
            dirs.add(parent)

    if not dirs:
        # No manifest anywhere: fall back to top-level directories that hold files.
        for path in paths:
            if "/" in path:
                dirs.add(path.split("/", 1)[0])
    return sorted(dirs, key=lambda d: (-d.count("/"), d))


def _root_module(repo: Path, paths: List[str], manifests: List[str]) -> Dict:
    """Decide whether the scan root is itself one module, and what it is called.

    **The bug this exists to fix.** Pointing `--repo` at a single module — the
    normal way to scan one service — put a manifest at the scan root and none
    below it. `_module_roots` excluded the root by rule and then fell through to
    its last resort, inventing one module per top-level directory: a repository
    whose whole identity is `<artifactId>my-service</artifactId>` was reported as
    a module named `src`, with zero declared edges (nothing named `src` in any
    manifest) and zero observed edges (there was only one module to import from).

    The distinction that was missing is *aggregator vs. leaf*. A root manifest
    with sub-manifests beneath it is an aggregator and the old rule is right. A
    root manifest with nothing beneath it **is** the module, and its name is the
    one the build gives it — never the directory, which is an artifact of where
    someone happened to clone.

    Degrades honestly (§R6): when the manifest yields no name, the root is still
    one module, but it keeps the anonymous `(root)` label and `named` is false,
    so `cmd_scan` can raise a structural unknown instead of guessing.
    """
    root_manifests = [m for m in manifests if "/" not in m]
    sub_manifests = [m for m in manifests if "/" in m]
    if not root_manifests or sub_manifests:
        return {
            "is_module": False,
            "named": False,
            "name": None,
            "manifest": None,
            "reason": (
                "sub-manifests exist; the root is the root scope (§3.3)"
                if sub_manifests
                else "no build manifest at the scan root"
            ),
        }

    name, manifest = _root_module_name(repo, paths, root_manifests)
    return {
        "is_module": True,
        "named": bool(name),
        "name": name,
        "manifest": manifest,
        "reason": (
            "a build manifest at the scan root with none beneath it: the root is "
            "one module"
        ),
    }


#: Manifest notes that carry the build's own name for the thing it builds, best
# first. `root_project_name` is Gradle's explicit statement of identity;
# `artifact` is the Maven artifactId, the npm `name`, the go module path, the
# Cargo/PEP-621 package name.
_NAME_NOTES = ("root_project_name=", "artifact=")

#: Gradle splits identity from configuration: `build.gradle` marks the module,
# `settings.gradle` names it. Reading the marker alone would leave every
# single-module Gradle build anonymous.
_GRADLE_SETTINGS = ("settings.gradle", "settings.gradle.kts")

_PROJECT_FILE_SUFFIXES = (".csproj", ".fsproj", ".vbproj")


def _root_module_name(
    repo: Path, paths: List[str], root_manifests: List[str]
) -> Tuple[Optional[str], Optional[str]]:
    """`(name, manifest)` read out of the root manifest, or `(None, manifest)`.

    Reuses the real manifest extractors rather than re-parsing: the same code
    that produces `declared_deps` produces the name, so the two cannot drift.
    """
    present = set(paths)
    candidates = sorted(root_manifests) + [s for s in _GRADLE_SETTINGS if s in present]

    notes: List[Tuple[str, str]] = []
    for rel in candidates:
        try:
            facts = extract_file(rel, read_lines(repo / rel), ROOT_MODULE)
        except OSError:
            continue
        for note in facts.notes:
            notes.append((note, rel))

    for prefix in _NAME_NOTES:
        for note, rel in notes:
            if note.startswith(prefix):
                name = note[len(prefix):].strip().rsplit("/", 1)[-1]
                if name:
                    return name, rel
    # An MSBuild project file has no name element: the file stem *is* the
    # assembly name. That is still the build's own statement of identity, not
    # the directory's.
    for rel in sorted(root_manifests):
        if rel.endswith(_PROJECT_FILE_SUFFIXES):
            return rel.rsplit(".", 1)[0], rel
    return None, (sorted(root_manifests)[0] if root_manifests else None)


def _module_for(rel: str, module_roots: List[str], root_name: str = ROOT_MODULE) -> str:
    for root in module_roots:  # deepest first
        if rel == root or rel.startswith(root + "/"):
            return root
    return root_name


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
    repo: Path,
    files: List[Dict],
    module_roots: List[str],
    manifests: List[str],
    root_name: str = ROOT_MODULE,
) -> List[Dict]:
    names = sorted(set(f["module"] for f in files))
    manifest_by_dir: Dict[str, List[str]] = {}
    for m in manifests:
        parent = m.rsplit("/", 1)[0] if "/" in m else root_name
        manifest_by_dir.setdefault(parent, []).append(m)

    out = []
    for name in names:
        owned = [f for f in files if f["module"] == name]
        # The root module's path is the repository root, whether it is the
        # anonymous root scope or a named single module.
        path = "" if name == root_name else name
        # `(root)` is a scope, not a module, so it gets no census of its own.
        # A *named* root module is a module and does.
        censused = name != ROOT_MODULE
        disk = count_disk_files(repo / path) if censused else 0
        entry = {
            "name": name,
            "path": path,
            "manifests": sorted(manifest_by_dir.get(name, [])),
            "files": len(owned),
            "loc": sum(f["loc"] for f in owned),
            "by_language": _tally(owned, "language"),
            "by_role": _tally(owned, "role"),
        }
        if censused:
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
    root = inventory.get("root_module") or {}
    if root.get("is_module") and root.get("named"):
        lines.append("          scan root is one module, named '%s' by %s"
                     % (root["name"], root["manifest"]))
    elif root.get("is_module"):
        lines.append("          scan root is one module, but %s does not name it"
                     % (root.get("manifest") or "its manifest"))
    for m in sorted(inventory["modules"], key=lambda m: -m["files"]):
        flag = "  <- generated?" if m.get("generated_suspect") else ""
        lines.append(
            "  %-28s %4d files %7d loc  (disk %s)%s"
            % (m["name"], m["files"], m["loc"], m.get("on_disk", "-"), flag)
        )
    return lines
