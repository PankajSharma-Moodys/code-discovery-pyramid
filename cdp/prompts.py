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

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .partition import DEFAULT_MAX_INHERITED
from .rules import all_edges
from .tiering import compute_tier
from .util import CdpError, sha256_text, truncate

MAX_STRUCTURE_ROWS = 120

#: crude chars/token estimate for `cdp prompts --measure` (M5.6, 4.9) -- no
#: real tokenizer is stdlib, and this is only meant to size the fixed/variable
#: split, not to predict a real model's count.
CHARS_PER_TOKEN_EST = 4

#: M6.3 (4.2): per-file cap on the digest section, chars not tokens (same
#: crude estimate as everywhere else in this module). A file over the cap is
#: exactly the case `unknowns[]`'s "escalation" instruction exists for --
#: the digest says so rather than silently truncating.
MAX_DIGEST_CHARS_PER_FILE = 6000

#: Whole-prompt ceiling, in the same crude tokens_est unit as everywhere else
#: in this module. Unlike `--max-leaf-files`/`--max-leaf-loc` (bound what a
#: leaf *reads*) or `max_inherited` (bound the *inherited* section alone),
#: this bounds the assembled prompt file as a whole. Enforced by tightening
#: the same three levers `build_prompt` already exposes -- inherited-sigma
#: budget, then digest per-file cap, then structure row cap -- cheapest
#: (least information lost) first, and it fires and logs rather than
#: shipping an over-budget prompt silently.
DEFAULT_MAX_PROMPT_TOKENS = 10_000

MIN_DIGEST_CHARS_PER_FILE = 500
MIN_STRUCTURE_ROWS = 10


def build_prompt(
    scope: Dict,
    inventory: Dict,
    extraction: Dict,
    xref: Dict,
    schedule: Dict,
    prior_claims: Sequence[Dict],
    run_id: str,
    max_inherited: int = DEFAULT_MAX_INHERITED,
    digest_mode: bool = False,
    repo_root: Optional[Path] = None,
    symbol_index: Optional[Tuple[Dict[str, List[str]], Dict[str, List[str]]]] = None,
    extra_third_party: Set[str] = frozenset(),
    prompt_fixes: Sequence[Dict] = (),
    max_prompt_tokens: Optional[int] = DEFAULT_MAX_PROMPT_TOKENS,
    inbox_dir: Optional[Path] = None,
    rereview: Optional[Dict] = None,
) -> Tuple[str, Dict]:
    """`rereview` (C2) = `rereview.Plan.as_prompt()`: the leaf sees only the changed files and the
    stale claims of the scope; the unchanged files are named as context, never read or re-claimed."""
    node = scope["node"]
    module = scope["module"]
    full_scope = scope
    if rereview:
        scope = _narrow_scope(scope, inventory, rereview["files"])
    scope_files = set(scope["files"])

    imported = _imported_symbols(extraction, scope_files)
    structure = _structure(extraction, scope_files)
    budget_chars = max_prompt_tokens * CHARS_PER_TOKEN_EST if max_prompt_tokens else None

    cur_max_inherited = max_inherited
    cur_digest_cap = MAX_DIGEST_CHARS_PER_FILE
    cur_structure_rows = MAX_STRUCTURE_ROWS
    tightened: List[str] = []
    prompt_budget_exhausted = False

    while True:
        inherited, elided = _inherit(prior_claims, imported, module, schedule, cur_max_inherited)

        named_sections: List[Tuple[str, str]] = [
            ("header", _header(node, module, scope, run_id)),
            ("files", _files_section(inventory, scope, digest_mode)),
            ("structure", _structure_section(structure, row_cap=cur_structure_rows)),
            ("inherited", _inherited_section(inherited, elided, cur_max_inherited)),
            ("gaps", _gaps_section(xref, scope_files)),
        ]
        if rereview:
            named_sections.insert(1, ("rereview", _rereview_section(rereview, full_scope, scope)))
        digest_fingerprint = None
        if digest_mode:
            digest_text, digest_fingerprint = _digest_section(scope, repo_root, char_cap=cur_digest_cap)
            named_sections.append(("digest", digest_text))
        named_sections.append(("task", _task_section(node, run_id, digest_mode, inbox_dir)))

        # M9.3 (6.7) follow-up: a promoted `prompt_fix` was validated, cut and
        # pinned but never actually rendered anywhere -- consumed here the same
        # way `import_channel_hint`/`budget_change` already are. Applied by
        # `section` name against these exact same section labels (`reflect.py`'s
        # `KNOWN_PROMPT_SECTIONS` is this list, not an invented one), so a fix
        # aimed at `digest` is silently absent on a T3/non-digest scope -- that
        # section was never built for this call, not a bug.
        if prompt_fixes:
            by_section: Dict[str, List[str]] = {}
            for fix in prompt_fixes:
                by_section.setdefault(fix["section"], []).append(fix["instruction"])
            named_sections = [
                (name, _apply_prompt_fixes(text, by_section.get(name)))
                for name, text in named_sections
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
        total_chars = sum(section_chars.values())

        if budget_chars is None or total_chars <= budget_chars:
            break

        # Whole-prompt budget fired. Tighten the cheapest (least
        # information-losing) lever first, cheapest again next iteration,
        # and fall through to the next lever once this one is exhausted --
        # same "fires and logs, never silent" rule as the inherited-sigma
        # budget itself.
        if cur_max_inherited > 0:
            cur_max_inherited = cur_max_inherited // 2
            tightened.append("inherited(%d)" % cur_max_inherited)
        elif digest_mode and cur_digest_cap > MIN_DIGEST_CHARS_PER_FILE:
            cur_digest_cap = max(MIN_DIGEST_CHARS_PER_FILE, cur_digest_cap // 2)
            tightened.append("digest(%d)" % cur_digest_cap)
        elif cur_structure_rows > MIN_STRUCTURE_ROWS:
            cur_structure_rows = max(MIN_STRUCTURE_ROWS, cur_structure_rows // 2)
            tightened.append("structure(%d)" % cur_structure_rows)
        else:
            # Every lever is already at its floor and the prompt still does
            # not fit -- ship it anyway (a leaf with no prompt is worse) but
            # say so loudly rather than silently exceeding the budget.
            prompt_budget_exhausted = True
            break

    fixed_chars = section_chars["header"] + section_chars["task"]

    stats = {
        "node": node,
        "module": module,
        "files": scope["file_count"],
        "loc": scope["loc"],
        "imported_symbols": len(imported),
        "inherited_claims": len(inherited),
        "sigma_claims": sum(1 for c in inherited if _is_sigma_claim(c, imported)),
        "elided_claims": len(elided),
        "elided_subjects": sorted({str(c.get("subject", "")) for c in elided}),
        "budget_fired": bool(elided),
        "section_chars": section_chars,
        "total_chars": total_chars,
        "fixed_chars": fixed_chars,
        "tokens_est": total_chars // CHARS_PER_TOKEN_EST,
        "fixed_tokens_est": fixed_chars // CHARS_PER_TOKEN_EST,
        "digest_mode": digest_mode,
        "rereview_files": len(scope["files"]) if rereview else None,
        "rereview_stale_claims": len(rereview["stale"]) if rereview else None,
        "digest_fingerprint": digest_fingerprint,
        "max_prompt_tokens": max_prompt_tokens,
        "prompt_tightened": tightened or None,
        "prompt_budget_exhausted": prompt_budget_exhausted,
    }
    if symbol_index is not None:
        symbol_owner, namespace_owner = symbol_index
        module_set = {m["name"] for m in inventory["modules"]}
        stats["tiering"] = compute_tier(
            scope, extraction, module_set, symbol_owner, namespace_owner, extra_third_party
        )
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


def _is_sigma_claim(claim: Dict, imported: Set[str]) -> bool:
    """Narrower than "inherited": true only for a claim whose subject is one
    of this scope's own imported symbols, not one pulled in via a module
    dependency's entrypoint/data_model/ownership/deployable fallback below."""
    subject = str(claim.get("subject", ""))
    return subject in imported or any(
        subject.startswith(sym + ".") or sym.startswith(subject + ".") for sym in imported
    )


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
        nodes = claim.get("source_nodes") or []
        from_dep = any(n.startswith("root/") and n.split("/")[1] in deps for n in nodes)
        touches = _is_sigma_claim(claim, imported)
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
    edges = [e for e in all_edges(extraction) if e["file"] in scope_files]
    signals: Dict[str, List[str]] = {}
    for rel in sorted(scope_files):
        for signal in extraction["files"].get(rel, {}).get("signals", []):
            signals.setdefault(signal, []).append(rel)
    return {
        "defines": [d for d in defines if d["kind"] in _TYPE_KINDS],
        "constants": [d for d in defines if d["kind"] in ("constant", "config_key")],
        # Annotated declarations of any kind (types, methods, fields, ctors),
        # including those whose only annotations sit on a parameter.
        "annotated": [d for d in defines if d.get("annotations")
                      or any(p.get("annotations") for p in d.get("params") or [])],
        "edges": edges,
        "signals": signals,
    }


# --------------------------------------------------------------- sections


def _narrow_scope(scope: Dict, inventory: Dict, files: Sequence[str]) -> Dict:
    by_path = {f["path"]: f for f in inventory["files"]}
    keep = [f for f in scope["files"] if f in set(files)]
    return dict(scope, files=keep, file_count=len(keep), loc=sum(by_path.get(f, {}).get("loc", 0) for f in keep))


def _rereview_section(plan: Dict, full_scope: Dict, narrowed: Dict) -> str:
    """What changed since the last review, which claims that made stale, and what NOT to redo."""
    unchanged = [f for f in full_scope["files"] if f not in set(narrowed["files"])]
    rows = []
    for c in plan["stale"]:
        cites = ", ".join("`%s:%s`" % (a.get("file"), a.get("line")) for a in c.get("evidence") or [])
        rows.append("- `%s` [%s] %s: %s (cites %s)" % (c.get("id"), c.get("kind"), c.get("subject"),
                                                       truncate(str(c.get("statement")), 240), cites))
    ctx = ", ".join("`%s`" % f for f in unchanged[:8]) + (" and %d more" % (len(unchanged) - 8) if len(unchanged) > 8 else "")
    return (
        "## Re-review: only what changed\n\n"
        "%d file(s) changed since the last review (the files under *Your scope*). %d claim(s) cite them and are "
        "stale; the other %d are still valid and kept by CDP -- do not re-emit them.\n\n"
        "Stale claims -- for each, re-emit it (same `id`, current anchors) if it still holds, emit the "
        "corrected claim if its meaning changed, otherwise omit it or add an unknown:\n\n%s\n\n"
        "Also claim anything new in the changed files. Unchanged files (context only, do not read or "
        "cite): %s."
        % (len(narrowed["files"]), len(plan["stale"]), plan.get("carried", 0),
           "\n".join(rows) or "- (none: new files only)", ctx or "none")
    )


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


def _files_section(inventory: Dict, scope: Dict, digest_mode: bool = False) -> str:
    by_path = {f["path"]: f for f in inventory["files"]}
    rows = []
    for path in scope["files"]:
        entry = by_path.get(path, {})
        rows.append("- `%s` (%s, %s, %d loc)" % (path, entry.get("language", "?"), entry.get("role", "?"), entry.get("loc", 0)))
    if digest_mode:
        reading_note = (
            "\n\nTheir full text is in the **Digest** section below -- you do not need Read/Grep "
            "to see it. Reading one of these files directly is an escalation (see Your task)."
        )
    else:
        reading_note = ""
    return (
        "## Your scope — read these files and only these files\n\n"
        + "\n".join(rows)
        + reading_note
        + "\n\nIf you encounter a reference to something outside this list, record it and move on. "
        "Do not open it. Out-of-scope references are completed by a deterministic resolve pass "
        "that holds the global symbol table you do not have, so reporting a boundary never costs a fact."
    )


def _digest_section(
    scope: Dict, repo_root: Optional[Path], char_cap: int = MAX_DIGEST_CHARS_PER_FILE
) -> Tuple[str, str]:
    """M6.3 (4.2): the leaf's input becomes this text, not a filesystem.

    Full file text, capped per file at `MAX_DIGEST_CHARS_PER_FILE` -- a
    truncation is stated, never silent, because a silently-elided line is
    exactly how a claim the digest could not support gets asserted anyway.
    `digest_fingerprint` is a hash of what the leaf was actually shown, so a
    later audit can tell whether two runs saw the same input without diffing
    the whole prompt.
    """
    if repo_root is None:
        raise CdpError(
            "digest mode needs repo_root to read file content -- "
            "pass --repo (it is not safe to silently degrade to empty digests)"
        )
    parts = [
        "## Digest — full text of every in-scope file\n",
        "This *is* your input; there is no separate read step for these files.\n",
    ]
    pieces: List[str] = []
    for path in sorted(scope["files"]):
        try:
            text = (repo_root / path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise CdpError(
                "digest mode could not read %r under --repo %s: %s -- "
                "this is almost always a wrong or stale --repo, the same failure "
                "mode named in FINDINGS.md F16" % (path, repo_root, exc)
            ) from exc
        truncated = False
        if len(text) > char_cap:
            text = text[:char_cap]
            truncated = True
        numbered = "\n".join(
            "%5d| %s" % (i, line) for i, line in enumerate(text.splitlines(), start=1)
        )
        pieces.append(numbered)
        parts.append("### `%s`\n```\n%s\n```" % (path, numbered))
        if truncated:
            parts.append(
                "> **truncated at %d chars.** If the claim you need depends on what's past "
                "this point, that is an escalation -- read the rest of `%s` directly and say so."
                % (char_cap, path)
            )
    fingerprint = sha256_text("\n".join(pieces))
    parts.append("\n`digest_fingerprint`: `%s`" % fingerprint)
    return "\n".join(parts), fingerprint


# Prompt-only noise filter: stored and queryable everywhere else, but carrying
# no fact a leaf needs spelled out.
NOISE_ANNOTATIONS = frozenset({"Override", "SuppressWarnings", "Generated"})


_TYPE_KINDS = ("class", "interface", "enum", "record", "annotation")


def _ann_span(ann: Dict) -> str:
    line, end = ann.get("line"), ann.get("end_line")
    if not line:
        return ""
    return "L%d-%d" % (line, end) if end and end != line else "L%d" % line


def _annotation_rows(structure: Dict) -> List[str]:
    """`- Class#method L14-18: @Every(...)` -- verbatim text, cited lines. Parameter
    annotations follow their method as `(param: @X)`."""
    rows: List[Tuple[int, int, int, str]] = []
    freq: Dict[str, int] = {}
    for d in structure.get("annotated", []):
        for a in d.get("annotations") or []:
            freq[a.get("name")] = freq.get(a.get("name"), 0) + 1
    for d in structure.get("annotated", []):
        anns = [a for a in d.get("annotations") or [] if a.get("name") not in NOISE_ANNOTATIONS]
        params = []
        for prm in d.get("params") or []:
            texts = [a["text"] for a in prm.get("annotations") or [] if a.get("name") not in NOISE_ANNOTATIONS]
            if texts:
                params.append("%s: %s" % (prm.get("name", "?"), " ".join(texts)))
        if not anns and not params:
            continue
        owner, sep, member = d["fqn"].partition("#")
        if not sep and d["kind"] not in _TYPE_KINDS:  # fields/constants: `Class.field` -> `Class#field`
            owner, _, member = owner.rpartition(".")
            sep = "#"
        label = owner.rpartition(".")[2] + sep + member
        span = _ann_span(anns[0]) if anns else "L%d" % d["anchor"]["line"]
        text = " ".join(a["text"] for a in anns)
        if params:
            text = (text + " " if text else "") + "(" + "; ".join(params) + ")"
        # Cut order (stable, deterministic): when `row_cap` cuts, bare/unnamed-argument rows
        # (`@Component`, `@Test`, `@Autowired`, `@JsonProperty("x")`) go before rows carrying
        # named arguments (`@Every(value="60s")`, `@Table(name=...)`), rarest annotation first.
        named = 0 if any("=" in a["text"] for a in anns) else 1
        rank = min((freq.get(a.get("name"), 0) for a in anns), default=1 << 30)
        rows.append((named, rank, len(rows), "- %s %s: %s" % (label, span, text)))
    return [r[-1] for r in sorted(rows)]


def _structure_section(structure: Dict, row_cap: int = MAX_STRUCTURE_ROWS) -> str:
    constants_cap = max(10, row_cap // 2)  # 60 at the default row_cap=120, same as before this was parameterised

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
        for row in structure["defines"][:row_cap]:
            parts.append("- `%s` — %s %s, `%s:%d`" % (
                row["fqn"], row["visibility"], row["kind"], row["anchor"]["file"], row["anchor"]["line"]))
        if len(structure["defines"]) > row_cap:
            parts.append("- ... and %d more" % (len(structure["defines"]) - row_cap))
        parts.append("")

    ann_rows = _annotation_rows(structure)
    if ann_rows:
        # Shrinks with `row_cap`, i.e. on the same lever as the type and edge rows in
        # build_prompt's token loop (inherited -> digest -> structure rows), so the
        # existing shrink order is unchanged and deterministic.
        # Half the type/edge cap (like constants): annotations are the first rows to go,
        # so tightening never costs more type/edge rows than it did before this section.
        parts.append("### Annotations declared here (verbatim source; cite the lines)\n")
        parts.extend(ann_rows[:constants_cap])
        if len(ann_rows) > constants_cap:
            parts.append("- ... and %d more" % (len(ann_rows) - constants_cap))
        parts.append("")

    if structure["constants"]:
        parts.append("### Constants and config keys declared here\n")
        for row in structure["constants"][:constants_cap]:
            value = row.get("value")
            parts.append("- `%s` = %s — `%s:%d`" % (
                row["fqn"], repr(value) if value is not None else "?",
                row["anchor"]["file"], row["anchor"]["line"]))
        parts.append("")

    if structure["edges"]:
        parts.append("### Typed channel edges found here\n")
        for row in structure["edges"][:row_cap]:
            parts.append("- `%s` --%s--> `%s` — `%s:%d`" % (
                truncate(row["source"], 70), row["channel"], truncate(row["target"], 70),
                row["anchor"]["file"], row["anchor"]["line"]))
        if len(structure["edges"]) > row_cap:
            parts.append("- ... and %d more" % (len(structure["edges"]) - row_cap))

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


def _inbox_target(inbox_dir: Optional[Path], node: str) -> str:
    name = node.replace("/", "__") + ".json"
    return str(Path(inbox_dir) / name) if inbox_dir else "patches/inbox/" + name


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


def _apply_prompt_fixes(text: str, instructions: Optional[List[str]]) -> str:
    """A promoted `prompt_fix` is routing-only text, R10: it can add an
    instruction a leaf reads, never a fact a leaf is told to assert -- there
    is no claim-shaped field for it to land in. Appended, not prepended, so a
    lesson reads as an addendum to the section it targets, not a rewrite of it."""
    if not instructions:
        return text
    lesson_block = "\n\n".join("**Lesson:** %s" % instr for instr in instructions)
    return text + "\n\n" + lesson_block if text else lesson_block


def _task_section(node: str, run_id: str, digest_mode: bool = False,
                  inbox_dir: Optional[Path] = None) -> str:
    if digest_mode:
        discover = (
            "1. **Discover** — read the Digest section above, not the files themselves. It is your "
            "input. Look for what the structure section cannot say: why a module exists, what a type "
            "is *for*, which representation is authoritative, what a test reveals about intended "
            "behaviour, what a name does not mean.\n"
            "   - **Escalation.** If the digest is truncated where your claim needs it, or you "
            "genuinely cannot ground a claim from the digest alone, you may use Read on that one "
            "file. Set `\"escalated\": true` on any claim built that way -- it is not a violation, "
            "it is a logged, expected fallback the escalation-rate metric depends on being honest.\n"
        )
    else:
        discover = (
            "1. **Discover** — read every file in scope. Look for what the structure above cannot say: "
            "why a module exists, what a type is *for*, which representation is authoritative, what a "
            "test reveals about intended behaviour, what a name does not mean.\n"
        )
    return (
        "## Your task\n\n"
        "Follow the DVG contract in your agent definition. In short:\n\n"
        + discover +
        "2. **Ground** — emit a schema-valid patch where every claim carries at least one anchor "
        "of at least 12 characters that occurs at most three times in its file. An anchor may span "
        "consecutive lines; prefer a span when a single line is too short or too common.\n"
        "3. **Route what you cannot evidence to `unknowns[]`.** An explicit unknown is useful "
        "output — it names precisely where the knowledge still lives in someone's head. A claim "
        "you cannot anchor is not. Each unknown needs `needs`: one of needs_human, needs_runtime, "
        "needs_external_doc, needs_wider_scope, needs_other_repo.\n\n"
        "Annotations in the structure section are verbatim source facts: cite their lines "
        "as anchors and interpret what they mean for the system; never invent an annotation, "
        "argument or value that is not shown.\n\n"
        "Do not run a self-verification pass. An independent Python verifier re-opens every cited "
        "file and checks every anchor; claims that fail are demoted to `unknowns[]` automatically, "
        "and the demotion rate is being measured. Spending your budget re-reading your own "
        "citations would make that measurement impossible.\n\n"
        "Write your patch to `%s` with `\"node\": \"%s\"` and "
        "`\"run_id\": \"%s\"`."
        % (_inbox_target(inbox_dir, node), node, run_id)
    )
