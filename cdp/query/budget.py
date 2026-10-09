"""`Budget`: every cut list is counted and reported, never silent."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple


#: Rows a single response may emit, across every list in it.
#
# A *row* rather than a token count because rows are what CDP can count exactly:
# a token estimate would be a second, softer number that disagrees with the
# first. 200 is chosen to bind on a real monorepo — on `PHASE/TARGET.md`'s
# target, `query table` and `query config` both exceed it — so the elision path
# is exercised by the default rather than only by an unusual flag.
DEFAULT_BUDGET = 200


#: Queries that are never budgeted. `RESEARCH_GRAPHIFY.md §7.3` item 3: these
# are the epistemic safety rails `SKILL.md:58-61` tells the model to check
# before saying "there is no X". Budgeting them would compromise the check that
# detects compromised answers.
UNBUDGETED = frozenset(["stats", "coverage"])


class Budget:
    """A whole-response row allowance, drawn down by every list in the result.

    Not a per-list constant: the eleven hard-coded caps this replaces
    (`[:40]`, `[:25]`, `[:12]`, `[:8]`, `[:6]`, `[:4]`) were unrelated to each
    other and to any budget, so a response could be cut in six places and report
    a total of nothing. One allowance, spent in construction order, means the
    count of what was dropped is a single honest number.

    **Ranked, not head-truncated.** When the allowance binds, the rows dropped
    are the lowest-evidence ones, using the policy `prompts.py:120` already
    applies to the inherited-sigma budget: `-len(evidence)`, then subject. Using
    CDP's own existing idiom means the ranking has one definition rather than
    two. Surviving rows are emitted in their original order — ranking decides
    *what* is dropped, never what the output looks like.
    """

    def __init__(self, rows: Optional[int] = None) -> None:
        self.limit = DEFAULT_BUDGET if rows is None else max(0, int(rows))
        self.spent = 0
        self.elided = 0

    @property
    def fired(self) -> bool:
        return self.elided > 0

    def take(self, rows: Sequence[Any]) -> List[Any]:
        """Return as many of `rows` as the remaining allowance admits."""
        rows = list(rows)
        room = self.limit - self.spent
        if room <= 0:
            self.elided += len(rows)
            return []
        if len(rows) <= room:
            self.spent += len(rows)
            return rows
        self.spent += room
        self.elided += len(rows) - room
        keep = sorted(sorted(range(len(rows)), key=lambda i: _rank(rows[i], i))[:room])
        return [rows[i] for i in keep]

    def note(self) -> Optional[str]:
        """The stated reason, when the allowance admitted nothing at all.

        A zero-row answer and a zero-budget answer look identical otherwise, and
        the difference between "there is no such thing" and "you asked for no
        rows" is the whole point of this module.
        """
        if self.limit == 0:
            return (
                "--budget 0 admits no rows. Every row of this answer was elided; "
                "this is not evidence that there are none."
            )
        if self.fired and self.spent == 0:
            return (
                "--budget %d was exhausted before this list. Every row of it was "
                "elided; this is not evidence that there are none." % self.limit
            )
        return None


def _rank(row: Any, index: int) -> Tuple:
    """`(-evidence, subject, id, index)` — total, deterministic, no ties.

    The stress test that forces the last two components: two rows with equal
    evidence and equal subject must still order the same way on every run, or
    the determinism gate fails intermittently — the worst failure mode to debug,
    because a re-run hides it.
    """
    return (-_evidence_count(row), _subject_of(row), _identity(row), index)


def _evidence_count(row: Any) -> int:
    if not isinstance(row, dict):
        return 0
    for key in ("evidence", "sites", "defined_at", "anchors", "hops", "candidates"):
        value = row.get(key)
        if isinstance(value, list):
            return len(value)
    if isinstance(row.get("used_by_count"), int):
        return row["used_by_count"]
    return 1 if (row.get("anchor") or row.get("at")) else 0


def _subject_of(row: Any) -> str:
    if not isinstance(row, dict):
        return str(row)
    for key in ("subject", "fqn", "table", "key", "path", "route", "name",
                "question", "trigger", "target", "shared", "at"):
        value = row.get(key)
        if isinstance(value, str):
            return value
    return ""


def _identity(row: Any) -> str:
    if not isinstance(row, dict):
        return str(row)
    for key in ("id", "file", "module", "channel", "verb"):
        value = row.get(key)
        if isinstance(value, str):
            return value
    return ""
