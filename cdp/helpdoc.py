"""`cdp help` — guidance, not flags (`CDP_CLI_SCOPE.md §C` item 1.4).

`cdp --help` already lists every command and every flag. What it cannot say is
*when to use what, in what order, and what comes next* — which is the only thing
a person arriving at an unfamiliar tool, or a front-end discovering it
programmatically, actually needs.

**The command list is derived from the argparse tree, never hand-maintained.**
A help text that drifts from the CLI is worse than no help text: it is a
confident wrong answer about the tool itself, and it is the failure mode a
parallel table guarantees eventually. `describe()` walks the real parser, so a
subcommand added in `cli._parser` appears here without anyone remembering to add
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

from .util import CDP_VERSION

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
    }


def _describe_command(
    name: str, sub: argparse.ArgumentParser, action: argparse._SubParsersAction
) -> Dict:
    summary = ""
    for choice in action._choices_actions:
        if choice.dest == name:
            summary = choice.help or ""
    return {
        "name": name,
        "summary": summary,
        "usage": sub.format_usage().strip(),
        "options": [_describe_option(a) for a in sub._actions
                    if not isinstance(a, argparse._HelpAction)],
    }


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
    "asking questions": [
        "query trace <entrypoint>   the reading list for a question. Start here.",
        "query symbol <name>        definition sites and every use, transposed not guessed",
        "query table <name>         who owns, writes and reads a table",
        "query config <key>         where a key is declared and every site that reads it",
        "query routes [pattern]     the HTTP surface, with constants resolved",
        "query file <path>          what one file defines and what it touches",
        "query unknowns             what the index does not know, and why",
    ],
    "reading an answer honestly": [
        "Every answer ends with `elided: N` and `as of <repo>@<sha>, state vN`.",
        "elided: 0    the list is complete.",
        "elided: N>0  N rows were dropped to stay inside --budget. Raise it, or",
        "             narrow the question. Absence from a budgeted list is not",
        "             absence from the repository.",
        "`stats` and `coverage` are never budgeted, which is why they are the two",
        "commands to check before concluding that something does not exist.",
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


#: Named recipes. `CDP_CLI_SCOPE.md §C` item 1.4 names these four.
WORKFLOWS: Sequence[Dict] = (
    {
        "name": "onboard",
        "title": "Onboard onto an unfamiliar repository",
        "when": "First contact. You have a checkout and no idea what it is.",
        "steps": [
            "cdp scan --repo <repo>",
            "cdp query stats",
            "open <state>/docs/00-overview.md",
            "cdp query routes",
            "cdp query unknowns",
        ],
        "why": (
            "`stats` tells you the shape and whether the build calls itself "
            "something other than its directory. `routes` is the outside edge of "
            "the system. `unknowns` is the list of things no amount of reading "
            "will tell you, which is what to ask a human about."
        ),
    },
    {
        "name": "refresh",
        "title": "Refresh after a sprint",
        "when": "The index exists, the branch has moved.",
        "steps": [
            "cdp scan --repo <repo>",
            "cdp query stats",
            "cdp fold --check",
        ],
        "why": (
            "Re-scanning is cheap and deterministic. Incremental refresh with "
            "claim decay is Phase 3 (`cdp refresh`); until it lands, a full scan "
            "at the new commit is the honest option — and `fold --check` proves "
            "state.json is still the fold of its own log afterwards."
        ),
    },
    {
        "name": "investigate",
        "title": "Investigate a bug",
        "when": "You have a symptom and an entry point, and no map.",
        "steps": [
            "cdp query trace <route-or-symbol>",
            "cdp query symbol <the-thing-in-the-stack-trace>",
            "cdp query table <the-table-it-writes>",
            "cdp query coverage",
        ],
        "why": (
            "`trace` collapses a wide grep into a small cited read. `symbol` "
            "transposes the import table instead of asking a model who calls "
            "what. `coverage` is the check that stops 'I found nothing' from "
            "being reported as 'there is nothing'."
        ),
    },
    {
        "name": "review",
        "title": "Review a PR",
        "when": "You need the blast radius of a change.",
        "steps": [
            "cdp query file <changed-path>",
            "cdp query symbol <each-symbol-it-defines>",
            "cdp query table <each-table-it-touches>",
            "cdp query trace <the-entry-point-above-it>",
        ],
        "why": (
            "Blast radius is the union of the used-by transpose and the storage "
            "edges. Both are inversions of verified data, so neither can invent "
            "a caller — which is the failure mode of asking a model the same "
            "question."
        ),
    },
)


# --------------------------------------------------------------- rendering


def render(surface: Dict, topic: Optional[str] = None) -> str:
    if topic in ("workflow", "workflows"):
        return _render_workflows(surface)
    if topic:
        matches = [c for c in surface["commands"] if c["name"] == topic]
        if not matches:
            names = ", ".join(c["name"] for c in surface["commands"])
            return "No help topic %r. Try: workflows, or one of: %s" % (topic, names)
        return _render_command(matches[0])
    return _render_overview(surface)


def _render_overview(surface: Dict) -> str:
    lines = ["cdp %s — a citable index of a repository" % surface["cdp_version"], ""]
    for heading, body in GUIDANCE.items():
        lines.append(heading.upper())
        lines.extend("  " + line for line in body)
        lines.append("")
    lines.append("COMMANDS")
    for command in surface["commands"]:
        lines.append("  %-10s %s" % (command["name"], command["summary"]))
    lines.append("")
    lines.append("RECIPES")
    for workflow in surface["workflows"]:
        lines.append("  %-10s %s" % (workflow["name"], workflow["title"]))
    lines.append("")
    lines.append("  cdp help workflows      the recipes, in full")
    lines.append("  cdp help <command>      one command's flags, from the parser itself")
    lines.append("  cdp help --json         the same surface, machine-readable")
    return "\n".join(lines)


def _render_workflows(surface: Dict) -> str:
    lines: List[str] = []
    for workflow in surface["workflows"]:
        lines.append("%s — %s" % (workflow["name"], workflow["title"]))
        lines.append("  when: %s" % workflow["when"])
        for step in workflow["steps"]:
            lines.append("    $ %s" % step)
        lines.append("  why:  %s" % workflow["why"])
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_command(command: Dict) -> str:
    lines = ["%s — %s" % (command["name"], command["summary"]), "",
             "  %s" % command["usage"], ""]
    for option in command["options"]:
        flags = ", ".join(option["flags"]) or option["name"]
        suffix = ""
        if "choices" in option:
            suffix = "  {%s}" % ",".join(option["choices"])
        elif "default" in option:
            suffix = "  (default %s)" % option["default"]
        lines.append("  %-24s %s%s" % (flags, option["help"], suffix))
    return "\n".join(lines)
