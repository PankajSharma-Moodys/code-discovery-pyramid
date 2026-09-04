import json
from pathlib import Path

from code_scanner.languages.registry import ALL_PROFILES
from code_scanner.parse.session import get_parser

FIXTURE = Path(__file__).parent / "fixtures" / "grammar_enumeration.json"


def test_ten_grammars_load():
    assert len(ALL_PROFILES) == 10
    for profile in ALL_PROFILES:
        parser = get_parser(profile.grammar)
        tree = parser.parse(b"")
        assert tree.root_node is not None


def test_grammar_enumeration_matches_committed_fixture():
    """R28: pinned per PLAN.md. A grammar-pack bump that renames node kinds fails
    here rather than silently producing wrong metrics downstream."""
    expected = json.loads(FIXTURE.read_text())
    for profile in ALL_PROFILES:
        lang = get_parser(profile.grammar).language
        named = sorted({lang.node_kind_for_id(i) for i in range(lang.node_kind_count) if lang.node_kind_is_named(i)})
        assert named == expected[profile.name]["named_kinds"], (
            f"{profile.name}: grammar node kinds changed — re-verify languages/defs/{profile.name}.py"
        )
