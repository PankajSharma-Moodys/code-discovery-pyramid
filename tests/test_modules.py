from pathlib import Path

from code_scanner.discover.modules import assign_modules
from code_scanner.discover.walk import discover

MANIFESTS = ["pom.xml", "build.gradle", "build.gradle.kts", "package.json",
             "go.mod", "Cargo.toml", "pyproject.toml", "setup.py", "*.csproj", "*.fsproj"]


def test_three_manifests_yield_three_modules(multimodule_repo: Path):
    files = discover(multimodule_repo).files
    file_to_module, grouping = assign_modules(multimodule_repo, files, MANIFESTS)

    assert grouping == "manifest"
    module_ids = {m.id for m in file_to_module.values()}
    assert module_ids == {"module-a", "module-b", "generated-lib", "lib-py"}

    widget = next(f for f in files if f.name == "Widget.java")
    assert file_to_module[widget].id == "module-a"
    assert file_to_module[widget].ecosystem == "maven"


def test_pyproject_module_included(multimodule_repo: Path):
    files = discover(multimodule_repo).files
    file_to_module, _ = assign_modules(multimodule_repo, files, MANIFESTS)
    pyproject_file = next(f for f in files if f.name == "pyproject.toml")
    assert file_to_module[pyproject_file].ecosystem == "python"


def test_directory_fallback_when_below_minimum(tmp_path: Path):
    (tmp_path / "app" / "routers").mkdir(parents=True)
    (tmp_path / "app" / "services").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "app" / "routers" / "a.py").write_text("x = 1\n")
    (tmp_path / "app" / "services" / "b.py").write_text("y = 2\n")

    files = discover(tmp_path).files
    file_to_module, grouping = assign_modules(tmp_path, files, MANIFESTS, min_for_manifest_grouping=2)

    assert grouping == "directory"
    ids = {m.id for m in file_to_module.values() if m}
    assert "app/routers" in ids
    assert "app/services" in ids
