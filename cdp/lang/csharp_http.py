"""C# HTTP clients as `http_out` edges, so `link scan` can match them to a server's routes.

Three styles, all from the source text (no compiler):

* **Refit** -- an interface whose methods carry `[Get("/path")]`, `[Post(...)]`, ...: one
  edge per method, `Interface#Method`, anchored at the attribute line.
* **HttpClient** -- `client.GetAsync("/x")`, `PostAsJsonAsync($"{Base}/x/{id}", ...)`,
  `new HttpRequestMessage(HttpMethod.Post, "/x")`.
* **RestSharp** -- `new RestRequest("/x", Method.Post)`.

The target is `http:<VERB> <url>`; a leading interpolated base (`{BaseUrl}/x`) is dropped,
the path kept. A URL that is not a string literal is skipped, not guessed. Test projects are
skipped: a test calling its own service is not a dependency.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .base import ExtractContext, FileFacts, anchor_at, mk_edge, strip_block_comments

_VERBS = ("Get", "Post", "Put", "Delete", "Patch", "Head", "Options")
_STR = r'\$?@?\$?"((?:[^"\\]|\\.)*)"'
REFIT_RE = re.compile(r"\[\s*(?:[\w.]+\s*:\s*)?(%s)\s*\(\s*%s" % ("|".join(_VERBS), _STR))
CALL_RE = re.compile(r"\.(Get|Post|Put|Delete|Patch)(?:String|ByteArray|Stream|FromJson|AsJson)?Async"
                     r"\s*(?:<[^()]*>)?\s*\(\s*" + _STR)
REQUEST_RE = re.compile(r"HttpRequestMessage\s*\(\s*(?:System\.Net\.Http\.)?HttpMethod\.(\w+)\s*,\s*" + _STR)
REST_RE = re.compile(r"\bRestRequest\s*\(\s*" + _STR + r"(?:\s*,\s*Method\.(\w+))?")
_TEST_PATH = re.compile(r"(?:[/._]|[a-z])Tests?(?:/|\.cs$)|(?:^|/)tests?/")
_HOLE_BASE = re.compile(r"^\{[^{}]*\}(?=/)")


def _url(raw: str) -> Optional[str]:
    """`{BaseUrl}/x/{id}` -> `/x/{id}`; a relative or absolute URL is kept; no path -> None."""
    raw = _HOLE_BASE.sub("", raw.strip())
    if not raw or not ("/" in raw):
        return None
    return raw


_NS_RE = re.compile(r"^\s*namespace\s+([A-Za-z_][\w.]*)")
_TYPE_RE = re.compile(r"^\s*(?:(?:public|internal|private|protected|static|sealed|abstract|partial|readonly|unsafe|new)\s+)*"
                      r"(?:class|interface|record|struct)\s+([A-Za-z_]\w*)")


def _types(code: List[str], primary: str):
    """`[(line index, fqn)]` of every type header, plus the file's namespace for the fqn."""
    ns = ""
    out = []
    for idx, line in enumerate(code):
        m = _NS_RE.match(line)
        if m and not ns:
            ns = m.group(1)
        t = _TYPE_RE.match(line)
        if t:
            out.append((idx, (ns + "." if ns else "") + t.group(1)))
    return out or [(0, primary)]


def _type_owner(types, idx: int) -> str:
    best = types[0][1]
    for at, fqn in types:
        if at <= idx:
            best = fqn
    return best


def _method_after(code: List[str], idx: int) -> Optional[str]:
    for j in range(idx, min(idx + 8, len(code))):
        line = re.sub(r"\[[^\]]*\]", " ", code[j])
        m = re.search(r"[\w<>\[\],.?]\s+([A-Za-z_]\w*)\s*(?:<[^()]*>)?\s*\(", line)
        if m:
            return m.group(1)
    return None


def emit_http_clients(ctx: ExtractContext, facts: FileFacts, primary: str) -> None:
    if _TEST_PATH.search(ctx.path):
        return
    code = strip_block_comments(ctx.lines)
    types = _types(code, primary)
    text = "\n".join(code)
    refit = "Refit" in text
    client = bool(re.search(r"HttpClient|HttpRequestMessage|RestSharp|RestClient", text))
    if not (refit or client):
        return
    for idx, line in enumerate(code):
        found = []  # (source, verb, url)
        if refit:
            for m in REFIT_RE.finditer(line):
                method = _method_after(code, idx)
                owner = _type_owner(types, idx)
                found.append(((owner + "#" + method) if method else owner, m.group(1).upper(), m.group(2)))
        if client:
            owner = _type_owner(types, idx)
            for m in CALL_RE.finditer(line):
                found.append((owner, m.group(1).upper(), m.group(2)))
            for m in REQUEST_RE.finditer(line):
                found.append((owner, m.group(1).upper(), m.group(2)))
            for m in REST_RE.finditer(line):
                found.append((owner, (m.group(2) or "Get").upper(), m.group(1)))
        for source, verb, raw in found:
            url = _url(raw)
            anchor = anchor_at(ctx, idx)
            if url is None or anchor is None:
                continue
            facts.signals.append("http_client")
            facts.io_edges.append(mk_edge(source, "http:%s %s" % (verb, url), "http_out", anchor))
