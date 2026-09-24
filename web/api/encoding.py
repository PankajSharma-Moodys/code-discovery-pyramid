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

import bisect
import re
from typing import Dict, Iterable, List, Optional

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
    "config-file",
    "sql",
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
    # `config-file:`/`sql:` ids name the *file* that reads a config key or
    # persists to a table, not the key/table itself -- a source location,
    # like a module, not a boundary or state surface.
    "config-file": "code",
    "sql": "code",
    # L3-only type buckets inherit their members' family.
    "package": "code",
}

TYPE_ORDER = (
    "package",
    "module",
    "library",
    "config-file",
    "sql",
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
    "config-file": "config file",
    "sql": "SQL script",
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
    # Fallback only -- `resolve_owner_file` resolves both of these directly
    # from the id itself (see `PATH_LITERAL_PREFIXES` below), so a real
    # request should essentially never fall back to this bucket.
    "config-file": "Config Files",
    "sql": "SQL Scripts",
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


def package_of(raw_id: str, depth: int = 1) -> str:
    """The super-node `raw_id` rolls into at a given path `depth`: its first
    `depth` path segments when it is a module/symbol, otherwise its type's
    bucket (buckets have no path, so `depth` never affects them -- a `table:`
    or `route:` id rolls into the same bucket at every rung). `depth=1` is
    the original L3 behaviour and stays the default so every existing caller
    is unaffected.

    A bare id with fewer than `depth` segments clamps to all of them, which
    is what lets asymmetric-depth subtrees (one submodule six folders deep,
    another flat) work without special-casing: a shallow branch just stops
    changing group past its own segment count."""
    prefix, rest = split_prefix(raw_id)
    if prefix is not None:
        return BUCKET_OF_TYPE.get(prefix, prefix)
    segments = [s for s in _SEGMENT_SPLIT.split(rest.split("#")[0]) if s]
    if not segments:
        return rest
    return ".".join(segments[:depth])


def is_descendant(raw_id: str, ancestor_group: str) -> bool:
    """Whether `raw_id` falls under the group `ancestor_group` names, at
    whatever depth that group was produced -- derived from the group's own
    segment count rather than a depth passed in separately, so a scope minted
    at any rung can restrict any deeper one. Replaces two previously separate
    scope-matching rules (`_build_graph_l2`'s `package_of(id) == scope` and
    `_restrict_to_neighborhood`'s exact-id match) with one."""
    prefix, rest = split_prefix(raw_id)
    if prefix is not None:
        return BUCKET_OF_TYPE.get(prefix, prefix) == ancestor_group
    if ancestor_group in TYPE_OF_BUCKET:
        return False
    ancestor_segments = [s for s in _SEGMENT_SPLIT.split(ancestor_group) if s]
    segments = [s for s in _SEGMENT_SPLIT.split(rest.split("#")[0]) if s]
    return segments[: len(ancestor_segments)] == ancestor_segments


#: Ceiling a rung's group count is allowed to reach before `real_depths` stops
#: descending further -- the same comfort threshold the frontend already
#: documents for L2 (`graphEncoding.ts`'s `ROLE_HIDE_CLIENT_THRESHOLD`
#: neighbourhood, and the 353-node L2 this repo itself renders today). Not a
#: hard technical limit, just the point past which another rung buys more
#: clicks than it saves.
RUNG_SIZE_CEILING = 350


def real_depths(raw_ids: Iterable[str], size_ceiling: int = RUNG_SIZE_CEILING, max_depth: int = 8) -> List[int]:
    """Which depths, starting from 1, are a real fork in the path tree --
    i.e. produce a grouping genuinely different from the depth before it.
    Depth 1 (`"L3"`) is always included, matching today's ladder exactly for
    a repo with no deeper structure. Buckets are excluded from the
    comparison: they never fork by depth and must not skew the decision."""
    bare_ids = [raw_id for raw_id in raw_ids if type_of(raw_id) == MODULE_TYPE]
    depths = [1]
    prev_groups = {raw_id: package_of(raw_id, 1) for raw_id in bare_ids}
    for depth in range(2, max_depth + 1):
        sizes: dict = {}
        for group in prev_groups.values():
            sizes[group] = sizes.get(group, 0) + 1
        if sizes and max(sizes.values()) <= size_ceiling:
            break
        groups = {raw_id: package_of(raw_id, depth) for raw_id in bare_ids}
        by_parent: dict = {}
        for raw_id, parent in prev_groups.items():
            by_parent.setdefault(parent, set()).add(groups[raw_id])
        if not any(len(children) > 1 for children in by_parent.values()):
            break
        depths.append(depth)
        if all(groups[raw_id] == raw_id for raw_id in bare_ids):
            break
        prev_groups = groups
    return depths


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


# ----------------------------------------------------------------------
# Path-based container hierarchy (`WEB_REDESIGN_RESEARCH.md` §3.1).
#
# `package_of`/`real_depths` above group a node by segments of its own *id*
# string. That is the wrong key on a repo whose ids are bare class names with
# no dots (`AccessController`) -- every node becomes its own single-member
# "package" (823 of them on `unified-store`'s real index), while the 6-7
# modules a user actually expects (`sql-pool`, `service-api`, ...) only exist
# as directory names in `inventory.files`/`xref.symbols[...].sites[0].file`,
# which the id-based grouping never consults. These functions group by that
# resolved file path instead. Kept separate from `package_of`/`real_depths`
# (rather than changed in place) so the existing dotted-id contract and its
# tests stay intact -- this is an additional, correct grouping key, not a
# breaking change to the old one.

#: Dataflow edge channels that mean "the source/target of this edge is the
#: file that owns the *other* endpoint" -- the only two named in the doc.
#: Anything else (`call`, `persist`, `process_boundary`, `read`, ...) isn't an
#: ownership signal and is ignored for this purpose.
OWNER_CHANNELS = ("schema_own", "http_in")

#: Group for a file with no directory of its own (a root-level file sitting
#: beside real subdirectories) -- one shared group, not a dropped node and not
#: a singleton per file (`MONOREPO_HIERARCHY.md` §5's boundary case).
ROOT_GROUP = "(root)"

#: Prefixes whose `rest` (the part after the colon) *is* a literal file path,
#: verified against the real `unified-store` index
#: (`WEB_REDESIGN_RESEARCH.md` follow-up): `config-file:.github/workflows/
#: feature_flag_check.yml` and `sql:ms-sql-java/downgrade-processor/.../
#: Rollback_V21_to_V18.sql` both carry the owning file directly in the id, so
#: no `xref`/edge lookup is needed or possible (these ids don't back an
#: `xref` symbol at all).
PATH_LITERAL_PREFIXES = ("config-file", "sql")


def build_owner_edge_map(edges: Iterable[dict], symbol_table: dict) -> Dict[str, str]:
    """Precomputes, in a single O(edges) pass, what `resolve_owner_file`'s
    typed-node fallback branch would otherwise re-derive by re-scanning all of
    `edges` for *every* typed node (`table:`/`route:`/...) -- an O(nodes ×
    edges) cost that profiling against the real `unified-store` index showed
    consuming 96% of a `/api/graph` request (7.9s of 8.2s). Preserves the
    original loop's exact "first resolvable owning edge in list order wins"
    semantics: both endpoints of each edge are considered, in the same
    target-then-source priority the original per-node scan used, and
    `setdefault` (via the `in` guard) ensures an id already resolved by an
    earlier edge is never overwritten by a later one."""
    owner_by_id: Dict[str, str] = {}
    for edge in edges:
        kind = edge.get("kind") or edge.get("channel")
        if kind not in OWNER_CHANNELS:
            continue
        src, tgt = edge.get("source"), edge.get("target")
        for typed, other in ((tgt, src), (src, tgt)):
            if typed is None or other is None or typed in owner_by_id:
                continue
            if split_prefix(other)[0] is not None:
                continue  # only a bare/module owner counts, not another bucket
            sym = symbol_table.get(other)
            if sym and sym.get("sites"):
                owner_by_id[typed] = sym["sites"][0].get("file")
    return owner_by_id


def resolve_owner_file(
    raw_id: str,
    symbol_table: dict,
    edges: Iterable[dict],
    sorted_symbol_keys: Optional[List[str]] = None,
    owner_edge_map: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """The file `raw_id` should be grouped under. A bare/module id resolves
    directly through its own `xref` symbol site, same lookup
    `_dataflow_graph` already does for `role`; failing that, it falls back to
    the nearest resolvable dotted-prefix *descendant* (a namespace-aggregate
    id like `RMS.UnifiedStore.Core.App` with no symbol of its own, but whose
    leaf members do) via a bounded `bisect` prefix probe over
    `sorted_symbol_keys` -- first match, not a majority vote across every
    descendant, but a strict improvement over "always a singleton." A
    `config-file:`/`sql:` id resolves straight from its own suffix
    (`PATH_LITERAL_PREFIXES`), no lookup at all. Any other `type:`-prefixed id
    (`table:`/`route:`/...) has no file of its own -- it resolves through
    whichever edge `schema_own`s/`http_in`s it, taking the *other* endpoint's
    file, one hop only (a table owned by a table has nothing sensible to
    resolve further). `None` when nothing owns it -- the caller falls back to
    the type's global bucket, exactly as before this existed."""
    prefix, rest = split_prefix(raw_id)
    if prefix in PATH_LITERAL_PREFIXES:
        return rest or None
    if prefix is None:
        sym = symbol_table.get(raw_id)
        if sym and sym.get("sites"):
            return sym["sites"][0].get("file")
        keys = sorted_symbol_keys if sorted_symbol_keys is not None else sorted(symbol_table)
        probe = raw_id + "."
        i = bisect.bisect_left(keys, probe)
        if i < len(keys) and keys[i].startswith(probe):
            descendant = symbol_table.get(keys[i])
            if descendant and descendant.get("sites"):
                return descendant["sites"][0].get("file")
        return None
    if owner_edge_map is not None:
        return owner_edge_map.get(raw_id)
    for edge in edges:
        kind = edge.get("kind") or edge.get("channel")
        if kind not in OWNER_CHANNELS:
            continue
        src, tgt = edge.get("source"), edge.get("target")
        if tgt == raw_id:
            other = src
        elif src == raw_id:
            other = tgt
        else:
            continue
        if other is None or split_prefix(other)[0] is not None:
            continue  # only a bare/module owner counts, not another bucket
        sym = symbol_table.get(other)
        if sym and sym.get("sites"):
            return sym["sites"][0].get("file")
    return None


def path_group_of(path: str, depth: int = 1) -> str:
    """The container `path` rolls into at path-prefix depth `depth`: its
    first `depth` *directory* segments (the filename itself is never a
    segment), clamped the same way `package_of` clamps a shallow id. A
    root-level file (no directory) always returns `ROOT_GROUP`, at every
    depth, so it attaches to one shared root container instead of vanishing
    or becoming its own singleton group."""
    idx = path.rfind("/")
    directory = path[:idx] if idx >= 0 else ""
    segments = [s for s in directory.split("/") if s]
    if not segments:
        return ROOT_GROUP
    return "/".join(segments[:depth])


def container_group(raw_id: str, depth: int, file_of: "dict[str, Optional[str]]") -> str:
    """The super-node `raw_id` rolls into at `depth`, file-path aware: if
    `raw_id` resolves to an owning file (`file_of`, built once per request by
    `resolve_owner_file`), it groups exactly like a bare module at that
    directory depth -- this is what makes a `table:`/`route:` id a *child* of
    the container that owns it instead of a global peer bucket
    (`WEB_REDESIGN_RESEARCH.md` §3.1 point 3). Only an id with no resolvable
    owner falls back to the old global type bucket; a bare id with no
    resolvable file of its own (no `xref` symbol) falls back to a singleton
    group of itself, same as an id nothing else groups it with today."""
    path = file_of.get(raw_id)
    if path:
        return path_group_of(path, depth)
    prefix, _ = split_prefix(raw_id)
    if prefix is not None:
        return BUCKET_OF_TYPE.get(prefix, prefix)
    return raw_id


def container_descendant(raw_id: str, ancestor_group: str, file_of: "dict[str, Optional[str]]") -> bool:
    """Whether `raw_id` falls under the container `ancestor_group` names, at
    whatever depth that group was produced -- the file-path equivalent of
    `is_descendant`, reusing `container_group` itself so the two can never
    drift apart: `raw_id` descends from `ancestor_group` exactly when
    `raw_id`'s own group *at `ancestor_group`'s depth* is that same group."""
    depth = len(ancestor_group.split("/"))
    return container_group(raw_id, depth, file_of) == ancestor_group


def real_container_depths(
    id_to_path: "dict[str, str]", size_ceiling: int = RUNG_SIZE_CEILING, max_depth: int = 8
) -> List[int]:
    """`real_depths`'s fork-detection algorithm (a rung is only added when it
    produces a genuinely different, still-too-big grouping), over resolved
    file-path directory prefixes instead of a bare id's own dotted segments.
    `id_to_path` should hold only ids that actually resolved to a file
    (`container_group`'s bucket-fallback ids don't fork by depth and would
    only skew the decision, same reasoning `real_depths` already applies to
    prefixed ids). The existing "no real fork -> stop" rule already implements
    `MONOREPO_HIERARCHY.md` §2's pass-through-directory collapse structurally:
    a single-child directory chain never forks, so depths never advance past
    it -- no separate collapse pass is needed."""
    ids = list(id_to_path)
    depths = [1]
    prev_groups = {raw_id: path_group_of(id_to_path[raw_id], 1) for raw_id in ids}
    for depth in range(2, max_depth + 1):
        sizes: dict = {}
        for group in prev_groups.values():
            sizes[group] = sizes.get(group, 0) + 1
        if sizes and max(sizes.values()) <= size_ceiling:
            break
        groups = {raw_id: path_group_of(id_to_path[raw_id], depth) for raw_id in ids}
        by_parent: dict = {}
        for raw_id, parent in prev_groups.items():
            by_parent.setdefault(parent, set()).add(groups[raw_id])
        if not any(len(children) > 1 for children in by_parent.values()):
            break
        depths.append(depth)
        prev_groups = groups
    return depths
