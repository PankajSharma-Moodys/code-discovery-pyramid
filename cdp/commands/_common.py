"""Helpers shared by every command file: location flags, the per-repo lock."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from .. import lock as lock_mod
from ..session import open_store, paths_for, resolve_backend
from ..store import SqliteStore
from typing import Iterable, Optional

from ..util import CdpError


@dataclass(frozen=True)
class Spec:
    """A command's documentation, as data: the README command table is
    generated from it (`scripts/gen_readme.py`). `usage` is what follows `cdp`."""

    group: str
    usage: str
    what: str
    next: str


def paths_from_args(args) -> "Paths":
    """The `--repo` / `--state-dir` flags, resolved by the session engine."""
    return paths_for(getattr(args, "repo", "."), getattr(args, "state_dir", None))


def locked(shared: bool, timeout_s: float = lock_mod.DEFAULT_TIMEOUT_S, scope: Optional[str] = None):
    """Decorator: take the per-repo lock (`cdp/lock.py`) for this command's
    entire body before it touches the store, release it on any exit path.

    Resolves `paths`/backend kind itself, independently of whatever the
    wrapped `cmd_*` does with `paths_from_args(args)`/`open_store(paths)` -- both are
    pure functions of `args`, so computing them twice is cheap and keeps this
    decorator a pure wrapper that never has to reach into the function body.
    `shared=True` (read-consistency only: query/docs/status/diff/export/
    verify/doctor) lets concurrent readers proceed; `shared=False` (anything
    that appends a patch, writes an artifact, moves the snapshot pointer, or
    touches task/rollback state) blocks every other locked command, reader
    or writer alike, for as long as this one runs.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(args):
            paths = paths_from_args(args)
            kind, pg = resolve_backend(paths.state)
            db = getattr(args, "db", None)
            if db:
                existing_db(db)  # before the lock: a wrong path must create nothing
            if db and kind != "postgres":
                # `--db` names the store: the lock is that store's (kept beside it), not the machine home's
                paths = SimpleNamespace(state=Path(db).expanduser().resolve().parent, repo_id=paths.repo_id)
            with lock_mod.repo_lock(paths, kind, pg, shared=shared, timeout_s=timeout_s, scope=scope):
                return func(args)

        return wrapper

    return decorator


def existing_db(path) -> Path:
    """`--db PATH` names an existing store. A wrong path is an error: opening it would
    silently create an empty store and report on that instead."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise CdpError("--db %s: %s -- it must be an existing index.db "
                       "(omit --db to use the machine store)"
                       % (path, "is a directory" if p.is_dir() else "no such file"))
    return p.resolve()


def open_link_store(args, paths, command: str, writable: bool):
    """One way every `link` subcommand opens its store: `--db PATH` (must exist), else the
    machine store. Read-only commands open it read-only, so they cannot change a byte of it.
    Raises unless the backend can hold link data."""
    if getattr(args, "db", None):
        store = SqliteStore(existing_db(args.db), readonly=not writable)
    else:
        store = open_store(paths, readonly=not writable)
    if not store.supports_link_edges():
        store.close()
        raise CdpError("%s cannot back `cdp link %s` -- needs the sqlite backend (pass --db, or set "
                       "`backend = \"sqlite\"` in CDP_HOME/config.toml)" % (type(store).__name__, command))
    return store


def outcome_code(ok: int, failed: int) -> int:
    """The exit code of a command that fans work out: 0 when nothing failed (or there was
    nothing to do), 3 when some of it failed, 1 when all of it did."""
    if not failed:
        return 0
    return 1 if not ok else 3


def require_choice(value, choices: Iterable, what: str, flag: str):
    """Error (never a silent no-op) when `value` is not one of `choices`; lists them."""
    valid = sorted(set(choices), key=str)
    if value in valid:
        return value
    import difflib

    near = difflib.get_close_matches(str(value), [str(c) for c in valid], n=2)
    shown = ", ".join(str(c) for c in valid[:12]) + (" ... (%d total)" % len(valid) if len(valid) > 12 else "")
    raise CdpError("%s: no %s %r%s. Valid: %s" % (flag, what, value, " (did you mean %s?)" % " or ".join(near) if near else "",
                                                  shown or "none"))


def require_lesson_cut(trajectory, version: Optional[int], flag: str = "--lessons") -> None:
    """A pinned `--lessons N` must name a cut that exists."""
    if version is None:
        return
    have = trajectory.lesson_versions()
    if version not in have:
        raise CdpError("%s %d: no such lesson-set cut. %s" % (
            flag, version, ("Cuts: %s" % ", ".join("v%d" % v for v in have)) if have
            else "No cut exists yet (`cdp lessons cut` makes one)"))
