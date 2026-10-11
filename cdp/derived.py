"""The scan's own claims as one patch -- built the same way by `scan` and `refresh`, so a
refreshed index holds exactly the derived claims a fresh scan of that commit would."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .derive import derive_claims
from .inventory import ROOT_MODULE as ROOT_MODULE_LABEL
from .schema import Validator, schema_path, validate_patch
from .session import new_run_id, next_generation, stamp_claims
from .util import CdpError, SKILL_ROOT


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
                        "%d untracked source file(s) on disk dwarf its %d tracked file(s); they are generated "
                        "at build time, so its public surface cannot be read from the repository."
                        % (module.get("generated_files", 0), module["files"])
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


def build_derived_patch(repo: Path, inventory: Dict, extraction: Dict, graph: Dict, xref: Dict,
                        part: Dict, flow: Dict, existing_patches: List[Dict]) -> Dict:
    """The derived patch for the tree described by these artifacts (not yet written)."""
    derived = derive_claims(repo, inventory, extraction, graph, xref, part, flow)
    stamp_claims(derived, inventory["head"])
    patch = {
        "schema_version": "1.0.0",
        "node": "root",
        "run_id": new_run_id(inventory["head"]),
        "author_kind": "python",
        "status": "complete",
        "generation": next_generation(existing_patches, "root"),
        "claims": derived,
        "unknowns": structural_unknowns(inventory, xref, graph),
    }
    errors = validate_patch(patch, Validator.load(schema_path(SKILL_ROOT)))
    if errors:
        raise CdpError("derived claims failed their own schema:\n  " + "\n  ".join(errors[:10]))
    return patch
