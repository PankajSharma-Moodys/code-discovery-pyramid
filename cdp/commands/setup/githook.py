"""`cdp githook`."""

from __future__ import annotations

from pathlib import Path

from .._common import Spec, paths_from_args
from ... import githooks as githooks_mod


SPEC = Spec(
    group='setup',
    usage='githook install \\| uninstall',
    what='Installs/uninstalls git `post-commit`, `post-checkout`, `post-merge` and `post-rewrite` hooks that auto-run `cdp refresh` (commit, branch switch, pull, rebase; one install serves every worktree).',
    next='—',
)


def register(add) -> None:
    gh = add("githook", "install/uninstall post-commit, post-checkout, post-merge & post-rewrite hooks "
                        "that auto-run `cdp refresh` (M3.8, opt-in, off by default)")
    gh.add_argument("action", choices=["install", "uninstall"])
    gh.set_defaults(func=cmd_githook)


def cmd_githook(args) -> int:
    """M3.8. Distinct from `install --hook` above: that installs the
    PreToolUse nudge into `.claude/settings.json`; this installs real git
    `post-commit`/`post-checkout` hooks that call `cdp refresh`."""
    repo = paths_from_args(args).repo
    if args.action == "install":
        state_dir = getattr(args, "state_dir", None)
        lines = githooks_mod.install(repo, Path(state_dir).expanduser().resolve() if state_dir else None)
    else:
        lines = githooks_mod.uninstall(repo)
    for line in lines:
        print(line)
    return 0
