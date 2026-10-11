"""Per-claim screening of a leaf patch (L4, L15, K2): a bad claim is rejected on its own and
the rest of the patch is kept. Runs before the whole-patch schema check, at both entry points
(`collect` and `run`)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import factcheck
from .gates import build_extraction_index
from .schema import Validator, validate_patch
from .util import read_lines

#: What a test file cannot establish: how production code behaves toward the outside.
PRODUCTION_KINDS = ("side_effect", "data_model", "entrypoint", "public_api", "config", "deployable", "dependency")

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class Context:
    """What a dispatched scope may claim about: its files, the subjects CDP knows, which files are tests."""

    def __init__(self, scope: Optional[Dict], scope_nodes: Set[str], inventory: Dict, extraction: Dict,
                 xref: Dict, node: str, repo: Path) -> None:
        self.node, self.repo = node, Path(repo)
        self.files: Optional[Set[str]] = set(scope["files"]) if scope else None
        self.tests = {f["path"] for f in inventory.get("files", []) if f.get("role") == "test"}
        defs, edges, _ = build_extraction_index(extraction)
        self.subjects = set(defs) | set(edges) | set(scope_nodes) | set((xref or {}).get("symbols", {}))
        self.def_files = {d["fqn"]: d.get("file") for d in (extraction or {}).get("defines", []) if d.get("fqn")}
        self.facts = factcheck.Facts(extraction)
        self._text: Dict[str, str] = {}

    @classmethod
    def of_store(cls, store, node: str, repo: Path) -> "Context":
        scopes = {s["node"]: s for s in store.partition["scopes"]}
        return cls(scopes.get(node), set(scopes), store.inventory, store.extraction, store.xref, node, repo)

    def text(self, rel: str) -> str:
        if rel not in self._text:
            try:
                self._text[rel] = "\n".join(read_lines(self.repo / rel))
            except (OSError, UnicodeDecodeError):
                self._text[rel] = ""
        return self._text[rel]

    def subject_resolves(self, subject: str, files: List[str]) -> bool:
        """A known symbol, route, table or scope; or a name the cited files actually contain."""
        if subject in self.subjects:
            return True
        tail = _TOKEN.findall(subject)
        return bool(tail) and any(tail[-1] in self.text(f) for f in files)


def screen_claims(patch, validator: Validator, ctx: Context) -> Tuple[Dict, List[Dict]]:
    """`(patch with the bad claims removed, [{id, reasons}])`. A patch that is not an object with a
    list of claims is returned untouched for the whole-patch check to reject."""
    if not isinstance(patch, dict) or not isinstance(patch.get("claims"), list):
        return patch, []
    kept, dropped = [], []
    for i, claim in enumerate(patch["claims"]):
        reasons = _claim_problems(patch, claim, validator, ctx)
        if reasons:
            dropped.append({"id": claim.get("id") if isinstance(claim, dict) else None, "reasons": reasons})
        else:
            kept.append(claim)
    return dict(patch, claims=kept), dropped


def _claim_problems(patch: Dict, claim, validator: Validator, ctx: Context) -> List[str]:
    if not isinstance(claim, dict):
        return ["a claim is a JSON object, got %s" % type(claim).__name__]
    probe = {k: v for k, v in patch.items() if k not in ("claims", "unknowns", "defines", "uses", "io_edges")}
    probe.update(claims=[claim], unknowns=[])
    own = [e for e in validate_patch(probe, validator) if e.startswith("/claims[0]")]
    if own:
        return [e.replace("/claims[0]", "") .strip("/") or e for e in own[:3]]
    files = [str(a.get("file")) for a in claim.get("evidence") or [] if isinstance(a, dict)]
    reasons: List[str] = []
    if ctx.files is not None and not claim.get("pending_resolution"):
        outside = sorted({f for f in files if f not in ctx.files})
        if outside:
            reasons.append("evidence outside the dispatched scope %s: %s" % (ctx.node, ", ".join(outside[:3])))
    subject = str(claim.get("subject") or "")
    if not reasons and not ctx.subject_resolves(subject, files):
        reasons.append("subject %r names nothing CDP indexed and appears in none of the cited files" % subject)
    if not reasons and files and all(f in ctx.tests for f in files):
        home = ctx.def_files.get(subject)
        if home and home not in ctx.tests:
            reasons.append("a test file cannot support a claim about production code (%s is defined in %s)"
                           % (subject, home))
        elif claim.get("kind") in PRODUCTION_KINDS and not (home and home in ctx.tests):
            reasons.append("a %s claim about production behaviour is cited only from test files (%s)"
                           % (claim.get("kind"), ", ".join(sorted(set(files))[:3])))
    if not reasons and factcheck.asserts_persistence(str(claim.get("statement") or "")):
        fqn = subject[len("entity:"):] if subject.startswith("entity:") else subject
        home = ctx.def_files.get(fqn)
        if fqn in ctx.def_files and factcheck.wire_type(subject, home, ctx.facts):
            reasons.append("%s is a wire/DTO type with no @Entity, @Table or repository binding in the index; "
                           "it is not persisted" % fqn)
    return reasons
