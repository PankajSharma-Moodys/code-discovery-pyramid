"""Renders every guidance surface from `guide_kinds.py` + `guide_commands.py`.

One source, four generated surfaces: the MCP `cdp_query`/`cdp_help` schema text
(`mcp_server/schemas.py`), `SKILL.md`, `cdp help` / `help --json`, and
`docs/CDP_REFERENCE.md`. `scripts/gen_guide.py` writes the two files;
`tests/test_guide.py` fails when they drift from this source.
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Optional

from .guide_commands import COMMANDS, FLAG_HELP, RECIPES
from .guide_kinds import APPLIES, FLOW, FORMATS, KINDS, MATCHES, PARAMS, ROLES, VIEWS, CLAIM_KINDS  # noqa: F401  (re-exported)

PARTS = ("what", "how", "where")


# ----------------------------------------------------------------- parser help


def _walk(parser: argparse.ArgumentParser, prefix: str = ""):
    """`(command path, subparser)` for every command and nested subcommand."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                path = (prefix + " " + name).strip()
                yield path, sub
                yield from _walk(sub, path)


def apply_flag_help(parser: argparse.ArgumentParser) -> None:
    """Set the help of every option `FLAG_HELP` names, in place, so `--help`, `cdp help <cmd>`
    and `help --json` all describe the same flags (a bare flag gets the generic text for its name)."""
    for path, sub in _walk(parser):
        for action in sub._actions:
            if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)):
                continue
            flag = action.option_strings[0] if action.option_strings else action.dest
            text = FLAG_HELP.get("%s %s" % (path, flag))
            if text is None and not action.help:
                text = FLAG_HELP.get("* " + flag)
            if text is not None:
                action.help = text


# ---------------------------------------------------------------- kind / command


def kind_sections(kind: str) -> Dict[str, str]:
    """The three parts for one kind as text."""
    k = KINDS[kind]
    params = [p for p in APPLIES[kind] if p != "term"]
    lines = ["term: " + k["term"]]
    for p in params:
        lines.append("%s (%s): %s" % (p, PARAMS[p][0], PARAMS[p][1]))
    lines.append("examples: " + "; ".join("cdp " + e for e in k["examples"]))
    return {
        "what": "%s Limits: %s Reading it: %s" % (k["what"], k["not"], k["read"]),
        "how": "\n".join(lines),
        "where": "%s Next: %s" % (k["where"], k["next"]),
    }


def command_sections(name: str) -> Dict[str, str]:
    c = COMMANDS[name]
    return {"what": c["what"], "how": c["how"] + "\nexamples: " + "; ".join("cdp " + e[0] for e in c["examples"]),
            "where": c["where"]}


def render_kind(kind: str) -> str:
    s = kind_sections(kind)
    return "\n".join(["query %s -- %s" % (kind, KINDS[kind]["summary"]), "",
                      "WHAT  " + s["what"], "", "HOW", *("  " + x for x in s["how"].splitlines()),
                      "", "WHERE " + s["where"]])


def render_command(command: Dict) -> str:
    """`command` is one entry of `helpdoc.describe(...)["commands"]` (parser + guide)."""
    lines = ["%s -- %s" % (command["name"], command["summary"]), "", "  " + command["usage"], ""]
    if command.get("what"):
        lines += ["WHAT  " + command["what"], "", "HOW   " + command["how"], "",
                  "WHERE " + command["where"], "", "OPTIONS"]
    for option in command["options"]:
        flags = ", ".join(option["flags"]) or option["name"]
        suffix = ""
        if "choices" in option:
            suffix = "  {%s}" % ",".join(option["choices"])
        elif "default" in option:
            suffix = "  (default %s)" % option["default"]
        lines.append("  %-24s %s%s" % (flags, option["help"], suffix))
    for sub in command.get("subcommands", []):
        lines += ["", "SUBCOMMAND " + sub["name"] + " -- " + sub["summary"], "  " + sub["usage"]]
        for option in sub["options"]:
            lines.append("    %-22s %s" % (", ".join(option["flags"]) or option["name"], option["help"]))
    if command.get("examples"):
        lines += ["", "EXAMPLES"] + ["  $ cdp " + e for e in command["examples"]]
    return "\n".join(lines)


def render_kinds_overview() -> List[str]:
    return ["  %-9s %s" % (k, v["summary"]) for k, v in KINDS.items()]


def render_recipes() -> str:
    out: List[str] = []
    for r in RECIPES:
        out += ["%s -- %s" % (r["name"], r["title"]), "  when: " + r["when"]]
        out += ["    $ cdp " + s[0] for s in r["steps"]]
        out += ["  why:  " + r["why"], ""]
    return "\n".join(out).rstrip()


def flow_table() -> List[str]:
    return ["| %s | `%s` |" % (q, k) for q, k in FLOW]


# ----------------------------------------------------------------- MCP surface


#: How to work with answers (CONTEXT_PLAN.md): one text, shown in the session digest and SKILL.md, so the
#: two cannot drift. Answers are sized by the question; the agent pulls more only when it needs it.
USAGE = (
    "How to work with answers -- like grep, small targeted calls, pull more only when needed:",
    "1. Broad question: the default `list` -- one line per row, `name → handler  path/to/File.java:42` "
    "(repo-relative, opens in Read).",
    "2. One row in depth: `view=compact` with that row's name as `term` (`match=exact` for exactly it). "
    "`trace`, `symbol`, `file` and `paths` answer in compact already.",
    "3. Read only the cited lines (`offset`/`limit`), never the whole file.",
    "- Only a number needed (how many, is there any): `view=count`.",
    "- A cut answer ends with `count`, `shown` and `next: view=... offset=N`: page on only if you need the rest.",
    "- A row over the cap names `offset=N max_tokens=0` for that whole row; use it for that row only.",
    "- `match=regex` is `grep -E` (case-sensitive; `(?i)`), also on names: `routes term=^/v1/(servers|pools)`.",
    "- Wide blind question (many rows, few relevant): `filter=<regex>` greps the list before the cap (full or "
    "shown name), true `matched: N of M`; not with compact/detail/budget.",
    "- `view=detail`, `format=json`, `max_tokens=0`: only when compact is not enough. `.cdp.toml` `[query]` "
    "sets this repo's defaults.",
)


def mcp_query_description() -> str:
    lines = ["Ask the CDP index of a scanned repo a typed question; answers are cited file:line "
             "locations (not code), cheaper and more reliable than grep/find. Use BEFORE grepping, "
             "then Read only the cited lines. `repo` must be scanned (`cdp_scan`); `cdp_help` "
             "gives flags and recipes. Pick `kind`:"]
    lines += ["%s: %s [%s]" % (k, v["summary"], _term_tag(k)) for k, v in KINDS.items()]
    lines.append("Params apply per kind; passing one a kind does not use is an error. Big answers "
                 "are cut: `next` gives the offset; check `coverage` before saying 'no X'. At a fork (several "
                 "handlers, callers, implementations, readers or writers, a path that stops) query every "
                 "branch before answering. Tests and `library:` rows are dropped unless "
                 "include_tests / include_library; prefer the specific kind over `claims`.")
    return "\n".join(lines)


def session_primer() -> str:
    """The once-per-session `cdp_help` digest the SessionStart hook injects: every kind with its purpose, the
    parameters it takes and what it returns, then every parameter's effect. Generated from `KINDS`/`PARAMS`,
    so it cannot drift from `cdp_help` or the MCP schema."""
    lines = ["CDP query kinds -- `cdp_query(kind=..., ...)`; pick by what you need, not by habit. Each returns "
             "cited file:line rows, never code:"]
    for k, v in KINDS.items():
        extra = [p for p in v["uses"] if p not in ("term", "budget", "exclude_role", "include_tests")]
        lines.append("- %s [%s%s]: %s Use: %s" % (
            k, _term_tag(k), ("; " + ", ".join(extra)) if extra else "", v["summary"].rstrip(".") + ".",
            v["where"].strip()))
    lines.append("Parameters (a kind rejects one it does not use):")
    for name, (_flag, meaning) in PARAMS.items():
        lines.append("- %s: %s" % (name, meaning))
    lines.append("Tests and `library:` rows are dropped unless the question is about them; prefer the kind built "
                 "for the question over `claims`. `cdp_help(topic=<kind>)` has examples, `recipes` worked sequences.")
    lines.extend(USAGE)
    return "\n".join(lines)


def _term_tag(kind: str) -> str:
    k = KINDS[kind]
    if "term" not in k["uses"]:
        return "no term" if kind not in ("paths",) else "frm/to"
    return "term required" if "term" in k["required"] else "term optional"


def mcp_term_description() -> str:
    return ("Name to look up. Required: trace (route/symbol), symbol, file (path), module, search. "
            "Optional filter: routes (path or verb), table, config (key), unknowns (scope), claims "
            "(= claim_kind). Not used: paths (use frm/to), conflicts, stats, coverage.")


def mcp_properties() -> Dict[str, Dict]:
    return {
        "repo": {"type": "string", "description": "path to the repository (a scanned one)"},
        "kind": {"type": "string", "enum": list(KINDS), "description": "which question to ask"},
        "term": {"type": "string", "description": mcp_term_description()},
        "budget": {"type": "integer", "minimum": 0,
                   "description": PARAMS["budget"][1] + "; not for stats/coverage"},
        "exclude_role": {"type": "array", "items": {"type": "string", "enum": list(ROLES)},
                         "description": PARAMS["exclude_role"][1] + "; not for module/paths/conflicts/stats/coverage"},
        "include_tests": {"type": "boolean", "description": PARAMS["include_tests"][1]},
        "include_library": {"type": "boolean", "description": PARAMS["include_library"][1]},
        "claim_kind": {"type": "string", "enum": list(CLAIM_KINDS), "description": PARAMS["claim_kind"][1]},
        "module": {"type": "string", "description": PARAMS["module"][1]},
        "subject": {"type": "string", "description": PARAMS["subject"][1]},
        "frm": {"type": "string", "description": PARAMS["frm"][1]},
        "to": {"type": "string", "description": PARAMS["to"][1]},
        "max_hops": {"type": "integer", "minimum": 0, "description": PARAMS["max_hops"][1]},
        "exact": {"type": "boolean", "description": PARAMS["exact"][1]},
        "match": {"type": "string", "enum": list(MATCHES), "description": PARAMS["match"][1]},
        "view": {"type": "string", "enum": list(VIEWS), "description": PARAMS["view"][1]},
        "format": {"type": "string", "enum": list(FORMATS), "description": PARAMS["format"][1]},
        "offset": {"type": "integer", "minimum": 0, "description": PARAMS["offset"][1]},
        "max_tokens": {"type": "integer", "minimum": 0, "description": PARAMS["max_tokens"][1]},
        "filter": {"type": "string", "description": PARAMS["filter"][1]},
        "as_of": {"type": "string", "description": PARAMS["as_of"][1]},
    }


def help_topics() -> List[str]:
    return sorted(set(COMMANDS) | set(KINDS) | {"recipes", "reference"})


MCP_HELP_DESCRIPTION = (
    "Usage guide for CDP: What / How (every flag, defaults, examples) / Where (which question, what "
    "next) for a query kind (trace, symbol, ...) or CLI command (scan, link, ...). topic='recipes' "
    "gives worked sequences (who calls X, what breaks if I change Y, route->tables, config reads, "
    "two repos, refresh); empty gives the overview. Same text as `cdp help <topic>`."
)


MCP_LINK_DESCRIPTION = (
    "Cross-repo links across every repo scanned on this machine: which service calls which "
    "(HTTP route, event topic, table), each as `caller repo:file:line -> callee repo:file:line` "
    "with verb+path and match exact/heuristic. action=query + service (repo name, path or "
    "identity prefix): who calls it and what it calls that is unmatched. action=scan: every "
    "link. action=scan_save: same, and persists them for the CLI `link prompts/run`. "
    "Always matches the current index; scan each repo first (`cdp_scan`)."
)


# ------------------------------------------------------------------- SKILL.md


def skill_md() -> str:
    return """---
name: cdp
description: Reconstruct undocumented architecture from a codebase and answer questions about it with file:line citations. Use when asked to map, explain, document or onboard onto an unfamiliar repository; to find where a symbol/table/route/config key is used; to trace how data flows; or to produce architecture docs or a CLAUDE.md for a repo. Also use before broad grep-based exploration of a large repo — `cdp scan` builds a citable index once, and querying it is cheaper and more reliable than repeated searching. Portable: works on any repository, any language, no install.
---

<!-- GENERATED by scripts/gen_guide.py from cdp/guide_*.py -- edit those, not this file. -->
# CDP — a citable index of this repository

Every fact carries a `file:line` anchor. Ask the index before grep/find; Read only the cited
ranges. Over MCP (the primary channel) call `cdp_query(repo, kind, term, ...)`; the CLI
equivalent is `python3 .claude/skills/cdp/run.py query <kind> <term>`.
Headless `claude -p` refuses MCP tools unless allowed (`--allowedTools "mcp__cdp__*"`); interactive
sessions prompt once.

## Tools
- `cdp_query` -- the 14 kinds below. `cdp_status` -- fresh? covered? `cdp_scan` -- build the index (no model calls).
  `cdp_refresh` -- bring it up to HEAD when `behind` > 0 (clean working tree; no model calls).
  `cdp_link(action="query", service="<repo name>")` -- cross-repo: who calls that service and what it calls
  that no scanned repo serves (every repo scanned on this machine; `action="scan"` lists all links).
- `cdp_help(topic)` -- flags, defaults, examples and next steps for any kind or command; `topic="recipes"` for
  worked sequences. Call it instead of guessing a parameter; it is not dumped here.
- Not an MCP tool, CLI only: `docs`, `diff`, `link prompts|run|refresh` (AI resolution of heuristic links), `answer`, `run`.

## Which kind for which question
| The question | `kind` |
|---|---|
%s

`trace` is the default for "how does X work": `cdp_query(repo=".", kind="trace", term="/orders")` returns
the cited reading list (files on the call chain, with the edge that put each there). Then `symbol` on a
hop for callers, `table` / `config` for what it persists or reads, `paths` for A -> B.
`unknowns` lists gaps a human can close with `answer`.

## `/cdp <question>`
The text after `/cdp` is the question. Map it with the table, make the call(s) (scan first if the repo
has no index: `cdp_scan`), answer from the cited lines, quote each `file:line`. A bare name -> `symbol`
(then `trace`); a path -> `file`; a URL path -> `trace`. Do not start with grep.

## Answers are sized by the question
%s

## Rules
- Quote the citation; Read only the cited ranges.
- A cut answer ends with `count`, `shown` and `next` (the offset to continue). `elided: N` (N>0) means rows
  were left out by a `budget` or a kind's own limit; the answer's note says why and how to get them. A kind
  rejects parameters it does not use; the error says which kind takes them.
- Run `coverage` (never budgeted) before saying "there is no X"; below 100%% means "not examined".
- `medium`/`contested` confidence stays as is; `call` edges prove reachability, not invocation.
- A "not found" answer lists close names; retry with one of them.
- Answers come from the snapshot of HEAD, else the nearest clean ancestor, never another branch (else
  `scan`). `+uncommitted` on `as_of` = the index includes uncommitted edits; `refresh` needs a clean tree.

Full reference (every flag, defaults, examples): `cdp_help` or `run.py help <topic>` / `help reference`
(source repo: `docs/CDP_REFERENCE.md`).
""" % ("\n".join(flow_table()), "\n".join(USAGE[1:]))


# ------------------------------------------------------------- CDP_REFERENCE.md


def reference_md() -> str:
    out = ["<!-- GENERATED by scripts/gen_guide.py from cdp/guide_*.py -- edit those, not this file. -->",
           "# CDP reference", "",
           "Every query kind and command: **What** it answers (and does not), **How** to call it "
           "(parameters, defaults, examples), **Where** it fits (which question, what next). "
           "Same text as `cdp help <topic>` and the MCP `cdp_help` tool.", "",
           "## Which kind for which question", "", "| Question | kind |", "|---|---|", *flow_table(), "",
           "## Query parameters", "", "| MCP param | CLI flag | Meaning |", "|---|---|---|"]
    out += ["| `%s` | `%s` | %s |" % (p, f, d) for p, (f, d) in PARAMS.items()]
    out += ["", "Which kinds take which parameter:", "", "| kind | parameters |", "|---|---|"]
    out += ["| `%s` | %s |" % (k, ", ".join("`%s`" % p for p in APPLIES[k])) for k in KINDS]
    out += ["", "## Query kinds", ""]
    for kind, k in KINDS.items():
        s = kind_sections(kind)
        out += ["### `%s` -- %s" % (kind, k["summary"]), "", "**What.** " + k["what"], "",
                "- Limits: " + k["not"], "- Reading it: " + k["read"], "",
                "**How.** `term`: " + k["term"], ""]
        out += ["- `%s` (`%s`): %s" % (p, PARAMS[p][0], PARAMS[p][1]) for p in APPLIES[kind] if p != "term"]
        out += ["", *("    $ cdp " + e for e in k["examples"]), "",
                "**Where.** %s Next: %s" % (k["where"], k["next"]), ""]
    out += ["## Commands", ""]
    for name, c in COMMANDS.items():
        out += ["### `%s`" % name, "", "**What.** " + c["what"], "", "**How.** " + c["how"], "",
                *("    $ cdp " + e[0] for e in c["examples"]), "", "**Where.** " + c["where"], ""]
    out += ["## Recipes", ""]
    for r in RECIPES:
        out += ["### %s" % r["title"], "", "_%s_" % r["when"], "", *("    $ cdp " + s[0] for s in r["steps"]),
                "", r["why"], ""]
    return "\n".join(out).rstrip() + "\n"


def topic(name: Optional[str]) -> str:
    """Text for a non-parser topic (kind, recipes, reference); None when `name` is not one."""
    if name in KINDS:
        return render_kind(name)
    if name in ("recipes", "workflows", "workflow"):
        return render_recipes()
    if name == "reference":
        return reference_md()
    return None  # type: ignore[return-value]
