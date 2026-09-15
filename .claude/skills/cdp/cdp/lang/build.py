"""Build-manifest extractor — the *declared* arm of the dual-source graph (§5.2).

RESEARCH.md's strongest empirical result is that on the validation target the
declared graph has ~3 edges while the observed graph is a complete 5-level DAG.
That result only exists because both arms are built and neither is discarded, so
this extractor's job is to report exactly what the manifests say — including
when they say almost nothing.

Manifest presence is also how CDP finds module boundaries in a repository whose
layout it has never seen, which is what makes the tool portable: a directory
containing a build manifest is a module, in every ecosystem here.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from .base import ExtractContext, Extractor, FileFacts, anchor_at, count_loc, mk_define

# Filenames that mark a directory as a module root, most specific first.
MANIFEST_NAMES = (
    "build.gradle", "build.gradle.kts", "pom.xml", "package.json", "go.mod",
    "pyproject.toml", "setup.py", "Cargo.toml", "build.sbt", "*.csproj",
)

GRADLE_PROJECT_RE = re.compile(r"""project\s*\(\s*['"]:([^'"]+)['"]""")
GRADLE_INCLUDE_RE = re.compile(r"""^\s*include\s*\(?\s*['"]:?([^'"]+)['"]""")
GRADLE_ROOTNAME_RE = re.compile(r"""rootProject\.name\s*=\s*['"]([^'"]+)['"]""")
POM_MODULE_RE = re.compile(r"<module>\s*([^<]+?)\s*</module>")
POM_ARTIFACT_RE = re.compile(r"<artifactId>\s*([^<]+?)\s*</artifactId>")
GOMOD_MODULE_RE = re.compile(r"^\s*module\s+(\S+)")
GOMOD_REQUIRE_RE = re.compile(r"^\s*(?:require\s+)?([\w./-]+)\s+v\S+")
TOML_NAME_RE = re.compile(r"""^\s*name\s*=\s*['"]([^'"]+)['"]""")


class BuildExtractor(Extractor):
    language = "build"
    role = "build"
    names = (
        "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
        "pom.xml", "package.json", "go.mod", "pyproject.toml", "setup.py",
        "Cargo.toml", "build.sbt", "Makefile", "CMakeLists.txt", "requirements.txt",
    )
    extensions = (".gradle", ".csproj", ".fsproj", ".vbproj")

    def extract(self, ctx: ExtractContext) -> FileFacts:
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))
        name = ctx.path.rsplit("/", 1)[-1]

        if name.startswith("settings.gradle"):
            _settings_gradle(ctx, facts)
        elif name.startswith("build.gradle") or ctx.path.endswith(".gradle"):
            _build_gradle(ctx, facts)
        elif name == "pom.xml":
            _pom(ctx, facts)
        elif name == "package.json":
            _package_json(ctx, facts)
        elif name == "go.mod":
            _go_mod(ctx, facts)
        elif name in ("pyproject.toml", "Cargo.toml"):
            _toml(ctx, facts)

        facts.declared_deps = sorted(set(facts.declared_deps))
        return facts


def _settings_gradle(ctx: ExtractContext, facts: FileFacts) -> None:
    """`include` lines and `rootProject.name`.

    `rootProject.name = 'spm'` while every directory is `sql-pool-*` is §1.1's
    motivating example — the five-second fact that costs a newcomer an
    afternoon. It is captured as a citable `naming` definition so the overview
    document can state it with evidence rather than assert it.
    """
    for idx, line in enumerate(ctx.lines):
        m = GRADLE_ROOTNAME_RE.search(line)
        if m:
            anchor = anchor_at(ctx, idx)
            if anchor:
                facts.defines.append(
                    mk_define("build:rootProject.name", "config_key", "public", anchor, value=m.group(1))
                )
                facts.notes.append("root_project_name=" + m.group(1))
        m = GRADLE_INCLUDE_RE.match(line)
        if m:
            facts.notes.append("declares_module=" + m.group(1).replace(":", "/"))


def _build_gradle(ctx: ExtractContext, facts: FileFacts) -> None:
    for idx, line in enumerate(ctx.lines):
        stripped = line.strip()
        for dep in GRADLE_PROJECT_RE.findall(line):
            # Only dependency declarations are edges. `project(':x').buildDir`
            # inside a task configuration is a path reference, not a dependency,
            # and counting it would inflate the declared arm that §5.2 is
            # measuring against the observed one.
            if re.match(r"^\s*\w*(implementation|api|compile|runtime|testImplementation|annotationProcessor)\w*\s", line, re.I):
                facts.declared_deps.append(dep.replace(":", "/"))
        if stripped.startswith("rootProject.name"):
            m = GRADLE_ROOTNAME_RE.search(line)
            if m:
                facts.notes.append("root_project_name=" + m.group(1))


def _pom(ctx: ExtractContext, facts: FileFacts) -> None:
    text = "\n".join(ctx.lines)
    for module in POM_MODULE_RE.findall(text):
        facts.notes.append("declares_module=" + module)
    artifacts = POM_ARTIFACT_RE.findall(text)
    if artifacts:
        facts.notes.append("artifact=" + artifacts[0])
    # Dependency artifactIds after the first (self) one are candidate local deps;
    # graph.py keeps only those that match a known module.
    for artifact in artifacts[1:]:
        facts.declared_deps.append(artifact)


def _package_json(ctx: ExtractContext, facts: FileFacts) -> None:
    try:
        data = json.loads("\n".join(ctx.lines))
    except ValueError:
        facts.notes.append("parse_error")
        return
    if isinstance(data.get("name"), str):
        facts.notes.append("artifact=" + data["name"])
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            facts.declared_deps.extend(sorted(block))
    workspaces = data.get("workspaces")
    if isinstance(workspaces, list):
        for pattern in workspaces:
            facts.notes.append("workspace=" + str(pattern))
    elif isinstance(workspaces, dict) and isinstance(workspaces.get("packages"), list):
        for pattern in workspaces["packages"]:
            facts.notes.append("workspace=" + str(pattern))


def _go_mod(ctx: ExtractContext, facts: FileFacts) -> None:
    for line in ctx.lines:
        m = GOMOD_MODULE_RE.match(line)
        if m:
            facts.notes.append("artifact=" + m.group(1))
            continue
        m = GOMOD_REQUIRE_RE.match(line)
        if m and not line.lstrip().startswith(("module", "go ", "//")):
            facts.declared_deps.append(m.group(1))


def _toml(ctx: ExtractContext, facts: FileFacts) -> None:
    section = ""
    for line in ctx.lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        m = TOML_NAME_RE.match(line)
        if m and section in ("package", "project", "tool.poetry"):
            facts.notes.append("artifact=" + m.group(1))
        if section.endswith("dependencies"):
            dep = stripped.split("=", 1)[0].strip().strip('"')
            if dep and not dep.startswith("#"):
                facts.declared_deps.append(dep)
