"""The extractor seam.

RESEARCH.md §9 names language coverage as a standing limitation: "the vocabulary
is intended to be language-independent; the detectors are not." This module is
where that separation is enforced. The channel vocabulary (§6.2), the claim
schema, and every downstream phase are language-neutral; everything that knows
what an `import` statement looks like lives behind `Extractor`.

Adding a language means adding one file to `cdp/lang/` and registering it. It
means touching nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..anchor import build_anchor
from ..util import normalise_ws

# Import prefixes that are never internal to a repository. The resolve phase
# (§6.4) uses this to separate "third_party" from "unresolved": a use it cannot
# match against the global symbol table is only a finding if it looked like it
# should have matched.
THIRD_PARTY_PREFIXES: Tuple[str, ...] = (
    "java.", "javax.", "jakarta.", "jdk.", "sun.", "kotlin.", "scala.", "groovy.",
    "org.springframework.", "org.hibernate.", "org.apache.", "org.slf4j.",
    "org.junit.", "org.mockito.", "org.assertj.", "org.testng.", "org.quartz.",
    "org.json.", "org.yaml.", "org.w3c.", "org.xml.", "org.reactivestreams.",
    "com.google.", "com.fasterxml.", "com.codahale.", "com.jcraft.",
    "com.microsoft.", "com.amazonaws.", "com.azure.", "com.zaxxer", "com.sun.",
    "io.dropwizard.", "io.swagger.", "io.prometheus.", "io.netty.", "io.micrometer.",
    "io.reactivex.", "lombok.", "ch.qos.", "net.sf.", "reactor.", "graphql.",
    "software.amazon.", "feign.", "retrofit2.", "okhttp3.",
)

# Coarse per-language channel hints keyed on an import prefix. These are the
# §6.2 "signal" column, made machine-checkable. A hit produces an io_edge whose
# anchor is the import line itself, which is a genuinely citable fact: the file
# does import the thing.
IMPORT_CHANNEL_HINTS: Tuple[Tuple[str, str], ...] = (
    # --- JVM
    ("javax.ws.rs", "http_in"),
    ("jakarta.ws.rs", "http_in"),
    ("org.springframework.web.bind.annotation", "http_in"),
    ("io.dropwizard.jersey", "http_in"),
    ("javax.persistence", "persist"),
    ("jakarta.persistence", "persist"),
    ("org.springframework.data", "persist"),
    ("org.hibernate", "persist"),
    ("org.apache.http", "http_out"),
    ("okhttp3", "http_out"),
    ("retrofit2", "http_out"),
    ("java.net.http", "http_out"),
    ("org.springframework.web.client", "http_out"),
    ("com.jcraft.jsch", "ssh_exec"),
    ("org.quartz", "schedule"),
    ("io.dropwizard.jobs", "schedule"),
    ("org.springframework.scheduling", "schedule"),
    ("io.prometheus", "metric_emit"),
    ("com.codahale.metrics", "metric_emit"),
    ("io.micrometer", "metric_emit"),
    ("org.mapstruct", "map"),
    # --- Python
    ("flask", "http_in"),
    ("fastapi", "http_in"),
    ("django.urls", "http_in"),
    ("starlette", "http_in"),
    ("requests", "http_out"),
    ("httpx", "http_out"),
    ("aiohttp", "http_out"),
    ("urllib.request", "http_out"),
    ("sqlalchemy", "persist"),
    ("psycopg2", "persist"),
    ("pymysql", "persist"),
    ("pymongo", "persist"),
    ("django.db", "persist"),
    ("celery", "schedule"),
    ("apscheduler", "schedule"),
    ("paramiko", "ssh_exec"),
    ("prometheus_client", "metric_emit"),
    ("kafka", "event_publish"),
    ("pika", "event_publish"),
    # --- JS / TS
    ("express", "http_in"),
    ("fastify", "http_in"),
    ("koa", "http_in"),
    ("@nestjs/common", "http_in"),
    ("axios", "http_out"),
    ("node-fetch", "http_out"),
    ("got", "http_out"),
    ("typeorm", "persist"),
    ("sequelize", "persist"),
    ("mongoose", "persist"),
    ("@prisma/client", "persist"),
    ("pg", "persist"),
    ("node-cron", "schedule"),
    ("bull", "schedule"),
    ("kafkajs", "event_publish"),
    ("amqplib", "event_publish"),
    ("prom-client", "metric_emit"),
    # --- Go
    ("net/http", "http_out"),
    ("database/sql", "persist"),
    ("gorm.io/gorm", "persist"),
    ("github.com/gin-gonic/gin", "http_in"),
    ("github.com/gorilla/mux", "http_in"),
    ("golang.org/x/crypto/ssh", "ssh_exec"),
    ("github.com/prometheus/client_golang", "metric_emit"),
)


@dataclass
class FileFacts:
    """Everything one extractor learned about one file.

    Deliberately flat and JSON-shaped: these fields feed `defines[]`, `uses[]`
    and `io_edges[]` in the patch schema directly, so an extractor bug shows up
    as bad JSON rather than as a bad object graph.
    """

    path: str
    language: str
    loc: int = 0
    package: Optional[str] = None
    # The symbol this file is "about" — the type the data-flow graph uses as the
    # node for anything declared here. Without it a `call` edge would have to be
    # drawn from a file path, and paths are not symbols.
    primary: Optional[str] = None
    imports: List[Dict] = field(default_factory=list)
    defines: List[Dict] = field(default_factory=list)
    uses: List[Dict] = field(default_factory=list)
    io_edges: List[Dict] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)
    # Declared build dependencies, for build manifests only (§5.2 declared arm).
    declared_deps: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ExtractContext:
    path: str
    lines: List[str]
    module: str


class Extractor:
    """Base class. Subclasses set `language` and either `extensions` or `names`."""

    language: str = "unknown"
    extensions: Tuple[str, ...] = ()
    names: Tuple[str, ...] = ()
    role: str = "source"

    def extract(self, ctx: ExtractContext) -> FileFacts:  # pragma: no cover - abstract
        raise NotImplementedError


# ------------------------------------------------------------------ helpers


def anchor_at(ctx: ExtractContext, index: int) -> Optional[Dict]:
    return build_anchor(ctx.path, ctx.lines, index)


def mk_define(fqn: str, kind: str, visibility: str, anchor: Dict, value: Optional[str] = None) -> Dict:
    row = {"fqn": fqn, "kind": kind, "visibility": visibility, "anchor": anchor}
    if value is not None:
        row["value"] = value
    return row


def mk_use(fqn: str, anchor: Dict, via_import: bool = False, resolved: str = "external") -> Dict:
    return {"fqn": fqn, "resolved": resolved, "via_import": via_import, "anchor": anchor}


def mk_edge(source: str, target: str, channel: str, anchor: Dict) -> Dict:
    return {"source": source, "target": target, "channel": channel, "anchor": anchor}


def channel_for_import(fqn: str) -> Optional[str]:
    """Longest-prefix match against IMPORT_CHANNEL_HINTS. Longest wins so that
    `org.springframework.data` beats a hypothetical `org.springframework` entry.
    """
    best: Optional[Tuple[int, str]] = None
    for prefix, channel in IMPORT_CHANNEL_HINTS:
        if fqn == prefix or fqn.startswith(prefix + ".") or fqn.startswith(prefix + "/"):
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), channel)
    return best[1] if best else None


def is_third_party(fqn: str) -> bool:
    return any(fqn.startswith(p) for p in THIRD_PARTY_PREFIXES)


def strip_block_comments(lines: Sequence[str]) -> List[str]:
    """Blank out /* ... */ and // and # comment bodies, preserving line count.

    Line count preservation is not a nicety: every anchor in the run is a line
    number into the *original* file, so an extractor that reads a compacted copy
    would cite locations that do not exist.
    """
    out: List[str] = []
    in_block = False
    for raw in lines:
        line = raw
        result = []
        i = 0
        while i < len(line):
            if in_block:
                end = line.find("*/", i)
                if end == -1:
                    i = len(line)
                else:
                    in_block = False
                    i = end + 2
                continue
            start = line.find("/*", i)
            slash = line.find("//", i)
            if start != -1 and (slash == -1 or start < slash):
                result.append(line[i:start])
                in_block = True
                i = start + 2
                continue
            if slash != -1:
                result.append(line[i:slash])
                i = len(line)
                continue
            result.append(line[i:])
            i = len(line)
        out.append("".join(result))
    return out


STRING_LITERAL = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')


def first_string_literal(text: str) -> Optional[str]:
    m = STRING_LITERAL.search(text)
    return m.group(1) if m else None


def count_loc(lines: Sequence[str]) -> int:
    """Non-blank lines. Blank-line counts vary with formatter settings and would
    make the leaf budget in §3.3 a function of code style rather than content.
    """
    return sum(1 for line in lines if normalise_ws(line))
