"""Token + Origin guard for `POST /api/run`/`POST /api/refresh`
(`WEB_RESEARCH.md` §7.2.6). Every other route in this app is a read against a
`mode=ro` sqlite connection; these two spawn a subprocess and, via
`cdp run --runner-cmd`, an arbitrary shell command. A cookie proves nothing
against that -- any page open in the same browser can already POST to
`127.0.0.1`. `WEB_TOKEN` is generated once per process (or read from
`CDP_WEB_TOKEN` so a test can pin it) and printed to stdout at import time,
the same posture as a Jupyter/TensorBoard token: whoever can read the
server's own console output is the same party who started it. There is no
dedicated `uvicorn.run` launcher in this repo yet, so import time is the
earliest "server start" moment available."""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request

WEB_TOKEN = os.environ.get("CDP_WEB_TOKEN") or secrets.token_urlsafe(32)

if not os.environ.get("CDP_WEB_TOKEN"):
    print("cdp web: mutation token (send as X-CDP-Web-Token): %s" % WEB_TOKEN, flush=True)


def require_mutation_auth(request: Request) -> None:
    token = request.headers.get("x-cdp-web-token")
    if not token or not secrets.compare_digest(token, WEB_TOKEN):
        raise HTTPException(status_code=403, detail="missing/invalid X-CDP-Web-Token header")

    origin = request.headers.get("origin")
    if origin is not None:
        expected = "%s://%s" % (request.url.scheme, request.url.netloc)
        if origin != expected:
            raise HTTPException(
                status_code=403,
                detail="Origin %r does not match this server (%r)" % (origin, expected),
            )
