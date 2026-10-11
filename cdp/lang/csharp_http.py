"""C# HTTP clients as `http_out` edges, so `link scan` can match them to a server's routes.

Three styles, all from the source text (no compiler):

* **Refit** -- an interface whose methods carry `[Get("/path")]`, `[Post(...)]`, ...: one
  edge per method, `Interface#Method`, anchored at the attribute line.
* **HttpClient** -- `client.GetAsync("/x")` (the receiver must be provably an HTTP client: a variable,
  field, parameter or property typed `HttpClient`/`RestClient`, assigned `new HttpClient()` or
  `factory.CreateClient(..)`, or one of those expressions itself; the first argument must look like a
  path or URL, so `repo.GetAsync("a/b")` and `cache.GetAsync("some key")` are not edges), `PostAsJsonAsync($"{Base}/x/{id}", ...)`,
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
_CLIENT_TYPE = r"(?:System\.Net\.Http\.)?(?:HttpClient|RestClient|IRestClient|HttpMessageInvoker)"
_TYPED_RE = re.compile(r"\b" + _CLIENT_TYPE + r"\??\s+(@?\w+)")
_MADE_RE = re.compile(r"\b(@?\w+)\s*=\s*(?:await\s+)?(?:new\s+" + _CLIENT_TYPE + r"\b|[\w.?]*\bCreateClient\s*\()")
_COPY_RE = re.compile(r"\b(@?\w+)\s*=\s*(?:this\.)?(@?\w+)\s*[;,)]")
_RECV_MADE_RE = re.compile(r"(?:new\s+" + _CLIENT_TYPE + r"\s*\([^()]*\)|\bCreateClient\s*\([^()]*\))\s*$")
_RECV_NAME_RE = re.compile(r"(@?\w+)[?!]?$")
_URLISH = re.compile(r"^(?:/|https?://|\{[^{}]*\}/|[^\s/{}][^\s]*/)[^\s]*$")
_TEST_PATH = re.compile(r"(?:[/._]|[a-z])Tests?(?:/|\.cs$)|(?:^|/)tests?/")
_HOLE_BASE = re.compile(r"^\{[^{}]*\}(?=/)")


def _url(raw: str) -> Optional[str]:
    """`{BaseUrl}/x/{id}` -> `/x/{id}`; a relative or absolute URL is kept; no path -> None."""
    raw = _HOLE_BASE.sub("", raw.strip())
    if not raw or not _URLISH.match(raw):
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


def _clients(code: List[str]) -> set:
    """Names the file declares or assigns as an HTTP client (`_http`, `client`, `Client`...)."""
    text = "\n".join(code)
    names = set(_TYPED_RE.findall(text)) | set(_MADE_RE.findall(text))
    for _ in range(3):                      # `_client = client;` after `HttpClient client` is a parameter
        grown = {a for a, b in _COPY_RE.findall(text) if b in names}
        if grown <= names:
            break
        names |= grown
    return {n.lstrip("@") for n in names} | names


def _receiver_ok(code: List[str], idx: int, col: int, names: set) -> bool:
    """Is the expression just before `.XxxAsync(` at `code[idx][col]` an HTTP client?"""
    before = code[idx][:col]
    j = idx
    while not before.strip() and j > 0:     # a fluent call split across lines
        j -= 1
        before = code[j]
    before = before.rstrip()
    if _RECV_MADE_RE.search(before):
        return True
    m = _RECV_NAME_RE.search(before)
    return bool(m) and m.group(1) in names


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
    names = _clients(code) if client else set()
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
                if _receiver_ok(code, idx, m.start(), names):
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
