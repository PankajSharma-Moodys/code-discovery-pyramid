from pathlib import Path

from code_scanner.discover.walk import discover


def test_git_discovery_respects_nested_gitignore(multimodule_repo: Path):
    result = discover(multimodule_repo)
    rel = {p.relative_to(multimodule_repo).as_posix() for p in result.files}

    assert result.discovery == "git-ls-files"
    assert "debug.log" not in rel                              # top-level .gitignore
    assert "module-a/build/Ignored.java" not in rel             # nested .gitignore
    assert "module-a/src/main/java/com/acme/Widget.java" in rel


def test_subdirectory_scan_reports_only_files_under_it(multimodule_repo: Path):
    """D12.1: scanning a subdirectory must not enumerate the whole repository."""
    result = discover(multimodule_repo / "module-b")
    rel = {p.relative_to(multimodule_repo / "module-b").as_posix() for p in result.files}

    assert rel == {"pom.xml", "src/main/java/com/acme/Gadget.java"}


def test_non_git_directory_falls_back_to_pathspec(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("1;\n")

    result = discover(tmp_path)
    rel = {p.relative_to(tmp_path).as_posix() for p in result.files}

    assert result.discovery == "pathspec-walk"
    assert rel == {"a.py"}


def test_empty_directory_yields_empty_report(tmp_path: Path):
    result = discover(tmp_path)
    assert result.files == []
