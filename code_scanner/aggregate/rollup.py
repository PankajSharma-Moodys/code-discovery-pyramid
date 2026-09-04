"""file -> module -> language -> repo rollup. Score/complexity aggregation lands
at M4 (aggregate/score.py); this owns the structural counts rollup only."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from code_scanner.model import FileReport, LanguageAgg, ModuleReport, Score


def _empty_role_counts() -> dict[str, int]:
    return {"production": 0, "test": 0, "generated": 0, "vendored": 0}


def rollup_modules(files: list[FileReport], module_meta: dict[str, tuple[str | None, str | None]]) -> list[ModuleReport]:
    """module_meta: module id -> (manifest, ecosystem)."""
    totals: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "files": 0, "code": 0, "comment": 0, "blank": 0, "functions": 0, "types": 0,
        "doc_num": 0, "doc_den": 0,
    })
    by_role: dict[str, dict[str, int]] = defaultdict(_empty_role_counts)

    for f in files:
        if f.module is None:
            continue
        t = totals[f.module]
        t["files"] += 1
        t["code"] += f.lines.code
        t["comment"] += f.lines.comment
        t["blank"] += f.lines.blank
        t["functions"] += f.functions_count
        t["types"] += f.types_count
        if f.doc_coverage is not None:
            t["doc_num"] += f.documented_count
            t["doc_den"] += f.public_count
        by_role[f.module][f.role] += 1

    modules: list[ModuleReport] = []
    for module_id, t in sorted(totals.items()):
        manifest, ecosystem = module_meta.get(module_id, (None, None))
        doc_coverage = (t["doc_num"] / t["doc_den"]) if t["doc_den"] > 0 else None
        modules.append(ModuleReport(
            id=module_id,
            path=module_id,
            manifest=manifest,
            ecosystem=ecosystem,
            score=Score(value=None, grade=None),
            totals={
                "files": t["files"], "code": t["code"], "comment": t["comment"], "blank": t["blank"],
                "functions": t["functions"], "types": t["types"], "doc_coverage": doc_coverage,
            },
            by_role=by_role[module_id],
        ))
    return modules


def rollup_languages(files: list[FileReport]) -> list[LanguageAgg]:
    totals: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "files": 0, "code": 0, "comment": 0, "blank": 0, "functions": 0, "types": 0,
        "doc_num": 0, "doc_den": 0,
    })
    for f in files:
        if f.language is None:
            continue
        t = totals[f.language]
        t["files"] += 1
        t["code"] += f.lines.code
        t["comment"] += f.lines.comment
        t["blank"] += f.lines.blank
        t["functions"] += f.functions_count
        t["types"] += f.types_count
        if f.doc_coverage is not None:
            t["doc_num"] += f.documented_count
            t["doc_den"] += f.public_count

    languages: list[LanguageAgg] = []
    for name, t in sorted(totals.items()):
        doc_coverage = (t["doc_num"] / t["doc_den"]) if t["doc_den"] > 0 else None
        languages.append(LanguageAgg(
            name=name, files=t["files"], code=t["code"], comment=t["comment"], blank=t["blank"],
            functions=t["functions"], types=t["types"],
            mean_complexity=None, p95_complexity=None,
            doc_coverage=doc_coverage, doc_coverage_approximate=False,
            scope={"roles": ["production"], "files": t["files"]},
        ))
    return languages
