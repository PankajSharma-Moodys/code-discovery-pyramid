"""Span anchors — construction and verification.

This is the C7 amendment from PLAN.md made concrete. RESEARCH.md Appendix A
requires an anchor to be at least 12 characters, but the detection signals its
own channel vocabulary is defined on are shorter than that: on the validation
target `@Entity` (7 chars) sits alone on line 11 of `EServer.java` and
`@Table(name = "server")` on line 12. A per-line anchor therefore cannot cite
the evidence for the `persist` channel at all.

The fix is to treat an anchor as a **span** of consecutive source lines rather
than a single line. `build_anchor` grows the span downward (then upward) until
the text is long enough to satisfy the schema and specific enough to satisfy
§5.4, so `@Entity` becomes `@Entity @Table(name = "server")` — legal, and more
specific than either line alone.

Matching normalises interior whitespace, which is what makes a span comparable
across a line break, and is also why a claim's anchor survives a reformatting
pass that only changed indentation.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .util import normalise_ws

MIN_ANCHOR_LEN = 12
MAX_ANCHOR_LEN = 400
MAX_MATCHES_IN_FILE = 3
LINE_WINDOW = 5
MAX_SPAN = 4

# Demotion reasons, matching the schema's `demoted_reason` enum.
NOT_FOUND = "anchor_not_found"
AMBIGUOUS = "ambiguous_anchor"
TOO_COMMON = "anchor_too_common"


def find_matches(lines: Sequence[str], anchor: str, max_span: int = MAX_SPAN) -> List[int]:
    """Every 1-based line at which `anchor` *begins*, matched across up to
    `max_span` consecutive lines with interior whitespace normalised.

    The "begins" qualifier is load-bearing. Without it, a single-line anchor on
    line 40 also reports a match at line 39 (span 2 covers it), at line 38
    (span 3), and so on — which would make every anchor look `anchor_too_common`
    and demote the entire corpus. A hit is only recorded at line *i* if the
    anchor is not already contained in the remainder of the span below *i*.
    """
    needle = normalise_ws(anchor)
    if not needle:
        return []
    hits: List[int] = []
    n = len(lines)
    for i in range(n):
        span = None
        for width in range(1, max_span + 1):
            if i + width > n:
                break
            window = normalise_ws(" ".join(lines[i : i + width]))
            if needle in window:
                span = width
                break
        if span is None:
            continue
        if span > 1:
            tail = normalise_ws(" ".join(lines[i + 1 : i + span]))
            if needle in tail:
                continue  # the match really starts further down
        hits.append(i + 1)
    return hits


def _qualifies(lines: Sequence[str], text: str, line_no: int) -> bool:
    """§5.4: at most 3 matches in the file, exactly one within +/-5 lines."""
    if len(text) < MIN_ANCHOR_LEN or len(text) > MAX_ANCHOR_LEN:
        return False
    hits = find_matches(lines, text)
    if not (1 <= len(hits) <= MAX_MATCHES_IN_FILE):
        return False
    near = [h for h in hits if abs(h - line_no) <= LINE_WINDOW]
    return len(near) == 1


def build_anchor(
    rel_path: str,
    lines: Sequence[str],
    index: int,
    max_span: int = MAX_SPAN,
) -> Optional[Dict[str, object]]:
    """Build the shortest qualifying span anchor starting at 0-based `index`.

    Returns None when the file cannot produce a citable anchor there at all —
    a 3-line file of `}` characters, for instance. Callers must treat None as
    "this fact is not citable" and drop it rather than emit an anchor that the
    verifier will demote anyway.
    """
    n = len(lines)
    if not (0 <= index < n):
        return None
    line_no = index + 1

    # Grow downward first: an annotation's meaning is carried by what follows it.
    for width in range(1, max_span + 1):
        if index + width > n:
            break
        text = normalise_ws(" ".join(lines[index : index + width]))
        if _qualifies(lines, text, line_no):
            return {"file": rel_path, "line": line_no, "anchor": text}

    # Then upward, keeping the cited line as the span's end.
    for width in range(2, max_span + 1):
        start = index - width + 1
        if start < 0:
            break
        text = normalise_ws(" ".join(lines[start : index + 1]))
        if _qualifies(lines, text, start + 1):
            return {"file": rel_path, "line": start + 1, "anchor": text}

    return None


def build_anchor_for_text(
    rel_path: str,
    lines: Sequence[str],
    index: int,
    must_contain: str,
) -> Optional[Dict[str, object]]:
    """Like `build_anchor`, but guarantees the span still contains `must_contain`.

    Used where the interesting token is short and the surrounding lines are what
    make it specific -- `@Entity` needs `@Table(...)` beside it, but an anchor
    that grew upward past `@Entity` would no longer evidence the annotation.
    """
    anchor = build_anchor(rel_path, lines, index)
    if anchor is None:
        return None
    if normalise_ws(must_contain) in normalise_ws(str(anchor["anchor"])):
        return anchor
    return None


def verify_anchor(lines: Sequence[str], anchor: Dict[str, object]) -> Tuple[bool, int, Optional[str]]:
    """Check one anchor against a file's lines.

    Returns `(ok, line, reason)`. On success `line` is the *true* location,
    which may differ from the cited one within the tolerance window; §5.4
    requires the citation to be rewritten rather than silently accepted, so
    callers must store the returned line.
    """
    text = str(anchor.get("anchor") or "")
    cited = int(anchor.get("line") or 0)
    if len(normalise_ws(text)) < MIN_ANCHOR_LEN:
        return False, cited, NOT_FOUND

    hits = find_matches(lines, text)
    if not hits:
        return False, cited, NOT_FOUND
    if len(hits) > MAX_MATCHES_IN_FILE:
        return False, cited, TOO_COMMON

    near = [h for h in hits if abs(h - cited) <= LINE_WINDOW]
    if not near:
        # Present in the file but outside the tolerance window. Treated as a
        # failed citation rather than a silent relocation: a claim pointing 200
        # lines away is not evidence of the thing it points at.
        return False, cited, NOT_FOUND
    if len(near) > 1:
        return False, cited, AMBIGUOUS
    return True, near[0], None
