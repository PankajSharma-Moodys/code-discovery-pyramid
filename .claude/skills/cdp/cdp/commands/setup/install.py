"""`cdp install`."""

from __future__ import annotations

from .._common import Spec
from ... import hook as hook_mod, install as install_mod
from ...util import CdpError, SKILL_ROOT
from pathlib import Path


SPEC = Spec(
    group='setup',
    usage='install <repo> [--self] [--framework {claude-code,langgraph,adk,none}] [--hook]',
    what='Copies the skill into another repository (and, by default, the `cdp-leaf` Claude Code agent).',
    next='next: `scan --repo <target>` (printed for you). tip: `--hook` to auto-refresh on every commit, `--framework {langgraph,adk}` for non-Claude-Code leaves.',
)


def register(add) -> None:
    i = add("install", "copy this skill into another repository")
    i.add_argument("target", nargs="?", help="repository to install into")
    i.add_argument("--self", action="store_true",
                   help="refresh this repository's own vendored .claude/skills/cdp copy")
    i.add_argument("--framework", choices=["claude-code", "langgraph", "adk", "none"],
                   default="claude-code",
                   help="which agent framework will drive the leaf wave loop "
                        "(default claude-code); langgraph/adk print pip-install "
                        "and import guidance instead of writing .claude/agents/, "
                        "none skips agent registration entirely")
    i.add_argument("--hook", action="store_true",
                   help="also install the PreToolUse nudge (claude-code only)")
    i.add_argument("--strict", action="store_true",
                   help="with --hook, block the first source read of a session "
                        "instead of nudging, when the index is fresh and its "
                        "coverage fraction is at least %.2f" % hook_mod.STRICT_MIN_COVERAGE)
    i.set_defaults(func=cmd_install)


def cmd_install(args) -> int:
    """Copy the skill into another repository. This is the portability story.

    One directory, no dependencies, no build step. `.claude/skills/cdp/` in the
    target is everything CDP is.

    `--self` refreshes this repository's own vendored copy. The vendored tree is
    *generated*, never hand-edited: `tests/test_distribution.py` asserts it is
    byte-identical to the source, so an edit made in the wrong place fails the
    build instead of silently diverging.
    """
    if getattr(args, "self", False):
        if args.target:
            raise CdpError("--self takes no target (it refreshes this repository)")
        target = SKILL_ROOT
    else:
        if not args.target:
            raise CdpError("install needs a target repository, or --self")
        target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        raise CdpError("not a directory: %s" % target)

    framework = getattr(args, "framework", "claude-code")
    hook = getattr(args, "hook", False)
    if hook and framework != "claude-code":
        raise CdpError("--hook installs a Claude Code PreToolUse nudge; "
                        "it does not apply to --framework %s" % framework)

    install_mod.install(target, framework=framework, hook=hook,
                        strict=getattr(args, "strict", False), say=print)
    return 0
