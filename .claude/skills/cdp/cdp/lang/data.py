"""Schema, container and configuration extractors.

These three file types carry facts that no source-language extractor can see,
and §3.3's root-scope rule exists largely for them: `Dockerfile`s and top-level
config sit outside every module directory, so under a naive partition no agent
would ever read them.

- SQL migrations establish `schema_own` — who is authoritative for a table, as
  distinct from who reads or writes it.
- Dockerfiles establish deployable units, which is what makes the
  `process_boundary` channel (§6.2) more than a label.
- Property/YAML files establish the config keys that source files read.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .base import ExtractContext, Extractor, FileFacts, anchor_at, count_loc, mk_define, mk_edge

CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"\[]?[\w.]+[`\"\]]?)", re.I)
ALTER_TABLE_RE = re.compile(r"\bALTER\s+TABLE\s+([`\"\[]?[\w.]+[`\"\]]?)", re.I)
CREATE_INDEX_RE = re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+\w+\s+ON\s+([`\"\[]?[\w.]+[`\"\]]?)", re.I)
INSERT_RE = re.compile(r"\bINSERT\s+INTO\s+([`\"\[]?[\w.]+[`\"\]]?)", re.I)
FLYWAY_RE = re.compile(r"^(?:V|U|R)([\d._]*)__(.+)\.sql$", re.I)

DOCKER_FROM_RE = re.compile(r"^\s*FROM\s+(\S+)", re.I)
DOCKER_EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+(.+)$", re.I)
DOCKER_ENTRY_RE = re.compile(r"^\s*(ENTRYPOINT|CMD)\s+(.+)$", re.I)
DOCKER_ENV_RE = re.compile(r"^\s*(?:ENV|ARG)\s+([A-Za-z_][\w]*)", re.I)

PROP_RE = re.compile(r"^\s*([A-Za-z_][\w.\-]*)\s*[:=]\s*(.*)$")


class SqlExtractor(Extractor):
    language = "sql"
    role = "schema"
    extensions = (".sql", ".ddl")

    def extract(self, ctx: ExtractContext) -> FileFacts:
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))
        name = ctx.path.rsplit("/", 1)[-1]
        migration = FLYWAY_RE.match(name)
        owner = "migration:" + name if migration else "sql:" + ctx.path
        if migration:
            facts.signals.append("migration")
            facts.notes.append("migration_version=" + migration.group(1))

        seen = set()
        for idx, line in enumerate(ctx.lines):
            for regex, channel in (
                (CREATE_TABLE_RE, "schema_own"),
                (ALTER_TABLE_RE, "schema_own"),
                (CREATE_INDEX_RE, "schema_own"),
                (INSERT_RE, "persist"),
            ):
                for raw in regex.findall(line):
                    table = raw.strip("`\"[]")
                    key = (table, channel)
                    if key in seen:
                        continue
                    anchor = anchor_at(ctx, idx)
                    if anchor is None:
                        continue
                    seen.add(key)
                    facts.io_edges.append(mk_edge(owner, "table:" + table, channel, anchor))
                    if channel == "schema_own" and regex is CREATE_TABLE_RE:
                        facts.defines.append(mk_define("table:" + table, "table", "public", anchor))
        return facts


class DockerExtractor(Extractor):
    language = "docker"
    role = "build"
    names = ("Dockerfile", "Containerfile")
    extensions = (".dockerfile",)

    def extract(self, ctx: ExtractContext) -> FileFacts:
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))
        unit = ctx.path.rsplit("/", 1)[0] if "/" in ctx.path else "root"
        deployable = "process:" + unit
        facts.signals.append("deployable")

        for idx, line in enumerate(ctx.lines):
            anchor = None
            m = DOCKER_ENTRY_RE.match(line)
            if m:
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.defines.append(
                        mk_define(deployable, "config_key", "public", anchor, value=m.group(2).strip())
                    )
                    facts.io_edges.append(mk_edge(unit, deployable, "process_boundary", anchor))
            m = DOCKER_EXPOSE_RE.match(line)
            if m:
                anchor = anchor_at(ctx, idx)
                if anchor:
                    for port in m.group(1).split():
                        facts.io_edges.append(mk_edge(deployable, "port:" + port.strip(), "http_in", anchor))
            m = DOCKER_ENV_RE.match(line)
            if m:
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.io_edges.append(mk_edge(deployable, "config:" + m.group(1), "config_read", anchor))
            m = DOCKER_FROM_RE.match(line)
            if m:
                facts.notes.append("base_image=" + m.group(1))
        return facts


class ConfigExtractor(Extractor):
    language = "config"
    role = "config"
    extensions = (".properties", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".env")

    def extract(self, ctx: ExtractContext) -> FileFacts:
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))
        owner = "config-file:" + ctx.path
        prefix: List[str] = []
        for idx, line in enumerate(ctx.lines):
            if not line.strip() or line.lstrip().startswith(("#", "//")):
                continue
            m = PROP_RE.match(line)
            if not m:
                continue
            key = m.group(1)
            value = m.group(2).strip()
            if ctx.path.endswith((".yaml", ".yml")):
                depth = (len(line) - len(line.lstrip())) // 2
                prefix = prefix[:depth]
                if not value:
                    prefix.append(key)
                    continue
                key = ".".join(prefix + [key])
            anchor = anchor_at(ctx, idx)
            if anchor is None:
                continue
            facts.defines.append(
                mk_define("config:" + key, "config_key", "public", anchor, value=value[:200] or None)
            )
            facts.io_edges.append(mk_edge(owner, "config:" + key, "config_read", anchor))
        return facts


class GenericExtractor(Extractor):
    """Fallback. Records the file's existence and size and claims nothing else.

    Producing no symbols is the correct behaviour for an unknown language: a
    wrong `defines[]` entry poisons the global symbol table for every module,
    while an absent one only shows up as an `unresolved` use that §6.4 already
    knows how to report.
    """

    language = "other"
    extensions = ()

    def extract(self, ctx: ExtractContext) -> FileFacts:
        return FileFacts(path=ctx.path, language=_guess_language(ctx.path), loc=count_loc(ctx.lines))


def _guess_language(path: str) -> str:
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "md": "markdown", "rst": "markdown", "txt": "text", "json": "json",
        "xml": "xml", "html": "html", "css": "css", "scss": "css",
        "sh": "shell", "bash": "shell", "zsh": "shell", "bat": "batch",
        "kt": "kotlin", "kts": "kotlin", "scala": "scala", "groovy": "groovy",
        "rb": "ruby", "php": "php", "cs": "csharp", "rs": "rust",
        "c": "c", "h": "c", "cpp": "cpp", "hpp": "cpp", "swift": "swift",
    }.get(suffix, "other")
