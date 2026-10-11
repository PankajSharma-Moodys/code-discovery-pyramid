"""Config reads through wrappers, resolved across files.

A method whose body reads a configuration key named by one of its *parameters*
(`getOptionalNonEmptyValue(ConfigProvider p, String key)` calling `p.getOptionalValue(key)`,
or `System.getenv(key)`) is a wrapper: its define row carries `cfgp` (parameter indexes).
Call rows carry `ka`, the key-like arguments at the call site (`[index, key]`, `key` a
literal, `${Type.CONST}` or `@pN` for the caller's own parameter N). A call to a wrapper
that passes a key at the wrapper's key parameter is a read of that key at the call site;
a call that passes its own parameter makes the caller a wrapper too, to a fixed point."""

from __future__ import annotations

from typing import Dict, List, Sequence, Set, Tuple

MAX_ROUNDS = 6


def wrapped_reads(symbols: Dict[str, Dict], calls: Sequence[Tuple[str, Dict]]) -> List[Dict]:
    """`calls`: `(resolved target, use row)` of every call row that carries `ka`.
    Returns `config_read` edge rows (`source`, `target`, `channel`, `file`, `module`,
    `anchor`, `wrapper`) for the reads those calls make through wrappers."""
    wrappers: Dict[str, Set[int]] = {f: set(e["cfgp"]) for f, e in symbols.items() if e.get("cfgp")}
    if not wrappers:
        return []
    out: Dict[Tuple, Dict] = {}
    for _ in range(MAX_ROUNDS):
        changed = False
        for target, row in calls:
            idxs = wrappers.get(target)
            if not idxs:
                continue
            for arg, key in row["ka"]:
                if arg not in idxs:
                    continue
                if key.startswith("@p"):
                    caller = row.get("from_symbol")
                    mine = wrappers.setdefault(caller, set()) if caller else None
                    if mine is not None and int(key[2:]) not in mine:
                        mine.add(int(key[2:]))
                        changed = True
                    continue
                site = (row["file"], row["anchor"]["line"], key)
                if site not in out:
                    out[site] = {"source": row.get("from_symbol") or "", "target": "config:" + key,
                                 "channel": "config_read", "file": row["file"], "module": row["module"],
                                 "anchor": row["anchor"], "wrapper": target}
        if not changed:
            break
    return sorted(out.values(), key=lambda r: (r["file"], r["anchor"]["line"], r["target"]))
