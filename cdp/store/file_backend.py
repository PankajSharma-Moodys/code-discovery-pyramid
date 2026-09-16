"""`FileStore` — `WorkspaceStore` over today's directory-of-JSON-files layout.

The only backend until M2.2, and the one every other backend's conformance is
measured against. Paths are exactly what `cli.py` wrote before this module
existed, so a scan through `FileStore` is byte-identical to one before it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import WorkspaceStore
from ..util import CdpError, read_json, write_json

PATCH_GLOB = "*.json"
DERIVED_PATCH = "0000-derived.json"


class FileStore(WorkspaceStore):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # ------------------------------------------------------------ artifacts

    def _artifact_path(self, name: str) -> Path:
        return self.root / (name + ".json")

    def read_artifact(self, name: str, default: Any = None) -> Any:
        path = self._artifact_path(name)
        if not path.exists():
            if default is None:
                raise CdpError("missing %s — run `scan` first" % path)
            return default
        return read_json(path)

    def write_artifact(self, name: str, data: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        write_json(self._artifact_path(name), data)

    def has_artifact(self, name: str) -> bool:
        return self._artifact_path(name).is_file()

    # -------------------------------------------------------------- reports

    def write_report(self, name: str, data: Any) -> None:
        write_json(self.root / "reports" / (name + ".json"), data)

    def read_report(self, name: str, default: Any = None) -> Any:
        path = self.root / "reports" / (name + ".json")
        if not path.exists():
            if default is None:
                raise CdpError("missing report %s" % path)
            return default
        return read_json(path)

    # ------------------------------------------------------------ patch log

    def _patches_dir(self) -> Path:
        return self.root / "patches"

    def load_patches(self) -> List[Dict]:
        directory = self._patches_dir()
        if not directory.is_dir():
            return []
        out = []
        for path in sorted(directory.glob(PATCH_GLOB)):
            try:
                out.append(read_json(path))
            except ValueError as exc:
                raise CdpError("corrupt patch %s: %s" % (path, exc))
        return out

    def append_patch(self, patch: Dict, label: str) -> str:
        directory = self._patches_dir()
        directory.mkdir(parents=True, exist_ok=True)
        used = []
        for path in directory.glob(PATCH_GLOB):
            head = path.name.split("-", 1)[0]
            if head.isdigit():
                used.append(int(head))
        index = max(used) + 1 if used else 1
        safe = label.replace("/", "__").replace(" ", "_")
        path = directory / ("%04d-%s.json" % (index, safe))
        write_json(path, patch)
        return str(path)

    def write_derived_patch(self, patch: Dict) -> None:
        directory = self._patches_dir()
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory / DERIVED_PATCH, patch)

    # ---------------------------------------------------------------- inbox

    def _inbox_dir(self) -> Path:
        return self._patches_dir() / "inbox"

    def ensure_inbox(self) -> None:
        self._inbox_dir().mkdir(parents=True, exist_ok=True)

    def read_inbox(self) -> List[Tuple[str, Any]]:
        inbox = self._inbox_dir()
        if not inbox.is_dir():
            raise CdpError("no inbox at %s — run `cdp prompts` first" % inbox)
        out: List[Tuple[str, Any]] = []
        for path in sorted(inbox.glob("*.json")):
            try:
                out.append((path.name, read_json(path)))
            except ValueError as exc:
                out.append((path.name, exc))
        return out

    def clear_inbox(self, node: str) -> None:
        (self._inbox_dir() / (node.replace("/", "__") + ".json")).unlink(missing_ok=True)
