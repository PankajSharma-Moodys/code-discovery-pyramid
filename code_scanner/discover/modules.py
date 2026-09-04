"""Manifest table -> module assignment (RESEARCH §4). Zero build-system parsing:
a module is any directory containing a build manifest; every file belongs to its
nearest enclosing one. Falls back to directory grouping when too few modules are
found (§4 — a single pyproject.toml over app/ would otherwise collapse to one row)."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

_ECOSYSTEM_BY_MANIFEST = {
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "package.json": "npm",
    "go.mod": "go",
    "Cargo.toml": "cargo",
    "pyproject.toml": "python",
    "setup.py": "python",
    "*.csproj": "dotnet",
    "*.fsproj": "dotnet",
}


@dataclass(frozen=True)
class Module:
    id: str
    path: str            # relative to scan root
    manifest: str | None
    ecosystem: str | None


def _ecosystem_for_manifest(name: str) -> str | None:
    if name in _ECOSYSTEM_BY_MANIFEST:
        return _ECOSYSTEM_BY_MANIFEST[name]
    for pattern, eco in _ECOSYSTEM_BY_MANIFEST.items():
        if "*" in pattern and fnmatch.fnmatch(name, pattern):
            return eco
    return None


def find_manifest_dirs(root: Path, manifest_patterns: list[str]) -> dict[Path, tuple[str, str | None]]:
    """dir -> (manifest_filename, ecosystem). Skips vendor/build dirs proactively."""
    skip_dirs = {".git", "node_modules", "vendor", "dist", "build", "target", "__pycache__", ".venv"}
    found: dict[Path, tuple[str, str | None]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.relative_to(root).parts[:-1]):
            continue
        name = path.name
        for pattern in manifest_patterns:
            if fnmatch.fnmatch(name, pattern):
                d = path.parent
                if d not in found:
                    found[d] = (name, _ecosystem_for_manifest(pattern if "*" in pattern else name))
                break
    return found


def assign_modules(
    root: Path,
    files: list[Path],
    manifest_patterns: list[str],
    min_for_manifest_grouping: int = 2,
) -> tuple[dict[Path, Module], str]:
    """Returns (file -> Module, grouping) where grouping is "manifest" | "directory"."""
    manifest_dirs = find_manifest_dirs(root, manifest_patterns)

    def nearest_manifest_dir(file_path: Path) -> Path | None:
        current = file_path.parent
        while True:
            if current in manifest_dirs:
                return current
            if current == root or current.parent == current:
                return None
            current = current.parent

    file_to_manifest_dir: dict[Path, Path | None] = {f: nearest_manifest_dir(f) for f in files}
    distinct_manifest_dirs = {d for d in file_to_manifest_dir.values() if d is not None}

    if len(distinct_manifest_dirs) >= min_for_manifest_grouping:
        modules: dict[Path, Module] = {}
        result: dict[Path, Module] = {}
        for f in files:
            d = file_to_manifest_dir[f]
            if d is None:
                continue
            if d not in modules:
                manifest_name, ecosystem = manifest_dirs[d]
                rel = d.relative_to(root).as_posix() if d != root else "."
                modules[d] = Module(id=rel, path=rel, manifest=manifest_name, ecosystem=ecosystem)
            result[f] = modules[d]
        return result, "manifest"

    # Directory fallback: group by the top-level source directory (first two path
    # segments when available), so app/routers and app/services stay distinguishable.
    dir_modules: dict[str, Module] = {}
    result = {}
    for f in files:
        parts = f.relative_to(root).parts[:-1]
        key = "/".join(parts[:2]) if len(parts) >= 2 else ("/".join(parts) if parts else ".")
        if key not in dir_modules:
            dir_modules[key] = Module(id=key, path=key, manifest=None, ecosystem=None)
        result[f] = dir_modules[key]
    return result, "directory"
