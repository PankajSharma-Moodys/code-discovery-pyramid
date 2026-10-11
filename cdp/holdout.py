"""Holdout A/B of a lesson cut (L10): what the lessons change, measured on claims, with no model call.

A lesson steers routing and prompt assembly, never claim content (R10). So the deterministic effect
of a cut on a repo it did not learn from is read from the same inputs a real `run` would use: each
scope's tier, its assembled prompt (cost, inherited claims elided) and the repo's own claims (which
of the elided ones were verified facts, which claims of the scope cite an elided subject).
Both arms (`none` and `lessons`) are computed from the same store; the cut is promoted only if no
quality metric got worse and the prompt cost did not grow by more than `COST_SLACK`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from . import entail as entail_mod, reflect as reflect_mod, tiering as tiering_mod
from .prompts import build_prompt

#: Prompt tokens may grow this much (a larger `max_inherited` costs tokens) before it counts as a regression.
COST_SLACK = 0.10

#: Promotion kinds this A/B can judge. `prompt_fix` is free text for a model: nothing deterministic measures it.
MEASURABLE = ("import_channel_hint", "budget_change")

#: Lower is better for each of these; a rise is a regression.
QUALITY = ("t3_rate", "elided_verified", "elision_regret", "contradicted_rate")


def unmeasurable(lessons: List[Dict]) -> List[str]:
    return sorted({row["kind"] for row in lessons} - set(MEASURABLE))


def measure(store, hints: Dict) -> Dict:
    """Claim-level metrics of one arm. `hints` is `reflect.apply_lessons(...)` (or `{}` for none)."""
    scopes = store.partition["scopes"]
    claims = store.state.get("claims", [])
    verdicts = {c.get("id"): c.get("verdict") for c in entail_mod.entail_claims(claims, store.extraction)}
    index = tiering_mod.build_symbol_index_for_tiering(store.extraction)
    extra = hints.get("third_party_patterns", frozenset())
    kwargs = {"max_inherited": hints["max_inherited"]} if hints.get("max_inherited") is not None else {}
    run_id = str(store.manifest.get("run_id", "cdp"))
    t3 = tokens = elided = verified = regret = 0
    for scope in scopes:
        _text, stats = build_prompt(scope, store.inventory, store.extraction, store.xref, store._load("schedule"),
                                    claims, run_id, symbol_index=index, extra_third_party=extra,
                                    prompt_fixes=hints.get("prompt_fixes", ()), **kwargs)
        t3 += stats["tiering"]["tier"] == tiering_mod.T3
        tokens += stats["tokens_est"]
        elided += stats["elided_claims"]
        gone = set(stats["elided_subjects"])
        verified += sum(1 for c in claims if c.get("subject") in gone
                        and verdicts.get(c.get("id")) in (entail_mod.ENTAILED, entail_mod.CONSISTENT))
        regret += sum(1 for c in claims if c.get("source_node") == scope["node"] and c.get("subject") in gone)
    n = len(claims)
    count = lambda v: sum(1 for x in verdicts.values() if x == v)  # noqa: E731
    return {
        "scopes": len(scopes), "claims": n, "t3_rate": t3 / len(scopes) if scopes else 0.0,
        "tokens_est": tokens, "elided_claims": elided, "elided_verified": verified, "elision_regret": regret,
        "entailed_rate": count(entail_mod.ENTAILED) / n if n else 0.0,
        "consistent_rate": count(entail_mod.CONSISTENT) / n if n else 0.0,
        "contradicted_rate": count(entail_mod.CONTRADICTED) / n if n else 0.0,
        "claims_per_ktok": 1000.0 * n / tokens if tokens else 0.0,
    }


def compare(none: Dict, lessons: Dict) -> Tuple[bool, List[str]]:
    """`(promote?, [metric that regressed])`."""
    if not none["claims"]:
        return False, ["the holdout repo has no claims to measure"]
    bad = [m for m in QUALITY if lessons[m] > none[m] + 1e-12]
    if lessons["tokens_est"] > none["tokens_est"] * (1 + COST_SLACK):
        bad.append("tokens_est +%.0f%%" % (100.0 * (lessons["tokens_est"] / none["tokens_est"] - 1)))
    return not bad, bad
