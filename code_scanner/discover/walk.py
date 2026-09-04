"""Discovery — delegate to git for correct gitignore semantics; pathspec fallback otherwise.

D12.1: run with cwd = the scan target, and treat output as target-relative — `git -C <root>`
enumerates the whole repository even when asked to scan one subdirectory, which is the wrong
denominator for every metric.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pathspec

DEFAULT_IGNORES = [
    ".git/", "node_modules/", "vendor/", "dist/", "build/", "target/",
    "__pycache__/", ".venv/", "*.min.js", "*.lock", "package-lock.json",
    "yarn.lock", "Pipfile.lock", "poetry.lock",
]


@dataclass
class DiscoveryResult:
    files: list[Path]          # absolute paths
    discovery: str              # "git-ls-files" | "pathspec-walk"
    skipped_binary: int = 0
    skipped_too_large: int = 0


def _is_git_worktree(root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root, capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git_ls_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=True,
    )
    names = result.stdout.split(b"\x00")
    return [root / name.decode("utf-8", errors="replace") for name in names if name]


def _pathspec_walk(root: Path) -> list[Path]:
    spec = pathspec.PathSpec.from_lines("gitignore", DEFAULT_IGNORES)
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if spec.match_file(rel):
            continue
        files.append(path)
    return files


def _is_binary(path: Path, sniff_bytes: int) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(sniff_bytes)
    except OSError:
        return False
    return b"\x00" in chunk


def discover(
    root: Path,
    max_file_bytes: int = 1_048_576,
    binary_sniff_bytes: int = 8192,
    follow_symlinks: bool = False,
) -> DiscoveryResult:
    if _is_git_worktree(root):
        candidates = _git_ls_files(root)
        discovery = "git-ls-files"
    else:
        candidates = _pathspec_walk(root)
        discovery = "pathspec-walk"

    files: list[Path] = []
    skipped_binary = 0
    skipped_too_large = 0
    for path in candidates:
        try:
            if not follow_symlinks and path.is_symlink():
                continue
            if not path.is_file():
                continue
            size = path.stat().st_size
        except OSError:
            continue
        if size > max_file_bytes:
            skipped_too_large += 1
            continue
        if _is_binary(path, binary_sniff_bytes):
            skipped_binary += 1
            continue
        files.append(path)

    return DiscoveryResult(
        files=sorted(files),
        discovery=discovery,
        skipped_binary=skipped_binary,
        skipped_too_large=skipped_too_large,
    )
