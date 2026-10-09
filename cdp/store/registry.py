"""Machine home, repo identity and `.cdp.toml` (Phase 2).

**One store per machine.** Everything CDP keeps lives under `CDP_HOME`
(default `~/.cdp`): `index.db` holds every repo, snapshot and link; `work/<repo>/`
holds the files an agent session hands over (inbox, prompts, rendered docs).
Nothing is written into the folder being scanned. `CDP_HOME` is the one
override, for CI and tests; `--state-dir` is an alias for it.

**Repo identity is never the filesystem path** — a path is exactly what two
clones of the same repo do not share. Order:

    declared id (`.cdp-id` in the scanned folder, a one-line opt-in file)
    -> normalised origin remote (`git remote get-url origin`)
    -> a UUID persisted at `<repo>/.git/cdp-identity`
    -> (not a git repo) a hash of the resolved path

A folder below the git root is a different repo from its parent: its identity
is `<repo identity>#<path from git root>`. Without that, scanning `svc/` wrote
over the index of the whole repo, because both share one remote.

`CDP_HOME/config.toml` holds the machine's one backend choice (`backend`,
`[postgres]`). `.cdp.toml` (checked into a repo) keeps only `exclude`; the
removed keys (`store`, `backend`, `[postgres]`) are rejected with a message
that points here.
"""

from __future__ import annotations

import tomllib
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..util import CdpError, run_git

import hashlib
import os
import re

HOME_ENV = "CDP_HOME"
DECLARED_ID_FILE = ".cdp-id"
TEAM_CONFIG_FILE = ".cdp.toml"
CONFIG_FILE = "config.toml"
REMOVED_TEAM_KEYS = ("store", "backend", "postgres")


def cdp_home() -> Path:
    """`CDP_HOME`, else `~/.cdp`. Resolved on every call so tests and CI can
    point it elsewhere after import."""
    override = os.environ.get(HOME_ENV)
    return Path(override).expanduser().resolve() if override else Path.home() / ".cdp"


def _normalise_remote(url: str) -> str:
    """`git@github.com:a/b.git`, `https://github.com/a/b/` and
    `https://github.com/a/b.git` must all name the same repo."""
    url = url.strip()
    if url.startswith("git@"):
        url = url[len("git@"):].replace(":", "/", 1)
    for prefix in ("https://", "http://", "git://", "ssh://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    if url.endswith(".git"):
        url = url[: -len(".git")]
    return url.rstrip("/").lower()


def _declared_id(repo: Path) -> Optional[str]:
    path = repo / DECLARED_ID_FILE
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


def _origin_remote(repo: Path) -> Optional[str]:
    url = run_git(repo, "remote", "get-url", "origin")
    return _normalise_remote(url) if url else None


def _persisted_uuid(repo: Path) -> str:
    """A UUID kept in the repo's *common* git dir, so every linked worktree of
    one repo shares it (`.git` is a file, not a directory, in a worktree)."""
    common = (run_git(repo, "rev-parse", "--git-common-dir") or "").strip()
    git_dir = (repo / common).resolve() if common else repo / ".git"
    marker = git_dir / "cdp-identity"
    if marker.is_file():
        existing = marker.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    generated = str(uuid.uuid4())
    if git_dir.is_dir():
        marker.write_text(generated + "\n", encoding="utf-8")
    return generated


def git_root(repo: Path) -> Tuple[Optional[Path], str]:
    """`(git toplevel, path of repo below it)`; `(None, "")` outside git."""
    top = run_git(repo, "rev-parse", "--show-toplevel")
    if not top or not top.strip():
        return None, ""
    prefix = (run_git(repo, "rev-parse", "--show-prefix") or "").strip().strip("/")
    return Path(top.strip()), prefix


def _root_identity(root: Path) -> str:
    return _declared_id(root) or _origin_remote(root) or _persisted_uuid(root)


def repo_identity(repo: Path) -> str:
    repo = Path(repo).expanduser().resolve()
    top, prefix = git_root(repo)
    if top is None:
        return _declared_id(repo) or "path:" + hashlib.sha256(str(repo).encode()).hexdigest()[:16]
    if prefix:
        # A folder's own `.cdp-id` is a full, explicit identity.
        declared = _declared_id(repo)
        return declared or "%s#%s" % (_root_identity(top), prefix)
    return _root_identity(top)


def candidate_identities(start: Path) -> List[Tuple[Path, str]]:
    """Every folder from `start` up to its git root, with the identity a scan
    of that folder would have, innermost first. The hook uses it to find the
    most specific scanned repo containing a file without a git call per
    ancestor."""
    start = Path(start).expanduser().resolve()
    top, prefix = git_root(start)
    if top is None:
        return []
    base = _root_identity(top)
    parts = [p for p in prefix.split("/") if p]
    out: List[Tuple[Path, str]] = []
    for depth in range(len(parts), -1, -1):
        folder = start
        for _ in range(len(parts) - depth):
            folder = folder.parent
        out.append((folder, "%s#%s" % (base, "/".join(parts[:depth])) if depth else base))
    return out


def repo_slug(repo_id: str) -> str:
    """A filesystem-safe, collision-proof directory name for `repo_id`."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", repo_id).strip("_")[:60] or "repo"
    return "%s-%s" % (safe, hashlib.sha256(repo_id.encode()).hexdigest()[:8])


def work_dir(home: Path, repo_id: str) -> Path:
    """Where one repo's inbox, prompts and rendered docs live."""
    return Path(home) / "work" / repo_slug(repo_id)


# ----------------------------------------------------------- machine config


def read_config(home: Optional[Path] = None) -> dict:
    """`CDP_HOME/config.toml`. A file written by an older CDP held a `[repos]`
    registry; that table is ignored, everything else is the machine's config."""
    path = Path(home if home is not None else cdp_home()) / CONFIG_FILE
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def machine_backend(home: Optional[Path] = None) -> str:
    """Which `WorkspaceStore` this machine uses. Chosen once, in
    `CDP_HOME/config.toml`; default `"sqlite"`."""
    return str(read_config(home).get("backend", "sqlite"))


def machine_postgres_config(home: Optional[Path] = None) -> Optional[Dict[str, str]]:
    pg = read_config(home).get("postgres")
    if not isinstance(pg, dict):
        return None
    return {"dsn": pg.get("dsn"), "schema": pg.get("schema")}


# ---------------------------------------------------------------- .cdp.toml


def _read_team_config(repo: Path) -> dict:
    """`.cdp.toml` walking up from `repo`, if a team has opted in to one."""
    current = Path(repo).resolve()
    for candidate in [current] + list(current.parents):
        config = candidate / TEAM_CONFIG_FILE
        if config.is_file():
            try:
                return tomllib.loads(config.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
    return {}


def check_team_config(repo: Path) -> None:
    """Reject the keys that moved to `CDP_HOME/config.toml`, loudly: a silently
    ignored `backend = "postgres"` would put a team's scans in the wrong place."""
    config = _read_team_config(repo)
    gone = [k for k in REMOVED_TEAM_KEYS if k in config]
    if gone:
        raise CdpError(
            ".cdp.toml key(s) %s are no longer read: CDP keeps one store per machine. "
            "Set the backend in %s instead (`backend = ...`, `[postgres]`); a store "
            "location is `CDP_HOME`." % (", ".join(gone), cdp_home() / CONFIG_FILE)
        )


def team_excludes(repo: Path) -> List[str]:
    """`.cdp.toml`'s `exclude` array -- directory-name segments a team wants
    excluded from every scan of this repo, in addition to (never instead of)
    `inventory.DEFAULT_EXCLUDES`. E.g.:

        exclude = [".idea-shared-notes"]
    """
    exclude = _read_team_config(repo).get("exclude")
    return [str(x) for x in exclude] if isinstance(exclude, list) else []
