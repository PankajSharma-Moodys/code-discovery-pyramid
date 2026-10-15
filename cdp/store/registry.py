"""Machine home, repo identity and `.cdp.toml` (Phase 2).

**One store per machine.** Everything CDP keeps lives under `CDP_HOME`
(default `~/.cdp`): `index.db` holds every repo, snapshot and link; `work/<repo>/`
holds the files an agent session hands over (inbox, prompts, rendered docs).
No file is written into the working tree of the folder being scanned (`git status`
stays clean): the one thing written under the repo is `.git/cdp-identity`, a UUID
inside `.git/` that git does not track and that stays. A `CDP_HOME` inside the
repo is refused. `CDP_HOME` is the one override, for CI and tests; `--state-dir`
is an alias for it.

**Repo identity is never the filesystem path** — a path is exactly what two
clones of the same repo do not share. Order:

    declared id (`.cdp-id` in the scanned folder, a one-line opt-in file)
    -> what this history was first known as: `CDP_HOME/identity-aliases.json` (`root:<oldest root
       commit>` -> identity: a remote-less copy that lost its marker finds the old identity), and
       `<common git dir>/cdp-identity`:
       its normalised origin remote, else a UUID (so `git remote add` later changes nothing)
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

import json
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


def check_home_outside_repo(home: Path, repo: Path) -> None:
    """A store inside the scanned repo would show up in `git status` (and get indexed)."""
    top, _ = git_root(repo)
    root = (top or Path(repo)).resolve()
    home = Path(home).resolve()
    if home == root or root in home.parents:
        raise CdpError(
            "CDP_HOME (%s) is inside the repository being scanned (%s): its files would appear "
            "in `git status`. Point CDP_HOME (or --state-dir) outside the repo."
            % (home, root)
        )


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


def _identity_marker(repo: Path) -> Tuple[Path, bool]:
    """`(marker file, whether its directory exists)`: kept in the repo's *common* git dir, so
    every linked worktree of one repo shares it (`.git` is a file, not a directory, in a worktree)."""
    common = (_git_once(repo, "rev-parse", "--git-common-dir") or "").strip()
    git_dir = (repo / common).resolve() if common else repo / ".git"
    return git_dir / "cdp-identity", git_dir.is_dir()


def _root_identity(root: Path) -> str:
    """Declared id, else what this git repo was first known as: its normalised origin remote,
    or a fresh UUID. The first answer is written to the common git dir and kept, so adding or
    changing `origin` later does not orphan the snapshots already stored under the old identity."""
    declared = _declared_id(root)
    if declared:
        return declared
    marker, writable = _identity_marker(root)
    if marker.is_file():
        existing = marker.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    alias = _root_commit_alias(root)
    identity = _origin_remote(root) or _alias_lookup(alias) or str(uuid.uuid4())
    if writable:
        marker.write_text(identity + "\n", encoding="utf-8")
    _alias_remember(alias, identity)
    return identity


def _root_commit_alias(root: Path) -> Optional[str]:
    """`root:<oldest root commit>`: what a copy of this history shares even when it has lost
    `.git/cdp-identity`. Used only when there is no origin remote to name the repo (an origin is
    a stronger statement of who the repo is than a shared first commit, which forks also have). A shallow clone's boundary
    commit is a different one, so it simply finds no alias."""
    out = run_git(root, "rev-list", "--max-parents=0", "HEAD")
    roots = sorted(out.split()) if out else []
    return "root:" + roots[0] if roots else None


def remember_alias(repo: Path) -> None:
    """Called by a scan once the machine home exists: records `root:<sha>` -> this repo's identity."""
    top, _ = git_root(Path(repo))
    if top is not None:
        _alias_remember(_root_commit_alias(top), _root_identity(top))


def _alias_file() -> Path:
    return cdp_home() / "identity-aliases.json"


def _alias_lookup(alias: Optional[str]) -> Optional[str]:
    """The identity first recorded for this root commit in this machine's store, if any."""
    if not alias:
        return None
    try:
        return json.loads(_alias_file().read_text(encoding="utf-8")).get(alias)
    except (OSError, ValueError, AttributeError):
        return None


def _alias_remember(alias: Optional[str], identity: str) -> None:
    """First writer wins; only once the machine home exists (a bare `query` creates nothing)."""
    path = _alias_file()
    if not alias or not path.parent.is_dir() or _alias_lookup(alias):
        return
    try:
        known = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        known = {}
    known.setdefault(alias, identity)
    tmp = path.with_name(".identity-aliases.%d.tmp" % os.getpid())
    tmp.write_text(json.dumps(known, sort_keys=True, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _common_dir(repo: Path) -> Optional[Path]:
    common = (run_git(repo, "rev-parse", "--git-common-dir") or "").strip()
    return (repo / common).resolve() if common else None


def same_repository(a: Path, b: Path) -> bool:
    """Whether two folders are checkouts (worktrees) of one git repository, at the same
    place below its root: they share a common git dir."""
    common_a, common_b = _common_dir(Path(a)), _common_dir(Path(b))
    if common_a is None or common_b is None:
        return Path(a).resolve() == Path(b).resolve()
    return common_a == common_b and git_root(Path(a))[1] == git_root(Path(b))[1]


_GIT_ANSWERS: Dict[Tuple[str, Tuple[str, ...]], Optional[str]] = {}


def _git_once(repo: Path, *args: str) -> Optional[str]:
    """`run_git`, asked once per command: where a repo's root and git dir are does not change while one
    CLI command or MCP call runs, and a query asked it 6 times over (12 subprocesses, ~0.2 s)."""
    key = (str(repo), args)
    if key not in _GIT_ANSWERS:
        _GIT_ANSWERS[key] = run_git(repo, *args)
    return _GIT_ANSWERS[key]


def clear_git_answers() -> None:
    """Called as each CLI command and MCP call starts, so a long-running server never reuses an answer."""
    _GIT_ANSWERS.clear()


def git_root(repo: Path) -> Tuple[Optional[Path], str]:
    """`(git toplevel, path of repo below it)`; `(None, "")` outside git."""
    top = _git_once(repo, "rev-parse", "--show-toplevel")
    if not top or not top.strip():
        return None, ""
    prefix = (_git_once(repo, "rev-parse", "--show-prefix") or "").strip().strip("/")
    return Path(top.strip()), prefix


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


def checkout_key(repo: Path) -> str:
    """Names one checkout of a repo: its git toplevel (a worktree and a local
    clone each have their own); "" outside git, where the identity is the path."""
    top, _ = git_root(repo)
    return hashlib.sha256(str(top.resolve()).encode()).hexdigest()[:8] if top else ""


def snapshot_checkout_key(repo: Path) -> str:
    """The checkout a snapshot is recorded against (what lets a scan drop the snapshots it
    supersedes): `checkout_key`, or for a directory outside git a key of its path, so a plain
    directory's old scans are pruned like a worktree's dirty ones."""
    key = checkout_key(repo)
    return key or "p" + hashlib.sha256(str(Path(repo).resolve()).encode()).hexdigest()[:7]


def work_dir_of(home: Path, repo: Path) -> Path:
    return work_dir(home, repo_identity(repo), checkout_key(repo))


def work_dir(home: Path, repo_id: str, checkout: str = "") -> Path:
    """Where one checkout's inbox, prompts and rendered docs live."""
    return Path(home) / "work" / (repo_slug(repo_id) + ("-" + checkout if checkout else ""))


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


from ..guide_kinds import FORMATS as QUERY_FORMATS, VIEWS as QUERY_VIEWS  # noqa: E402  (pure data module)


def team_query_config(repo: Path) -> Dict:
    """`.cdp.toml`'s `[query]` section, validated: `max_tokens`, `default_view`, `view` (per kind),
    `format` (per view) and `drop_fields` (per kind). A bad value is an error, not a silent default:
    the team believes the dial is set."""
    raw = _read_team_config(repo).get("query")
    if raw is None:
        return {}
    where = "%s [query]" % TEAM_CONFIG_FILE
    if not isinstance(raw, dict):
        raise CdpError("%s must be a table" % where)
    known = ("max_tokens", "default_view", "view", "format", "drop_fields")
    extra = [k for k in raw if k not in known]
    if extra:
        raise CdpError("%s: unknown key(s) %s (known: %s)" % (where, ", ".join(extra), ", ".join(known)))
    out: Dict = {}
    if "max_tokens" in raw:
        n = raw["max_tokens"]
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise CdpError("%s: max_tokens must be a non-negative integer (0 = no cap)" % where)
        out["max_tokens"] = n
    if "default_view" in raw:
        if raw["default_view"] not in QUERY_VIEWS:
            raise CdpError("%s: default_view must be one of %s" % (where, ", ".join(QUERY_VIEWS)))
        out["default_view"] = raw["default_view"]
    for key, allowed in (("view", QUERY_VIEWS), ("format", QUERY_FORMATS)):
        if key in raw:
            table = raw[key]
            if not isinstance(table, dict) or not all(isinstance(v, str) and v in allowed for v in table.values()):
                raise CdpError("%s: %s must map a name to one of %s" % (where, key, ", ".join(allowed)))
            out[key] = dict(table)
    if "drop_fields" in raw:
        table = raw["drop_fields"]
        if not isinstance(table, dict) or not all(
                isinstance(v, list) and all(isinstance(f, str) for f in v) for v in table.values()):
            raise CdpError("%s: drop_fields must map a kind to a list of field names" % where)
        out["drop_fields"] = {k: list(v) for k, v in table.items()}
    return out
