"""Configuration reads in C# member bodies (B13).

`Environment.GetEnvironmentVariable("K")` and `IConfiguration` reads -- `cfg["A:B"]`,
`cfg.GetValue<T>("k")`, `cfg.GetSection("A")["B"]`, `cfg.GetConnectionString("n")`,
`cfg.GetSection("A").Get<T>()` / `.Bind(x)` -- each become a `config_read` edge from the
enclosing member to `config:<key>` (sections joined with `:`, as .NET does). The key is a string
literal, a constant, or a concatenation of those; a constant of another type stays `${Type.NAME}`
for the resolve phase, which holds the constant table; a computed key is `config:(dynamic)`.

A receiver is an `IConfiguration` when the file declares its name with a configuration type, or
when its last identifier says so (`configuration`, `_config`, `builder.Configuration`).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .base import ExtractContext, FileFacts, anchor_at, mk_edge
from .csharp_tokens import CsTokens, string_value

DYNAMIC = "(dynamic)"
CFG_TYPES = frozenset(["IConfiguration", "IConfigurationSection", "IConfigurationRoot", "ConfigurationManager",
                       "IConfigurationBuilder"])
NAME_HINT = re.compile(r"config|settings", re.I)
SECTION = frozenset(["GetSection", "GetRequiredSection"])
READS = frozenset(["GetValue", "GetConnectionString", "GetRequiredValue"])
BINDS = frozenset(["Get", "Bind"])


KEYWORDS = frozenset(["return", "await", "new", "throw", "in", "is", "as", "case", "out", "ref", "var", "yield",
                      "else", "goto", "typeof", "default", "using", "params", "this", "base", "when", "and", "or"])


class ConfigNames:
    """Which identifiers of a file are configuration objects: those declared with a configuration
    type are; those declared with any other type are not (`kubeConfigCache` is a dictionary);
    an undeclared one (`builder.Configuration`) is judged by its name."""

    def __init__(self, tk: CsTokens) -> None:
        self.yes: Set[str] = set()
        self.no: Set[str] = set()
        for i in range(1, tk.n):
            if tk.kind[i] != "id" or tk.at(i + 1) not in ("=", ";", ",", ")", "{", "(", "=>", ":") or tk.text[i] in KEYWORDS:
                continue
            p = tk.text[i - 1]
            if tk.kind[i - 1] == "id" and p not in KEYWORDS:
                (self.yes if p in CFG_TYPES else self.no).add(tk.text[i])
            elif p in (">", "]") or (p == "?" and tk.kind[i - 2] == "id"):
                # generic / array / nullable type: look through to its head
                j = i - 1
                if p == ">":
                    depth = 0
                    while j > 0:
                        if tk.text[j] == ">":
                            depth += 1
                        elif tk.text[j] == "<":
                            depth -= 1
                            if depth == 0:
                                break
                        j -= 1
                    head = tk.text[j - 1] if j > 0 else ""
                elif p == "]":
                    head = tk.text[tk.match[i - 1] - 1] if tk.match[i - 1] > 0 else ""
                else:
                    head = tk.text[i - 2]
                (self.yes if head in CFG_TYPES else self.no).add(tk.text[i])
        self.no -= self.yes

    def is_config(self, name: str) -> bool:
        if name in self.yes:
            return True
        return name not in self.no and bool(NAME_HINT.search(name))


def config_names(tk: CsTokens) -> "ConfigNames":
    return ConfigNames(tk)


def _split_args(tk: CsTokens, open_i: int) -> List[Tuple[int, int]]:
    close = tk.close(open_i)
    out: List[Tuple[int, int]] = []
    a = open_i + 1
    j = a
    while j < close:
        if tk.kind[j] == "op" and tk.text[j] in "([{":
            j = tk.close(j)
        elif tk.text[j] == "," and tk.kind[j] == "op":
            out.append((a, j))
            a = j + 1
        j += 1
    if a < close:
        out.append((a, close))
    return out


def key_of(tk: CsTokens, a: int, b: int, constants: Dict[str, str], own: str) -> str:
    """The key an argument expression denotes: literal text, `${Type.NAME}`, or `(dynamic)`."""
    parts: List[str] = []
    j = a
    while j < b:
        k, t = tk.kind[j], tk.text[j]
        if k == "str":
            v = string_value(t)
            if v is None:
                return DYNAMIC
            parts.append(v)
            j += 1
        elif k == "id" and t == "nameof" and tk.at(j + 1) == "(":
            c = tk.close(j + 1)
            if c - 1 > j + 1 and tk.is_id(c - 1):
                parts.append(tk.text[c - 1])
            else:
                return DYNAMIC
            j = c + 1
        elif k == "id" and t not in ("new", "this", "base", "typeof", "default"):
            names = [t]
            while tk.at(j + 1) == "." and tk.is_id(j + 2):
                names.append(tk.text[j + 2])
                j += 2
            if tk.at(j + 1) in ("(", "[", "<", "?."):
                return DYNAMIC
            if len(names) == 1 and names[0] in constants:
                parts.append(constants[names[0]])
            else:
                head = [own(names[0]) if callable(own) else own] + names if len(names) == 1 else names[-2:]
                parts.append("${%s}" % ".".join(head))
            j += 1
        elif t == "(" and k == "op":
            c = tk.close(j)
            if c != b - 1:
                return DYNAMIC
            return key_of(tk, j + 1, c, constants, own)
        else:
            return DYNAMIC
        if j < b:
            if tk.at(j) != "+":
                return DYNAMIC
            j += 1
            if j >= b:
                return DYNAMIC
    return "".join(parts) if parts else DYNAMIC


def _is_config_recv(tk: CsTokens, end: int, cfg: ConfigNames) -> bool:
    """Is the expression ending at token `end` (inclusive) a configuration object?"""
    if end < 0:
        return False
    t = tk.text[end]
    if tk.kind[end] == "id":
        return cfg.is_config(t)
    if t == ")":
        o = tk.match[end]
        if o > 0 and tk.is_id(o - 1) and tk.text[o - 1] in SECTION:
            return True
        # `provider.GetService<IConfiguration>()`
        if o > 0 and tk.text[o - 1] == ">" and any(tk.text[q] in CFG_TYPES for q in range(max(0, o - 8), o - 1)):
            return True
    return False


def _prefix(tk: CsTokens, end: int, constants, own) -> Optional[str]:
    """Section path of the receiver ending at `end`: `X.GetSection("A").GetSection("B")` -> `A:B`;
    "" for a plain configuration object; None when a section key is computed."""
    if end >= 0 and tk.text[end] == ")":
        o = tk.match[end]
        if o > 0 and tk.is_id(o - 1) and tk.text[o - 1] in SECTION and tk.at(o - 2) in (".", "?."):
            args = _split_args(tk, o)
            if len(args) != 1:
                return None
            key = key_of(tk, *args[0], constants, own)
            if key == DYNAMIC:
                return None
            outer = _prefix(tk, o - 3, constants, own)
            if outer is None:
                return None
            return outer + ":" + key if outer else key
    return ""


def _join(prefix: Optional[str], key: str) -> str:
    if prefix is None or key == DYNAMIC:
        return DYNAMIC
    return prefix + ":" + key if prefix else key


def emit_config(ctx: ExtractContext, facts: FileFacts, tk: CsTokens, a: int, b: int, symbol: str,
                constants: Dict[str, str], own: str, cfg: "ConfigNames") -> None:
    def edge(line: int, key: str) -> None:
        anchor = anchor_at(ctx, line)
        if anchor is not None:
            facts.signals.append("config_read")
            facts.io_edges.append(mk_edge(symbol, "config:" + key, "config_read", anchor))

    for i in range(a, b):
        t = tk.text[i]
        if tk.kind[i] == "id" and t == "GetEnvironmentVariable" and tk.at(i + 1) == "(" and tk.at(i - 1) == "." \
                and tk.at(i - 2) == "Environment":
            args = _split_args(tk, i + 1)
            if args:
                edge(tk.line[i], key_of(tk, *args[0], constants, own))
            continue
        if tk.kind[i] == "op" and t == "[" and i > a and tk.match[i] > i:
            if not _is_config_recv(tk, i - 1, cfg) and not (tk.at(i - 1) == "!" and _is_config_recv(tk, i - 2, cfg)):
                continue
            end = i - 1 if tk.at(i - 1) != "!" else i - 2
            args = _split_args(tk, i)
            if len(args) == 1:
                edge(tk.line[i], _join(_prefix(tk, end, constants, own), key_of(tk, *args[0], constants, own)))
            continue
        if tk.kind[i] != "id" or tk.at(i - 1) not in (".", "?.") or i <= a:
            continue
        o = i + 1
        if tk.at(o) == "<":
            from .csharp_decl import skip_angle
            k = skip_angle(tk, o)
            if k is None:
                continue
            o = k
        if tk.at(o) != "(":
            continue
        recv_end = i - 2
        if t in READS or t in SECTION:
            if not _is_config_recv(tk, recv_end, cfg):
                continue
            args = _split_args(tk, o)
            if not args:
                continue
            key = key_of(tk, *args[0], constants, own)
            prefix = _prefix(tk, recv_end, constants, own)
            if t == "GetConnectionString":
                key = DYNAMIC if key == DYNAMIC else "ConnectionStrings:" + key
                prefix = ""
            edge(tk.line[i], _join(prefix, key))
        elif t in BINDS and tk.at(recv_end) == ")":
            op = tk.match[recv_end]
            if op > 0 and tk.text[op - 1] in SECTION and _is_config_recv(tk, recv_end, cfg):
                prefix = _prefix(tk, recv_end, constants, own)
                edge(tk.line[i], DYNAMIC if prefix is None else prefix)
