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
from typing import Dict, List, Optional

from .base import ExtractContext, Extractor, FileFacts, anchor_at, count_loc, mk_define, mk_edge

# A table name: up to two qualifiers (`${schema}.`, `dbo.`, `[dbo].`) then the name.
_NAME = r"((?:[`\"\[]?[\w$]+[`\"\]]?\.){0,2}[`\"\[]?[\w$]+[`\"\]]?)"
CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + _NAME, re.I)
ALTER_TABLE_RE = re.compile(r"\bALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?" + _NAME, re.I)
CREATE_INDEX_RE = re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?(?:CLUSTERED\s+|NONCLUSTERED\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w$.]+\s+ON\s+" + _NAME, re.I)
INSERT_RE = re.compile(r"\bINSERT\s+INTO\s+" + _NAME, re.I)
PLACEHOLDER_RE = re.compile(r"\$\{[^}]*\}|\{\{[^}]*\}\}|\$\([\w.]+\)")
LINE_COMMENT_RE = re.compile(r"--.*$")
SQL_RESERVED = frozenset(["select", "set", "values", "where", "from", "as", "on", "if", "not", "exists",
                          "table", "into", "only", "using", "default", "null", "and", "or"])
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
        in_block = False
        for idx, raw_line in enumerate(ctx.lines):
            # Comments are prose, not DDL; Flyway `${placeholders}` stand for a
            # schema or table prefix and must not hide the statement.
            line = raw_line
            if in_block:
                if "*/" not in line:
                    continue
                line = line.split("*/", 1)[1]
                in_block = False
            while "/*" in line:
                head, _, tail = line.partition("/*")
                if "*/" in tail:
                    line = head + " " + tail.split("*/", 1)[1]
                else:
                    line, in_block = head, True
            line = LINE_COMMENT_RE.sub("", line)
            line = PLACEHOLDER_RE.sub("__ph__", line)
            for regex, channel in (
                (CREATE_TABLE_RE, "schema_own"),
                (ALTER_TABLE_RE, "schema_own"),
                (CREATE_INDEX_RE, "schema_own"),
                (INSERT_RE, "persist"),
            ):
                for raw in regex.findall(line):
                    table = _table_name(raw)
                    if not table:
                        continue
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


def _table_name(raw: str) -> Optional[str]:
    """The table itself, without schema qualifier or quoting; None for a bare
    placeholder or a SQL keyword that the pattern caught by accident."""
    name = raw.strip().split(".")[-1].strip("`\"[]")
    if not name or name == "__ph__" or name.lower() in SQL_RESERVED:
        return None
    return name


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


#: `${NAME}` / `${NAME:-default}` / `${NAME:?why}` in a config value: an environment variable the
#: file reads (Dropwizard, Docker Compose). Dotted names are Spring property references, not env vars.
ENV_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-?=+])([^}]*))?\}")
BLOCK_SCALARS = frozenset(["|", ">", "|-", ">-", "|+", ">+"])


def _yaml_keys(lines: List[str]):
    """`(index, dotted key, value)` for every `key: value` line of a YAML file.

    Nesting follows indentation, whatever its width. A list item (`- key: v`, also
    `key:` followed by `- ...` at the same indent) is an indexed frame, so its keys
    read `servers[0].port` rather than collapsing into the parent."""
    stack: List[tuple] = []   # (indent, label, is_item)
    counters: dict = {}
    block_indent = None
    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if block_indent is not None:
            if indent > block_indent:
                continue          # the body of a `|` / `>` scalar
            block_indent = None
        text = stripped
        if text == "-" or text.startswith("- "):
            while stack and (stack[-1][0] > indent or (stack[-1][0] == indent and stack[-1][2])):
                stack.pop()
            owner = ".".join(f[1] for f in stack)
            n = counters.get(owner, 0)
            counters[owner] = n + 1
            stack.append((indent, "[%d]" % n, True))
            body = text[1:].lstrip(" ")
            indent += len(text) - len(body)
            text = body
            if not text:
                continue
        else:
            while stack and stack[-1][0] >= indent:
                stack.pop()
        m = PROP_RE.match(text)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value in BLOCK_SCALARS:
            block_indent = indent
            value = ""
        path = ""
        for f in stack:
            path += f[1] if f[2] else (("." if path else "") + f[1])
        full = path + ("." if path else "") + key
        yield idx, full, value
        if not value or value.startswith("#"):
            stack.append((indent, key, False))
            counters.pop(full, None)


class ConfigExtractor(Extractor):
    language = "config"
    role = "config"
    extensions = (".properties", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".env")

    def extract(self, ctx: ExtractContext) -> FileFacts:
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))
        owner = "config-file:" + ctx.path
        yaml = ctx.path.endswith((".yaml", ".yml"))
        if yaml:
            entries = _yaml_keys(ctx.lines)
        else:
            entries = ((i, m.group(1), m.group(2).strip()) for i, m in
                       ((i, PROP_RE.match(line)) for i, line in enumerate(ctx.lines)
                        if line.strip() and not line.lstrip().startswith(("#", "//"))) if m)
        for idx, key, value in entries:
            if yaml and not value:
                continue
            anchor = anchor_at(ctx, idx)
            if anchor is None:
                continue
            value = value.strip().rstrip()
            facts.defines.append(
                mk_define("config:" + key, "config_key", "public", anchor, value=value[:200] or None)
            )
            facts.io_edges.append(mk_edge(owner, "config:" + key, "config_read", anchor))
            if yaml:
                _env_placeholders(facts, anchor, value)
        return facts


def _env_placeholders(facts: FileFacts, anchor: Dict, value: str) -> None:
    """`port: ${DW_APP_PORT:-8070}` declares the environment variable `DW_APP_PORT`
    (default `8070`) alongside the key that uses it."""
    for name, op, default in ENV_PLACEHOLDER_RE.findall(value):
        facts.defines.append(mk_define("config:" + name, "config_key", "public", anchor,
                                       value=default[:200] if op in ("-", ":-") and default else None))


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
