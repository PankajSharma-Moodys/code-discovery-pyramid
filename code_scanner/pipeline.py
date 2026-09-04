"""discover -> classify -> parse -> analyze -> aggregate -> score -> render (RESEARCH §4).

Each file is analyzed independently in a worker process and returns a small
FileReport; the AST is discarded inside the worker, so peak memory is O(workers),
not O(repository). Analyzers (complexity/smells/docs/security) land at M2/M3 —
this milestone wires discovery, module/role assignment and line classification.
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from code_scanner.aggregate.rollup import rollup_languages, rollup_modules
from code_scanner.config import Config
from code_scanner.discover.modules import assign_modules
from code_scanner.discover.roles import BUILTIN_GENERATED, BUILTIN_TEST, BUILTIN_VENDORED, resolve_patterns, assign_role
from code_scanner.discover.walk import discover
from code_scanner.languages.registry import profile_for_path
from code_scanner.model import FileReport, Lines, ScanResult, Score
from code_scanner.parse.lines import parse_file


@dataclass(frozen=True)
class _RoleParams:
    test_patterns: list[str]
    generated_patterns: list[str]
    vendored_patterns: list[str]
    generated_markers: list[str]
    generated_sniff_lines: int
    stub_extensions: list[str]


def _process_file(
    abs_path: Path,
    rel_path: str,
    module_id: str | None,
    role_params: _RoleParams,
    degraded_error_ratio: float,
) -> FileReport:
    profile = profile_for_path(rel_path)
    try:
        raw = abs_path.read_bytes()
    except OSError:
        return FileReport(
            path=rel_path, module=module_id, language=profile.name if profile else None,
            role="production", parse_status="unparsed", detection="extension",
            lines=Lines(total=0, code=0, comment=0, blank=0, approximate=True),
        )

    outcome = parse_file(raw, profile, degraded_error_ratio=degraded_error_ratio)
    role = assign_role(
        rel_path, abs_path,
        test_patterns=role_params.test_patterns,
        generated_patterns=role_params.generated_patterns,
        vendored_patterns=role_params.vendored_patterns,
        generated_markers=role_params.generated_markers,
        generated_sniff_lines=role_params.generated_sniff_lines,
        stub_extensions=role_params.stub_extensions,
    )

    return FileReport(
        path=rel_path,
        module=module_id,
        language=profile.name if profile else None,
        role=role,  # type: ignore[arg-type]
        parse_status=outcome.parse_status,  # type: ignore[arg-type]
        detection="extension",
        lines=outcome.lines,
    )


def run_scan(root: Path, config: Config, detail: str = "threshold") -> ScanResult:
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    root = root.resolve()

    scan_cfg = config.resolved["scan"]
    discovery_result = discover(
        root,
        max_file_bytes=scan_cfg["max_file_bytes"],
        binary_sniff_bytes=scan_cfg["binary_sniff_bytes"],
        follow_symlinks=scan_cfg["follow_symlinks"],
    )

    modules_cfg = config.resolved["modules"]
    file_to_module: dict[Path, object] = {}
    grouping = "directory"
    if modules_cfg["enabled"]:
        file_to_module, grouping = assign_modules(
            root, discovery_result.files, modules_cfg["manifests"], modules_cfg["min_for_manifest_grouping"],
        )

    roles_cfg = config.resolved["roles"]

    role_params = _RoleParams(
        test_patterns=resolve_patterns(BUILTIN_TEST, roles_cfg.get("test", [])),
        generated_patterns=resolve_patterns(BUILTIN_GENERATED, roles_cfg.get("generated", [])),
        vendored_patterns=resolve_patterns(BUILTIN_VENDORED, roles_cfg.get("vendored", [])),
        generated_markers=roles_cfg.get("generated_markers", []),
        generated_sniff_lines=roles_cfg.get("generated_sniff_lines", 5),
        stub_extensions=roles_cfg.get("stub_extensions", []),
    )

    degraded_error_ratio = config.resolved["parse"]["degraded_error_ratio"]
    jobs = scan_cfg.get("jobs", 0) or None

    tasks = []
    for abs_path in discovery_result.files:
        rel_path = abs_path.relative_to(root).as_posix()
        module = file_to_module.get(abs_path)
        module_id = module.id if module is not None else None
        tasks.append((abs_path, rel_path, module_id))

    files: list[FileReport] = []
    if jobs == 1 or len(tasks) < 8:
        for abs_path, rel_path, module_id in tasks:
            files.append(_process_file(abs_path, rel_path, module_id, role_params, degraded_error_ratio))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futures = [
                pool.submit(_process_file, abs_path, rel_path, module_id, role_params, degraded_error_ratio)
                for abs_path, rel_path, module_id in tasks
            ]
            files = [fut.result() for fut in futures]

    by_role = {"production": 0, "test": 0, "generated": 0, "vendored": 0}
    files_degraded = files_unparsed = 0
    for f in files:
        by_role[f.role] += 1
        if f.parse_status == "degraded":
            files_degraded += 1
        elif f.parse_status == "unparsed":
            files_unparsed += 1

    module_meta = {}
    for module in file_to_module.values():
        module_meta[module.id] = (module.manifest, module.ecosystem)

    modules = rollup_modules(files, module_meta)
    languages = rollup_languages(files)

    duration_ms = int((time.monotonic() - started) * 1000)

    return ScanResult(
        root=str(root),
        started_at=started_at,
        duration_ms=duration_ms,
        discovery=discovery_result.discovery,
        grouping=grouping,
        detail=detail,
        files_scanned=len(files),
        files_excluded=0,
        files_skipped=discovery_result.skipped_binary + discovery_result.skipped_too_large,
        files_degraded=files_degraded,
        files_unparsed=files_unparsed,
        by_role=by_role,
        packs_active=[],
        config=config.resolved,
        config_source=config.source,
        config_digest=config.digest,
        score=Score(value=None, grade=None, scope={"roles": ["production"], "files": by_role["production"]}),
        modules=modules,
        languages=languages,
        files=files,
    )
