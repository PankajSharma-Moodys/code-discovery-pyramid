"""Copying the skill into another repository and wiring its hook."""

from __future__ import annotations

import shutil

from . import hook as hook_mod
from .store import registry as registry_mod
from .util import CdpError, SKILL_ROOT, read_json, write_json
from pathlib import Path
from typing import Callable, Dict, List


#: Everything that constitutes the distributable skill, relative to SKILL_ROOT.
#
# This is an allow-list rather than a copy-everything-and-ignore, because
# SKILL_ROOT is now the repository root: a `copytree` with an ignore list would
# vendor `.git/`, `.venv/`, `PHASE/` and the design documents into every target
# repository, and would grow silently every time a file is added at the root.
# Naming the members means a new top-level file is *not* shipped until someone
# decides it should be.
#
# `mcp_server/`, `litellm_adapter/`, `agent_adapter/` (Phase 9, 7.1/7.2/7.4)
# are deliberately absent -- they are consumed via `pip install cdp[mcp]` /
# an MCP client config / a LangGraph or ADK agent importing `agent_adapter`,
# never by copying into a target repo's `.claude/skills/`. Not an oversight.
DIST_MEMBERS = ("cdp", "tests", "schema", "agents", "run.py", "SKILL.md")


# `golden` is excluded deliberately: baselines are development artifacts of
# *this* repository, they are large, and `cdp selftest` inside a target repo has
# no use for another repository's blessed output.
DIST_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".cdp", "runs", ".DS_Store", "golden",
)


#: `matcher` is compared as an exact string when it contains only letters,
# digits and `|`, so this fires on exactly these three tools and nothing else.
HOOK_MATCHER = "Read|Grep|Glob"


def copy_distribution(dest: Path) -> None:
    """Materialise the skill tree at `dest`, replacing whatever was there.

    Deterministic and total: the destination afterwards contains exactly
    `DIST_MEMBERS` and nothing else, which is what makes the vendored copy
    comparable byte-for-byte against the source.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for member in DIST_MEMBERS:
        src = SKILL_ROOT / member
        if not src.exists():
            raise CdpError("distribution member missing from source tree: %s" % src)
        if src.is_dir():
            shutil.copytree(src, dest / member, ignore=DIST_IGNORE)
        else:
            shutil.copy2(src, dest / member)


def register_leaf_agent(target: Path, framework: str,
                        say: Callable[..., None] = lambda *a: None) -> None:
    """Point `target` at whatever produces leaf patches for `framework`.

    `claude-code` is the only framework with a file to copy: `.claude/agents/`
    is a Claude Code discovery convention, and `cdp-leaf.md` is meaningless to
    anything else. `langgraph`/`adk` leaves are Python the target repo's own
    graph/agent code imports (`agent_adapter.langgraph_leaf`/`adk_leaf`), so
    -- like `agent_adapter/` itself, which `DIST_MEMBERS` deliberately never
    vendors -- there is nothing to copy; printing the install/import guidance
    is the entire "installation". `none` registers nothing, for repos driving
    leaves purely through `cdp run --wave-all --runner-cmd`.
    """
    if framework == "claude-code":
        agents = target / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        source_agent = SKILL_ROOT / "agents" / "cdp-leaf.md"
        if source_agent.exists():
            shutil.copy2(source_agent, agents / "cdp-leaf.md")
            say("installed %s" % (agents / "cdp-leaf.md"))
    elif framework in ("langgraph", "adk"):
        module = "agent_adapter.%s_leaf" % framework
        say("no files copied for --framework %s -- in %s, run:" % (framework, target))
        say("  pip install cdp[agent]")
        say("  from %s import run_leaf" % module)
    elif framework == "none":
        pass


def install_hook(target: Path, dest: Path, strict: bool = False) -> List[str]:
    """Register the PreToolUse nudge in `<target>/.claude/settings.json`.

    The hook finds the machine store (`CDP_HOME`) and the repo's rows in it
    (`hook.find_state`). It cannot see a scan that has never happened, so that
    case is named here rather than left to a silent no-op.
    """
    import json as json_mod

    notes: List[str] = []
    has_state = hook_mod.has_snapshot(registry_mod.cdp_home(), registry_mod.repo_identity(target))
    if not has_state:
        notes.append(
            "note      no scan of %s yet, so the hook will no-op until you run:\n"
            "            python3 %s scan --repo %s"
            % (target, dest / "run.py", target)
        )

    settings_path = target / ".claude" / "settings.json"
    settings: Dict = {}
    if settings_path.exists():
        try:
            settings = read_json(settings_path)
        except ValueError:
            raise CdpError(
                "%s is not valid JSON; refusing to overwrite it. Fix or move it, "
                "then re-run with --hook." % settings_path
            )
    if not isinstance(settings, dict):
        raise CdpError("%s does not contain a JSON object" % settings_path)

    # Flags live in the command string, not an `args` field: with `args` present
    # Claude Code spawns `command` as a bare executable (no shell), so
    # "python3 /path/hook.py" fails with ENOENT.
    base = "python3 %s" % (dest / "cdp" / "hook.py")
    command = base + (" --strict" if strict else "")
    entry = {"type": "command", "command": command}
    hooks = settings.setdefault("hooks", {})
    groups = hooks.setdefault("PreToolUse", [])
    # Idempotent: drop any earlier CDP entry wherever it sits (an older install
    # used a narrower matcher or the `args` form), then add the current one.
    for group in groups:
        if isinstance(group, dict) and isinstance(group.get("hooks"), list):
            group["hooks"] = [h for h in group["hooks"]
                              if not (isinstance(h, dict)
                                      and str(h.get("command", "")).startswith(base))]
    groups[:] = [g for g in groups if not (isinstance(g, dict) and g.get("hooks") == [])]
    for group in groups:
        if isinstance(group, dict) and group.get("matcher") == HOOK_MATCHER:
            group.setdefault("hooks", []).append(entry)
            break
    else:
        groups.append({"matcher": HOOK_MATCHER, "hooks": [entry]})

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(settings_path, settings)
    notes.insert(0, "hook      PreToolUse on %s -> %s" % (HOOK_MATCHER, settings_path))
    if strict:
        notes.insert(1, "          strict mode: blocks the first source read of a session "
                        "when the index is fresh\n          and covers at least %d%% of the "
                        "repo; degrades to the nudge otherwise, and never\n          blocks "
                        "(or nudges) twice in one session."
                        % int(hook_mod.STRICT_MIN_COVERAGE * 100))
    else:
        notes.insert(1, "          it fires only on files whose inventory role is 'source', "
                        "at most once\n          per session, and no-ops silently when "
                        "inventory.head != git HEAD.")
    notes.append("          python3 %s --explain   to see what it injects and why"
                 % (dest / "cdp" / "hook.py"))
    return notes


SESSION_MATCHER = "startup|resume|clear|compact"


def _load_json_object(path: Path, hint: str) -> Dict:
    if not path.exists():
        return {}
    try:
        data = read_json(path)
    except ValueError:
        raise CdpError("%s is not valid JSON; refusing to overwrite it. %s" % (path, hint))
    if not isinstance(data, dict):
        raise CdpError("%s does not contain a JSON object" % path)
    return data


def install_session_hook(target: Path, dest: Path) -> List[str]:
    """Register the SessionStart hook: refresh the index, show a short status."""
    settings_path = target / ".claude" / "settings.json"
    settings = _load_json_object(settings_path, "Fix or move it, then re-run.")
    command = "python3 %s --session-start" % (dest / "cdp" / "hook.py")
    groups = settings.setdefault("hooks", {}).setdefault("SessionStart", [])
    # Replace, not skip: an older install registered a narrower matcher
    # (`startup|resume`), which never fires after `/clear`.
    for group in groups:
        if isinstance(group, dict) and isinstance(group.get("hooks"), list):
            group["hooks"] = [h for h in group["hooks"]
                              if not (isinstance(h, dict) and h.get("command") == command)]
    groups[:] = [g for g in groups if not (isinstance(g, dict) and g.get("hooks") == [])]
    groups.append({"matcher": SESSION_MATCHER,
                   "hooks": [{"type": "command", "command": command, "timeout": 120}]})
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(settings_path, settings)
    return ["hook      SessionStart (%s) -> refresh + status, in %s" % (SESSION_MATCHER, settings_path)]


def install_mcp(target: Path) -> List[str]:
    """Register the `cdp` MCP server in `<target>/.mcp.json`.

    `mcp_server/` is not vendored into the target (see `DIST_MEMBERS`), so the
    server runs from this checkout via PYTHONPATH.
    """
    mcp_path = target / ".mcp.json"
    config = _load_json_object(mcp_path, "Fix or move it, then re-run.")
    config.setdefault("mcpServers", {})["cdp"] = {
        "command": "python3",
        "args": ["-m", "mcp_server.server"],
        "env": {"PYTHONPATH": str(SKILL_ROOT)},
    }
    write_json(mcp_path, config)
    return ["mcp       server `cdp` (cdp_query, cdp_scan, cdp_status) -> %s" % mcp_path]


def remove_harness(target: Path) -> List[str]:
    """Undo `install_hook` / `install_session_hook` / `install_mcp`; leaves the
    copied skill files and every non-CDP entry alone."""
    notes: List[str] = []
    settings_path = target / ".claude" / "settings.json"
    if settings_path.exists():
        settings = _load_json_object(settings_path, "Fix or move it, then re-run.")
        hooks = settings.get("hooks")
        removed = 0
        if isinstance(hooks, dict):
            for event in list(hooks):
                kept_groups = []
                for group in hooks[event]:
                    handlers = group.get("hooks", []) if isinstance(group, dict) else []
                    kept = [h for h in handlers
                            if not (isinstance(h, dict) and "cdp/hook.py" in str(h.get("command", "")))]
                    removed += len(handlers) - len(kept)
                    if kept or not isinstance(group, dict):
                        if isinstance(group, dict):
                            group["hooks"] = kept
                        kept_groups.append(group)
                if kept_groups:
                    hooks[event] = kept_groups
                else:
                    del hooks[event]
            if not hooks:
                del settings["hooks"]
        write_json(settings_path, settings)
        notes.append("removed   %d CDP hook(s) from %s" % (removed, settings_path))
    mcp_path = target / ".mcp.json"
    if mcp_path.exists():
        config = _load_json_object(mcp_path, "Fix or move it, then re-run.")
        servers = config.get("mcpServers")
        if isinstance(servers, dict) and servers.pop("cdp", None) is not None:
            if not servers:
                del config["mcpServers"]
            write_json(mcp_path, config)
            notes.append("removed   MCP server `cdp` from %s" % mcp_path)
    return notes


def install(
    target: Path,
    *,
    framework: str = "claude-code",
    hook: bool = False,
    strict: bool = False,
    harness: bool = False,
    say: Callable[..., None] = lambda *a: None,
) -> Path:
    """Copy the skill into `target`'s `.claude/skills/cdp/`, register the leaf agent for
    `framework`, and optionally wire the refresh hook. Returns the skill dir."""
    dest = target / ".claude" / "skills" / "cdp"
    copy_distribution(dest)
    say("installed %s" % dest)

    register_leaf_agent(target, framework, say)

    # Tier-0 (7.9): a root-level AGENTS.md works for any assistant, hook-less
    # or not — Cursor, Codex, Copilot, Aider all read it. Placed at the
    # target's root, not inside dest, since that is where those tools look.
    # Never overwritten: a repo's own AGENTS.md is the operator's file.
    agents_md = target / "AGENTS.md"
    source_agents_md = SKILL_ROOT / "AGENTS.md"
    if agents_md.exists():
        say("kept      %s (already present, not overwritten)" % agents_md)
    elif source_agents_md.exists():
        shutil.copy2(source_agents_md, agents_md)
        say("wrote     %s" % agents_md)
    if hook or harness:
        for line in install_hook(target, dest, strict=strict):
            say(line)
    if harness:
        for line in install_session_hook(target, dest) + install_mcp(target):
            say(line)
    say("try       python3 %s scan --repo %s"
          % (dest / "run.py", target))
    say("tip       --hook to auto-refresh state on every commit, "
          "--framework {langgraph,adk} for non-Claude-Code leaves")
    return dest
