from pathlib import Path

from code_scanner.config import DEFAULTS
from code_scanner.discover.roles import BUILTIN_GENERATED, BUILTIN_TEST, BUILTIN_VENDORED, assign_role


def _classify(rel_path: str, abs_path: Path) -> str:
    roles_cfg = DEFAULTS["roles"]
    return assign_role(
        rel_path, abs_path,
        test_patterns=BUILTIN_TEST,
        generated_patterns=BUILTIN_GENERATED,
        vendored_patterns=BUILTIN_VENDORED,
        generated_markers=roles_cfg["generated_markers"],
        generated_sniff_lines=roles_cfg["generated_sniff_lines"],
        stub_extensions=roles_cfg["stub_extensions"],
    )


def test_src_test_tree_is_test_role(multimodule_repo: Path):
    p = multimodule_repo / "module-a" / "src" / "test" / "java" / "com" / "acme" / "WidgetTest.java"
    assert _classify("module-a/src/test/java/com/acme/WidgetTest.java", p) == "test"


def test_do_not_edit_marker_sniffs_as_generated(multimodule_repo: Path):
    p = multimodule_repo / "generated-lib" / "src" / "generated" / "java" / "com" / "acme" / "Stub.java"
    assert _classify("generated-lib/src/generated/java/com/acme/Stub.java", p) == "generated"


def test_normal_production_file(multimodule_repo: Path):
    p = multimodule_repo / "module-b" / "src" / "main" / "java" / "com" / "acme" / "Gadget.java"
    assert _classify("module-b/src/main/java/com/acme/Gadget.java", p) == "production"


def test_pyi_stub_is_generated_role(tmp_path: Path):
    p = tmp_path / "types.pyi"
    p.write_text("def f() -> int: ...\n")
    assert _classify("types.pyi", p) == "generated"


def test_all_four_roles_reachable(multimodule_repo: Path):
    from code_scanner.discover.walk import discover
    files = discover(multimodule_repo).files
    roles = {_classify(f.relative_to(multimodule_repo).as_posix(), f) for f in files}
    assert "production" in roles
    assert "test" in roles
    assert "generated" in roles
