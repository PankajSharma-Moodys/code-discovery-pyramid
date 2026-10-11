"""`cdp githook`."""

from __future__ import annotations

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
    fn = githooks_mod.install if args.action == "install" else githooks_mod.uninstall
    for line in fn(repo):
        print(line)
    return 0
