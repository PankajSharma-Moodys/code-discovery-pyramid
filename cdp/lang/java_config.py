"""Environment and system-property reads in Java member bodies (B13).

`System.getenv("K")`, `System.getProperty("k"[, d])`, `Long.getLong`,
`Integer.getInteger`, `Boolean.getBoolean` and `System.getenv().getOrDefault("K", d)`
each become a `config_read` edge from the enclosing member to `config:<key>`.

The key is the string literal, a constant of this file, or a concatenation of those.
A constant declared elsewhere is left as `${Type.NAME}` for the resolve phase, which
holds the constant table (as for route paths); a key computed at run time is
`config:(dynamic)`, so the read is still counted and cited rather than lost.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .base import ExtractContext, FileFacts, anchor_at, first_string_literal, mk_edge
from .java_tokens import Tokens

DYNAMIC = "(dynamic)"
#: (class, method) -> the call reads a key from its first argument.
KEY_APIS = frozenset([("System", "getenv"), ("System", "getProperty"), ("Long", "getLong"),
                      ("Integer", "getInteger"), ("Boolean", "getBoolean")])
ENV_MAP_READS = frozenset(["getOrDefault", "get"])
#: Key-reading methods of a configuration/properties/environment provider
#: (`configProvider.getValue(KEY)`, `env.getProperty("k")`). `get` and `getOrDefault`
#: are also Map methods, so they need a receiver that says "config" outright.
PROVIDER_METHODS = frozenset(["getValue", "getOptionalValue", "getRequiredValue", "getValueOrDefault",
                              "getString", "getInt", "getInteger", "getLong", "getBoolean", "getDouble",
                              "getProperty", "getRequiredProperty", "getEnv", "getenv", "getOptional",
                              "get", "getOrDefault"])
MAP_LIKE = frozenset(["get", "getOrDefault"])
PROVIDER_TYPE = re.compile(r"config|propert|environment|settings?$", re.I)
PROVIDER_NAME = re.compile(r"(?i:config|setting|environment|propert)|^env$|^env[A-Z_]|Env$|^props?$|Props$")
STRONG_NAME = re.compile(r"(?i:config|setting|environment)|^env$|^env[A-Z_]|Env$")
KEYLIKE = re.compile(r"^[A-Za-z][\w.\-]{2,}$")
ALL_CAPS = re.compile(r"^[A-Z][A-Z0-9_]*$")


def provider_names(tk: Tokens) -> frozenset:
    """Variables, fields and parameters declared with a configuration-ish type."""
    out = set()
    for i in range(tk.n):
        if tk.kind[i] != "id" or not tk.text[i][:1].isupper() or not PROVIDER_TYPE.search(tk.text[i]):
            continue
        j = i + 1
        if tk.at(j) == "<":
            j = tk.skip_angle(j) or j
        if tk.is_id(j) and tk.at(j + 1) in ("=", ";", ",", ")"):
            out.add(tk.text[j])
    return frozenset(out)


def _receiver_ids(tk: Tokens, dot_i: int) -> List[str]:
    """Identifiers of the receiver chain left of the `.` at `dot_i`, nearest first."""
    ids: List[str] = []
    p = dot_i - 1
    while p >= 0:
        if tk.at(p) in (")", "]"):
            if tk.match[p] < 0:
                break
            p = tk.match[p] - 1
            continue
        if tk.is_id(p):
            ids.append(tk.text[p])
            if tk.at(p - 1) == ".":
                p -= 2
                continue
        break
    return ids


def key_arg(tk: Tokens, a: int, b: int, constants: Dict[str, str], static_imports: Dict[str, str],
            own_types: frozenset) -> Optional[str]:
    """The key a *single* literal or constant argument names (no concatenation), else None."""
    if b - a == 1 and tk.kind[a] == "str":
        lit = first_string_literal(tk.text[a])
        return lit if lit and KEYLIKE.match(lit) else None
    if b <= a or tk.kind[a] != "id" or not ALL_CAPS.match(tk.text[b - 1]):
        return None
    if any(not (tk.kind[j] == "id" or tk.text[j] == ".") for j in range(a, b)):
        return None
    key = _key(tk, a, b, constants, static_imports, own_types)
    return None if key == DYNAMIC else key


def _args(tk: Tokens, open_i: int) -> List[Tuple[int, int]]:
    """Token ranges `[a, b)` of the top-level arguments of the call opened at `open_i`."""
    close = tk.close(open_i)
    out: List[Tuple[int, int]] = []
    start, j = open_i + 1, open_i + 1
    while j < close:
        if tk.kind[j] == "op" and tk.text[j] in "([{":
            j = tk.close(j)
        elif tk.kind[j] == "op" and tk.text[j] == ",":
            out.append((start, j))
            start = j + 1
        j += 1
    if start < close:
        out.append((start, close))
    return out


def _key(tk: Tokens, a: int, b: int, constants: Dict[str, str], static_imports: Dict[str, str],
         own_types: frozenset) -> str:
    """The key an argument expression names, `${Type.NAME}` for a constant elsewhere, or `(dynamic)`."""
    parts: List[str] = []
    i = a
    while i < b:
        k, t = tk.kind[i], tk.text[i]
        if k == "str":
            lit = first_string_literal(t)
            if lit is None:
                return DYNAMIC
            parts.append(lit)
            i += 1
        elif k == "id" and tk.at(i + 1) == ".":
            chain = [t]
            j = i
            while tk.at(j + 1) == "." and tk.is_id(j + 2):
                chain.append(tk.text[j + 2])
                j += 2
            if j + 1 < b and tk.at(j + 1) != "+":
                return DYNAMIC  # a call or index on the way: computed
            owner, name = chain[-2], chain[-1]
            if owner in own_types and name in constants:
                parts.append(constants[name])
            else:
                parts.append("${%s.%s}" % (owner, name))
            i = j + 1
        elif k == "id" and (i + 1 >= b or tk.at(i + 1) == "+") and t not in ("null", "true", "false"):
            if t in constants:
                parts.append(constants[t])
            elif t in static_imports:
                parts.append("${%s.%s}" % (static_imports[t].rsplit(".", 1)[-1], t))
            else:
                return DYNAMIC
            i += 1
        else:
            return DYNAMIC
        if i < b:
            if tk.at(i) != "+":
                return DYNAMIC
            i += 1
    return "".join(parts) if parts else DYNAMIC


def emit_config(ctx: ExtractContext, facts: FileFacts, tk: Tokens, a: int, b: int, caller: str,
                constants: Dict[str, str], static_imports: Dict[str, str], own_types: frozenset,
                params: Sequence[str] = ()) -> None:
    for i in range(a, b):
        if tk.kind[i] != "id" or tk.at(i + 1) != "." or not tk.is_id(i + 2) or tk.at(i + 3) != "(":
            continue
        cls, name, open_i = tk.text[i], tk.text[i + 2], i + 3
        if tk.at(i - 1) == "." and tk.at(i - 2) != "lang" and tk.at(i - 2) not in ("util",):
            continue  # `x.System.getenv`: someone else's type
        args = _args(tk, open_i)
        line_i, rng = i + 2, None
        if (cls, name) in KEY_APIS:
            if args:
                rng = args[0]
            elif (cls, name) == ("System", "getenv"):
                # `System.getenv().getOrDefault("K", d)` / `.get("K")`
                c = tk.close(open_i)
                if tk.at(c + 1) == "." and tk.at(c + 2) in ENV_MAP_READS and tk.at(c + 3) == "(":
                    inner = _args(tk, c + 3)
                    if inner:
                        rng, line_i = inner[0], c + 2
        if rng is None:
            continue
        anchor = anchor_at(ctx, tk.line[line_i])
        if anchor is None:
            continue
        key = _key(tk, rng[0], rng[1], constants, static_imports, own_types)
        if key == DYNAMIC and rng[1] - rng[0] == 1 and tk.text[rng[0]] in params:
            _note_wrapper(facts, caller, list(params).index(tk.text[rng[0]]))
        facts.io_edges.append(mk_edge(caller, "config:" + key, "config_read", anchor))


def _note_wrapper(facts: FileFacts, caller: str, idx: int) -> None:
    for d in facts.defines:
        if d["fqn"] == caller and d["kind"] == "method":
            if idx not in d.setdefault("cfgp", []):
                d["cfgp"].append(idx)


def emit_provider_reads(ctx: ExtractContext, facts: FileFacts, tk: Tokens, a: int, b: int, caller: str,
                        constants: Dict[str, str], static_imports: Dict[str, str], own_types: frozenset,
                        providers: frozenset, params: Sequence[str] = ()) -> None:
    """`configProvider.getValue(KEY)`: a read of a key through a configuration provider.

    The receiver must say it is one (its declared type or any name in its chain mentions
    config / properties / environment) and the key must be a literal or a constant: a
    computed key on a guessed receiver names nothing. A call whose key is a *parameter*
    of the enclosing method marks that method a wrapper (`cfgp` on its define row); the
    resolve phase turns calls to wrappers into reads of the key they pass."""
    for i in range(a, b):
        if tk.kind[i] != "id" or tk.text[i] not in PROVIDER_METHODS or tk.at(i - 1) != "." or tk.at(i + 1) != "(":
            continue
        ids = _receiver_ids(tk, i - 1)
        if not ids or "System" in ids or ids[-1] in ("Long", "Integer", "Boolean"):
            continue
        name = tk.text[i]
        named = any((STRONG_NAME if name in MAP_LIKE else PROVIDER_NAME).search(x) for x in ids)
        if not (named or (name not in MAP_LIKE and any(x in providers for x in ids))):
            continue
        args = _args(tk, i + 1)
        if not args:
            continue
        a0, b0 = args[0]
        key = key_arg(tk, a0, b0, constants, static_imports, own_types)
        if key is None:
            if b0 - a0 == 1 and tk.text[a0] in params:
                _note_wrapper(facts, caller, list(params).index(tk.text[a0]))
            continue
        anchor = anchor_at(ctx, tk.line[i])
        if anchor is not None:
            edge = mk_edge(caller, "config:" + key, "config_read", anchor)
            edge["provider"] = True
            facts.io_edges.append(edge)


def call_keys(tk: Tokens, open_i: int, constants: Dict[str, str], static_imports: Dict[str, str],
              own_types: frozenset, params: Dict[str, int]) -> List[list]:
    """Key-like arguments of the call opened at `open_i`, as `[arg index, key]`: a literal or
    constant key, or `"@pN"` when the argument is the enclosing method's parameter N. These
    ride on the call row so a call to a wrapper (a method that reads the key its parameter
    names) can be read as a read of that key."""
    out: List[list] = []
    for idx, (a, b) in enumerate(_args(tk, open_i)[:3]):
        if b - a == 1 and tk.kind[a] == "id" and tk.text[a] in params:
            out.append([idx, "@p%d" % params[tk.text[a]]])
            continue
        key = key_arg(tk, a, b, constants, static_imports, own_types)
        if key:
            out.append([idx, key])
    return out
