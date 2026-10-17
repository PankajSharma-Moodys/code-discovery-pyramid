"""In-process MCP harness run: `mcp_server.tools` functions called the way server.py does.

    CDP_HOME=<state> PYTHONPATH=<code> python3 mcp_run.py <corpus.json> <repo path> <out dir>

Prints one JSON timing line per call; writes each result to <out dir>/<id>.json.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time


def main():
    corpus_path, repo, out = sys.argv[1:4]
    from mcp_server import tools
    with open(corpus_path) as fh:
        corpus = json.load(fh)
    os.makedirs(out, exist_ok=True)
    for call in corpus["mcp"]:
        kw = dict(call["kwargs"])
        fn = tools.TOOLS[call["tool"]]
        if call["tool"] in ("cdp_query", "cdp_status"):
            kw["repo"] = repo
        t0 = time.perf_counter()
        try:
            result, rc = fn(**kw), 0
        except Exception as exc:  # the error text is part of the answer
            result, rc = {"error": "%s: %s" % (type(exc).__name__, exc)}, 1
        wall = time.perf_counter() - t0
        with open(os.path.join(out, call["id"] + ".json"), "w") as fh:
            json.dump(result, fh, indent=2, sort_keys=True, default=str)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(json.dumps({"id": call["id"], "kind": "mcp:" + kw.get("kind", call["tool"]), "fmt": "mcp", "rc": rc,
                          "wall_s": round(wall, 4), "rss": rss if sys.platform == "darwin" else rss * 1024}), flush=True)


if __name__ == "__main__":
    main()
