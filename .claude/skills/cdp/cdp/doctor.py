"""`cdp doctor` -- model conformance harness (M6.1, `CDP_CLI_SCOPE.md` §F 4.10).

The gate on "works with any LLM." Extends the deterministic `minirepo` golden
test (`tests/test_minirepo.py` checks Python's own extraction; this checks
what a *model* does with the prompt Python built) into five metrics:

    schema validity     -- did the runner produce a schema-valid patch at all
    anchor survival     -- fraction of claims whose anchors verify (verify.py)
    entailment split     -- entailed / consistent / contradicted (entail.py)
    recall vs golden    -- did the model state each gold fact
    false-unknown rate  -- gold facts the model answered with an unknown

Recall alone is not the gate: a model that answers "unknown" to everything
scores perfectly on precision and zero on usefulness. False-unknown rate is
what a doctor run exists to catch (yield collapse: 17 leaves in, 3 claims out,
14 nodes of unknowns).

The golden set below is hand-authored from reading `tests/fixtures/minirepo`
source directly, not from blessing a prior CDP run (the stress test in
`PHASE/phase_6_plan.md` this would otherwise fail is "golden set written from
CDP's own output -- circular"). It is deliberately small (2 facts per module):
a doctor run's job here is to prove the five metrics are wired correctly, not
to carry statistical weight on its own -- that is the graded benchmark's job
(M6.2, out of scope for this milestone).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .entail import entail_claims, summarize as entail_summarize
from .prompts import build_prompt
from .runner import RunResult
from .schema import Validator
from .verify import STRICT, FileCache, verify_patch

# subject substring + statement-keyword substring, both case-insensitive.
# A "hit" needs a claim whose subject contains the substring AND whose
# statement contains the keyword -- matching subject alone would credit a
# model for restating structure Python already gave it.
GOLDEN_MINIREPO: Dict[str, List[Dict[str, str]]] = {
    "core": [
        {
            "subject_contains": "WidgetRepository",
            "keyword": "custom",
            "fact": "WidgetRepository declares no custom query methods; every "
                    "operation is inherited CRUD from JpaRepository.",
        },
        {
            "subject_contains": "core.Widget",
            "keyword": "duplicate",
            "fact": "com.example.mini.core.Widget is defined twice (main and "
                    "test) -- a naming collision, not a cross-module dependency.",
        },
    ],
    "web": [
        {
            "subject_contains": "WidgetResource",
            "keyword": "empty",
            "fact": "WidgetResource.list() always returns an empty list; it "
                    "never reads the WidgetRepository field it stores.",
        },
        {
            "subject_contains": "WebApplication",
            "keyword": "log",
            "fact": "WebApplication's main() prints a startup line; nothing "
                    "in this scope actually starts a server.",
        },
    ],
}


def _extract_json(raw: str) -> Optional[Dict]:
    """A CLI-driven model may wrap the patch in prose or a code fence despite
    being told not to. Take the outermost `{...}` span; anything else is a
    schema-validity failure, not a parse workaround worth expanding."""
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None


def doctor_scope(
    scope: Dict,
    inventory: Dict,
    extraction: Dict,
    xref: Dict,
    schedule: Dict,
    prior_claims: Sequence[Dict],
    run_id: str,
    runner,
    repo: Path,
    prompt_path: Path,
    patch_path: Path,
    validator: Validator,
    golden: Sequence[Dict],
) -> Dict:
    """Run one scope through one runner and score it. Returns a per-scope
    report; `run_doctor` aggregates across scopes."""
    text, _stats = build_prompt(scope, inventory, extraction, xref, schedule, prior_claims, run_id)
    prompt_path.write_text(text, encoding="utf-8")
    if patch_path.exists():
        patch_path.unlink()

    result: RunResult = runner.run(prompt_path, patch_path)
    report: Dict = {"node": scope["node"], "wall_ms": result.wall_ms, "runner_ok": result.ok}
    if not result.ok:
        report.update(schema_valid=False, empty=True, error=result.error)
        return _score_golden(report, [], [], golden)

    if not patch_path.exists():
        report.update(schema_valid=False, empty=True, error="runner ok but no patch written (yield collapse)")
        return _score_golden(report, [], [], golden)

    patch = _extract_json(patch_path.read_text(encoding="utf-8"))
    if patch is None:
        report.update(schema_valid=False, empty=True, error="patch was not parseable JSON")
        return _score_golden(report, [], [], golden)

    errors = validator.validate(patch)
    report["schema_valid"] = not errors
    report["schema_errors"] = errors[:5]
    if errors:
        report["empty"] = not patch.get("claims")
        return _score_golden(report, patch.get("claims") or [], patch.get("unknowns") or [], golden)

    claims = patch.get("claims") or []
    unknowns = patch.get("unknowns") or []
    report["claims_emitted"] = len(claims)
    report["unknowns_emitted"] = len(unknowns)
    report["empty"] = not claims and not unknowns

    cache = FileCache(repo)
    verified_patch, verify_stats = verify_patch(dict(patch), cache, mode=STRICT)
    checked = verify_stats["anchors_checked"]
    report["anchor_survival"] = round(verify_stats["anchors_ok"] / checked, 4) if checked else None
    report["verify_stats"] = verify_stats
    surviving_claims = verified_patch.get("claims", [])
    report["claims_surviving"] = len(surviving_claims)

    entailed = entail_summarize(entail_claims(surviving_claims, extraction))
    report["entailment"] = entailed["counts"]

    return _score_golden(report, surviving_claims, verified_patch.get("unknowns", []), golden)


def _score_golden(report: Dict, claims: List[Dict], unknowns: List[Dict], golden: Sequence[Dict]) -> Dict:
    hits, misses, false_unknowns = [], [], []
    for fact in golden:
        subj_needle = fact["subject_contains"].lower()
        kw = fact["keyword"].lower()
        hit = any(
            subj_needle in (c.get("subject") or "").lower()
            and kw in (c.get("statement") or "").lower()
            for c in claims
        )
        if hit:
            hits.append(fact["fact"])
            continue
        asked_unknown = any(subj_needle in (u.get("subject") or "").lower() for u in unknowns)
        if asked_unknown:
            false_unknowns.append(fact["fact"])
        else:
            misses.append(fact["fact"])
    total = len(golden)
    report["golden_total"] = total
    report["golden_hits"] = len(hits)
    report["golden_misses"] = misses
    report["golden_false_unknowns"] = false_unknowns
    report["recall"] = round(len(hits) / total, 4) if total else None
    report["false_unknown_rate"] = round(len(false_unknowns) / total, 4) if total else None
    return report


def aggregate(reports: List[Dict]) -> Dict:
    n = len(reports)
    schema_valid = sum(1 for r in reports if r.get("schema_valid"))
    empty = sum(1 for r in reports if r.get("empty"))
    golden_total = sum(r.get("golden_total") or 0 for r in reports)
    golden_hits = sum(r.get("golden_hits") or 0 for r in reports)
    false_unknowns = sum(len(r.get("golden_false_unknowns") or []) for r in reports)
    verdict_counts = {"entailed": 0, "consistent": 0, "contradicted": 0}
    for r in reports:
        for k, v in (r.get("entailment") or {}).items():
            verdict_counts[k] = verdict_counts.get(k, 0) + v
    return {
        "scopes": n,
        "schema_validity_rate": round(schema_valid / n, 4) if n else None,
        "yield_collapse_rate": round(empty / n, 4) if n else None,
        "entailment_counts": verdict_counts,
        "recall": round(golden_hits / golden_total, 4) if golden_total else None,
        "false_unknown_rate": round(false_unknowns / golden_total, 4) if golden_total else None,
        "golden_total": golden_total,
    }


def compatibility_table(models: Dict[str, Dict]) -> str:
    lines = ["model            schema_valid  yield_collapse  recall  false_unknown"]
    for name, agg in sorted(models.items()):
        lines.append(
            "%-16s %11s%%  %13s%%  %5s%%  %11s%%"
            % (
                name,
                _pct(agg.get("schema_validity_rate")),
                _pct(agg.get("yield_collapse_rate")),
                _pct(agg.get("recall")),
                _pct(agg.get("false_unknown_rate")),
            )
        )
    return "\n".join(lines)


def _pct(x: Optional[float]) -> str:
    return "?" if x is None else str(round(x * 100))
