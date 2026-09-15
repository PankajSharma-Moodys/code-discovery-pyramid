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

import bisect
from collections import OrderedDict
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
    and demote the entire corpus. A hit is only recorded at the line the match
    genuinely starts on.

    **Why this is a whole-file index and not a scan.** The obvious
    implementation — for every start line, join up to `max_span` lines,
    normalise, test — re-normalises the entire file once per span width per
    anchor. Profiling a 477-file scan put 83% of the *total* runtime in this
    function and counted 7,168,250 `normalise_ws` calls for 6,476 anchors:
    roughly 1,100 normalisations per anchor, almost all of them of lines that
    had already been normalised for the previous anchor.

    Normalising the file once into a single string and letting `str.find` do
    the search in C is the same computation with the redundancy removed. It is
    160x faster on the same input and returns identical results — which the
    golden baseline, not this docstring, is what actually proves.
    """
    needle = normalise_ws(anchor)
    if not needle:
        return []
    blob, offsets, numbers = _normalised_index(lines)
    if not blob:
        return []

    hits: List[int] = []
    position = 0
    while True:
        found = blob.find(needle, position)
        if found < 0:
            break
        start = bisect.bisect_right(offsets, found) - 1
        end = bisect.bisect_right(offsets, found + len(needle) - 1) - 1
        # The span is measured in *source* lines, not in non-blank ones: the
        # naive version joined blank lines too, and they cost span width while
        # contributing nothing to the text.
        if numbers[end] - numbers[start] < max_span:
            if not hits or hits[-1] != numbers[start]:
                hits.append(numbers[start])
        position = found + 1
    return hits


#: Bounded memo of the last few files' normalised forms.
#
# Keyed on `id(lines)`, which is only sound because the entry holds a reference
# to the list itself: without that the list could be collected and a different
# list allocated at the same address, and this function would then answer about
# the wrong file — a correctness bug that would surface as a mis-anchored claim,
# which is the single worst failure mode CDP has. The identity re-check below is
# the guard; the held reference is what makes the guard sufficient.
_INDEX_CACHE: "OrderedDict[int, Tuple[Sequence[str], str, List[int], List[int]]]" = OrderedDict()
_INDEX_CACHE_MAX = 8


def _normalised_index(lines: Sequence[str]) -> Tuple[str, List[int], List[int]]:
    """`(blob, offsets, numbers)` — the file as one normalised string.

    `blob` is every non-empty normalised line joined by a single space.
    `offsets[k]` is where the k-th such line starts in `blob`, and `numbers[k]`
    is its 1-based source line number. Joining with a space and normalising is
    associative, so a needle matches `blob` exactly when it matched the naive
    per-window join.
    """
    key = id(lines)
    cached = _INDEX_CACHE.get(key)
    if cached is not None and cached[0] is lines:
        _INDEX_CACHE.move_to_end(key)
        return cached[1], cached[2], cached[3]

    parts: List[str] = []
    offsets: List[int] = []
    numbers: List[int] = []
    cursor = 0
    for index, line in enumerate(lines):
        text = normalise_ws(line)
        if not text:
            continue
        parts.append(text)
        offsets.append(cursor)
        numbers.append(index + 1)
        cursor += len(text) + 1  # the joining space

    entry = (lines, " ".join(parts), offsets, numbers)
    _INDEX_CACHE[key] = entry
    _INDEX_CACHE.move_to_end(key)
    while len(_INDEX_CACHE) > _INDEX_CACHE_MAX:
        _INDEX_CACHE.popitem(last=False)
    return entry[1], entry[2], entry[3]


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
