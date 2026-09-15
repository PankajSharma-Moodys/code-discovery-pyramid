"""Phase 5b — evidence-or-drop verification (§5.4).

An independent Python pass re-opens every cited file and matches the anchor
against it. Independence is the whole value: asking the model to check its own
citations is asking the entity that produced the error to detect it, using the
same context that produced it.

The matching rule is specified rather than left to taste, because "occurs near
the cited line" is three different rules depending on how you read it. All three
live in `cdp/anchor.py`: a +/-5 line tolerance window with the line rewritten to
the true location, exactly one match inside that window, and at most three
matches in the whole file.

**What this pass does not check.** It confirms that cited text exists where a
claim says it exists. It does *not* confirm that the cited text supports the
statement. A claim reading "server status transitions are validated", anchored
on a line that genuinely reads `public void updateStatus(ServerStatus s)`,
passes cleanly. That boundary is deliberate — entailment is a judgement — and it
is why §8 scores anchor validity and evidence sufficiency as two separate
criteria, and why only the second is a real test of whether this works.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .anchor import verify_anchor
from .util import read_lines

STRICT = "strict"
LENIENT = "lenient"


class FileCache:
    """Files are re-opened once per run, not once per anchor. A claim with three
    anchors into one file would otherwise read it three times."""

    def __init__(self, repo: Path) -> None:
        self.repo = Path(repo)
        self._cache: Dict[str, List[str]] = {}

    def lines(self, rel: str) -> List[str]:
        if rel not in self._cache:
            self._cache[rel] = read_lines(self.repo / rel)
        return self._cache[rel]


def verify_patch(patch: Dict, cache: FileCache, mode: str = STRICT) -> Tuple[Dict, Dict]:
    """Verify one patch in place, returning `(patch, stats)`.

    Failed claims are moved to `unknowns[]` with `demoted_from` and the reason
    attached — never deleted. That inversion is the point: a model that cannot
    find evidence for something it believes will otherwise either assert it
    anyway or quietly omit it, and the second is worse because it destroys the
    signal. An explicit unknown is a precise statement of where tribal knowledge
    still lives in someone's head.
    """
    out = dict(patch)
    kept: List[Dict] = []
    unknowns: List[Dict] = list(patch.get("unknowns") or [])
    stats = {
        "claims_in": 0,
        "claims_kept": 0,
        "claims_demoted": 0,
        "anchors_checked": 0,
        "anchors_ok": 0,
        "anchors_relocated": 0,
        "reasons": {},
        # C1 instrumentation: how many strict demotions had at least one good
        # anchor and would have survived a lenient rule. Free to collect, and it
        # is the number that decides whether the strict reading is costing recall.
        "would_survive_lenient": 0,
    }

    for claim in patch.get("claims") or []:
        stats["claims_in"] += 1
        good: List[Dict] = []
        failures: List[Tuple[Dict, str]] = []
        for anchor in claim.get("evidence") or []:
            stats["anchors_checked"] += 1
            lines = cache.lines(str(anchor.get("file")))
            if not lines:
                failures.append((anchor, "anchor_not_found"))
                continue
            ok, line, reason = verify_anchor(lines, anchor)
            if ok:
                stats["anchors_ok"] += 1
                if line != anchor.get("line"):
                    stats["anchors_relocated"] += 1
                fixed = dict(anchor)
                fixed["line"] = line
                good.append(fixed)
            else:
                failures.append((anchor, reason or "anchor_not_found"))

        survives = bool(good) if mode == LENIENT else (bool(good) and not failures)
        if survives:
            kept_claim = dict(claim)
            kept_claim["evidence"] = good
            kept.append(kept_claim)
            stats["claims_kept"] += 1
        else:
            reason = failures[0][1] if failures else "anchor_not_found"
            stats["claims_demoted"] += 1
            stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
            if good:
                stats["would_survive_lenient"] += 1
            entry = {
                "question": "Unverified: %s" % claim.get("statement", claim.get("id", "?")),
                "why_unresolved": "Citation failed verification (%s): %s"
                % (reason, _describe(failures)),
                "demoted_from": str(claim.get("id", "")),
            }
            if failures:
                entry["anchor"] = failures[0][0]
            elif good:
                entry["anchor"] = good[0]
            unknowns.append(entry)

    out["claims"] = kept
    out["unknowns"] = unknowns
    return out, stats


def _describe(failures: Sequence[Tuple[Dict, str]]) -> str:
    parts = []
    for anchor, reason in failures[:3]:
        parts.append("%s:%s (%s)" % (anchor.get("file"), anchor.get("line"), reason))
    return "; ".join(parts) or "no evidence supplied"


def verify_all(repo: Path, patches: Sequence[Dict], mode: str = STRICT) -> Tuple[List[Dict], Dict]:
    cache = FileCache(repo)
    verified: List[Dict] = []
    totals = {
        "mode": mode,
        "claims_in": 0,
        "claims_kept": 0,
        "claims_demoted": 0,
        "anchors_checked": 0,
        "anchors_ok": 0,
        "anchors_relocated": 0,
        "would_survive_lenient": 0,
        "reasons": {},
        "by_node": {},
    }
    for patch in patches:
        out, stats = verify_patch(patch, cache, mode)
        verified.append(out)
        for key in ("claims_in", "claims_kept", "claims_demoted", "anchors_checked",
                    "anchors_ok", "anchors_relocated", "would_survive_lenient"):
            totals[key] += stats[key]
        for reason, count in stats["reasons"].items():
            totals["reasons"][reason] = totals["reasons"].get(reason, 0) + count
        totals["by_node"][patch.get("node", "?")] = {
            "in": stats["claims_in"],
            "kept": stats["claims_kept"],
            "demoted": stats["claims_demoted"],
        }

    totals["demotion_rate"] = (
        round(totals["claims_demoted"] / totals["claims_in"], 4) if totals["claims_in"] else 0.0
    )
    totals["reasons"] = dict(sorted(totals["reasons"].items()))
    totals["by_node"] = dict(sorted(totals["by_node"].items()))
    return verified, totals
