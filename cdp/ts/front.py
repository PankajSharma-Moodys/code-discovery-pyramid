"""Crash-isolated, cached access to the worker. call(op, lang, text) -> result dict; never raises, never hides a failure:
a dead/hung/erroring worker yields {"rows": [], "crash"|"error": ..., "has_error": True} and a log warning.
CDP_TS_INPROC=1 runs in this process (tests, benchmarks)."""
import atexit
import json
import logging
import os
import select
import subprocess
import sys

from . import cache, engine

log = logging.getLogger("cdp.ts")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOOT = "import sys; sys.path[0] = %r; from cdp.ts import worker; worker.main()" % ROOT
_W = {"p": None}


def _stop():
    p, _W["p"] = _W["p"], None
    if p is not None:
        p.kill()
        p.wait()


atexit.register(_stop)


def _roundtrip(req, timeout):
    if _W["p"] is None or _W["p"].poll() is not None:
        _W["p"] = subprocess.Popen([sys.executable, "-c", _BOOT], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   text=True, bufsize=1, encoding="utf8", errors="replace")
    p = _W["p"]
    p.stdin.write(json.dumps(req) + "\n")
    p.stdin.flush()
    if not select.select([p.stdout], [], [], timeout)[0]:
        _stop()
        raise TimeoutError("worker silent for %ss" % timeout)
    line = p.stdout.readline()
    if not line:
        _stop()
        raise EOFError("worker died (exit before reply)")
    return json.loads(line)


def _run(op, lang, text):
    if os.environ.get("CDP_TS_INPROC"):
        from . import worker
        try:
            return worker.handle({"op": op, "lang": lang, "src": text})
        except Exception as e:
            if type(e).__name__ in ("NoRules", "GrammarMissing"):
                return {"unsupported": str(e)}
            return {"error": "%s: %s" % (type(e).__name__, e)}
    timeout = float(os.environ.get("CDP_TS_TIMEOUT", engine.POLICY["timeout_s"]))
    last = None
    for _attempt in range(2):                     # one restart after a dead worker, then give up on this file
        try:
            return _roundtrip({"op": op, "lang": lang, "src": text}, timeout)
        except (OSError, EOFError, TimeoutError, ValueError) as e:
            last = e
            log.warning("cdp.ts worker failure on %s/%s: %r", op, lang, e)
    return {"crash": repr(last)}


def call(op, lang, text):
    data = text.encode("utf8", "replace")
    k = cache.key(op, lang, data)
    r = cache.get(k)
    if r is not None:
        return r
    r = _run(op, lang, text)
    if "unsupported" in r:
        return r
    if "crash" in r or "error" in r:
        log.warning("cdp.ts %s/%s failed: %s", op, lang, r.get("crash") or r.get("error"))
        return {"rows": [], "has_error": True, **r}      # failures are never cached
    cache.put(k, r)
    return r
