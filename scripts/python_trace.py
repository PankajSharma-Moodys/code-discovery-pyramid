#!/usr/bin/env python3
"""Runtime call truth: every call that really happened, via `sys.monitoring`.

    python scripts/python_trace.py ROOT OUT.jsonl -- pytest -q tests/test_x.py
    python scripts/python_trace.py ROOT OUT.jsonl --script path/to/exercise.py

Records `(caller file, line span, callee def)` for each CALL instruction executed
in a file under ROOT whose callee is a Python function (or a class, taken to its
`__init__`) defined under ROOT. Unlike `python_truth.py` it sees `obj.method()`
through whatever `obj` really was, so it is the check on dynamic receivers.
Rows: {"t":"trace","file","line","end","target","count"}; the fqn scheme is
`python_truth.py`'s. Run it on a throwaway copy of the code, so line numbers match
what is indexed.
"""

from __future__ import annotations

import ast
import json
import os
import runpy
import sys
import types
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    argv = sys.argv[1:]
    root = Path(argv[0]).resolve()
    out = Path(argv[1])
    rest = argv[2:]
    sys.path.insert(0, str(HERE))
    import python_truth as pt

    truth = pt.Truth(root, [])          # defs only; modules are loaded by the workload itself
    by_code: dict = {}
    abs_files = truth.abs

    def target_for(callable_obj):
        obj = callable_obj
        for _ in range(6):
            if isinstance(obj, types.MethodType):
                obj = obj.__func__
            elif hasattr(obj, "func") and type(obj).__name__ == "partial":
                obj = obj.func
            else:
                break
        if isinstance(obj, type):
            init = None
            for k in obj.__mro__:
                if "__init__" in k.__dict__:
                    init = k.__dict__["__init__"]
                    break
            fqn = truth.fn_fqn(init) if init is not None else None
            return fqn or truth.cls_fqn(obj)
        return truth.fn_fqn(obj)

    counts: Counter = Counter()
    memo: dict = {}
    posmemo: dict = {}
    mon = sys.monitoring
    tool = mon.PROFILER_ID
    mon.use_tool_id(tool, "cdp-trace")

    def on_call(code, offset, callable_obj, arg0):
        f = code.co_filename
        rel = abs_files.get(f)
        if rel is None:
            rel = abs_files.get(str(Path(f).resolve())) if f and not f.startswith("<") else None
            abs_files[f] = rel
        if rel is None:
            return
        base = getattr(callable_obj, "__func__", callable_obj)
        key = (code, offset, id(base))
        hit = memo.get(key)
        if hit is None:
            try:
                tgt = target_for(callable_obj)
            except Exception:  # noqa: BLE001
                tgt = None
            pk = (code, offset)
            pos = posmemo.get(pk)
            if pos is None:
                pos = (None, None)
                for i, p in enumerate(code.co_positions()):
                    if i * 2 == offset:
                        pos = (p[0], p[1])
                        break
                posmemo[pk] = pos
            memo[key] = hit = (tgt, pos[0], pos[1], base)   # `base` keeps the id() valid
        if hit[0] and hit[1]:
            counts[(rel, hit[1], hit[2], hit[0])] += 1

    mon.register_callback(tool, mon.events.CALL, on_call)
    mon.set_events(tool, mon.events.CALL)
    sys.path.insert(0, str(root))
    os.chdir(root)
    try:
        if rest and rest[0] == "--script":
            sys.argv = [rest[1]] + rest[2:]
            runpy.run_path(rest[1], run_name="__main__")
        else:
            cmd = rest[1:] if rest and rest[0] == "--" else rest
            if cmd[0] == "pytest":
                import pytest
                pytest.main(cmd[1:])
            else:
                sys.argv = cmd
                runpy.run_module(cmd[0], run_name="__main__", alter_sys=True)
    except SystemExit:
        pass
    finally:
        mon.set_events(tool, 0)
        mon.free_tool_id(tool)
    with out.open("w") as fh:
        for (rel, line, end, tgt), n in sorted(counts.items()):
            fh.write(json.dumps({"t": "trace", "file": rel, "line": line, "end": end, "target": tgt,
                                 "count": n}, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
