"""Path rules + generated-content sniff -> file role (RESEARCH §4).

Only role == production contributes to the quality score; everything else is
counted and broken out, never scored.
"""

from __future__ import annotations

from pathlib import Path

import pathspec

BUILTIN_TEST = [
    "**/src/test/**", "**/test/**", "**/tests/**",
    "*Test.java", "*_test.go", "test_*.py", "*_test.py", "*.spec.ts", "*.spec.tsx",
    "*.spec.js", "*_spec.rb",
]
BUILTIN_GENERATED = [
    "**/generated/**", "**/target/generated-sources/**", "*.pb.go", "*_pb2.py",
    "**/migrations/**", "**/alembic/versions/**",
]
BUILTIN_VENDORED = ["**/vendor/**", "**/third_party/**", "**/node_modules/**"]


def resolve_patterns(builtin: list[str], override: list[str]) -> list[str]:
    """Empty override -> built-in. Entries prefixed '+' append; otherwise replace (§4)."""
    if not override:
        return builtin
    if all(p.startswith("+") for p in override):
        return builtin + [p[1:] for p in override]
    return [p[1:] if p.startswith("+") else p for p in override]


def _spec(patterns: list[str]) -> pathspec.PathSpec:
    return pathspec.PathSpec.from_lines("gitignore", patterns)


def _sniff_generated(path: Path, markers: list[str], sniff_lines: int) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = [next(f, "") for _ in range(sniff_lines)]
    except OSError:
        return False
    text = "\n".join(head)
    return any(marker in text for marker in markers)


def assign_role(
    rel_path: str,
    abs_path: Path,
    *,
    test_patterns: list[str],
    generated_patterns: list[str],
    vendored_patterns: list[str],
    generated_markers: list[str],
    generated_sniff_lines: int,
    stub_extensions: list[str],
) -> str:
    if _spec(vendored_patterns).match_file(rel_path):
        return "vendored"
    if _spec(test_patterns).match_file(rel_path):
        return "test"
    if _spec(generated_patterns).match_file(rel_path):
        return "generated"
    if any(rel_path.endswith(ext) for ext in stub_extensions):  # R9
        return "generated"
    if _sniff_generated(abs_path, generated_markers, generated_sniff_lines):
        return "generated"
    return "production"


def build_role_classifier(roles_config: dict):
    test_patterns = resolve_patterns(BUILTIN_TEST, roles_config.get("test", []))
    generated_patterns = resolve_patterns(BUILTIN_GENERATED, roles_config.get("generated", []))
    vendored_patterns = resolve_patterns(BUILTIN_VENDORED, roles_config.get("vendored", []))
    generated_markers = roles_config.get("generated_markers", [])
    generated_sniff_lines = roles_config.get("generated_sniff_lines", 5)
    stub_extensions = roles_config.get("stub_extensions", [])

    def classify(rel_path: str, abs_path: Path) -> str:
        return assign_role(
            rel_path, abs_path,
            test_patterns=test_patterns,
            generated_patterns=generated_patterns,
            vendored_patterns=vendored_patterns,
            generated_markers=generated_markers,
            generated_sniff_lines=generated_sniff_lines,
            stub_extensions=stub_extensions,
        )

    return classify
