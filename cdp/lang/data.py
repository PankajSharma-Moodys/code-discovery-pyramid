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
from typing import Dict, List, Optional, Tuple

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


# ---------------------------------------------------------------- SQL in code (ANNOTATIONS_PLAN P7)
#
# `sql_tables` reads the SQL (or JPQL) of an annotation or a string, not a migration file: it knows
# SELECT/FROM/JOIN, UPDATE, DELETE, INSERT/MERGE INTO and TRUNCATE. The migration extractor above is
# unchanged and keeps its line patterns.

_SQL_STOP = frozenset(SQL_RESERVED | {
    "select", "where", "group", "order", "having", "union", "intersect", "except", "minus", "limit", "offset",
    "fetch", "for", "window", "returning", "when", "then", "else", "case", "join", "inner", "outer", "left",
    "right", "full", "cross", "natural", "straight_join", "apply", "lateral", "set", "of", "nowait", "wait",
    "skip", "cascade", "restrict", "with", "connect", "start", "qualify", "dual", "delete", "update", "insert",
    "merge", "using", "by", "all", "distinct", "top", "end", "is", "in", "like", "between", "key", "no", "do",
    "conflict", "matched", "tablesample", "partition", "values", "value"})
_CLAUSE_END = frozenset(["where", "group", "order", "having", "union", "intersect", "except", "minus", "limit",
                         "offset", "fetch", "for", "window", "duplicate", "conflict", "set", "values", "returning",
                         "select", "when", "then", "connect", "start", "qualify", "using"])
_FROM_FUNCS = frozenset(["extract", "trim", "substring", "overlay", "position", "substr"])
_TABLE_MODS = frozenset(["only", "lateral", "table", "fetch"])
_NOT_TARGET_PREV = frozenset(["for", "no", "key", "on", "of", "do", "before", "after", "instead", "then"])


def _skip_placeholder(text: str, i: int) -> int:
    """End of the placeholder starting at `i` (`${..}`, `{{..}}`, `#{..}`, `$(..)`), or -1."""
    for opener, closer in (("${", "}"), ("#{", "}"), ("{{", "}}"), ("$(", ")")):
        if text.startswith(opener, i):
            j = text.find(closer, i + len(opener))
            return len(text) if j < 0 else j + len(closer)
    return -1


def _sql_tokens(text: str) -> List[tuple]:
    """`(kind, value)` tokens: `w` word, `q` quoted name, `ph` placeholder (`${x}`, `:x`, `?`, `@x`,
    `#tmp`), `n` number, `s` string literal (content dropped), punctuation as itself. Comments and
    string contents never reach the parser."""
    out: List[tuple] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == "'":
            i += 1
            while i < n:
                if text[i] == "'":
                    if text[i + 1:i + 2] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(("s", ""))
        elif c in '"`' or (c == "[" and re.match(r"\[[^\[\]\n,]*[^\W\d][^\[\]\n,]*\]", text[i:i + 200])):
            close = "]" if c == "[" else c
            j = text.find(close, i + 1)
            j = n if j < 0 else j
            out.append(("q", text[i + 1:j]))
            i = j + 1
        elif _skip_placeholder(text, i) >= 0:
            i = _glue(text, _skip_placeholder(text, i))
            out.append(("ph", ""))
        elif c == ":" and text.startswith("::", i):
            i += 2
            out.append(("o", "::"))
        elif c == ":" and re.match(r":#?[A-Za-z_{]", text[i:i + 2]):
            if text.startswith(":#{", i):
                j = text.find("}", i)
                i = n if j < 0 else j + 1
            else:
                i += 1
                while i < n and (text[i].isalnum() or text[i] in "_."):
                    i += 1
                    if text[i - 1] == "." and not (i < n and text[i].isalpha()):
                        i -= 1
                        break
            out.append(("ph", ""))
        elif c == "?":
            i += 1
            while i < n and text[i].isdigit():
                i += 1
            out.append(("ph", ""))
        elif c in "@#" and re.match(r"[@#]+[A-Za-z_]", text[i:i + 3]):
            while i < n and text[i] in "@#":
                i += 1
            while i < n and (text[i].isalnum() or text[i] in "_$"):
                i += 1
            out.append(("ph", ""))
        elif c.isalpha() or c == "_" or ord(c) > 127:
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in "_$" or ord(text[j]) > 127) \
                    and _skip_placeholder(text, j) < 0:
                j += 1
            glued = _skip_placeholder(text, j)
            if glued >= 0:
                i = _glue(text, glued)
                out.append(("ph", ""))
            else:
                out.append(("w", text[i:j]))
                i = j
        elif c.isdigit():
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            out.append(("n", text[i:j]))
            i = j
        else:
            out.append((c if c in ".(),;" else "o", c))
            i += 1
    return out


def _glue(text: str, i: int) -> int:
    """A placeholder inside a name (`pool_${env}_cfg`) makes the whole name unknown."""
    n = len(text)
    while i < n:
        end = _skip_placeholder(text, i)
        if end >= 0:
            i = end
        elif text[i].isalnum() or text[i] in "_$":
            i += 1
        else:
            break
    return i


def _cte_names(toks: List[tuple]) -> set:
    """Names defined by `WITH a AS (...), b(cols) AS (...)`: not tables."""
    names = set()

    def group(j: int) -> int:
        depth = 0
        while j < len(toks):
            depth += 1 if toks[j][0] == "(" else -1 if toks[j][0] == ")" else 0
            j += 1
            if depth == 0:
                return j
        return j

    for i, (kind, val) in enumerate(toks):
        if kind != "w" or val.lower() != "with":
            continue
        j = i + 1
        if j < len(toks) and toks[j][0] == "w" and toks[j][1].lower() == "recursive":
            j += 1
        while j < len(toks) and toks[j][0] in ("w", "q"):
            name = toks[j][1]
            j += 1
            if j < len(toks) and toks[j][0] == "(":
                j = group(j)
            if not (j < len(toks) and toks[j][0] == "w" and toks[j][1].lower() == "as"):
                break
            j += 1
            while j < len(toks) and toks[j][0] == "w" and toks[j][1].lower() in ("not", "materialized"):
                j += 1
            if j >= len(toks) or toks[j][0] != "(":
                break
            names.add(name.lower())
            j = group(j)
            if j < len(toks) and toks[j][0] == ",":
                j += 1
                continue
            break
    return names


def _name_at(toks: List[tuple], j: int):
    """`(parts, next index)` of the dotted name at `j`; parts hold None for a placeholder."""
    parts: List[Optional[str]] = []
    while j < len(toks) and toks[j][0] in ("w", "q", "ph"):
        parts.append(None if toks[j][0] == "ph" else toks[j][1])
        j += 1
        if j + 1 < len(toks) and toks[j][0] == "." and toks[j + 1][0] in ("w", "q", "ph"):
            j += 1
            continue
        break
    return parts, j


def sql_tables(text: str, jpql: bool = False) -> List[Tuple[str, str]]:
    """`[(table, "read" | "write"), ...]` for the SQL in `text`, in order of appearance, deduplicated.

    Reads: `FROM`/`JOIN` (comma lists, subqueries, `USING` of a MERGE/DELETE). Writes: `UPDATE`,
    `DELETE [FROM]`, `INSERT/REPLACE/MERGE/SELECT ... INTO`, `TRUNCATE`. Names lose their schema
    qualifier and quoting (`[dbo].[server]` -> `server`), like the migration extractor's; an alias
    given to an `UPDATE`/`DELETE` target resolves to its table. Not tables: CTE names, `dual`,
    functions in `FROM`, `${schema}`/`:param`/`?`/`#{x}` placeholders standing alone (a qualified
    `${schema}.server` is `server`). Comments and string literals are ignored; keywords any case.
    `jpql=True` reads entity names instead (`FROM Entity e`, `JOIN Entity`, `UPDATE Entity`) and
    skips member paths (`JOIN e.items`)."""
    toks = _sql_tokens(text or "")
    segments, cur = [], []
    for t in toks:
        if t[0] == ";":
            segments.append(cur)
            cur = []
        else:
            cur.append(t)
    segments.append(cur)
    out: List[Tuple[str, str]] = []
    for seg in segments:
        for row in _statement(seg, jpql):
            if row not in out:
                out.append(row)
    return out


def _statement(toks: List[tuple], jpql: bool) -> List[Tuple[str, str]]:
    ctes = _cte_names(toks)
    events: List[list] = []        # [name, kind, qualified, alias_form]
    aliases: Dict[str, str] = {}
    lists: set = set()
    parens: List[str] = []
    using_ok = False
    n = len(toks)

    def word(j: int, *vals: str) -> bool:
        return 0 <= j < n and toks[j][0] == "w" and (not vals or toks[j][1].lower() in vals)

    def table_at(j: int, kind: str, join: bool = False, alias_ok: bool = True) -> int:
        while word(j) and toks[j][1].lower() in _TABLE_MODS:
            j += 1
        if j >= n or toks[j][0] not in ("w", "q", "ph"):
            return j
        if toks[j][0] == "w" and toks[j][1].lower() in _SQL_STOP:
            return j
        parts, k = _name_at(toks, j)
        name = parts[-1] if parts else None
        is_func = k < n and toks[k][0] == "(" and kind == "read"
        skip = name is None or is_func
        if jpql and not skip and len(parts) > 1 and (join or (parts[0] or "").lower() in aliases):
            skip = True                      # a member path (`e.items`), not an entity
        if not skip and kind == "write" and k < n and toks[k][0] == "o" and toks[k][1] == "=":
            skip = True                      # `ON DUPLICATE KEY UPDATE col = ...`
        if not skip:
            events.append([name, kind, len(parts) > 1, False])
        if alias_ok and k < n:
            a = k + 1 if word(k, "as") else k
            if (word(a) and toks[a][1].lower() not in _SQL_STOP | _CLAUSE_END) or (a > k and a < n and toks[a][0] == "q"):
                if name:
                    aliases[toks[a][1].lower()] = name
                k = a + 1
        return k

    i = 0
    while i < n:
        kind, val = toks[i]
        low = val.lower() if kind == "w" else ""
        prev = toks[i - 1][1].lower() if i and toks[i - 1][0] == "w" else ""
        if kind == "(":
            parens.append(prev)
            i += 1
            continue
        if kind == ")":
            if parens:
                parens.pop()
            lists = {d for d in lists if d <= len(parens)}
            i += 1
            continue
        depth = len(parens)
        if kind == "," and depth in lists:
            i = table_at(i + 1, "read")
            continue
        if kind != "w":
            i += 1
            continue
        if low in _CLAUSE_END:
            lists.discard(depth)
        if low == "from":
            infunc = bool(parens) and parens[-1] in _FROM_FUNCS
            if prev == "distinct" or infunc:
                i += 1
            else:
                lists.add(depth)
                i = table_at(i + 1, "write" if prev == "delete" else "read")
            continue
        if low == "join" or (low == "using" and using_ok):
            i = table_at(i + 1, "read", join=True)
            continue
        if low == "into":
            i = table_at(i + 1, "write", alias_ok=False)
            continue
        if low == "update" and prev not in _NOT_TARGET_PREV:
            j = i + 1
            while word(j, "only", "versioned"):
                j += 1
            start = len(events)
            i = table_at(j, "write")
            for ev in events[start:]:
                ev[3] = True
            continue
        if low == "delete" and prev not in _NOT_TARGET_PREV:
            using_ok = True
            if word(i + 1, "from"):
                i += 1
                continue
            start = len(events)
            j = i + 1
            if word(j) or toks[j:j + 1] and toks[j][0] in ("q", "ph"):
                i = table_at(j, "write", alias_ok=jpql)
                for ev in events[start:]:
                    ev[3] = True
                continue
        if low == "merge":
            using_ok = True
        if low == "truncate":
            i = table_at(i + 1, "write", alias_ok=False)
            continue
        i += 1
    rows = []
    for name, kind, qualified, alias_form in events:
        if alias_form and kind == "write" and not qualified:
            name = aliases.get(name.lower(), name)
        elif not qualified and name.lower() in ctes:
            continue
        rows.append((name, kind))
    return rows


def sql_edges(text: str) -> List[Tuple[str, str]]:
    """The `SQL_HOOK` for rules: `[(target, channel)]`, `table:<name>` with `persist` for a write and
    `read` for a read."""
    return [("table:" + t, "persist" if k == "write" else "read") for t, k in sql_tables(text)]


def jpql_edges(text: str) -> List[Tuple[str, str]]:
    """The same for JPQL: `entity:<Name>` edges."""
    return [("entity:" + t, "persist" if k == "write" else "read") for t, k in sql_tables(text, jpql=True)]


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
