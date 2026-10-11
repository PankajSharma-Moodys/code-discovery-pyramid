"""`cdp install`."""

from __future__ import annotations

from .._common import Spec
from ... import hook as hook_mod, install as install_mod
from ...util import CdpError, SKILL_ROOT
from pathlib import Path


SPEC = Spec(
    group='setup',
    usage='install <repo> [--self] [--framework {claude-code,langgraph,adk,none}] [--hook] [--harness] [--strict] [--agents-md] [--remove-harness]',
    what='Copies the skill into another repository (and, by default, the `cdp-leaf` Claude Code agent). Writes nothing else unless asked: `--harness` adds the Claude Code hooks + MCP server, `--agents-md` adds AGENTS.md.',
    next='next: `scan --repo <target>` (printed for you). tip: `--harness` adds the Claude Code hooks (a nudge, never a block; `--strict` to deny) + MCP server (`githook install` is what auto-refreshes on commit, pull and rebase); `--framework {langgraph,adk}` for non-Claude-Code leaves.',
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
    i.add_argument("--harness", action="store_true",
                   help="one-step Claude Code setup: a nudge on the first source read/search "
                        "(it never blocks; add --strict for the denying gate), a SessionStart "
                        "hook that refreshes the index and shows its status, a PostToolUse hook "
                        "that points at the index after an empty search, and the MCP server in "
                        ".mcp.json (claude-code only)")
    i.add_argument("--agents-md", action="store_true",
                   help="also write AGENTS.md at the repository root (read by Cursor, Codex, "
                        "Copilot, Aider); never overwrites an existing one. Off by default: it "
                        "adds a file to the repository")
    i.add_argument("--remove-harness", action="store_true",
                   help="remove everything --harness / --hook added to settings.json and "
                        ".mcp.json; copied skill files stay")
    i.add_argument("--strict", action="store_true",
                   help="block instead of nudging. With --harness: install the denying gate "
                        "(a recursive grep/find, or whole-file Read, the index answers is "
                        "denied once with the answer). With --hook alone: block the first "
                        "source read of a session when the index is fresh and its coverage "
                        "fraction is at least %.2f" % hook_mod.STRICT_MIN_COVERAGE)
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

    if getattr(args, "remove_harness", False):
        extra = [f for f, on in (("--hook", args.hook), ("--harness", args.harness), ("--strict", args.strict),
                                 ("--agents-md", args.agents_md)) if on]
        if extra:
            raise CdpError("--remove-harness only removes; it cannot be combined with %s" % ", ".join(extra))
        for line in install_mod.remove_harness(target):
            print(line)
        return 0

    framework = getattr(args, "framework", "claude-code")
    harness = getattr(args, "harness", False)
    hook = getattr(args, "hook", False) or harness
    if hook and framework != "claude-code":
        raise CdpError("--hook/--harness set up Claude Code; "
                        "they do not apply to --framework %s" % framework)

    strict = getattr(args, "strict", False)
    if strict and not hook:
        raise CdpError("--strict applies to --hook or --harness (it chooses blocking over the nudge)")
    install_mod.install(target, framework=framework, hook=hook, strict=strict, harness=harness,
                        agents_md=getattr(args, "agents_md", False), say=print)
    return 0
