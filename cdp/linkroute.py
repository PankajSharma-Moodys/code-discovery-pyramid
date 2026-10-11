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


class RouteIndex:
    """Inbound routes by exact key and by trailing-segment suffix."""

    def __init__(self) -> None:
        self.exact: Dict[Tuple[str, ...], List] = {}
        self.suffix: Dict[Tuple[str, ...], List] = {}

    def add(self, segs: Tuple[str, ...], item) -> None:
        self.exact.setdefault(segs, []).append(item)
        for tail in _suffixes(segs):
            self.suffix.setdefault(tail, []).append(item)

    def lookup(self, segs: Tuple[str, ...]) -> List:
        """Candidates for an outbound path: same shape, a server with a longer (context) prefix,
        or a client URL that carries the server's prefix. Each once, exact first."""
        out, seen = [], set()

        def take(items):
            for it in items:
                if id(it) not in seen:
                    seen.add(id(it))
                    out.append(it)

        take(self.exact.get(segs, []))
        if len(segs) >= 2 and informative(segs) >= 2:
            take(self.suffix.get(segs, []))
        for tail in _suffixes(segs):
            take(self.exact.get(tail, []))
        return out
