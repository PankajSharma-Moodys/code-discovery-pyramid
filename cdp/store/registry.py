"""Store resolution and repo identity (M2.6, `PHASE/phase_2_plan.md` 2.3).

**Repo identity is never the filesystem path** — a path is exactly what two
clones of the same repo do not share, and what a moved repo does not keep
(`RESEARCH_GRAPHIFY.md §12.2`; the sharp edge in `ARCHITECTURE.md` where a
second scan silently clobbers the first). Order:

    declared id (`.cdp-id` at the repo root, a one-line opt-in file)
    -> normalised origin remote (`git remote get-url origin`)
    -> a UUID persisted at `<repo>/.git/cdp-identity`

The UUID case is a repo with no remote and no declared id: it survives a
*move* of the repo (the marker lives inside `.git/`, which moves with it) but
not a fresh clone, which is correct — a clone with no remote is, as far as
identity goes, a new and unrelated tree.

**The registry** (`~/.cdp/config.toml`) maps `repo_id -> state path`, written
by `cmd_scan` and read by anything that needs to find a repo's store without
being told where it is — the case `hook.find_state` could not handle before
this milestone, since CDP's default state location is *outside* the repo
(`cli.py`'s module docstring) and a directory walk from inside the repo can
never reach it. `.cdp.toml` (checked into the repo, for a team) is read here
too if present, but nothing in this module writes one — that is a human
decision, not one `scan` should make silently. See `.cdp.toml.example` at the
repo root for every field this module reads (`store`, `backend`, `[postgres]`,
`exclude`), documented and ready to rename and edit.
"""

from __future__ import annotations

import tomllib
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from ..util import run_git

REGISTRY_PATH = Path.home() / ".cdp" / "config.toml"
DECLARED_ID_FILE = ".cdp-id"
TEAM_CONFIG_FILE = ".cdp.toml"


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
    marker = repo / ".git" / "cdp-identity"
    if marker.is_file():
        existing = marker.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    generated = str(uuid.uuid4())
    if marker.parent.is_dir():
        marker.write_text(generated + "\n", encoding="utf-8")
    return generated


def repo_identity(repo: Path) -> str:
    repo = Path(repo)
    return _declared_id(repo) or _origin_remote(repo) or _persisted_uuid(repo)


def _read_team_config(repo: Path) -> dict:
    """`.cdp.toml` walking up from `repo`, if a team has opted in to one.
    Shared by `team_store` and `team_excludes` so the walk-and-parse step
    isn't duplicated between them."""
    current = Path(repo).resolve()
    for candidate in [current] + list(current.parents):
        config = candidate / TEAM_CONFIG_FILE
        if config.is_file():
            try:
                return tomllib.loads(config.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
    return {}


def team_store(repo: Path) -> Optional[Path]:
    store = _read_team_config(repo).get("store")
    return Path(store).expanduser() if store else None


def team_excludes(repo: Path) -> List[str]:
    """`.cdp.toml`'s `exclude` array -- directory-name segments a team wants
    excluded from every scan of this repo, in addition to (never instead of)
    `inventory.DEFAULT_EXCLUDES`. E.g.:

        exclude = [".idea-shared-notes"]
    """
    exclude = _read_team_config(repo).get("exclude")
    return [str(x) for x in exclude] if isinstance(exclude, list) else []


def team_backend(repo: Path) -> str:
    """`.cdp.toml`'s `backend` key -- which `WorkspaceStore` implementation
    `cdp` should construct for this repo. Defaults to `"sqlite"`, today's
    behaviour for a repo with no `.cdp.toml` or one that doesn't name a
    backend."""
    backend = _read_team_config(repo).get("backend", "sqlite")
    return str(backend)


def team_postgres_config(repo: Path) -> Optional[Dict[str, str]]:
    """`.cdp.toml`'s `[postgres]` table (`dsn`, optional `schema`), or `None`
    if absent -- only consulted when `team_backend` is `"postgres"`."""
    pg = _read_team_config(repo).get("postgres")
    if not isinstance(pg, dict):
        return None
    return {"dsn": pg.get("dsn"), "schema": pg.get("schema")}


def register(repo_id: str, state_path: Path) -> None:
    """Record where `repo_id`'s state lives, idempotently."""
    entries = _read_registry()
    entries[repo_id] = str(Path(state_path).resolve())
    _write_registry(entries)


def lookup(repo_id: str) -> Optional[Path]:
    value = _read_registry().get(repo_id)
    return Path(value) if value else None


def resolve_store(repo: Path, env: Optional[str] = None, default: Optional[Path] = None) -> Path:
    """`CDP_STORE` -> `.cdp.toml` walking up -> registry -> `default`.

    `--store`/`--state-dir` and `--in-repo` are handled by the caller as a
    higher-priority override before this is ever reached (`cli.py` `_paths`);
    this is the fallback chain for when neither is given.
    """
    if env:
        return Path(env).expanduser().resolve()
    team = team_store(repo)
    if team is not None:
        return team.resolve()
    found = lookup(repo_identity(repo))
    if found is not None:
        return found
    return Path(default).expanduser().resolve() if default else Path.cwd() / ".cdp"


def _read_registry() -> dict:
    if not REGISTRY_PATH.is_file():
        return {}
    try:
        data = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(data.get("repos", {}))


def _write_registry(entries: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[repos]"]
    for key, value in sorted(entries.items()):
        lines.append("%s = %s" % (_toml_string(key), _toml_string(value)))
    REGISTRY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _toml_string(value: str) -> str:
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')
