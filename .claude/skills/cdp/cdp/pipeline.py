"""The deterministic scan pipeline: inventory to folded state, no model calls."""

from __future__ import annotations

import datetime

from . import dataflow as dataflow_mod, graph as graph_mod, inventory as inventory_mod, partition as partition_mod, query as query_mod, refresh as refresh_mod, resolve as resolve_mod, schedule as schedule_mod, snapshot as snapshot_mod
from .derive import derive_claims
from .extract import run_extract
from .inventory import ROOT_MODULE as ROOT_MODULE_LABEL
from .schema import Validator, schema_path, validate_patch
from .session import Paths, extra_excludes, fold_and_write, new_run_id, next_generation, open_store, render_docs, stamp_claims
from .util import CDP_VERSION, CdpError, SKILL_ROOT
from typing import Callable, Dict, List, Optional, Sequence


def structural_unknowns(inventory: Dict, xref: Dict, graph: Dict) -> List[Dict]:
    out: List[Dict] = []
    root = inventory.get("root_module") or {}
    if root.get("is_module") and not root.get("named"):
        out.append(
            {
                "question": "What is this module called?",
                "why_unresolved": (
                    "The scan root holds a build manifest (%s) and no sub-manifests, so the "
                    "repository is one module — but the manifest states no name, and the "
                    "directory name is an artifact of where the repository was cloned rather "
                    "than the module's identity. It is reported as %s rather than guessed."
                    % (root.get("manifest") or "unreadable", ROOT_MODULE_LABEL)
                ),
            }
        )
    for row in graph.get("declared_ambiguous", []):
        out.append(
            {
                "question": "Which module does %s's declared dependency on '%s' point at?"
                % (row["from"], row["dep"]),
                "why_unresolved": (
                    "%d modules share the basename '%s' (%s). A build manifest names a "
                    "dependency by its short name, and picking one of two equally-supported "
                    "candidates would assert an edge the repository does not state, so no "
                    "declared edge is drawn."
                    % (len(row["candidates"]), row["dep"], ", ".join(row["candidates"]))
                ),
            }
        )
    if inventory["source"] == "walk":
        out.append(
            {
                "question": "Which files in this repository are generated rather than authored?",
                "why_unresolved": (
                    "The target is not a git repository, so the inventory came from a filesystem "
                    "walk with a heuristic exclude list. Generated and build-output files may be "
                    "present in the census and described as if they were design."
                ),
            }
        )
    for module in inventory["modules"]:
        if module.get("generated_suspect"):
            out.append(
                {
                    "question": "What contract does %s actually publish?" % module["name"],
                    "why_unresolved": (
                        "%d of its %d files are untracked and generated at build time, so its "
                        "public surface cannot be read from the repository."
                        % (module.get("on_disk", 0) - module["files"], module.get("on_disk", 0))
                    ),
                }
            )
    for route in xref["unresolved_routes"]:
        out.append(
            {
                "question": "What literal path does %s serve?" % route["route"],
                "why_unresolved": "Constant(s) %s are not defined anywhere in the repository."
                % ", ".join(route.get("unresolved_constants", [])),
                "anchor": route["evidence"][0],
            }
        )
    return out


def scan(
    paths: Paths,
    *,
    max_leaf_files: int,
    max_leaf_loc: int,
    max_concurrent: int,
    max_hops: int,
    workers: Optional[int] = None,
    exclude: Optional[Sequence[str]] = None,
    docs: bool = True,
    say: Callable[..., None] = lambda *a: None,
) -> Dict:
    """Run every deterministic phase and write the snapshot. Returns the run's
    id and head; everything else is in the store."""

    inventory = inventory_mod.build_inventory(paths.repo, extra_excludes=extra_excludes(paths.repo, exclude))
    say("\n".join(inventory_mod.summarise(inventory)))

    extraction = run_extract(paths.repo, inventory, workers=workers)
    say("extract   %d files parsed, %d symbols, %d edges, %d imports"
        % (extraction["totals"]["parsed_files"], extraction["totals"]["defines"],
           extraction["totals"]["io_edges"], extraction["totals"]["imports"]))

    graph = graph_mod.build_graph(inventory, extraction)
    say("\n".join(graph_mod.summarise(graph)))

    part = partition_mod.partition(inventory, max_leaf_files, max_leaf_loc)
    refresh_mod.annotate_scope_hashes(paths.repo, part)
    say("partition %d scopes (%d oversized)" % (part["totals"]["scopes"], part["totals"]["oversized"]))

    sched = schedule_mod.build_schedule(part, graph, max_concurrent)
    say("\n".join(schedule_mod.summarise(sched)))

    xref = resolve_mod.build_xref(inventory, extraction, graph)
    say("\n".join(resolve_mod.summarise(xref)))

    flow = dataflow_mod.build_dataflow(extraction, xref, graph, max_hops)
    say("\n".join(dataflow_mod.summarise(flow)))

    state_dir = paths.state
    store = open_store(paths)
    store.begin_snapshot(*snapshot_mod.resolve_snapshot(paths.repo, inventory["head"]))
    store.write_artifact("inventory", inventory)
    store.write_artifact("extract", extraction)
    store.write_artifact("graph", graph)
    store.write_artifact("partition", part)
    store.write_artifact("schedule", sched)
    store.write_artifact("xref", xref)
    store.write_artifact("dataflow", flow)

    # The derived claims are appended as patch 0000. They enter state through
    # the same log every agent patch does, so the fold invariant holds from the
    # first commit rather than being retrofitted once agents exist.
    derived = derive_claims(paths.repo, inventory, extraction, graph, xref, part, flow)
    stamp_claims(derived, inventory["head"])
    run_id = new_run_id(inventory["head"])
    patch = {
        "schema_version": "1.0.0",
        "node": "root",
        "run_id": run_id,
        "author_kind": "python",
        "status": "complete",
        "generation": next_generation(store.load_patches(), "root"),
        "claims": derived,
        "unknowns": structural_unknowns(inventory, xref, graph),
    }
    validator = Validator.load(schema_path(SKILL_ROOT))
    errors = validate_patch(patch, validator)
    if errors:
        raise CdpError("derived claims failed their own schema:\n  " + "\n  ".join(errors[:10]))

    # M2.3: the log holds `patch` exactly as derived, unverified. Verification
    # runs inside `fold`, against `paths.repo`, so it is re-runnable at a
    # different commit without mutating the log (`cdp/state.py` `fold`).
    store.write_derived_patch(patch)
    store.ensure_inbox()

    st = fold_and_write(store, xref, part, repo=paths.repo)
    verify_stats = st["verification"]
    say("verify    %d/%d derived claims anchored (%d demoted, rate %.3f)"
        % (verify_stats["claims_kept"], verify_stats["claims_in"],
           verify_stats["claims_demoted"], verify_stats["demotion_rate"]))
    say("merge     %d claims over %d subjects, %d conflicts, %d near-misses"
        % (len(st["claims"]), st["merge_stats"]["groups"],
           len(st["conflicts"]), len(st["near_misses"])))

    store.write_report("verify", verify_stats)
    store.write_report("conflicts", {"conflicts": st["conflicts"], "near_misses": st["near_misses"]})
    store.write_artifact(
        "manifest",
        {
            "cdp_version": CDP_VERSION,
            "run_id": run_id,
            "repo": str(paths.repo),
            "head": inventory["head"],
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "budgets": {
                "max_leaf_files": max_leaf_files,
                "max_leaf_loc": max_leaf_loc,
                "max_concurrent": max_concurrent,
                "max_hops": max_hops,
            },
            "module_level": sched["module_level"],
            "coverage": st["coverage"],
            "counts": inventory["counts"],
            # PLAN.md C2: tokens are not measurable under in-session execution.
            # This is: the exact source volume the run authorises agents to read.
            "source_loc_scheduled": sched["totals"]["source_loc_scheduled"],
            "note": (
                "manifest.json is the only state file containing a timestamp, and is excluded "
                "from the byte-identical reproducibility check for that reason."
            ),
        },
    )

    # §C item 1.2: docs were a separate command, so a rescan produced state and
    # no visible output, and the user-facing half of the module-detection bug
    # was invisible until someone remembered to run `cdp docs`. Rendering here
    # is the default; `--no-docs` opts out.
    if docs:
        written = render_docs(query_mod.Store(store), paths.work / "docs")
        say("docs      %d file(s) -> %s" % (len(written), paths.work / "docs"))

    say("\nstate     %s  (repo %s)" % (state_dir, paths.repo_id))
    say("next      cdp query stats | cdp query trace <entrypoint> | cdp prompts")
    store.close()
    return {"run_id": run_id, "head": inventory["head"]}
