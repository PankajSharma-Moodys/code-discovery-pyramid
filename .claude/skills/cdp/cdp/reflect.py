"""Phase 9 (M9.3, 6.6 only) -- outlier reflection.

Reflection is a real LLM call, but a rare one: only on outlier scopes a
run's own `fact_leaf_run` corpus (M9.2) already flags as high-spend/low-yield
or high-contradiction. *Which* scopes get reflected on is a deterministic
SQL-shaped selection, not a model decision -- the model is asked one
question about a handful of pre-selected scopes, never asked to browse the
corpus itself.

R10 binds the output: **learning may steer routing, never claim content.**
Enforced here by construction, not convention -- a promotion's schema
(`PROMOTION_KINDS`) shares no vocabulary with a claim's own `kind` field, has
no `subject`/`anchor`/`evidence` shape to carry claim content in, and
`validate_promotion` rejects any extra key a model might try to smuggle in.
If a reflection cannot be cashed out as one of the three closed, deterministic
promotion kinds, it is discarded -- never stored as a vague "lesson".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

#: A promotion is one of exactly these -- never a claim, never free text.
PROMOTION_KINDS = ("import_channel_hint", "prompt_fix", "budget_change")

#: `prompts.py`'s own named prompt sections (`build_prompt`'s `named_sections`
#: list) -- a `prompt_fix` must target a real section, not an invented one.
KNOWN_PROMPT_SECTIONS = ("header", "files", "structure", "inherited", "gaps", "digest", "task")

#: Knobs `prompts.py` actually exposes today -- a `budget_change` must name
#: one of these, not an invented parameter.
KNOWN_BUDGET_PARAMS = ("max_inherited",)

#: Outlier thresholds (6.6: "a handful per run"). Corpus-derived judgment
#: calls, recorded as open in `PHASE/FINDINGS.md` rather than asserted as
#: tuned -- there is no labelled corpus yet to tune them against.
HIGH_SPEND_TOKENS_EST = 5000
DEFAULT_LIMIT = 5


def apply_lessons(lessons: Sequence[Dict]) -> Dict:
    """M9.3 (6.8): the missing consumer -- until this, a pinned lesson-set
    changed nothing about a run, so `--lessons vN` vs `--lessons none` had no
    observable difference for the holdout A/B to measure. Turns a cut's
    promotion rows into the two routing-only knobs `prompts.py`/`graph.py`
    actually expose: extra third-party import patterns (`import_channel_hint`)
    and a `max_inherited` override (`budget_change`). `prompt_fix` promotions
    are read back by `apply_lessons` too but only their `section`/`instruction`
    pair is exposed -- never concatenated into claim-bearing text here, R10.
    Last `budget_change` wins (append order); `import_channel_hint` patterns
    union. No claim content anywhere in the return value, by construction."""
    third_party_patterns: List[str] = []
    max_inherited: Optional[int] = None
    prompt_fixes: List[Dict] = []
    for row in lessons:
        payload = row.get("payload", row)
        kind = payload.get("promotion")
        if kind == "import_channel_hint":
            third_party_patterns.append(payload["pattern"])
        elif kind == "budget_change" and payload.get("parameter") == "max_inherited":
            max_inherited = payload["new_value"]
        elif kind == "prompt_fix":
            prompt_fixes.append({"section": payload["section"], "instruction": payload["instruction"]})
    return {
        "third_party_patterns": frozenset(third_party_patterns),
        "max_inherited": max_inherited,
        "prompt_fixes": prompt_fixes,
    }


def select_outliers(leaf_rows: Sequence[Dict], limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """Deterministic, no model call: a scope qualifies if it contradicted a
    structural fact (gold-standard signal per `entail.py`'s own docstring --
    "every entry is an agent error or an extractor gap") or spent a lot of
    prompt budget and emitted nothing. Sorted worst-first, capped at `limit`
    ("a handful per run", not the whole corpus)."""
    outliers = []
    for row in leaf_rows:
        contradicted = row.get("contradicted") or 0
        tokens_est = row.get("tokens_est") or 0
        claims_emitted = row.get("claims_emitted") or 0
        if contradicted > 0:
            outliers.append(dict(row, reason="high_contradiction"))
        elif tokens_est >= HIGH_SPEND_TOKENS_EST and claims_emitted == 0:
            outliers.append(dict(row, reason="high_spend_low_yield"))
    outliers.sort(key=lambda r: (-(r.get("contradicted") or 0), -(r.get("tokens_est") or 0)))
    return outliers[:limit]


def build_reflection_prompt(row: Dict) -> str:
    return (
        "# Reflection\n\n"
        "Scope `%s` was flagged as an outlier: %s "
        "(tokens_est=%s, claims_emitted=%s, contradicted=%s).\n\n"
        "Name **one** deterministic, mechanical change that would fix the "
        "*general* pattern this scope exhibits -- not a comment about this "
        "scope's own content. Reply with exactly one JSON object, one of:\n\n"
        '  {"promotion": "import_channel_hint", "pattern": "<import FQN or '
        'glob>", "channel": "<config|db|http|queue|...>"}\n'
        '  {"promotion": "prompt_fix", "section": "<one of %s>", '
        '"instruction": "<a concrete, mechanical change to that section>"}\n'
        '  {"promotion": "budget_change", "parameter": "<one of %s>", '
        '"new_value": <int>}\n'
        '  {"promotion": "none"}\n\n'
        "If no concrete, mechanical change follows from this scope, reply "
        '{"promotion": "none"} -- do not describe a vague lesson instead.\n'
        % (row.get("node"), row.get("reason"), row.get("tokens_est"),
           row.get("claims_emitted"), row.get("contradicted"),
           ", ".join(KNOWN_PROMPT_SECTIONS), ", ".join(KNOWN_BUDGET_PARAMS))
    )


def validate_promotion(obj) -> Optional[str]:
    """Returns an error string (reason to discard) or `None` if `obj` is a
    well-formed, actionable promotion. A closed allowlist per kind -- unknown
    keys are rejected rather than ignored, so a model cannot smuggle
    claim-shaped fields (`subject`/`anchor`/`evidence`/...) through here."""
    if not isinstance(obj, dict):
        return "not a JSON object"
    kind = obj.get("promotion")
    if kind == "none":
        return "no actionable promotion"
    if kind not in PROMOTION_KINDS:
        return "not a recognised promotion kind: %r" % (kind,)
    if kind == "import_channel_hint":
        allowed = {"promotion", "pattern", "channel"}
        pattern, channel = obj.get("pattern"), obj.get("channel")
        if not isinstance(pattern, str) or not pattern.strip():
            return "import_channel_hint needs a non-empty 'pattern'"
        if not isinstance(channel, str) or not channel.strip():
            return "import_channel_hint needs a non-empty 'channel'"
    elif kind == "prompt_fix":
        allowed = {"promotion", "section", "instruction"}
        section, instruction = obj.get("section"), obj.get("instruction")
        if section not in KNOWN_PROMPT_SECTIONS:
            return "prompt_fix 'section' must be one of %s, got %r" % (KNOWN_PROMPT_SECTIONS, section)
        if not isinstance(instruction, str) or not instruction.strip():
            return "prompt_fix needs a non-empty 'instruction'"
        if len(instruction) > 500:
            return "prompt_fix 'instruction' too long (%d chars, max 500) -- not mechanical" % len(instruction)
    else:  # budget_change
        allowed = {"promotion", "parameter", "new_value"}
        parameter, new_value = obj.get("parameter"), obj.get("new_value")
        if parameter not in KNOWN_BUDGET_PARAMS:
            return "budget_change 'parameter' must be one of %s, got %r" % (KNOWN_BUDGET_PARAMS, parameter)
        if not isinstance(new_value, int) or isinstance(new_value, bool):
            return "budget_change needs an integer 'new_value'"
    extra = set(obj.keys()) - allowed
    if extra:
        return "unexpected field(s) %s on a %s promotion -- R10 closed vocabulary" % (sorted(extra), kind)
    return None


def reflect(outliers: Sequence[Dict], runner, prompts_dir: Path) -> Tuple[List[Dict], List[Dict]]:
    """Run one real reflection call per outlier via `runner` (the same
    `SubprocessRunner`/`FileRunner` protocol `cdp run`/`link prompts` already
    use -- `runner.run(prompt_path, output_path)`). Returns
    `(accepted, discarded)`, each a list of `{"node", "reason"|"promotion"}`."""
    accepted: List[Dict] = []
    discarded: List[Dict] = []
    out_dir = prompts_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    for row in outliers:
        node = row["node"]
        safe = node.replace("/", "__")
        prompt_path = prompts_dir / (safe + ".md")
        out_path = out_dir / (safe + ".json")
        if out_path.exists():
            out_path.unlink()
        prompt_path.write_text(build_reflection_prompt(row))
        result = runner.run(prompt_path, out_path)
        if not result.ok:
            discarded.append({"node": node, "reason": "runner failure: %s" % result.error})
            continue
        if not out_path.exists():
            discarded.append({"node": node, "reason": "runner wrote no reflection"})
            continue
        try:
            obj = json.loads(out_path.read_text())
        except ValueError as exc:
            discarded.append({"node": node, "reason": "not valid JSON: %s" % exc})
            continue
        error = validate_promotion(obj)
        if error is not None:
            discarded.append({"node": node, "reason": error})
            continue
        accepted.append({"node": node, "reason": row["reason"], "promotion": obj})
    return accepted, discarded
