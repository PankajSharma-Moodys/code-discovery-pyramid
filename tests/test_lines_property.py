import pytest

from code_scanner.languages.registry import ALL_PROFILES
from code_scanner.parse.lines import parse_file

SAMPLES = {
    "python": b'"""Module doc."""\n\ndef add(a, b):\n    """Add.\n    multi.\n    """\n    return a + b  # trailing\n\n\n',
    "javascript": b'// c\nfunction f() {\n  return 1; // trail\n}\n',
    "typescript": b'// c\nfunction f(): number {\n  return 1;\n}\n',
    "tsx": b'// c\nfunction f(): number {\n  return 1;\n}\n',
    "go": b'package main\n\n// doc\nfunc main() {\n}\n',
    "java": b'/** doc */\nclass X {\n    // c\n    void f() {\n        int x = 1; // trail\n    }\n}\n',
    "rust": b'/// doc\nfn main() {\n    let x = 1;\n}\n',
    "ruby": b'# c\ndef f\n  1\nend\n',
    "csharp": b'// c\nclass X {\n  void F() {}\n}\n',
    "cpp": b'// c\nint main() {\n  return 0;\n}\n',
}


@pytest.mark.parametrize("profile", ALL_PROFILES, ids=lambda p: p.name)
def test_loc_invariant_holds(profile):
    source = SAMPLES[profile.name]
    outcome = parse_file(source, profile)
    lines = outcome.lines
    assert lines.code + lines.comment + lines.blank == lines.total


def test_no_trailing_newline_total_matches_splitlines():
    outcome = parse_file(b"a\nb", None)
    assert outcome.lines.total == 2


def test_trailing_newline_total_matches_splitlines():
    outcome = parse_file(b"a\nb\n", None)
    assert outcome.lines.total == 2
