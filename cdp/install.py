"""Copying the skill into another repository and wiring its hook."""

from __future__ import annotations

import shutil

from . import hook as hook_mod
from .store import registry as registry_mod
from .util import CdpError, SKILL_ROOT, read_json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


#: Everything that constitutes the distributable skill, relative to SKILL_ROOT.
#
# This is an allow-list rather than a copy-everything-and-ignore, because
# SKILL_ROOT is now the repository root: a `copytree` with an ignore list would
# vendor `.git/`, `.venv/`, `PHASE/` and the design documents into every target
# repository, and would grow silently every time a file is added at the root.
# Naming the members means a new top-level file is *not* shipped until someone
# decides it should be.
#
# `mcp_server/` ships so the `.mcp.json` entry can point inside the target
# (`${CLAUDE_PROJECT_DIR:-.}/.claude/skills/cdp`) instead of at this checkout.
# `litellm_adapter/` and `agent_adapter/` are deliberately absent -- a LangGraph
# or ADK agent imports `agent_adapter`, it is never copied into a target repo's
# `.claude/skills/`. Not an oversight.
DIST_MEMBERS = ("cdp", "mcp_server", "tests", "schema", "agents", "run.py", "SKILL.md")

# What an install into *another* repository copies: everything the skill needs at
# runtime, and no `tests/`. The suite and its fixtures (Java/SQL/Python/C# sources,
# ~2 MB) are development material of this repository; vendored into a target they
# double every `grep -r` match there and bloat the repo. `DIST_MEMBERS` (with tests)
# is only this repository's own `.claude/skills/cdp/` (`install --self`), which
# `tests/test_distribution.py` holds byte-identical to the source. `cdp selftest`
# is therefore repo-only: in a target it says so and exits non-zero.
TARGET_MEMBERS = tuple(m for m in DIST_MEMBERS if m != "tests")


# `golden` is excluded deliberately: baselines are development artifacts of
# *this* repository, they are large, and `cdp selftest` inside a target repo has
# no use for another repository's blessed output.
DIST_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".cdp", "runs", ".DS_Store", "golden",
)
# A target copy also drops every nested `tests/` (`mcp_server/tests/`), not just the top-level member.
TARGET_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".cdp", "runs", ".DS_Store", "golden", "tests",
)


#: `matcher` is compared as an exact string when it contains only letters,
# digits and `|`, so this fires on exactly these three tools and nothing else.
HOOK_MATCHER = "Read|Grep|Glob|Bash"

#: The flags `hook.py` takes when registered as a Claude Code hook.
HOOK_FLAGS = ("--strict", "--gate", "--session-start", "--prompt-submit", "--post-search")


def hook_command(target: Path, dest: Path, flag: str = "") -> str:
    """The hook command to register: a path under `$CLAUDE_PROJECT_DIR`, so the
    settings file is the same on every checkout and machine (J4). Falls back to an
    absolute path when `dest` is not inside `target`."""
    try:
        script = '"$CLAUDE_PROJECT_DIR/%s"' % (dest.relative_to(target) / "cdp" / "hook.py").as_posix()
    except ValueError:
        script = str(dest / "cdp" / "hook.py")
    return "python3 %s" % script + (" " + flag if flag else "")


def cdp_hook_commands(dest: Path, target: Optional[Path] = None) -> frozenset:
    """Every command string the installers below can write for a skill vendored at `dest`:
    the absolute form older installs wrote and, given `target`, the portable one.

    `install_*` and `remove_harness` both match handlers against exactly this set, so a
    user's own hook that merely mentions `cdp/hook.py` is neither replaced nor removed."""
    base = "python3 %s" % (dest / "cdp" / "hook.py")
    commands = [base] + [base + " " + flag for flag in HOOK_FLAGS]
    if target is not None:
        commands += [hook_command(target, dest, flag) for flag in ("",) + HOOK_FLAGS]
    return frozenset(commands)


def _drop_handlers(groups: List, commands) -> int:
    """Remove handlers whose command is in `commands`, and the groups that removal left
    empty (a user's own group that was already empty stays). Returns how many handlers went."""
    removed = 0
    emptied = []
    for group in groups:
        if isinstance(group, dict) and isinstance(group.get("hooks"), list):
            kept = [h for h in group["hooks"]
                    if not (isinstance(h, dict) and h.get("command") in commands)]
            if len(kept) != len(group["hooks"]):
                removed += len(group["hooks"]) - len(kept)
                group["hooks"] = kept
                if not kept:
                    emptied.append(group)
    groups[:] = [g for g in groups if not any(g is e for e in emptied)]
    return removed


#: The hook events `install` writes into `settings.json`.
HOOK_EVENTS = ("PreToolUse", "SessionStart", "UserPromptSubmit", "PostToolUse")


def _write_settings(path: Path, obj: Dict) -> None:
    """Write `obj` keeping its key order: the file is the user's, so installing must not re-sort it."""
    import json as json_mod

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_mod.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _check_shapes(settings: Dict, path: Path) -> None:
    """Refuse a `hooks` / event list of an unexpected type before anything is written."""
    hooks = settings.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        raise CdpError("%s: `hooks` must be an object, found %s; refusing to change it. "
                       "Fix it, then re-run." % (path, type(hooks).__name__))
    for event in HOOK_EVENTS:
        if isinstance(hooks, dict) and hooks.get(event) is not None and not isinstance(hooks[event], list):
            raise CdpError("%s: `hooks.%s` must be a list, found %s; refusing to change it. "
                           "Fix it, then re-run." % (path, event, type(hooks[event]).__name__))


def _event_groups(settings: Dict, event: str) -> List:
    return settings.setdefault("hooks", {}).setdefault(event, [])


def copy_distribution(dest: Path, members: Tuple[str, ...] = DIST_MEMBERS) -> None:
    """Materialise the skill tree at `dest`, replacing whatever was there.

    Deterministic and total: the destination afterwards contains exactly
    `members` (`DIST_MEMBERS` for this repository's own vendored copy,
    `TARGET_MEMBERS` for any other repository) and nothing else, which is what
    makes the vendored copy comparable byte-for-byte against the source.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for member in members:
        src = SKILL_ROOT / member
        if not src.exists():
            raise CdpError("distribution member missing from source tree: %s" % src)
        if src.is_dir():
            shutil.copytree(src, dest / member, ignore=DIST_IGNORE if "tests" in members else TARGET_IGNORE)
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
    settings = _load_json_object(settings_path, "Fix or move it, then re-run with --hook.")
    _check_shapes(settings, settings_path)

    # Flags live in the command string, not an `args` field: with `args` present
    # Claude Code spawns `command` as a bare executable (no shell), so
    # "python3 /path/hook.py" fails with ENOENT.
    command = hook_command(target, dest, "--strict" if strict else "")
    entry = {"type": "command", "command": command}
    groups = _event_groups(settings, "PreToolUse")
    # Idempotent: drop any earlier CDP entry wherever it sits (an older install
    # used a narrower matcher or the `args` form), then add the current one.
    _drop_handlers(groups, cdp_hook_commands(dest, target))
    for group in groups:
        if isinstance(group, dict) and group.get("matcher") == HOOK_MATCHER \
                and isinstance(group.get("hooks"), list):
            group["hooks"].append(entry)
            break
    else:
        groups.append({"matcher": HOOK_MATCHER, "hooks": [entry]})

    _write_settings(settings_path, settings)
    notes.insert(0, "hook      PreToolUse on %s -> %s" % (HOOK_MATCHER, settings_path))
    if strict:
        notes.insert(1, "          strict mode: blocks the first source read of a session "
                        "when the index is fresh\n          and covers at least %d%% of the "
                        "repo; degrades to the nudge otherwise, and never\n          blocks "
                        "(or nudges) twice in one session."
                        % int(hook_mod.STRICT_MIN_COVERAGE * 100))
    else:
        notes.insert(1, "          a nudge, never a block: it fires only on source reads/searches, at most once\n"
                        "          per session, and no-ops silently when inventory.head != git HEAD.")
    notes.append("          python3 %s --explain   to see what it injects and why"
                 % (dest / "cdp" / "hook.py"))
    return notes


SESSION_MATCHER = "startup|resume|clear|compact|fork"
POST_MATCHER = "Bash|Grep|Glob"


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


GATE_MATCHER = "^(Read|Grep|Glob|Bash|mcp__.*cdp_query)$"


def install_gate_hook(target: Path, dest: Path) -> List[str]:
    """PreToolUse gate: the first source search/read of a session is denied once
    until the index has been asked. Replaces the plain nudge (same script). Opt-in
    (`--harness --strict`): it denies calls."""
    settings_path = target / ".claude" / "settings.json"
    settings = _load_json_object(settings_path, "Fix or move it, then re-run.")
    _check_shapes(settings, settings_path)
    groups = _event_groups(settings, "PreToolUse")
    _drop_handlers(groups, cdp_hook_commands(dest, target))
    groups.append({"matcher": GATE_MATCHER,
                   "hooks": [{"type": "command", "command": hook_command(target, dest, "--gate"),
                              "timeout": 30}]})
    _write_settings(settings_path, settings)
    return ["hook      PreToolUse gate -> first source search/read is denied once until the "
            "index is asked, in %s" % settings_path]


def install_session_hook(target: Path, dest: Path) -> List[str]:
    """Register the SessionStart hook: refresh the index, show a short status."""
    settings_path = target / ".claude" / "settings.json"
    settings = _load_json_object(settings_path, "Fix or move it, then re-run.")
    _check_shapes(settings, settings_path)
    command = hook_command(target, dest, "--session-start")
    groups = _event_groups(settings, "SessionStart")
    # Replace, not skip: an older install registered a narrower matcher
    # (`startup|resume`), which never fires after `/clear`.
    commands = cdp_hook_commands(dest, target)
    _drop_handlers(groups, commands)
    groups.append({"matcher": SESSION_MATCHER,
                   "hooks": [{"type": "command", "command": command, "timeout": 120}]})
    # UserPromptSubmit runs before the model's first tool call, which no other
    # hook can promise (PreToolUse only sees the tools it matches).
    prompt_command = hook_command(target, dest, "--prompt-submit")
    prompt_groups = _event_groups(settings, "UserPromptSubmit")
    _drop_handlers(prompt_groups, commands)
    prompt_groups.append({"hooks": [{"type": "command", "command": prompt_command, "timeout": 30}]})
    # PostToolUse: an empty grep is a success to the harness (verified live), so this is the
    # one place the index can say "it knows that name".
    post_groups = _event_groups(settings, "PostToolUse")
    _drop_handlers(post_groups, commands)
    post_groups.append({"matcher": POST_MATCHER, "hooks": [
        {"type": "command", "command": hook_command(target, dest, "--post-search"), "timeout": 30}]})
    _write_settings(settings_path, settings)
    return ["hook      SessionStart (%s) -> refresh + status; UserPromptSubmit -> use the index first; "
            "PostToolUse (%s) -> after an empty search, what the index knows; in %s"
            % (SESSION_MATCHER, POST_MATCHER, settings_path)]


def install_mcp(target: Path, dest: Optional[Path] = None) -> List[str]:
    """Register the `cdp` MCP server in `<target>/.mcp.json`.

    `mcp_server/` ships with the skill (`DIST_MEMBERS`), so the server runs from
    the vendored copy via a `${CLAUDE_PROJECT_DIR:-.}`-relative PYTHONPATH and the file
    is the same on every checkout. (`${CLAUDE_PROJECT_DIR}` alone is not defined for MCP
    config -- verified on Claude Code 2.1.296 -- so the `:-.` default is what makes it connect.) Without a vendored copy it points at this checkout.
    """
    mcp_path = target / ".mcp.json"
    config = _load_json_object(mcp_path, "Fix or move it, then re-run.")
    dest = dest or target / ".claude" / "skills" / "cdp"
    try:
        root = "${CLAUDE_PROJECT_DIR:-.}/%s" % dest.relative_to(target).as_posix()
    except ValueError:
        root = str(SKILL_ROOT)
    if not (dest / "mcp_server").is_dir():
        root = str(SKILL_ROOT)
    if config.get("mcpServers") is not None and not isinstance(config["mcpServers"], dict):
        raise CdpError("%s: `mcpServers` must be an object, found %s; refusing to change it. "
                       "Fix it, then re-run." % (mcp_path, type(config["mcpServers"]).__name__))
    config.setdefault("mcpServers", {})["cdp"] = {
        "command": "python3",
        "args": ["-m", "mcp_server.server"],
        "env": {"PYTHONPATH": root},
    }
    _write_settings(mcp_path, config)
    return ["mcp       server `cdp` (cdp_query, cdp_refresh, cdp_scan, cdp_status, cdp_help) -> %s" % mcp_path]


def _settings_empty(settings: Dict) -> bool:
    return not settings


def remove_harness(target: Path) -> List[str]:
    """Undo `install_hook` / `install_session_hook` / `install_mcp`; leaves the
    copied skill files and every non-CDP entry alone. A settings or MCP file that
    this leaves as `{}` is deleted rather than left behind."""
    notes: List[str] = []
    settings_path = target / ".claude" / "settings.json"
    if settings_path.exists():
        settings = _load_json_object(settings_path, "Fix or move it, then re-run.")
        hooks = settings.get("hooks")
        removed = 0
        if isinstance(hooks, dict):
            commands = cdp_hook_commands(target / ".claude" / "skills" / "cdp", target)
            for event in list(hooks):
                if isinstance(hooks[event], list) and hooks[event]:
                    n = _drop_handlers(hooks[event], commands)
                    removed += n
                    if n and not hooks[event]:
                        del hooks[event]  # emptied by this removal; a list the user left empty stays
            if removed and not hooks:
                del settings["hooks"]
        if removed:
            if _settings_empty(settings):
                settings_path.unlink()
                notes.append("deleted   %s (nothing else in it)" % settings_path)
            else:
                _write_settings(settings_path, settings)
        notes.append("removed   %d CDP hook(s) from %s" % (removed, settings_path))
    mcp_path = target / ".mcp.json"
    if mcp_path.exists():
        config = _load_json_object(mcp_path, "Fix or move it, then re-run.")
        servers = config.get("mcpServers")
        if isinstance(servers, dict) and servers.pop("cdp", None) is not None:
            if not servers:
                del config["mcpServers"]
            if config:
                _write_settings(mcp_path, config)
            else:
                mcp_path.unlink()
                notes.append("deleted   %s (nothing else in it)" % mcp_path)
            notes.append("removed   MCP server `cdp` from %s" % mcp_path)
    return notes


def install(
    target: Path,
    *,
    framework: str = "claude-code",
    hook: bool = False,
    strict: bool = False,
    harness: bool = False,
    agents_md: bool = False,
    say: Callable[..., None] = lambda *a: None,
) -> Path:
    """Copy the skill into `target`'s `.claude/skills/cdp/`, register the leaf agent for
    `framework`, and optionally wire the refresh hook. Returns the skill dir."""
    dest = target / ".claude" / "skills" / "cdp"
    # Refuse before writing anything: an unreadable settings/.mcp.json must not leave
    # the skill copied and the hooks missing.
    if hook or harness:
        settings_file = target / ".claude" / "settings.json"
        _check_shapes(_load_json_object(settings_file, "Fix or move it, then re-run."), settings_file)
    if harness:
        mcp_file = target / ".mcp.json"
        servers = _load_json_object(mcp_file, "Fix or move it, then re-run.").get("mcpServers")
        if servers is not None and not isinstance(servers, dict):
            raise CdpError("%s: `mcpServers` must be an object, found %s; refusing to change it. "
                           "Fix it, then re-run." % (mcp_file, type(servers).__name__))
    copy_distribution(dest, DIST_MEMBERS if target.resolve() == SKILL_ROOT.resolve() else TARGET_MEMBERS)
    say("installed %s" % dest)

    register_leaf_agent(target, framework, say)

    # Tier-0 (7.9): a root-level AGENTS.md works for any assistant, hook-less
    # or not (Cursor, Codex, Copilot, Aider all read it). It is a new file in the
    # target repository, so only on request (`--agents-md`), and never overwritten:
    # a repo's own AGENTS.md is the operator's file.
    if agents_md:
        agents_path = target / "AGENTS.md"
        source_agents_md = SKILL_ROOT / "AGENTS.md"
        if agents_path.exists():
            say("kept      %s (already present, not overwritten)" % agents_path)
        elif source_agents_md.exists():
            shutil.copy2(source_agents_md, agents_path)
            say("wrote     %s" % agents_path)
    if hook and not harness:
        for line in install_hook(target, dest, strict=strict):
            say(line)
    if harness:
        # The default is the nudge: it never blocks. The denying gate is `--strict`.
        first = install_gate_hook(target, dest) if strict else install_hook(target, dest)
        for line in first + install_session_hook(target, dest) + install_mcp(target, dest):
            say(line)
    say("try       python3 %s scan --repo %s"
          % (dest / "run.py", target))
    say("tip       --harness for the Claude Code hooks + MCP server (add --strict to deny repo-wide "
        "greps the index answers); `githook install` to refresh on commit/pull/rebase; "
        "headless `claude -p` refuses MCP tools unless allowed (`--allowedTools \"mcp__cdp__*\"`; "
        "interactive sessions prompt once); --agents-md to add AGENTS.md; --framework {langgraph,adk} for non-Claude-Code leaves")
    return dest
