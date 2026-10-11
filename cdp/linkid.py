"""A link's identity: the same pairing keeps one id across scans and commits."""

from __future__ import annotations

from typing import Dict

from .util import stable_hash


def _side(side: Dict) -> Dict:
    return {"repo": side.get("repo"), "file": (side.get("anchor") or {}).get("file"),
            "symbol": side.get("node"), "target": side.get("target")}


def link_id(link: Dict) -> str:
    """Protocol plus caller and callee (repo, file, symbol, target) -- no commit and no
    line, which move with every unrelated edit. Resolutions are kept under this id."""
    return stable_hash({"protocol": link["protocol"], "caller": _side(link["caller"]),
                        "callee": _side(link["callee"])})[:16]


def anchor_of(side: Dict) -> Dict:
    return {"repo": side.get("repo"), "file": side["anchor"]["file"], "line": side["anchor"]["line"]}


def reanchor(link: Dict, resolution: Dict) -> Dict:
    """A resolution cites one end of its link. When that end moves (an unrelated edit shifts the
    call site) the citation follows it. `anchor_side` says which end; a resolution saved without
    one is matched by file (nearest line when both ends share a file)."""
    cited = resolution.get("anchor") or {}
    side = resolution.get("anchor_side")
    if side not in ("caller", "callee"):
        repo = cited.get("repo")
        near = [s for s in ("caller", "callee") if link[s]["anchor"]["file"] == cited.get("file")
                and (repo is None or repo == link[s]["repo"]
                     or repo == link[s]["repo"].rsplit("#", 1)[-1].rstrip("/").rsplit("/", 1)[-1])]
        if not near:
            return resolution
        try:
            line = int(cited.get("line"))
        except (TypeError, ValueError):
            line = 0
        side = min(near, key=lambda s: abs(link[s]["anchor"]["line"] - line))
    return dict(resolution, anchor=anchor_of(link[side]), anchor_side=side)
