"""Helpers shared by every command file: location flags, the per-repo lock."""

from __future__ import annotations

import functools
from dataclasses import dataclass

from .. import lock as lock_mod
from ..session import paths_for, resolve_backend
from typing import Optional


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
            with lock_mod.repo_lock(paths, kind, pg, shared=shared, timeout_s=timeout_s, scope=scope):
                return func(args)

        return wrapper

    return decorator
