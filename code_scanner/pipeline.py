"""M0 walking skeleton: a line-count-only Python path.

This is deliberately minimal — no git-ls-files discovery, no module/role
assignment, no AST. It exists so the schema, config and CLI can be proven
end-to-end before any analyzer is built (Appendix C). Superseded at M1 by
discover/{walk,modules,roles}.py + parse/{session,lines}.py.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from code_scanner.config import Config
from code_scanner.model import FileReport, Lines, ModuleReport, Score, ScanResult

_SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", "__pycache__", ".venv"}


def _discover_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return files


def _scan_file(path: Path, root: Path) -> FileReport:
    text = path.read_text(encoding="utf-8", errors="replace")
    total = len(text.splitlines())
    lines = Lines(total=total, code=total, comment=0, blank=0, approximate=True)
    return FileReport(
        path=str(path.relative_to(root)),
        module=None,
        language="python",
        role="production",
        parse_status="unparsed",
        detection="extension",
        lines=lines,
    )


def run_scan(root: Path, config: Config, detail: str = "threshold") -> ScanResult:
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    files = [_scan_file(p, root) for p in _discover_python_files(root)]

    by_role = {"production": 0, "test": 0, "generated": 0, "vendored": 0}
    for f in files:
        by_role[f.role] += 1

    duration_ms = int((time.monotonic() - started) * 1000)

    return ScanResult(
        root=str(root),
        started_at=started_at,
        duration_ms=duration_ms,
        discovery="pathspec-walk",
        grouping="directory",
        detail=detail,
        files_scanned=len(files),
        files_excluded=0,
        files_skipped=0,
        files_degraded=0,
        files_unparsed=len(files),
        by_role=by_role,
        packs_active=[],
        config=config.resolved,
        config_source=config.source,
        config_digest=config.digest,
        score=Score(value=None, grade=None, scope={"roles": ["production"], "files": 0}),
        modules=[],
        languages=[],
        files=files,
    )
