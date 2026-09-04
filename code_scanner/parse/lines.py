"""Per-line classification. Owns the LOC invariant: code + comment + blank == total.

One classification slot per line: mark every line touched by a comment node span
(and, when enabled, a doc-position string span), then resolve — this gets mixed
lines and multi-line comments right where `line.strip().startswith("//")` does not.
"""

from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Node, Tree

from code_scanner.languages.profile import DocStyle, LanguageProfile
from code_scanner.model import Lines
from code_scanner.parse.session import get_parser


@dataclass
class ParseOutcome:
    tree: Tree | None
    lines: Lines
    parse_status: str  # "ok" | "degraded" | "unparsed"
    source_text: str


def read_source(raw: bytes) -> tuple[str, bool]:
    """Decode bytes to text. R18: never raises; marks approximate on a lossy decode."""
    try:
        return raw.decode("utf-8"), False
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), True


def _error_byte_ratio(root: Node, total_bytes: int) -> float:
    """Union of top-most ERROR/MISSING byte ranges / file size (R7). Non-overlapping
    because we stop descending once a node of interest is found — nesting siblings/
    children of an ERROR node are not double-counted."""
    if total_bytes == 0:
        return 0.0
    covered = 0

    def walk(node: Node) -> None:
        nonlocal covered
        if node.is_error or node.type == "ERROR" or node.is_missing:
            covered_end = min(node.end_byte, total_bytes)
            covered_start = min(node.start_byte, total_bytes)
            if covered_end > covered_start:
                covered += covered_end - covered_start
            return  # top-most only — do not descend into an already-counted error
        for child in node.children:
            walk(child)

    walk(root)
    return min(covered / total_bytes, 1.0)


def _is_docstring_position(node: Node, profile: LanguageProfile) -> bool:
    """FIRST_STRING_IN_BODY: a string node that is the first statement of a
    module/class/function body (R10). tree-sitter-python has no `expression_statement`
    wrapper — bare expressions are direct children of `module`/`block` — so the test is
    against the enclosing block directly, not an intermediate statement node."""
    if profile.doc_style != DocStyle.FIRST_STRING_IN_BODY:
        return False
    if node.type not in profile.string_nodes:
        return False
    block = node.parent
    if block is None or block.type not in ("module", "block"):
        return False
    named_children = [c for c in block.children if c.is_named]
    return bool(named_children) and named_children[0] == node


def _collect_comment_and_doc_spans(root: Node, profile: LanguageProfile) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []

    def walk(node: Node) -> None:
        if node.type in profile.comment_nodes:
            spans.append((node.start_byte, node.end_byte))
            return
        if _is_docstring_position(node, profile):
            spans.append((node.start_byte, node.end_byte))
        for child in node.children:
            walk(child)

    walk(root)
    return spans


def classify_lines(
    source_bytes: bytes,
    source_text: str,
    root: Node | None,
    profile: LanguageProfile | None,
    docstring_as_comment: bool = True,
) -> Lines:
    raw_lines = source_text.splitlines(keepends=True)
    total = len(raw_lines)

    if root is None or profile is None:
        # D14: no comment spans available — every non-blank line is code, marked approximate.
        blank = sum(1 for line in raw_lines if line.strip() == "")
        code = total - blank
        return Lines(total=total, code=code, comment=0, blank=blank, approximate=True)

    spans = _collect_comment_and_doc_spans(root, profile)
    if not docstring_as_comment:
        # Recompute without doc spans by filtering out ones whose start doesn't match a comment node.
        comment_only_spans: list[tuple[int, int]] = []

        def walk_comments(node: Node) -> None:
            if node.type in profile.comment_nodes:
                comment_only_spans.append((node.start_byte, node.end_byte))
                return
            for child in node.children:
                walk_comments(child)

        walk_comments(root)
        spans = comment_only_spans

    # Byte offset of the start of each line, in the UTF-8 encoding tree-sitter used.
    line_byte_starts: list[int] = []
    offset = 0
    for line in raw_lines:
        line_byte_starts.append(offset)
        offset += len(line.encode("utf-8"))

    code = comment = blank = 0
    for i, line in enumerate(raw_lines):
        stripped = line.strip()
        if stripped == "":
            blank += 1
            continue

        line_start = line_byte_starts[i]
        line_end = line_start + len(line.encode("utf-8"))

        # Bytes on this line not covered by any comment/doc span.
        covered_ranges = [
            (max(s, line_start), min(e, line_end))
            for s, e in spans
            if e > line_start and s < line_end
        ]
        line_bytes = line.encode("utf-8")
        mask = bytearray(line_bytes)
        for s, e in covered_ranges:
            for pos in range(s - line_start, e - line_start):
                if 0 <= pos < len(mask):
                    mask[pos] = 0x20  # blank out covered bytes

        remainder = mask.decode("utf-8", errors="replace").strip()
        if remainder == "":
            comment += 1
        else:
            code += 1

    return Lines(total=total, code=code, comment=comment, blank=blank, approximate=False)


def parse_file(source_bytes: bytes, profile: LanguageProfile | None, degraded_error_ratio: float = 0.20) -> ParseOutcome:
    source_text, decode_lossy = read_source(source_bytes)

    if profile is None:
        lines = classify_lines(source_bytes, source_text, None, None)
        if decode_lossy:
            lines = Lines(lines.total, lines.code, lines.comment, lines.blank, approximate=True)
        return ParseOutcome(tree=None, lines=lines, parse_status="unparsed", source_text=source_text)

    parser = get_parser(profile.grammar)
    tree = parser.parse(source_bytes)
    root = tree.root_node

    error_ratio = _error_byte_ratio(root, len(source_bytes))
    if error_ratio > degraded_error_ratio:
        status = "degraded"
    else:
        status = "ok"

    lines = classify_lines(source_bytes, source_text, root, profile)
    if decode_lossy:
        lines = Lines(lines.total, lines.code, lines.comment, lines.blank, approximate=True)

    return ParseOutcome(tree=tree, lines=lines, parse_status=status, source_text=source_text)
