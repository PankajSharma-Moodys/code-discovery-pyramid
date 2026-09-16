"""Leaf prompt assembly — `A_t = (P, sigma_t, O_t)` made concrete.

SKILL.state replaces the append-only transcript with an explicit mutable state.
This module builds the `(P, sigma, O)` triple for one leaf: the fixed protocol
`P` lives in the agent definition and is not repeated here, `sigma` is the
inherited verified state, and `O` is the scope — its file list plus the
structure Python already extracted from it.

**Inherited-sigma pruning (§3.3) is the budget that is easy to forget.**
`--max-leaf-files` and `--max-leaf-loc` bound what a leaf *reads*. Neither
bounds what a leaf is *given*. On the validation target eight modules inherit
`sql-pool-common`; handing each of them common's entire surface would replicate
a large prefix eight times and let inherited context grow with the dependency's
size, reintroducing through the side door exactly the unbounded growth that
bounded scope exists to prevent.

The filter costs no model calls: a leaf inherits only facts about symbols its
own import table actually references, and that table was extracted before the
agent was spawned. Per PLAN.md C3 the budget is implemented as an assertion that
*fires and logs* rather than as a silent truncation — if it never fires on a
real repository, that is a finding about the default, which RESEARCH.md §9
admits is a guess.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .partition import DEFAULT_MAX_INHERITED
from .util import truncate

MAX_STRUCTURE_ROWS = 120

#: crude chars/token estimate for `cdp prompts --measure` (M5.6, 4.9) -- no
#: real tokenizer is stdlib, and this is only meant to size the fixed/variable
#: split, not to predict a real model's count.
CHARS_PER_TOKEN_EST = 4


def build_prompt(
    scope: Dict,
    inventory: Dict,
    extraction: Dict,
    xref: Dict,
    schedule: Dict,
    prior_claims: Sequence[Dict],
    run_id: str,
    max_inherited: int = DEFAULT_MAX_INHERITED,
) -> Tuple[str, Dict]:
    node = scope["node"]
    module = scope["module"]
    scope_files = set(scope["files"])

    imported = _imported_symbols(extraction, scope_files)
    inherited, elided = _inherit(prior_claims, imported, module, schedule, max_inherited)
    structure = _structure(extraction, scope_files)

    named_sections: List[Tuple[str, str]] = [
        ("header", _header(node, module, scope, run_id)),
        ("files", _files_section(inventory, scope)),
        ("structure", _structure_section(structure)),
        ("inherited", _inherited_section(inherited, elided, max_inherited)),
        ("gaps", _gaps_section(xref, scope_files)),
        ("task", _task_section(node, run_id)),
    ]

    # M5.6 (4.9): `CDP_CLI_SCOPE.md` marks per-leaf fixed overhead
    # "unverified -- measure first". `header`/`task` are the two sections
    # whose size is a function of `node`/`run_id` only, not of the scope's
    # content -- the part of the prompt that scales with *scope count*, not
    # code size, which is exactly what a wrong cost curve would look like.
    # `CHARS_PER_TOKEN_EST` is the crude chars/4 estimate (`cdp prompts --measure`'s
    # own docstring says so) -- close enough to size the fixed/variable split,
    # not a claim about any real tokenizer's output.
    section_chars = {name: len(text) for name, text in named_sections}
    fixed_chars = section_chars["header"] + section_chars["task"]
    total_chars = sum(section_chars.values())

    stats = {
        "node": node,
        "module": module,
        "files": scope["file_count"],
        "loc": scope["loc"],
        "imported_symbols": len(imported),
        "inherited_claims": len(inherited),
        "elided_claims": len(elided),
        "budget_fired": bool(elided),
        "section_chars": section_chars,
        "total_chars": total_chars,
        "fixed_chars": fixed_chars,
        "tokens_est": total_chars // CHARS_PER_TOKEN_EST,
        "fixed_tokens_est": fixed_chars // CHARS_PER_TOKEN_EST,
    }
    return "\n\n".join(text for _name, text in named_sections if text), stats


# ---------------------------------------------------------------- sigma


def _imported_symbols(extraction: Dict, scope_files: Set[str]) -> Set[str]:
    """Every FQN this scope's own import table references, plus its namespaces.

    Namespaces are included because a wildcard import (`...model.domain.*`) is a
    reference to everything in a package, and dropping it would silently deny
    the leaf the facts it most needs.
    """
    out: Set[str] = set()
    for row in extraction["imports"]:
        if row["file"] not in scope_files:
            continue
        fqn = row["fqn"]
        out.add(fqn)
        if fqn.endswith(".*"):
            out.add(fqn[:-2])
        cut = fqn.rfind(".")
        if cut > 0:
            out.add(fqn[:cut])
    return out


def _inherit(
    prior_claims: Sequence[Dict],
    imported: Set[str],
    module: str,
    schedule: Dict,
    max_inherited: int,
) -> Tuple[List[Dict], List[Dict]]:
    deps = set(schedule.get("module_deps", {}).get(module, []))

    relevant: List[Dict] = []
    for claim in prior_claims:
        subject = str(claim.get("subject", ""))
        nodes = claim.get("source_nodes") or []
        from_dep = any(n.startswith("root/") and n.split("/")[1] in deps for n in nodes)
        touches = subject in imported or any(
            subject.startswith(sym + ".") or sym.startswith(subject + ".") for sym in imported
        )
        if touches or (from_dep and claim.get("kind") in ("entrypoint", "data_model", "ownership", "deployable")):
            relevant.append(claim)

    # Highest fan-in first, so that if the budget does fire the facts most
    # modules depend on survive it.
    relevant.sort(key=lambda c: (-len(c.get("evidence") or []), str(c.get("subject"))))
    if len(relevant) <= max_inherited:
        return relevant, []
    return relevant[:max_inherited], relevant[max_inherited:]


# ------------------------------------------------------------- structure


def _structure(extraction: Dict, scope_files: Set[str]) -> Dict:
    defines = [d for d in extraction["defines"] if d["file"] in scope_files]
    edges = [e for e in extraction["io_edges"] if e["file"] in scope_files]
    signals: Dict[str, List[str]] = {}
    for rel in sorted(scope_files):
        for signal in extraction["files"].get(rel, {}).get("signals", []):
            signals.setdefault(signal, []).append(rel)
    return {
        "defines": [d for d in defines if d["kind"] in ("class", "interface", "enum", "record", "annotation")],
        "constants": [d for d in defines if d["kind"] in ("constant", "config_key")],
        "edges": edges,
        "signals": signals,
    }


# --------------------------------------------------------------- sections


def _header(node: str, module: str, scope: Dict, run_id: str) -> str:
    return (
        "# CDP leaf scope: `%s`\n\n"
        "- **run_id**: `%s`\n"
        "- **module**: `%s`\n"
        "- **files in scope**: %d (%d non-blank lines)\n\n"
        "You are the only agent that will read these files. No other agent will "
        "check your work by re-reading them, and no parent will re-derive what you miss."
        % (node, run_id, module, scope["file_count"], scope["loc"])
    )


def _files_section(inventory: Dict, scope: Dict) -> str:
    by_path = {f["path"]: f for f in inventory["files"]}
    rows = []
    for path in scope["files"]:
        entry = by_path.get(path, {})
        rows.append("- `%s` (%s, %s, %d loc)" % (path, entry.get("language", "?"), entry.get("role", "?"), entry.get("loc", 0)))
    return (
        "## Your scope — read these files and only these files\n\n"
        + "\n".join(rows)
        + "\n\nIf you encounter a reference to something outside this list, record it and move on. "
        "Do not open it. Out-of-scope references are completed by a deterministic resolve pass "
        "that holds the global symbol table you do not have, so reporting a boundary never costs a fact."
    )


def _structure_section(structure: Dict) -> str:
    parts = ["## Structure already extracted (do not re-derive this)\n"]
    parts.append(
        "A deterministic Java/Python/JS/Go extractor has already produced the declarations, "
        "imports and typed channel edges below, with anchors. Your patch must not restate them. "
        "Your job is what they *mean*.\n"
    )

    if structure["signals"]:
        parts.append("**Signals seen in this scope:** " + ", ".join(
            "%s (%d)" % (k, len(v)) for k, v in sorted(structure["signals"].items())) + "\n")

    if structure["defines"]:
        parts.append("### Types declared here\n")
        for row in structure["defines"][:MAX_STRUCTURE_ROWS]:
            parts.append("- `%s` — %s %s, `%s:%d`" % (
                row["fqn"], row["visibility"], row["kind"], row["anchor"]["file"], row["anchor"]["line"]))
        if len(structure["defines"]) > MAX_STRUCTURE_ROWS:
            parts.append("- ... and %d more" % (len(structure["defines"]) - MAX_STRUCTURE_ROWS))
        parts.append("")

    if structure["constants"]:
        parts.append("### Constants and config keys declared here\n")
        for row in structure["constants"][:60]:
            value = row.get("value")
            parts.append("- `%s` = %s — `%s:%d`" % (
                row["fqn"], repr(value) if value is not None else "?",
                row["anchor"]["file"], row["anchor"]["line"]))
        parts.append("")

    if structure["edges"]:
        parts.append("### Typed channel edges found here\n")
        for row in structure["edges"][:MAX_STRUCTURE_ROWS]:
            parts.append("- `%s` --%s--> `%s` — `%s:%d`" % (
                truncate(row["source"], 70), row["channel"], truncate(row["target"], 70),
                row["anchor"]["file"], row["anchor"]["line"]))
        if len(structure["edges"]) > MAX_STRUCTURE_ROWS:
            parts.append("- ... and %d more" % (len(structure["edges"]) - MAX_STRUCTURE_ROWS))

    return "\n".join(parts)


def _inherited_section(inherited: Sequence[Dict], elided: Sequence[Dict], budget: int) -> str:
    if not inherited and not elided:
        return (
            "## Inherited state (sigma)\n\n"
            "Nothing. This scope is at the root of the dependency DAG, or nothing it "
            "imports has been described yet."
        )
    parts = [
        "## Inherited state (sigma) — verified facts about what this scope imports\n",
        "These were established by earlier leaves and have already passed anchor verification. "
        "Treat them as given. Do not re-derive them, and do not contradict them without evidence "
        "from a file in *your* scope.\n",
    ]
    for claim in inherited:
        parts.append("- **%s** (`%s`): %s" % (claim.get("kind"), claim.get("subject"), claim.get("statement")))
        parts.append("  - %s" % " ".join(
            "`%s:%d`" % (a["file"], a["line"]) for a in (claim.get("evidence") or [])[:3]))
    if elided:
        parts.append(
            "\n> **%d further inherited fact(s) were elided** to stay inside the %d-claim budget "
            "(§3.3). They were dropped lowest-evidence-first. If your scope depends on something "
            "you were not told, say so in `unknowns[]` rather than guessing."
            % (len(elided), budget)
        )
    return "\n".join(parts)


def _gaps_section(xref: Dict, scope_files: Set[str]) -> str:
    unresolved = [
        u for u in xref["uses"]
        if u["resolved"] == "unresolved" and u["from_file"] in scope_files
    ]
    if not unresolved:
        return ""
    rows = sorted({u["fqn"] for u in unresolved})[:30]
    return (
        "## References this run could not resolve\n\n"
        "These appear in your scope and match no symbol anywhere in the repository. "
        "Usually reflection, code generation, or a genuinely external dependency. "
        "If you can say which, that is a useful claim; if you cannot, that is a useful unknown.\n\n"
        + "\n".join("- `%s`" % r for r in rows)
    )


def _task_section(node: str, run_id: str) -> str:
    return (
        "## Your task\n\n"
        "Follow the DVG contract in your agent definition. In short:\n\n"
        "1. **Discover** — read every file in scope. Look for what the structure above cannot say: "
        "why a module exists, what a type is *for*, which representation is authoritative, what a "
        "test reveals about intended behaviour, what a name does not mean.\n"
        "2. **Ground** — emit a schema-valid patch where every claim carries at least one anchor "
        "of at least 12 characters that occurs at most three times in its file. An anchor may span "
        "consecutive lines; prefer a span when a single line is too short or too common.\n"
        "3. **Route what you cannot evidence to `unknowns[]`.** An explicit unknown is useful "
        "output — it names precisely where the knowledge still lives in someone's head. A claim "
        "you cannot anchor is not.\n\n"
        "Do not run a self-verification pass. An independent Python verifier re-opens every cited "
        "file and checks every anchor; claims that fail are demoted to `unknowns[]` automatically, "
        "and the demotion rate is being measured. Spending your budget re-reading your own "
        "citations would make that measurement impossible.\n\n"
        "Write your patch to `.cdp/patches/inbox/%s.json` with `\"node\": \"%s\"` and "
        "`\"run_id\": \"%s\"`."
        % (node.replace("/", "__"), node, run_id)
    )
