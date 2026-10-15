"""`cdp help` — guidance, not flags (`CDP_CLI_SCOPE.md §C` item 1.4).

`cdp --help` already lists every command and every flag. What it cannot say is
*when to use what, in what order, and what comes next* — which is the only thing
a person arriving at an unfamiliar tool, or a front-end discovering it
programmatically, actually needs.

**The command list is derived from the argparse tree, never hand-maintained.**
A help text that drifts from the CLI is worse than no help text: it is a
confident wrong answer about the tool itself, and it is the failure mode a
parallel table guarantees eventually. `describe()` walks the real parser, so a
subcommand added in `parser.build_parser` appears here without anyone remembering to add
it, and `tests/test_help.py` asserts exactly that.

`--json` is the machine-readable surface. `RESEARCH_GRAPHIFY.md §7.11` and
`CDP_CLI_SCOPE.md §I` both want a LangGraph/ADK/MCP front-end to discover the
command set without a hand-written adapter; this is that discovery document, and
Phase 9's 7.4 bootstraps from it rather than from a second description of the
same thing.
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Optional, Sequence

from . import guide as guide_mod
from .guide_commands import COMMANDS, RECIPES
from .guide_kinds import FLOW, KINDS
from .util import CDP_VERSION, CdpError

#: The schema `--json` output satisfies, committed beside this module as
#: `schema/help.schema.json` and checked by `tests/test_help.py`.
HELP_SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------- derivation


def describe(parser: argparse.ArgumentParser) -> Dict:
    """Walk a built parser into a JSON-serialisable description of the surface."""
    commands: List[Dict] = []
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        # `choices` is the authoritative mapping name -> subparser. Iterating
        # `_choices_actions` instead would give the help strings but not the
        # parsers, and the flags are the half that drifts.
        for name, sub in sorted(action.choices.items()):
            commands.append(_describe_command(name, sub, action))
    return {
        "schema_version": HELP_SCHEMA_VERSION,
        "cdp_version": CDP_VERSION,
        "prog": parser.prog,
        "commands": commands,
        "workflows": [dict(w) for w in WORKFLOWS],
        "guidance": dict(GUIDANCE),
        "kinds": [{"name": k, "summary": v["summary"], **guide_mod.kind_sections(k),
                   "examples": list(v["examples"])} for k, v in KINDS.items()],
    }


def _describe_command(
    name: str, sub: argparse.ArgumentParser, action: argparse._SubParsersAction
) -> Dict:
    summary = ""
    for choice in action._choices_actions:
        if choice.dest == name:
            summary = choice.help or ""
    out = {
        "name": name,
        "summary": summary,
        "usage": sub.format_usage().strip(),
        "options": [_describe_option(a) for a in sub._actions
                    if not isinstance(a, (argparse._HelpAction, argparse._SubParsersAction))],
    }
    guide = COMMANDS.get(name)
    if guide:
        out.update(what=guide["what"], how=guide["how"], where=guide["where"],
                   examples=[e[0] for e in guide["examples"]])
    nested = [a for a in sub._actions if isinstance(a, argparse._SubParsersAction)]
    if nested:
        out["subcommands"] = [_describe_command(n, p, nested[0]) for n, p in sorted(nested[0].choices.items())]
    return out


def _describe_option(action: argparse.Action) -> Dict:
    out: Dict = {
        "name": action.option_strings[0] if action.option_strings else action.dest,
        "flags": list(action.option_strings),
        "positional": not action.option_strings,
        "required": bool(action.required),
        "help": action.help or "",
    }
    if action.choices is not None:
        out["choices"] = sorted(str(c) for c in action.choices)
    # `argparse.SUPPRESS` is a sentinel object, not data. Emitting it would
    # serialise as the string "==SUPPRESS==" and describe a default that does
    # not exist.
    if action.default is not None and action.default is not argparse.SUPPRESS:
        out["default"] = action.default if isinstance(
            action.default, (str, int, float, bool)) else str(action.default)
    return out


# ----------------------------------------------------------------- content


#: Ordered guidance. Each entry is (heading, lines).
GUIDANCE: Dict[str, List[str]] = {
    "what this is": [
        "CDP builds a citable index of a repository and answers questions from it.",
        "Every answer carries file:line evidence and the commit it was computed at.",
        "`scan` is deterministic Python and costs no tokens. The agent phases",
        "(`prompts` / `collect` / `fold`) add meaning on top and are optional.",
    ],
    "the order things happen in": [
        "1. cdp scan            deterministic extraction + docs. Start here, always.",
        "2. cdp query stats     what was found. Read this before believing anything else.",
        "3. cdp query coverage  what was *not* examined. Read this before saying 'there is no X'.",
        "4. cdp prompts         one leaf prompt per scope, if you want the meaning layer",
        "5. cdp collect         validate + verify + append the patches the agents wrote",
        "6. cdp fold --check    prove state.json is still the fold of its log",
    ],
    "asking questions": ["%-64s query %s" % (q, k) for q, k in FLOW],
    "reading an answer honestly": [
        "Every answer ends with `elided: N` and `as of <repo>@<sha>, state vN`.",
        "elided: 0    nothing was dropped; the list is complete once every page is",
        "             read (a paged answer says `shown 1-57` of its rows: follow `next`).",
        "elided: N>0  N rows were dropped to stay inside --budget. Raise it, or",
        "             narrow the question. Absence from a budgeted list is not",
        "             absence from the repository.",
        "`stats` and `coverage` are never budgeted, which is why they are the two",
        "commands to check before concluding that something does not exist.",
    ],
    "exit codes": [
        "0  done (a query: something matched)        2  usage or environment error (one line, no traceback)",
        "1  nothing done: a query matched nothing (narrowed, like grep); every patch/task failed",
        "3  partly done: collect, link collect, run, link prompts, doctor, reflect -- some items failed",
    ],
    "unknowns, honestly": [
        "An unknown is validated around, never on its content -- CDP checks that",
        "its subject exists and isn't already answered, not whether the gap is real.",
        "Completeness of unknowns is out of scope permanently: whether an agent",
        "failed to notice something it did not know it did not know is unknowable",
        "by construction. Coverage and `doctor`'s recall against a golden set are",
        "the only proxies. `needs_*` says what would resolve one; `cdp answer`",
        "resolves it through the same pipeline a model claim goes through.",
    ],
}


#: Named recipes, from the guide (`guide_commands.RECIPES`); steps are runnable `cdp` commands.
WORKFLOWS: Sequence[Dict] = tuple(
    dict(r, steps=["cdp " + step[0] for step in r["steps"]]) for r in RECIPES
)


# --------------------------------------------------------------- rendering


def render(surface: Dict, topic: Optional[str] = None) -> str:
    text = guide_mod.topic(topic)
    if text is not None:
        return text
    if topic:
        matches = [c for c in surface["commands"] if c["name"] == topic]
        if not matches:
            raise CdpError("no help topic %r; one of: %s" % (
                topic, ", ".join(guide_mod.help_topics())))
        return guide_mod.render_command(matches[0])
    return _render_overview(surface)


def help_text(topic: Optional[str] = None) -> str:
    """`cdp help <topic>` and the MCP `cdp_help` tool: one function, so they cannot differ."""
    from .parser import build_parser

    return render(describe(build_parser()), topic)


def _render_overview(surface: Dict) -> str:
    lines = ["cdp %s — a citable index of a repository" % surface["cdp_version"], ""]
    for heading, body in GUIDANCE.items():
        lines.append(heading.upper())
        lines.extend("  " + line for line in body)
        lines.append("")
    lines.append("QUERY KINDS  (cdp help <kind>)")
    lines.extend(guide_mod.render_kinds_overview())
    lines.append("")
    lines.append("COMMANDS")
    for command in surface["commands"]:
        lines.append("  %-10s %s" % (command["name"], command["summary"]))
    lines.append("")
    lines.append("RECIPES")
    for workflow in surface["workflows"]:
        lines.append("  %-13s %s" % (workflow["name"], workflow["title"]))
    lines.append("")
    lines.append("  cdp help recipes        the recipes, in full")
    lines.append("  cdp help <command|kind> What / How / Where, every flag, examples")
    lines.append("  cdp help reference      the full reference (docs/CDP_REFERENCE.md)")
    lines.append("  cdp help --json         the same surface, machine-readable")
    lines.append("  MCP: cdp_help(topic)    the same text")
    return "\n".join(lines)
