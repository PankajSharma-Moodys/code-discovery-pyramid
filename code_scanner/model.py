"""Shared vocabulary across stages: FileReport, ModuleReport, ScanResult, Observations.

An accidentally-crossed stage boundary shows up as an unexpected import of this module
from somewhere it shouldn't be (e.g. render/ importing parse/ directly instead of reading
the ScanResult these dataclasses produce).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["production", "test", "generated", "vendored"]
ParseStatus = Literal["ok", "degraded", "unparsed"]
Detection = Literal["extension", "sniff"]


@dataclass
class Observations:
    """Raw per-file tree-walk output, produced by parse/walk.py, consumed by analyze/*.

    One traversal per file populates this; every analyzer reads from it rather than
    re-walking the AST (gate: one traversal per file, not one per analyzer).
    """

    language: str | None = None
    parse_status: ParseStatus = "unparsed"
    error_ratio: float = 0.0
    lines_total: int = 0
    lines_code: int = 0
    lines_comment: int = 0
    lines_blank: int = 0
    lines_approximate: bool = False
    functions: list[dict[str, Any]] = field(default_factory=list)
    types: list[dict[str, Any]] = field(default_factory=list)
    string_literals: list[dict[str, Any]] = field(default_factory=list)
    assignments: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    imports: list[dict[str, Any]] = field(default_factory=list)
    suppressed_lines: set[int] = field(default_factory=set)


@dataclass
class Lines:
    total: int
    code: int
    comment: int
    blank: int
    approximate: bool = False

    def __post_init__(self) -> None:
        assert self.code + self.comment + self.blank == self.total, (
            f"LOC invariant violated: {self.code}+{self.comment}+{self.blank} != {self.total}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "code": self.code,
            "comment": self.comment,
            "blank": self.blank,
            "approximate": self.approximate,
        }


@dataclass
class FunctionReport:
    name: str
    line: int
    end_line: int
    body_line: int
    body_end_line: int
    length: int
    complexity: int
    params: int
    max_nesting: int
    public: bool
    documented: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "line": self.line, "end_line": self.end_line,
            "body_line": self.body_line, "body_end_line": self.body_end_line,
            "length": self.length, "complexity": self.complexity, "params": self.params,
            "max_nesting": self.max_nesting, "public": self.public, "documented": self.documented,
        }


@dataclass
class TypeReport:
    name: str
    kind: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "line": self.line}


@dataclass
class Smell:
    kind: str
    line: int
    value: float
    threshold: float
    scored: bool = True
    attribution: str | None = None
    suppressed_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "line": self.line, "value": self.value, "threshold": self.threshold,
            "scored": self.scored, "attribution": self.attribution, "suppressed_by": self.suppressed_by,
        }


@dataclass
class Outlier:
    kind: str
    line: int
    value: float
    baseline_p95: float
    population: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "line": self.line, "value": self.value,
            "baseline_p95": self.baseline_p95, "population": self.population,
        }


@dataclass
class SecurityFinding:
    kind: str
    line: int
    severity: str
    confidence: str
    detector: str
    message: str
    scored: bool = True
    suppressed_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "line": self.line, "severity": self.severity,
            "confidence": self.confidence, "detector": self.detector, "message": self.message,
            "scored": self.scored, "suppressed_by": self.suppressed_by,
        }


@dataclass
class FileReport:
    path: str
    module: str | None
    language: str | None
    role: Role
    parse_status: ParseStatus
    detection: Detection
    lines: Lines
    functions_count: int = 0
    types_count: int = 0
    public_count: int = 0
    documented_count: int = 0
    doc_coverage: float | None = None
    functions: list[FunctionReport] = field(default_factory=list)
    types: list[TypeReport] = field(default_factory=list)
    smells: list[Smell] = field(default_factory=list)
    outliers: list[Outlier] = field(default_factory=list)
    security: list[SecurityFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "module": self.module,
            "language": self.language,
            "role": self.role,
            "parse_status": self.parse_status,
            "detection": self.detection,
            "lines": self.lines.to_dict(),
            "counts": {
                "functions": self.functions_count,
                "types": self.types_count,
                "public": self.public_count,
                "documented": self.documented_count,
            },
            "doc_coverage": self.doc_coverage,
            "functions": [f.to_dict() for f in self.functions],
            "types": [t.to_dict() for t in self.types],
            "smells": [s.to_dict() for s in self.smells],
            "outliers": [o.to_dict() for o in self.outliers],
            "security": [s.to_dict() for s in self.security],
        }


@dataclass
class Score:
    value: float | None
    grade: str | None
    scope: dict[str, Any] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value, "grade": self.grade,
            "scope": self.scope, "penalties": self.penalties, "inputs": self.inputs,
        }


@dataclass
class ModuleReport:
    id: str
    path: str
    manifest: str | None
    ecosystem: str | None
    score: Score
    totals: dict[str, Any]
    by_role: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "path": self.path, "manifest": self.manifest, "ecosystem": self.ecosystem,
            "score": self.score.to_dict(), "totals": self.totals, "by_role": self.by_role,
        }


@dataclass
class LanguageAgg:
    name: str
    files: int
    code: int
    comment: int
    blank: int
    functions: int
    types: int
    mean_complexity: float | None
    p95_complexity: float | None
    doc_coverage: float | None
    doc_coverage_approximate: bool
    scope: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "files": self.files, "code": self.code, "comment": self.comment,
            "blank": self.blank, "functions": self.functions, "types": self.types,
            "mean_complexity": self.mean_complexity, "p95_complexity": self.p95_complexity,
            "doc_coverage": self.doc_coverage, "doc_coverage_approximate": self.doc_coverage_approximate,
            "scope": self.scope,
        }


@dataclass
class ScanResult:
    root: str
    started_at: str
    duration_ms: int
    discovery: str
    grouping: str
    detail: str
    files_scanned: int
    files_excluded: int
    files_skipped: int
    files_degraded: int
    files_unparsed: int
    by_role: dict[str, int]
    packs_active: list[str]
    config: dict[str, Any]
    config_source: str | None
    config_digest: str
    score: Score
    modules: list[ModuleReport]
    languages: list[LanguageAgg]
    files: list[FileReport]
    tool_name: str = "code-scanner"
    tool_version: str = "0.1.0"
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool": {"name": self.tool_name, "version": self.tool_version},
            "scan": {
                "root": self.root,
                "started_at": self.started_at,
                "duration_ms": self.duration_ms,
                "discovery": self.discovery,
                "grouping": self.grouping,
                "detail": self.detail,
                "files_scanned": self.files_scanned,
                "files_excluded": self.files_excluded,
                "files_skipped": self.files_skipped,
                "files_degraded": self.files_degraded,
                "files_unparsed": self.files_unparsed,
                "by_role": self.by_role,
                "packs_active": self.packs_active,
                "config": self.config,
                "config_source": self.config_source,
                "config_digest": self.config_digest,
            },
            "score": self.score.to_dict(),
            "modules": [m.to_dict() for m in self.modules],
            "languages": [l.to_dict() for l in self.languages],
            # R17: sort by path so two runs can be diffed regardless of pool completion order.
            "files": [f.to_dict() for f in sorted(self.files, key=lambda f: f.path)],
        }
