"""Type strings, and the little the extractor knows about the JDK.

A type is a string: `pkg.Foo`, `java.util.List<pkg.Foo>`, `pkg.Foo[]`, or `~T`
for a type variable. Names are the extractor's best guess (explicit import,
else same package); the resolve phase, which owns the symbol table, settles
them. The JDK model is only what chained calls and lambdas need: what a
collection, `Optional`, `Map` or `Stream` hands back.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

TOKEN = re.compile(r"[A-Za-z_$~][\w$.]*|[<>,\[\]?&]")

COLLECTIONS = frozenset(["List", "ArrayList", "LinkedList", "Collection", "Set", "HashSet", "TreeSet",
                         "LinkedHashSet", "SortedSet", "NavigableSet", "Queue", "Deque", "ArrayDeque",
                         "Iterable", "Iterator", "ListIterator", "Optional", "Stack", "Vector",
                         "PriorityQueue", "CopyOnWriteArrayList", "ImmutableList", "ImmutableSet",
                         "Stream", "ArgumentCaptor", "BlockingQueue", "LinkedBlockingQueue", "ConcurrentLinkedQueue"])
MAPS = frozenset(["Map", "HashMap", "TreeMap", "LinkedHashMap", "SortedMap", "NavigableMap",
                  "ConcurrentHashMap", "ConcurrentMap", "ImmutableMap", "Hashtable", "EnumMap"])
ELEMENT_OF = frozenset(["getValue", "get", "getFirst", "getLast", "peek", "poll", "pop", "first", "last", "next",
                        "orElse", "orElseThrow", "orElseGet", "element", "pollFirst", "pollLast",
                        "peekFirst", "peekLast", "removeFirst", "removeLast", "previous", "take",
                        "floor", "ceiling", "higher", "lower"])
SAME_TYPE = frozenset(["subList", "filter", "sorted", "distinct", "limit", "skip", "peek", "or",
                       "reversed", "headSet", "tailSet", "subSet", "parallel", "sequential",
                       "unordered", "onClose", "takeWhile", "dropWhile"])
VALUE_OF = frozenset(["get", "getOrDefault", "put", "remove", "computeIfAbsent", "putIfAbsent",
                      "computeIfPresent", "compute", "merge", "replace"])
LAMBDA_ELEMENT = frozenset(["forEach", "filter", "anyMatch", "allMatch", "noneMatch", "removeIf",
                            "peek", "map", "flatMap", "mapToInt", "mapToLong", "mapToDouble",
                            "mapToObj", "ifPresent", "ifPresentOrElse", "takeWhile", "dropWhile",
                            "sorted", "min", "max", "sort", "replaceAll", "forEachOrdered", "reduce",
                            "collect", "orElseGet", "ifPresentOrElse", "thenComparing"])
LAMBDA_MAP = frozenset(["forEach", "computeIfAbsent", "computeIfPresent", "compute", "merge",
                        "replaceAll"])


def split_type(t: str) -> Tuple[str, List[str], int]:
    """`java.util.Map<K,List<V>>[]` -> (`java.util.Map`, [`K`, `List<V>`], 1)."""
    t = t.strip()
    arrays = 0
    while t.endswith("[]"):
        t = t[:-2]
        arrays += 1
    lt = t.find("<")
    if lt < 0 or not t.endswith(">"):
        return t, [], arrays
    base, inner = t[:lt], t[lt + 1:-1]
    args, depth, cur = [], 0, []
    for ch in inner:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur))
    return base, [a.strip() for a in args], arrays


def simple(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def is_jdk(base: str) -> bool:
    base = split_type(base)[0]
    s = simple(base)
    return (s in COLLECTIONS or s in MAPS or s == "Entry") and ("." not in base or base.startswith(("java.", "com.google.common", "org.mockito.")))


def jdk_step(type_str: str, step: str) -> Optional[str]:
    """The type that `step` produces from `type_str`, per the JDK model.
    Steps: `m:name` a method call, `e` element, `k`/`v` map key/value, `a` array index."""
    base, args, arrays = split_type(type_str)
    if step == "a":
        return split_type(type_str)[0] + "[]" * (arrays - 1) if arrays else None
    if arrays:
        return None
    s = simple(base)
    first = args[0] if args else None
    if step == "e":
        if s in COLLECTIONS:
            return first
        if s in MAPS:
            return "java.util.Map.Entry<%s>" % ",".join(args) if len(args) == 2 else None
        return None
    if step == "k":
        return first if s in MAPS else None
    if step == "v":
        return args[1] if s in MAPS and len(args) == 2 else None
    if not step.startswith("m:"):
        return None
    name = step[2:]
    if s in COLLECTIONS:
        if name in ELEMENT_OF:
            return first
        if name in SAME_TYPE:
            return type_str
        if name == "stream" or name == "parallelStream":
            return "java.util.stream.Stream<%s>" % first if first else None
        if name == "iterator":
            return "java.util.Iterator<%s>" % first if first else None
        if name in ("findFirst", "findAny", "min", "max") and s == "Stream":
            return "java.util.Optional<%s>" % first if first else None
        if name == "toList" and s == "Stream":
            return "java.util.List<%s>" % first if first else None
        return None
    if s in MAPS and len(args) == 2:
        if name in VALUE_OF:
            return args[1]
        if name == "values":
            return "java.util.Collection<%s>" % args[1]
        if name == "keySet":
            return "java.util.Set<%s>" % args[0]
        if name == "entrySet":
            return "java.util.Set<java.util.Map.Entry<%s>>" % ",".join(args)
        return None
    if s == "Entry" and len(args) == 2:
        return args[0] if name == "getKey" else args[1] if name == "getValue" else None
    return None


def norm_type(text: str, resolve, tvars=frozenset()) -> str:
    """Resolve every name in a type text through `resolve(name) -> fqn`.
    Names in `tvars` become `~T`. Wildcards keep their bound."""
    toks = TOKEN.findall(text.replace("...", "[]"))
    pos = 0

    def parse() -> str:
        nonlocal pos
        out = ""
        while pos < len(toks):
            t = toks[pos]
            if t in ("extends", "super", "&"):
                pos += 1
                continue
            if t == "?":
                pos += 1
                if pos < len(toks) and toks[pos] in ("extends", "super"):
                    continue
                return "?"
            if t in (",", ">", "]"):
                break
            if t == "[":
                pos += 2
                out += "[]"
                continue
            if t == "<":
                pos += 1
                args = []
                while pos < len(toks) and toks[pos] != ">":
                    if toks[pos] == ",":
                        pos += 1
                        continue
                    args.append(parse())
                pos += 1
                out += "<" + ",".join(args) + ">"
                continue
            pos += 1
            out += ("~" + t) if t in tvars else resolve(t)
        return out

    return parse()


PRIMS = frozenset(["int", "long", "double", "float", "boolean", "byte", "short", "char", "void"])


def resolve_name(resolver, name: str) -> str:
    """A (possibly dotted) type name through the file's imports and package."""
    if name in PRIMS:
        return name
    return resolver.resolve(name)[0]


def wildcard_alts(resolver, fqn: str, suffix: str = "") -> List[str]:
    """Wildcard-import candidates for a name this file could not settle: the part
    of `fqn` below the file's own package (`Outer.Inner`), or its simple name."""
    pkg = resolver.pkg
    base = fqn.split("#", 1)[0]
    rel = base[len(pkg) + 1:] if pkg and base.startswith(pkg + ".") else base.rsplit(".", 1)[-1]
    return [w + "." + rel + suffix for w in resolver.wildcards]
