"""stdio MCP server over `tools.py` + `schemas.py`.

Speaks the protocol directly (newline-delimited JSON-RPC 2.0: `initialize`,
`ping`, `tools/list`, `tools/call`) instead of going through the `mcp` SDK.
Verified against a real client (`mcp` 2.3.0's `ClientSession`); the SDK's
server API differs between 1.x and 2.x, so depending on it meant a server
that broke on whichever version a user happened to have installed.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from . import tools as tools_mod
from .schemas import TOOL_SCHEMAS

#: Newest first. The client's requested version is echoed back when we know it.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


def _call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name not in tools_mod.TOOLS:
        raise ValueError("unknown tool %r -- one of %s" % (name, sorted(tools_mod.TOOLS)))
    return tools_mod.TOOLS[name](**arguments)


def handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One JSON-RPC message in, the response out (None for notifications)."""
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if request_id is None:
        return None  # notifications (initialized, cancelled, ...) get no reply

    def ok(result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    if method == "initialize":
        asked = params.get("protocolVersion")
        return ok({
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "cdp", "version": "1"},
        })
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [
            {"name": name, "description": schema["description"],
             "inputSchema": schema["inputSchema"]}
            for name, schema in TOOL_SCHEMAS.items()
        ]})
    if method == "tools/call":
        # Tool failures are results with isError, not protocol errors, so the
        # model sees the message and can correct its call.
        try:
            result = _call(str(params.get("name")), params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}]})
        except Exception as exc:  # noqa: BLE001 -- any failure is reported to the model
            return ok({"content": [{"type": "text", "text": "%s: %s" % (type(exc).__name__, exc)}],
                       "isError": True})
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": "method not found: %s" % method}}


def main() -> None:
    """`python3 -m mcp_server.server` -- stdio transport."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        response = handle(message) if isinstance(message, dict) else None
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
