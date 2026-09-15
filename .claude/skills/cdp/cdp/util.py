"""Shared primitives: deterministic IO, git access, text handling.

Everything CDP writes goes through `write_json` so that two runs over the same
commit produce byte-identical files. That is the reproducibility gate the plan
asks for at every phase, and it only holds if nothing bypasses this module.

Stdlib only, Python 3.9+. CDP is meant to be copied into a target repository
with no install step, so a third-party dependency here would defeat the point.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

SCHEMA_VERSION = "1.0.0"
CDP_VERSION = "0.1.0"

# Directories a filesystem walk must never descend into. Only consulted when the
# target is not a git repository (§5.1 prefers `git ls-files` precisely so that
# this list never has to be right).
WALK_EXCLUDE = frozenset(
    """
    .git .hg .svn .cdp .gradle .idea .vscode .mypy_cache .pytest_cache .ruff_cache
    .tox .venv venv env node_modules bower_components vendor target build out dist
    __pycache__ .next .nuxt .parcel-cache .terraform .serverless coverage htmlcov
    bin obj Pods DerivedData .dart_tool .cargo .stack-work _build deps
    """.split()
)

BINARY_EXTS = frozenset(
    """
    .jar .war .ear .class .so .dylib .dll .exe .bin .o .a .zip .gz .bz2 .xz .7z
    .tar .tgz .rar .png .jpg .jpeg .gif .bmp .ico .webp .svgz .pdf .doc .docx
    .xls .xlsx .ppt .pptx .woff .woff2 .ttf .eot .otf .mp3 .mp4 .avi .mov .wav
    .db .sqlite .sqlite3 .pyc .pyo .keystore .jks .p12 .pfx .der
    """.split()
)


class CdpError(RuntimeError):
    """A user-facing failure. The CLI prints these without a traceback."""


# --------------------------------------------------------------- deterministic IO


def write_json(path: Path, obj: Any) -> Path:
    """Write `obj` as canonical JSON: sorted keys, 2-space indent, trailing newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def read_json(path: Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        if default is not None:
            return default
        raise CdpError("missing state file: %s (run `scan` first?)" % p)
    return json.loads(p.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def read_jsonl(path: Path) -> List[Any]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def write_text(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_hash(obj: Any) -> str:
    """Content hash of any JSON-serialisable value, stable across runs."""
    return sha256_text(json.dumps(obj, sort_keys=True, ensure_ascii=False))


# ------------------------------------------------------------------------- git


def run_git(repo: Path, *args: str) -> Optional[str]:
    """Run git in `repo`. Returns stdout, or None if git is unavailable/failed."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo)] + list(args),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def is_git_repo(repo: Path) -> bool:
    return run_git(repo, "rev-parse", "--git-dir") is not None


def git_head(repo: Path) -> Optional[str]:
    out = run_git(repo, "rev-parse", "HEAD")
    return out.strip() if out else None


def git_ls_files(repo: Path) -> Optional[List[str]]:
    """Tracked files, repo-relative, sorted.

    `git ls-files` run inside a subdirectory of a larger repository lists only
    that subtree, which is what we want: `sql-pool` is a directory inside the
    `unified-store` repo and must census as 391 files, not the whole monorepo.
    """
    out = run_git(repo, "ls-files", "-z")
    if out is None:
        return None
    files = [p for p in out.split("\0") if p]
    return sorted(files)


def walk_files(repo: Path) -> List[str]:
    """Fallback census for non-git targets. Noisier by construction (§5.1)."""
    root = Path(repo)
    found: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in WALK_EXCLUDE and not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            rel = Path(dirpath, name).relative_to(root).as_posix()
            found.append(rel)
    return sorted(found)


def count_disk_files(repo: Path) -> int:
    """Every regular file on disk, excluding .git. The denominator of §5.1's ratio."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        total += len(filenames)
    return total


# ------------------------------------------------------------------------ text


def is_binary_path(rel: str) -> bool:
    return Path(rel).suffix.lower() in BINARY_EXTS


def read_lines(path: Path) -> List[str]:
    """Read a source file as lines with no trailing newlines.

    Decoding is lossy on purpose. A file with one bad byte should still yield
    citable anchors for its other 400 lines.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return []
    if b"\0" in raw[:8192]:
        return []
    return raw.decode("utf-8", errors="replace").splitlines()


def normalise_ws(text: str) -> str:
    """Collapse runs of whitespace to a single space and strip the ends.

    Used by both anchor construction and anchor verification so that a span
    crossing a line break compares equal regardless of indentation (C7).
    """
    return " ".join(text.split())


def posix(path: str) -> str:
    return str(path).replace("\\", "/")


def rel_to(repo: Path, path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(repo).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


# ------------------------------------------------------------------- small utils


def group_by(rows: Iterable[Dict[str, Any]], key: str) -> Dict[Any, List[Dict[str, Any]]]:
    out: Dict[Any, List[Dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row.get(key), []).append(row)
    return out


def dedupe(items: Sequence[Any]) -> List[Any]:
    """Order-preserving dedupe over JSON-serialisable values."""
    seen = set()
    out = []
    for item in items:
        k = stable_hash(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def human_int(n: int) -> str:
    return "{:,}".format(n)
