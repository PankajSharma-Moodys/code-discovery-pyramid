"""`cdp export` (Phase 7, M7.5/0.19) -- four fixed output shapes, not a
general-purpose transform:

- **json**: every artifact/report, written through `FileStore`'s own
  interface -- R1 in practice ("files are an export format, not a storage
  format"): the destination is a real `FileStore` root afterward, readable by
  the same golden/conformance code that reads any other backend.
- **patches**: one reviewable file per patch, in log order -- for a human,
  never read back by CDP.
- **archive**: raw `claim_patches_archive` rows -- needs a backend that has
  one (M7.3).
- **anonymized**: claims/unknowns/conflicts with every path, subject and
  statement replaced by a stable per-corpus hash token.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from .store import ARTIFACTS, REPORTS, WorkspaceStore
from .store.file_backend import FileStore
from .util import CdpError


def export_json(store: WorkspaceStore, dest: Path) -> List[str]:
    dest.mkdir(parents=True, exist_ok=True)
    target = FileStore(dest)
    written = []
    for name in ARTIFACTS:
        if store.has_artifact(name):
            target.write_artifact(name, store.read_artifact(name))
            written.append(name)
    for name in REPORTS:
        # `default=None` to `read_report` means "no default", not "default
        # None" (`WorkspaceStore.read_report`'s own docstring) -- a report a
        # `scan` never wrote (e.g. no `collect` ever ran) is absent, not an
        # export failure, so the miss is caught rather than propagated.
        try:
            data = store.read_report(name, default={})
        except CdpError:
            continue
        if data:
            target.write_report(name, data)
            written.append("reports/%s" % name)
    return written


def _patch_filename(index: int, patch: Dict) -> str:
    label = patch.get("node") or patch.get("label") or patch.get("id") or "patch"
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(label))
    return "%04d-%s.json" % (index, safe)


def export_patches(store: WorkspaceStore, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    patches = store.load_patches()
    for i, patch in enumerate(patches):
        path = dest / _patch_filename(i, patch)
        path.write_text(json.dumps(patch, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return len(patches)


def export_archive(store: WorkspaceStore, dest: Path, partition: Dict = None) -> int:
    rows = store.dump_archive(partition)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "archive.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return len(rows)


def _token(prefix: str, value: str) -> str:
    return "%s_%s" % (prefix, hashlib.sha1(value.encode("utf-8")).hexdigest()[:12])


def _anon(cache: Dict[str, str], prefix: str, value: str) -> str:
    key = "%s:%s" % (prefix, value)
    if key not in cache:
        cache[key] = _token(prefix, value)
    return cache[key]


# Every free-text field CDP's claim/unknown/conflict shapes actually use for
# a subject, a statement, or a node/scope name (`schema/patch-1.0.0.json`,
# `cdp/merge.py`'s conflict record) -- scrubbed by field name, not by
# sniffing content, so a new field defaults to *kept* rather than *leaked*
# only if someone also forgets to add it here (the same posture R6 takes:
# name what is covered, don't assume coverage).
_TEXT_FIELDS = ("subject", "statement", "question", "why_unresolved")
_TEXT_LIST_FIELDS = ("statements",)
_NODE_FIELDS = ("source_node", "demoted_from")
_NODE_LIST_FIELDS = ("nodes", "contested_with", "source_nodes")


def _scrub_record(record: Dict, cache: Dict[str, str]) -> Dict:
    """Replace every path/subject/free-text field with a stable per-corpus
    token. `evidence` is dropped entirely -- it quotes the source file
    verbatim, which is exactly the leak the test checks for."""
    out = dict(record)
    for key in _TEXT_FIELDS:
        if out.get(key):
            out[key] = _anon(cache, "text", out[key])
    for key in _TEXT_LIST_FIELDS:
        if out.get(key):
            out[key] = [_anon(cache, "text", v) for v in out[key]]
    for key in _NODE_FIELDS:
        if out.get(key):
            out[key] = _anon(cache, "node", out[key])
    for key in _NODE_LIST_FIELDS:
        if out.get(key):
            out[key] = [_anon(cache, "node", v) for v in out[key]]
    anchor = out.get("anchor")
    if isinstance(anchor, dict) and anchor.get("file"):
        out["anchor"] = {"file": _anon(cache, "file", anchor["file"]), "line": anchor.get("line")}
    out.pop("evidence", None)
    return out


def export_anonymized(store: WorkspaceStore, dest: Path) -> Dict[str, int]:
    dest.mkdir(parents=True, exist_ok=True)
    state = store.read_artifact("state", {})
    cache: Dict[str, str] = {}
    scrubbed = {
        section: [_scrub_record(r, cache) for r in state.get(section, [])]
        for section in ("claims", "unknowns", "conflicts")
    }
    (dest / "corpus.json").write_text(
        json.dumps(scrubbed, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return {k: len(v) for k, v in scrubbed.items()}
