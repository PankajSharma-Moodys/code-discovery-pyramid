"""`cdp install`."""

from __future__ import annotations

from .._common import Spec
from ... import install as install_mod
from ...util import CdpError, SKILL_ROOT
from pathlib import Path


SPEC = Spec(
    group='setup',
    usage='install <repo> [--self] [--framework {claude-code,langgraph,adk,none}] [--hook] [--harness] [--strict] [--block-all] [--agents-md] [--claude-md] [--allow-mcp] [--priority] [--remove-harness]',
    what='Copies the skill into another repository (and, by default, the `cdp-leaf` Claude Code agent). Writes nothing else unless asked: `--harness` adds the Claude Code hooks + MCP server, `--agents-md` adds AGENTS.md, `--claude-md` a CDP rule block in CLAUDE.md, `--allow-mcp` the `mcp__cdp__*` permission, `--priority` all of those plus the strict gate.',
    next='next: `scan --repo <target>` (printed for you). tip: `--harness` adds the Claude Code hooks (a nudge that names the exact cdp_query, never a block; `--strict` to answer greps from the index; `--priority` for CDP-first in one flag) + MCP server (`githook install` is what auto-refreshes on commit, pull and rebase); `--framework {langgraph,adk}` for non-Claude-Code leaves.',
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
                   help="one-step Claude Code setup: a nudge that names the exact cdp_query for "
                        "the search/read the model reached for (it never blocks; add --strict for the gate), a SessionStart "
                        "hook that refreshes the index and shows its status, a PostToolUse hook "
                        "that points at the index after an empty search, and the MCP server in "
                        ".mcp.json (claude-code only)")
    i.add_argument("--agents-md", action="store_true",
                   help="also write AGENTS.md at the repository root (read by Cursor, Codex, "
                        "Copilot, Aider); never overwrites an existing one. Off by default: it "
                        "adds a file to the repository")
    i.add_argument("--claude-md", action="store_true",
                   help="write (or refresh) a marked CDP rule block in the target's CLAUDE.md: locate code with "
                        "cdp_query first, plus the question -> kind table (generated from the guide). Creates the "
                        "file if absent; never touches text outside the markers. Off by default")
    i.add_argument("--allow-mcp", action="store_true",
                   help="add `mcp__cdp__*` to permissions.allow in .claude/settings.json so the cdp MCP tools run "
                        "without a permission prompt (cdp_query/status/help read the index; cdp_scan/refresh/link "
                        "write only the index store; nothing edits the repository). Off by default")
    i.add_argument("--priority", action="store_true",
                   help="CDP-first preset = --harness --strict --claude-md --allow-mcp")
    i.add_argument("--remove-harness", action="store_true",
                   help="remove everything --harness / --hook / --claude-md / --allow-mcp / --agents-md added: hooks, the MCP "
                        "server entry, the CLAUDE.md block, the permission (only if install added it), an "
                        "AGENTS.md still identical to the one written; copied skill files stay")
    i.add_argument("--block-all", action="store_true", dest="block_all",
                   help="implies --strict, and denies EVERY Grep/Glob and pure grep/rg/find search in an indexed "
                        "source dir, every time, naming the cdp_query to use instead (Reads still run)")
    i.add_argument("--strict", action="store_true",
                   help="block instead of nudging. With --harness: install the denying gate "
                        "(a recursive grep/find, or whole-file Read, the index answers is "
                        "answered from the index and denied once; anything it cannot fully answer "
                        "runs; any cdp_query switches it off for the session). --hook --strict "
                        "installs the same gate")
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
    # The store's own lock file, or its db beside a `work/` dir -- and never a git checkout: an app repo's
    # own index.db (even next to a work/ folder) is no marker.
    if not (target / ".git").exists() and ((target / "index.db.migrate").exists()
                                            or ((target / "index.db").exists() and (target / "work").is_dir())):
        raise CdpError("%s is a CDP state directory, not a repository; install into the repository "
                       "(the index store is never a target)" % target)

    if getattr(args, "remove_harness", False):
        extra = [f for f, on in (("--hook", args.hook), ("--harness", args.harness), ("--strict", args.strict),
                                 ("--agents-md", args.agents_md), ("--claude-md", args.claude_md),
                                 ("--allow-mcp", args.allow_mcp), ("--priority", args.priority)) if on]
        if extra:
            raise CdpError("--remove-harness only removes; it cannot be combined with %s" % ", ".join(extra))
        for line in install_mod.remove_harness(target):
            print(line)
        return 0

    framework = getattr(args, "framework", "claude-code")
    priority = getattr(args, "priority", False)
    harness = getattr(args, "harness", False) or priority
    hook = getattr(args, "hook", False) or harness
    if hook and framework != "claude-code":
        raise CdpError("--hook/--harness set up Claude Code; "
                        "they do not apply to --framework %s" % framework)

    block_all = getattr(args, "block_all", False)
    strict = getattr(args, "strict", False) or priority or block_all
    if strict and not hook:
        raise CdpError("--strict applies to --hook or --harness (it chooses blocking over the nudge)")
    install_mod.install(target, framework=framework, hook=hook, strict=strict, harness=harness,
                        agents_md=getattr(args, "agents_md", False), claude_md=getattr(args, "claude_md", False),
                        allow_mcp=getattr(args, "allow_mcp", False), priority=priority, block_all=block_all, say=print)
    return 0
