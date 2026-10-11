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
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

#: The skill's own root: where `schema/`, `agents/` and the bundled tests live.
SKILL_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_VERSION = "1.0.0"
CDP_VERSION = "0.1.0"

# Files above this size are censused but not parsed (listed under `skipped` in the inventory).
MAX_PARSE_BYTES = 2_000_000

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


#: What a 0.0% coverage figure means on a fresh scan: shown beside the number, never instead of it
#: (`status`, the SessionStart text).
NO_REVIEW_NOTE = "model-reviewed (deterministic index complete; run `cdp run` for AI review)"


class CdpError(RuntimeError):
    """A user-facing failure. The CLI prints these without a traceback."""


class ArgError(CdpError, ValueError):
    """An argument of the wrong type or outside its range. One class for the CLI and
    for MCP tool arguments: the CLI prints it, the MCP server answers -32602."""


# --------------------------------------------------------- argument validation
# One validation layer: argparse `type=` helpers for the CLI, `check_*` for tool
# arguments (MCP), both built on the same functions.


def check_int(value: Any, name: str, minimum: Optional[int] = None, maximum: Optional[int] = None,
              strict: bool = False) -> int:
    """`value` as an int in [minimum, maximum]. Digit strings are accepted (they come
    from a command line) unless `strict` (a typed tool argument); bools, floats and
    other text never are."""
    if not strict and isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArgError("%s must be an integer, got %s %r" % (name, type(value).__name__, value))
    if minimum is not None and value < minimum:
        raise ArgError("%s must be %s, got %d" % (name, _range_text(minimum, maximum), value))
    if maximum is not None and value > maximum:
        raise ArgError("%s must be %s, got %d" % (name, _range_text(minimum, maximum), value))
    return value


def check_number(value: Any, name: str, minimum: float, maximum: Optional[float] = None,
                 exclusive_min: bool = False) -> float:
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            raise ArgError("%s must be a number, got %r" % (name, value))
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        raise ArgError("%s must be a number, got %s %r" % (name, type(value).__name__, value))
    low_bad = value <= minimum if exclusive_min else value < minimum
    if low_bad or (maximum is not None and value > maximum):
        raise ArgError("%s must be %s%s, got %g" % (
            name, "greater than %g" % minimum if exclusive_min else "at least %g" % minimum,
            " and at most %g" % maximum if maximum is not None else "", value))
    return float(value)


def check_str(value: Any, name: str, max_len: int = 500) -> str:
    """A tool argument that must be a non-empty string of sane length."""
    if not isinstance(value, str):
        raise ArgError("%s must be a string, got %s" % (name, type(value).__name__))
    if not value.strip() or len(value) > max_len:
        raise ArgError("%s must be 1-%d characters, got %d" % (name, max_len, len(value)))
    return value


def check_enum(value: Any, name: str, choices: Iterable[str]) -> str:
    """A tool argument that must be one of `choices` (a direct call, a client that skipped the schema)."""
    options = list(choices)
    if value not in options:
        raise ArgError("%s must be one of %s, got %r" % (name, ", ".join(options), value))
    return value


def _range_text(minimum: Optional[int], maximum: Optional[int]) -> str:
    if minimum is not None and maximum is not None:
        return "between %d and %d" % (minimum, maximum)
    if maximum is not None:
        return "at most %d" % maximum
    return "at least %d" % minimum


def _arg_type(check, what: str):
    """An argparse `type=` that reports `ArgError` as a plain usage error."""
    import argparse

    def convert(text: str):
        try:
            return check(text, "value")
        except ArgError as exc:
            raise argparse.ArgumentTypeError(str(exc).replace("value ", "", 1))

    convert.__name__ = what
    return convert


def bounded_int(minimum: Optional[int] = None, maximum: Optional[int] = None):
    return _arg_type(lambda v, n: check_int(v, n, minimum, maximum), "integer")


positive_int = bounded_int(1)
non_negative_int = bounded_int(0)
positive_float = _arg_type(lambda v, n: check_number(v, n, 0, exclusive_min=True), "number")
fraction = _arg_type(lambda v, n: check_number(v, n, 0, 1), "fraction")


#: Bounds of the integer parameters the CLI and the MCP tools share (min, max). The CLI
#: flags (`--max-hops`, ...) and the tool arguments (`max_hops`, ...) must agree on these.
LIMITS = {
    "budget": (0, None), "max_hops": (0, None), "max_leaf_files": (1, None),
    "max_leaf_loc": (1, None), "max_concurrent": (1, None), "workers": (1, None),
}


def check_limit(name: str, value: Any) -> int:
    """A tool argument named in `LIMITS`, checked at run time (a direct call, a client
    that skipped the schema): the same type and range rules as the CLI flag."""
    lo, hi = LIMITS[name]
    return check_int(value, name, lo, hi, strict=True)


def nonempty_arg(text: str) -> str:
    """argparse `type=` for a value that names something (a run, a commit): never blank,
    so an empty string cannot fall through to "the default" or invent an identity."""
    import argparse

    if not isinstance(text, str) or not text.strip():
        raise argparse.ArgumentTypeError("must not be empty")
    return text.strip()


def name_arg(text: str) -> str:
    """argparse `type=` for a label that becomes a file or directory name."""
    import argparse

    try:
        return safe_name(text, "name")
    except CdpError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def resolve_prefix(value: str, candidates: Iterable[str], what: str = "commit") -> str:
    """The one candidate that `value` names: exactly, or as a unique prefix (git's
    own short sha, 4+ hex digits). Unknown or ambiguous prefixes raise with the
    candidates listed. A clean `sha` wins over its `sha+dirty:tree` snapshots."""
    cands = sorted({c for c in candidates if c})
    if value in cands:
        return value
    shown = lambda items: ", ".join(c[:12] + ("+dirty" if "+dirty" in c else "") for c in items[:8]) \
        + (" ..." if len(items) > 8 else "")
    if not re.fullmatch(r"[0-9a-fA-F]{4,64}", value or ""):
        raise CdpError("%s %r matches nothing%s" % (what, value, "; known: " + shown(cands) if cands else ""))
    low = value.lower()
    hits = [c for c in cands if c.lower().startswith(low)]
    clean = [c for c in hits if "+dirty" not in c]
    if len(clean) == 1 and all(h == clean[0] or h.startswith(clean[0] + "+") for h in hits):
        return clean[0]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise CdpError("%s %r matches no known commit%s" % (what, value, "; known: " + shown(cands) if cands else ""))
    raise CdpError("%s prefix %r is ambiguous: %s -- give more digits" % (what, value, shown(hits)))


# ------------------------------------------------------------------ safe names


def safe_name(value: str, what: str, extra: str = "") -> str:
    """A label that becomes a file or directory name: `[A-Za-z0-9._-]+` (plus `extra`),
    never all dots. Anything else could climb out of the directory it is joined onto."""
    if (not isinstance(value, str) or not re.fullmatch("[A-Za-z0-9._%s-]+" % re.escape(extra), value)
            or set(value) <= {"."}):
        raise CdpError("%s %r is not a valid name: use letters, digits, '.', '_' and '-' only%s"
                       % (what, value, " (and %r)" % extra if extra else ""))
    return value


def path_within(base: Path, name: str, what: str) -> Path:
    """`base / name`, refusing a result whose resolved location is outside `base`
    (a symlink or `..` in `name`)."""
    base = Path(base).resolve()
    target = (base / name).resolve()
    if target.parent != base:
        raise CdpError("%s %r resolves outside %s" % (what, name, base))
    return target


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


def count_disk_files(repo: Path, excludes: Sequence[str] = ()) -> int:
    """Every regular file on disk, excluding .git and any path with a segment in `excludes`
    (the inventory's own exclusion patterns: `.claude/`, `.mcp.json`, ...). The denominator of
    §5.1's ratio: counting what the census drops would inflate it (500 tracked / 661 on disk
    after `install --harness`, the 161 being CDP's own files)."""
    skip = set(excludes) | {".git"}
    total = 0
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in skip]
        total += sum(1 for f in filenames if f not in skip)
    return total


# ------------------------------------------------------------------------ text


def resolves_inside(root: Path, path: Path) -> bool:
    """False for a path (typically a symlink) whose real location is outside `root`."""
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


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
