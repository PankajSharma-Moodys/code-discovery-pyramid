"""How an outbound HTTP call is matched to a server route: one path shape for every framework.

Params become `*` whatever the syntax -- Flask `<int:uid>`/`<x>`, `{x}`, `{id:int}`, Express `:x`,
JS template `${x}`, Refit `{x}`. Query strings are dropped, the verb is compared only when both
sides state one, and a client path that lacks the server's context prefix (Refit
`/sql-pool/v1/reservations` vs Dropwizard `/unified-store/sql-pool/v1/reservations`) matches as a
trailing-segment suffix when the shorter side carries at least two informative segments.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

_VERB_PREFIX_RE = re.compile(r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|ANY) ")
_URL_PATH_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+(/.*)?$")
_NEST = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
_PARAM_RE = re.compile(r"\$%s|%s|<[^<>/]*>|(?<=/):[A-Za-z_]\w*\??" % (_NEST, _NEST))
_VERSION_RE = re.compile(r"^v\d+(\.\d+)?$")


def verb_of(channel: str, target: str) -> Optional[str]:
    """The HTTP verb a target states, or None (no verb, or ANY)."""
    if channel == "http_in":
        rest = target[len("route:"):] if target.startswith("route:") else target
        m = _VERB_PREFIX_RE.match(rest)
    elif channel == "http_out":
        rest = target[len("http:"):] if target.startswith("http:") else target
        m = _VERB_PREFIX_RE.match(rest)
    else:
        return None
    return m.group(1) if m and m.group(1) != "ANY" else None


def path_of(channel: str, target: str) -> str:
    """The bare path/table a raw edge target names, verb/scheme/host/query stripped."""
    if channel == "http_in":
        path = target[len("route:"):] if target.startswith("route:") else target
        path = _VERB_PREFIX_RE.sub("", path)
        path = path.split(" ", 1)[1] if " " in path else path
    elif channel == "http_out":
        raw = target[len("http:"):] if target.startswith("http:") else target
        raw = _VERB_PREFIX_RE.sub("", raw)
        if raw.startswith("${") and "}" in raw:  # `${billing.url}/v1/x`: the host is a config key
            raw = raw.split("}", 1)[1] or "/"
        m = _URL_PATH_RE.match(raw)
        path = (m.group(1) or "/") if m else raw
    else:
        path = target
    if channel in ("http_in", "http_out"):
        path = path.split("?", 1)[0].split("#", 1)[0]
        return path
    return path.lower() if channel in ("persist", "schema_own") else path


def segments(path: str) -> Tuple[str, ...]:
    """Lower-cased path segments, every param spelling replaced by `*`."""
    path = _PARAM_RE.sub("*", path)
    return tuple(s.lower() for s in path.split("/") if s)


def informative(segs: Tuple[str, ...]) -> int:
    return sum(1 for s in segs if "*" not in s and s != "api" and not _VERSION_RE.match(s))


def key_of(segs: Tuple[str, ...]) -> str:
    return "/" + "/".join(segs)


def verbs_compatible(a: Optional[str], b: Optional[str]) -> bool:
    return a is None or b is None or a == b


def _suffixes(segs: Tuple[str, ...]):
    for i in range(1, len(segs) - 1):  # proper suffixes of at least two segments
        tail = segs[i:]
        if len(tail) >= 2 and informative(tail) >= 2:
            yield tail


def _seg_match(route: str, query: str) -> Optional[bool]:
    """None: the segments cannot match; False: equal; True: matched through a param (`*`)."""
    if route == query:
        return False
    if "*" not in route and "*" not in query:
        return None
    if route == "*" or query == "*" or ("*" in route and "*" in query):
        return True
    pattern, other = (route, query) if "*" in route else (query, route)
    rx = ".+".join(re.escape(part) for part in pattern.split("*"))
    return True if re.fullmatch(rx, other) else None


class _Node:
    __slots__ = ("kids", "pats", "items")

    def __init__(self) -> None:
        self.kids: Dict[str, "_Node"] = {}
        self.pats: List[Tuple[str, "_Node"]] = []      # children whose segment holds a `*`
        self.items: List[Tuple[int, object]] = []


class _Trie:
    def __init__(self) -> None:
        self.root = _Node()

    def add(self, segs: Tuple[str, ...], entry: Tuple[int, object]) -> None:
        node = self.root
        for seg in segs:
            nxt = node.kids.get(seg)
            if nxt is None:
                nxt = node.kids[seg] = _Node()
                if "*" in seg:
                    node.pats.append((seg, nxt))
            node = nxt
        node.items.append(entry)

    def match(self, segs: Tuple[str, ...], suffix: bool = False) -> List[Tuple[int, object]]:
        """Every route matching `segs` segment by segment. A route that needs no param to match
        beats one that does; among the rest the fewest param-matched segments win. A param match
        must still share one informative literal segment with the query, so `/v1/{x}` never
        swallows every `/v1/...` call. In a `suffix` match (a dropped context prefix) the first segment, the boundary,
        must be equal, never a param standing in for a literal, and two informative literals must
        agree rather than one: `/{t}/card/{e}/artifact/bulk` is not `/{t}/Card/{e}/bulk`."""
        found: List[Tuple[int, int, Tuple[int, object]]] = []

        def walk(node: _Node, i: int, wild: int, shared: int) -> None:
            if i == len(segs):
                if wild == 0 or shared >= (2 if suffix else 1):
                    found.extend((wild, shared, e) for e in node.items)
                return
            seg = segs[i]
            gain = 1 if "*" not in seg and seg != "api" and not _VERSION_RE.match(seg) else 0
            if "*" in seg:
                options = list(node.kids.items())
            else:
                options = [(seg, node.kids[seg])] if seg in node.kids else []
                options += [(k, n) for k, n in node.pats]
            for key, child in options:
                how = _seg_match(key, seg)
                if how is None or (how and suffix and i == 0):
                    continue
                walk(child, i + 1, wild + (1 if how else 0), shared + (gain if not how else 0))

        walk(self.root, 0, 0, 0)
        if not found:
            return []
        best = min(w for w, _, _ in found)
        return [e for w, _, e in found if w == best]


class RouteIndex:
    """Inbound routes by segment-wise match (a literal segment matches a server param) and by
    trailing-segment suffix."""

    def __init__(self) -> None:
        self.exact = _Trie()
        self.suffix = _Trie()
        self._n = 0

    def add(self, segs: Tuple[str, ...], item) -> None:
        entry = (self._n, item)
        self._n += 1
        self.exact.add(segs, entry)
        for tail in _suffixes(segs):
            self.suffix.add(tail, entry)

    def lookup(self, segs: Tuple[str, ...]) -> List:
        """Candidates for an outbound path: same shape, a server with a longer (context) prefix,
        or a client URL that carries the server's prefix. Each once, exact first."""
        out, seen = [], set()

        def take(entries):
            for n, it in sorted(entries, key=lambda e: e[0]):
                if n not in seen:
                    seen.add(n)
                    out.append(it)

        take(self.exact.match(segs))
        if len(segs) >= 2 and informative(segs) >= 2:
            take(self.suffix.match(segs, True))
        for tail in _suffixes(segs):
            take(self.exact.match(tail, True))
        return out
