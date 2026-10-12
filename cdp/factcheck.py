"""Index facts a claim can be checked against without a model (K1 values, K2 persistence).

* `Facts.bound`: types the index shows bound to persistence (an @Entity, a repository and the
  entity it manages). A DTO or wire type is none of those.
* `Facts.table_of`: entity -> the table its `@Table(name=...)` names, or None (JPA default).
"""

from __future__ import annotations

from .rules import all_edges
import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

_PERSISTS = re.compile(
    r"\b(?<!not )(?<!never )(persist(?:ed|s|ence)?|stored in (?:the )?(?:database|db|table)|saved (?:to|in) (?:the )?"
    r"(?:database|db|table)|written to (?:the )?(?:database|db|table)|database table|db table)\b", re.I)
_NEGATED = re.compile(r"\b(not|never|no|isn't|is not|are not|aren't|without)\b[^.]{0,40}\b(persist\w*|stored|saved|database)", re.I)
_WIRE_NAME = re.compile(r"(DTO|Dto|Request|Response|Payload|Message|Event|Command|Resource|VO|Vo)s?$")
_WIRE_PATH = re.compile(r"(^|/)(dto|dtos|wire|payload|payloads|api|model/request|model/response)(/|$)", re.I)
_STOP = {"is", "name", "not", "stated", "left", "default", "the", "a", "an", "none", "no", "of", "for", "in", "to", "that", "this"}
_TABLE_QUOTED = re.compile(r"""@Table\(\s*name\s*=\s*["']([\w.$-]+)["']|\btable(?:\s+name)?(?:\s+(?:is|=|named|called))?\s*[`'"]([\w.$-]+)[`'"]""", re.I)
_TABLE_BARE = re.compile(r"\btable\s+name\s+(?:is\s+|=\s*|named\s+|called\s+)?([A-Za-z_][\w$]*)", re.I)


class Facts:
    def __init__(self, extraction: Optional[Dict]) -> None:
        self.bound: Set[str] = set()
        self.table_of: Dict[str, Optional[str]] = {}
        self.table_at: Dict[str, str] = {}
        for e in all_edges(extraction or {}):
            if e.get("channel") != "persist":
                continue
            src, tgt = str(e.get("source") or ""), str(e.get("target") or "")
            if tgt.startswith("library:"):
                continue
            self.bound.add(src)
            if tgt.startswith("entity:"):
                self.bound.add(tgt[len("entity:"):])
                self.table_of.setdefault(tgt[len("entity:"):], None)
            elif tgt.startswith("table:"):
                self.table_of[src] = tgt[len("table:"):]
                anchor = e.get("anchor") if isinstance(e.get("anchor"), dict) else {}
                self.table_at[src] = "%s:%s" % (e.get("file"), anchor.get("line", "?"))


def asserts_persistence(statement: str) -> bool:
    return bool(_PERSISTS.search(statement)) and not _NEGATED.search(statement)


def wire_type(subject: str, home: Optional[str], facts: Facts) -> bool:
    """A class the index defines, with no persistence binding, that looks like a wire/DTO type."""
    fqn = subject[len("entity:"):] if subject.startswith("entity:") else subject
    if fqn in facts.bound or "#" in fqn:
        return False
    simple = fqn.rsplit(".", 1)[-1]
    return bool(_WIRE_NAME.search(simple) or (home and _WIRE_PATH.search(home)))


def claimed_table(statement: str) -> Optional[str]:
    m = _TABLE_QUOTED.search(statement)
    if m:
        return m.group(1) or m.group(2)
    m = _TABLE_BARE.search(statement)
    return m.group(1) if m and m.group(1).lower() not in _STOP else None


def table_clashes(claims: Sequence[Dict], facts: Facts) -> List[Dict]:
    """K1, same subject and predicate (the entity's table name), different value: claims against the
    index's `@Table(name=...)`, and claims against each other."""
    by_entity: Dict[str, List[Tuple[str, Dict]]] = {}
    for c in claims:
        subject = str(c.get("subject") or "")
        fqn = subject[len("entity:"):] if subject.startswith("entity:") else subject
        if fqn not in facts.table_of and fqn not in facts.bound:
            continue
        value = claimed_table(str(c.get("statement") or ""))
        if value:
            by_entity.setdefault(fqn, []).append((value, c))
    out = []
    for fqn, rows in sorted(by_entity.items()):
        index_value = facts.table_of.get(fqn)
        values: Dict[str, List[Dict]] = {}
        for value, c in rows:
            values.setdefault(value.lower(), []).append(c)
        positions = [{"values": {"table_name": rows_[0][0]}, "nodes": sorted({str(c.get("source_node", "")) for c in values[k]}),
                      "statements": sorted({str(c.get("statement", "")) for c in values[k]}),
                      "evidence_count": len({(a.get("file"), a.get("line")) for c in values[k] for a in c.get("evidence") or []}),
                      "won": False}
                     for k, rows_ in ((k, [r for r in rows if r[0].lower() == k]) for k in sorted(values))]
        distinct = set(values)
        if index_value is not None:  # the index's @Table(name=...) is one more position
            distinct.add(index_value.lower())
            if index_value.lower() not in values:
                positions.append({"values": {"table_name": index_value}, "nodes": ["index"],
                                  "statements": ["@Table(name=%r) at %s" % (index_value, facts.table_at.get(fqn, "?"))],
                                  "evidence_count": 1, "won": True})
        if len(distinct) > 1:
            out.append({"subject": fqn, "kind": "data_model", "resolved_by": None, "reason": "value",
                        "predicate": "table name",
                        "question": "Claims give different table names for %s; which is correct?" % fqn,
                        "positions": positions})
    return out
