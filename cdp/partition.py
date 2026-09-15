"""Phase 3b — budget-driven partitioning (§3.3).

Leaf scope is a function of *content*, not of directory nesting, because content
is what determines whether an agent's context rots. A directory over either
budget splits into its children; a directory under both becomes a leaf.

**Every tracked file belongs to exactly one leaf, including the files that
belong to no module.** `settings.gradle`, the root `build.gradle`, Dockerfiles
and CI definitions sit outside every module directory and would otherwise be
partitioned into nothing. That is not a tidiness rule: `rootProject.name = 'spm'`
— the fact RESEARCH.md opens with — lives in `settings.gradle` and in no module,
and parents are forbidden from re-reading source, so under a partition with no
root scope *no agent in the pipeline would ever read the file containing the
document's own motivating example.*

`assert_partition` enforces the exactly-one property mechanically. It is called
on every run, not only in tests, because a partition that silently drops files
produces a coverage figure that lies.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .inventory import ROOT_MODULE
from .util import CdpError

DEFAULT_MAX_FILES = 40
DEFAULT_MAX_LOC = 6000
DEFAULT_MAX_INHERITED = 200


def partition(
    inventory: Dict,
    max_files: int = DEFAULT_MAX_FILES,
    max_loc: int = DEFAULT_MAX_LOC,
) -> Dict:
    by_module: Dict[str, List[Dict]] = {}
    for f in inventory["files"]:
        by_module.setdefault(f["module"], []).append(f)

    # A module's *name* and its *path prefix* are not the same string. They
    # coincide for a module found by its sub-manifest, whose name is its
    # directory — but a single-module repository is named by its manifest
    # (`my-service`) while its files sit at the repository root. Deriving the
    # prefix from the name would look for `my-service/...` and split nothing.
    path_of = {m["name"]: m["path"] for m in inventory["modules"]}

    scopes: List[Dict] = []
    for module in sorted(by_module):
        files = sorted(by_module[module], key=lambda f: f["path"])
        node = "root" if module == ROOT_MODULE else "root/" + module
        path = path_of.get(module, "" if module == ROOT_MODULE else module)
        prefix = (path + "/") if path else ""
        _cut(node, module, prefix, files, max_files, max_loc, scopes)

    scopes = _coalesce(scopes, max_files, max_loc)
    scopes = _pack_siblings(scopes, max_files, max_loc)
    scopes.sort(key=lambda s: s["node"])
    assert_partition(inventory, scopes)
    return {
        "budgets": {"max_files": max_files, "max_loc": max_loc},
        "scopes": scopes,
        "totals": {
            "scopes": len(scopes),
            "oversized": sum(1 for s in scopes if s["oversized"]),
            "files": sum(s["file_count"] for s in scopes),
        },
    }


def _cut(
    node: str,
    module: str,
    prefix: str,
    files: List[Dict],
    max_files: int,
    max_loc: int,
    out: List[Dict],
) -> None:
    loc = sum(f["loc"] for f in files)
    if not files:
        return
    if len(files) <= max_files and loc <= max_loc:
        out.append(_scope(node, module, files, oversized=False))
        return

    # Split on the next path segment below `prefix`.
    here: List[Dict] = []
    groups: Dict[str, List[Dict]] = {}
    for f in files:
        rest = f["path"][len(prefix):] if prefix else f["path"]
        if "/" not in rest:
            here.append(f)
        else:
            groups.setdefault(rest.split("/", 1)[0], []).append(f)

    if not groups:
        # A single directory that exceeds the budget and cannot be split
        # further. Emitted whole and flagged, because dropping files to fit a
        # budget would silently reduce coverage.
        out.append(_scope(node, module, files, oversized=True))
        return

    if here:
        out.append(_scope(node + "/(files)", module, here, oversized=False))
    for name in sorted(groups):
        _cut(node + "/" + name, module, prefix + name + "/", groups[name], max_files, max_loc, out)


def _coalesce(scopes: List[Dict], max_files: int, max_loc: int) -> List[Dict]:
    """Merge sibling scopes back together while they still fit the budget.

    The top-down cut is correct but wasteful: a directory one file over budget
    splits into every child it has, and a package with a single exception class
    becomes a leaf of its own. Each such leaf pays the full ~8k-token fixed
    protocol prompt from Appendix B to describe one file, and — worse for the
    output — a one-file scope has no context in which to say anything
    interesting about that file.

    Merging bottom-up is safe because scopes form a tree partition: the children
    of a node are exactly the scopes whose path lies below it, so replacing a
    complete set of children with their parent moves no file between scopes and
    the exactly-once invariant is preserved by construction.
    """
    by_node = {s["node"]: s for s in scopes}
    changed = True
    while changed:
        changed = False
        parents = sorted(
            {n.rsplit("/", 1)[0] for n in by_node if "/" in n},
            key=lambda p: -p.count("/"),
        )
        for parent in parents:
            children = [n for n in by_node if n.startswith(parent + "/")]
            if len(children) < 2 and parent not in by_node:
                pass
            group = children + ([parent] if parent in by_node else [])
            if len(group) < 2:
                continue
            # Never merge across modules. On a small repository every module
            # fits the budget and they all share `root` as a parent, so without
            # this guard the whole repository collapses into one scope — which
            # discards the dependency order the scheduler exists to respect and
            # hands the deepest module none of the facts it depends on.
            if len({by_node[n]["module"] for n in group}) > 1:
                continue
            files = sum(by_node[n]["file_count"] for n in group)
            loc = sum(by_node[n]["loc"] for n in group)
            if files > max_files or loc > max_loc:
                continue
            if any(by_node[n]["oversized"] for n in group):
                continue
            merged_files: List[str] = []
            languages: Dict[str, int] = {}
            roles: Dict[str, int] = {}
            module = by_node[group[0]]["module"]
            for n in group:
                merged_files.extend(by_node[n]["files"])
                for k, v in by_node[n]["by_language"].items():
                    languages[k] = languages.get(k, 0) + v
                for k, v in by_node[n]["by_role"].items():
                    roles[k] = roles.get(k, 0) + v
                del by_node[n]
            by_node[parent] = {
                "node": parent,
                "module": module,
                "files": sorted(merged_files),
                "file_count": files,
                "loc": loc,
                "by_language": dict(sorted(languages.items(), key=lambda kv: (-kv[1], kv[0]))),
                "by_role": dict(sorted(roles.items(), key=lambda kv: (-kv[1], kv[0]))),
                "oversized": False,
            }
            changed = True
            break
    return list(by_node.values())


def _pack_siblings(scopes: List[Dict], max_files: int, max_loc: int) -> List[Dict]:
    """Bin-pack small siblings that could not all fit under their shared parent.

    `_coalesce` can only merge a *complete* set of children, so a package that
    is 27 files over budget leaves its one-file `exceptions/` subpackage as a
    leaf of its own. Packing the small siblings together fixes that without
    moving any file across a parent boundary.

    Packing is first-fit over siblings sorted by descending size — deterministic,
    and biased toward filling a bin before opening another, so the run ends up
    with a few well-fed leaves rather than many thin ones. A leaf holding one
    20-line exception class has no context in which to say anything worth
    citing; the fixed protocol prompt costs the same either way.
    """
    groups: Dict[str, List[Dict]] = {}
    for scope in scopes:
        groups.setdefault(scope["module"], []).append(scope)

    out: List[Dict] = []
    for module in sorted(groups):
        # Packing is confined to one module. Two modules that happen to be small
        # must not share a leaf: a scope carries a single module's DAG level
        # into the scheduler, so merging across modules would schedule the
        # deeper one too early and hand it none of the facts it depends on.
        members = groups[module]
        small = [
            s
            for s in members
            if not s["oversized"] and s["file_count"] * 2 <= max_files and s["loc"] * 2 <= max_loc
        ]
        if len(small) < 2:
            out.extend(members)
            continue
        small_nodes = {s["node"] for s in small}
        out.extend(s for s in members if s["node"] not in small_nodes)

        small.sort(key=lambda s: (-s["loc"], -s["file_count"], s["node"]))
        bins: List[List[Dict]] = []
        for scope in small:
            for slot in bins:
                if (
                    sum(x["file_count"] for x in slot) + scope["file_count"] <= max_files
                    and sum(x["loc"] for x in slot) + scope["loc"] <= max_loc
                ):
                    slot.append(scope)
                    break
            else:
                bins.append([scope])
        for slot in bins:
            out.append(_merge_scopes(slot) if len(slot) > 1 else slot[0])
    return out


def _common_prefix(nodes: List[str]) -> str:
    parts = [n.split("/") for n in nodes]
    shared: List[str] = []
    for chunk in zip(*parts):
        if len(set(chunk)) != 1:
            break
        shared.append(chunk[0])
    return "/".join(shared)


def _merge_scopes(slot: List[Dict]) -> Dict:
    slot = sorted(slot, key=lambda s: s["node"])
    parent = _common_prefix([s["node"] for s in slot])
    # Name from each member's own last segment, never from the path between the
    # shared prefix and the member: a Java package sitting eight directories
    # deep would otherwise produce a node id longer than the scope's file list.
    names = [s["node"].rsplit("/", 1)[-1].strip("()") or "." for s in slot]
    label = names[0] + ("+%d" % (len(names) - 1) if len(names) > 1 else "")
    files: List[str] = []
    languages: Dict[str, int] = {}
    roles: Dict[str, int] = {}
    for s in slot:
        files.extend(s["files"])
        for k, v in s["by_language"].items():
            languages[k] = languages.get(k, 0) + v
        for k, v in s["by_role"].items():
            roles[k] = roles.get(k, 0) + v
    return {
        "node": (parent + "/" if parent else "") + "(" + label + ")",
        "module": slot[0]["module"],
        "files": sorted(files),
        "file_count": len(files),
        "loc": sum(s["loc"] for s in slot),
        "by_language": dict(sorted(languages.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_role": dict(sorted(roles.items(), key=lambda kv: (-kv[1], kv[0]))),
        "oversized": False,
        "merged_from": [s["node"] for s in slot],
    }


def _scope(node: str, module: str, files: List[Dict], oversized: bool) -> Dict:
    paths = sorted(f["path"] for f in files)
    languages: Dict[str, int] = {}
    roles: Dict[str, int] = {}
    for f in files:
        languages[f["language"]] = languages.get(f["language"], 0) + 1
        roles[f["role"]] = roles.get(f["role"], 0) + 1
    return {
        "node": node,
        "module": module,
        "files": paths,
        "file_count": len(paths),
        "loc": sum(f["loc"] for f in files),
        "by_language": dict(sorted(languages.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_role": dict(sorted(roles.items(), key=lambda kv: (-kv[1], kv[0]))),
        "oversized": oversized,
    }


def assert_partition(inventory: Dict, scopes: Sequence[Dict]) -> None:
    """The partition must be a partition: every tracked file exactly once."""
    seen: Dict[str, str] = {}
    for scope in scopes:
        for path in scope["files"]:
            if path in seen:
                raise CdpError(
                    "partition is not a partition: %s claimed by both %s and %s"
                    % (path, seen[path], scope["node"])
                )
            seen[path] = scope["node"]
    tracked = {f["path"] for f in inventory["files"]}
    missing = tracked - set(seen)
    if missing:
        raise CdpError(
            "partition drops %d tracked file(s), e.g. %s"
            % (len(missing), ", ".join(sorted(missing)[:3]))
        )
    extra = set(seen) - tracked
    if extra:
        raise CdpError("partition invents %d untracked file(s)" % len(extra))


def summarise(part: Dict) -> List[str]:
    lines = [
        "partition %d scopes (budgets: %d files / %d loc)"
        % (part["totals"]["scopes"], part["budgets"]["max_files"], part["budgets"]["max_loc"])
    ]
    for scope in part["scopes"]:
        flag = "  OVERSIZED" if scope["oversized"] else ""
        lines.append("  %-52s %3d files %6d loc%s" % (scope["node"], scope["file_count"], scope["loc"], flag))
    return lines
