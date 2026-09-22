"""Node typing and rollup for the two graph canvases (`ATLAS_REDESIGN.md` §3).

`dataflow.edges` names its endpoints in one of two shapes: a bare
module/symbol id (`cdp.store.sqlite_backend`, `web.api.app#get_trace`) or a
`type:`-prefixed id (`table:churn_cache`, `route:GET /api/repos`). That
prefix is the only node-type signal the store carries, so classifying it is
the join between the data and every visual channel downstream.

This lives server-side rather than in the frontend for one reason: the L3
package rollup and the L2 node typing must agree exactly, or a super-node's
`members` stop matching what `?scope=` returns. Pure string functions, no
I/O -- `app.py`'s graph builders are the only callers.

**Colour is capped at three families and that cap is computed, not taste**
(`ATLAS_REDESIGN.md` §3): on the dark canvas only blue/orange/aqua clear the
all-pairs CVD floor, and a graph is inherently all-pairs. The nine node
types therefore share three fills and are disambiguated by *shape*, which
the frontend derives from `type` via the same table shape as this one.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

#: `dataflow` id prefixes that denote a node type. Anything without one of
#: these prefixes is a module or a symbol within a module.
PREFIX_TYPES = (
    "process",
    "entity",
    "table",
    "route",
    "config",
    "library",
    "migration",
    "port",
)

MODULE_TYPE = "module"

#: Three colour families (`ATLAS_REDESIGN.md` §3's table). Code reaches
#: through runtime surfaces into persistent state -- that ordering is the
#: story the canvas is meant to tell, so it is also the legend's order.
FAMILY_OF_TYPE = {
    "module": "code",
    "library": "code",
    "process": "runtime",
    "route": "runtime",
    "port": "runtime",
    "table": "state",
    "entity": "state",
    "migration": "state",
    "config": "state",
    # L3-only type buckets inherit their members' family.
    "package": "code",
}

TYPE_ORDER = (
    "package",
    "module",
    "library",
    "process",
    "route",
    "port",
    "table",
    "entity",
    "migration",
    "config",
)

TYPE_LABEL = {
    "package": "package",
    "module": "module",
    "library": "external library",
    "process": "process",
    "route": "HTTP route",
    "port": "port",
    "table": "table",
    "entity": "entity",
    "migration": "migration",
    "config": "config key",
}

#: L3 bucket names for the node types that have no code package of their own.
#: A `table:` or `config:` id is not "in" a package -- rolling it into one
#: would invent an ownership the store never recorded -- so each becomes its
#: own super-node. This is what keeps the code -> boundary -> state story
#: legible at L3 instead of collapsing it into intra-package self-loops.
BUCKET_OF_TYPE = {
    "process": "Processes",
    "entity": "Entities",
    "table": "Tables",
    "route": "Routes",
    "config": "Config",
    "library": "Libraries",
    "migration": "Migrations",
    "port": "Ports",
}

TYPE_OF_BUCKET = {bucket: kind for kind, bucket in BUCKET_OF_TYPE.items()}

_SEGMENT_SPLIT = re.compile(r"[./]")


def split_prefix(raw_id: str) -> "tuple[Optional[str], str]":
    """`"table:churn_cache"` -> `("table", "churn_cache")`;
    `"cdp.cli"` -> `(None, "cdp.cli")`. A colon that isn't one of
    `PREFIX_TYPES` (a Windows drive letter, a `GET /x` route body) is left in
    the remainder rather than guessed at."""
    prefix, sep, rest = raw_id.partition(":")
    if sep and prefix in PREFIX_TYPES:
        return prefix, rest
    return None, raw_id


def type_of(raw_id: str) -> str:
    prefix, _ = split_prefix(raw_id)
    return prefix or MODULE_TYPE


def package_of(raw_id: str) -> str:
    """The L3 super-node `raw_id` rolls into: its first path segment when it
    is a module/symbol, otherwise its type's bucket."""
    prefix, rest = split_prefix(raw_id)
    if prefix is not None:
        return BUCKET_OF_TYPE.get(prefix, prefix)
    head = _SEGMENT_SPLIT.split(rest.split("#")[0])[0]
    return head or rest


def package_type(group: str, members: Iterable[str]) -> str:
    """A type bucket keeps its own type (so `Tables` still renders as a table
    and still reads aqua); a code package gets the synthetic `package` type."""
    kind = TYPE_OF_BUCKET.get(group)
    if kind is not None:
        return kind
    return "package"


def package_label(group: str) -> str:
    return group


def short_label(raw_id: str) -> str:
    """What the canvas prints next to a node. Full dotted paths are unreadable
    at graph scale, so the label is the last one or two segments; the full id
    stays on the node for the peek card and the inspector."""
    prefix, rest = split_prefix(raw_id)
    if prefix in ("route", "config", "port", "migration"):
        return rest
    if prefix == "library":
        return rest.split(".")[-1] if "." in rest else rest
    base, _, member = rest.partition("#")
    segments = [s for s in _SEGMENT_SPLIT.split(base) if s]
    tail = ".".join(segments[-2:]) if len(segments) > 1 else (segments[-1] if segments else rest)
    return "%s#%s" % (tail, member) if member else tail


def legend_types(types: Iterable[str]) -> List[str]:
    present = set(types)
    return [kind for kind in TYPE_ORDER if kind in present]
