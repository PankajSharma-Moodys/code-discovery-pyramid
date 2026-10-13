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

from cdp.schema import Validator
from cdp.util import ArgError

from . import tools as tools_mod
from .schemas import TOOL_SCHEMAS

#: Newest first. The client's requested version is echoed back when we know it.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


class InvalidParams(ValueError):
    """The request names no such tool, or its arguments break the tool's input schema:
    a JSON-RPC -32602 error, not a tool failure."""


_VALIDATORS = {name: Validator(schema["inputSchema"]) for name, schema in TOOL_SCHEMAS.items()}


def _call(name: str, arguments: Any) -> Dict[str, Any]:
    if name not in tools_mod.TOOLS:
        raise InvalidParams("unknown tool %r -- one of %s" % (name, sorted(tools_mod.TOOLS)))
    errors = _VALIDATORS[name].validate(arguments)
    if errors:
        raise InvalidParams("invalid arguments for %s: %s" % (name, "; ".join(errors)))
    return tools_mod.TOOLS[name](**arguments)


def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One JSON-RPC message in, the response out (None for notifications)."""
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params")
    if params is None:
        params = {}
    if request_id is None:
        return None  # notifications (initialized, cancelled, ...) get no reply
    if not isinstance(params, dict):
        return _error(request_id, -32602, "params must be an object")

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
        # A malformed call is a protocol error (-32602); a tool that runs and
        # fails is a result with isError, so the model sees the message.
        try:
            result = _call(str(params.get("name")), params.get("arguments", {}))
            # A `format=text` answer is the tool text itself, not JSON wrapping a string; JSON is compact.
            text = (result["text"] if isinstance(result, dict) and result.get("format") == "text"
                    and isinstance(result.get("text"), str)
                    else json.dumps(result, sort_keys=True, separators=(",", ":")))
            return ok({"content": [{"type": "text", "text": text}]})
        except (InvalidParams, ArgError) as exc:
            return _error(request_id, -32602, str(exc))
        except Exception as exc:  # noqa: BLE001 -- any failure is reported to the model
            return ok({"content": [{"type": "text", "text": "%s: %s" % (type(exc).__name__, exc)}],
                       "isError": True})
    return _error(request_id, -32601, "method not found: %s" % method)


def main() -> None:
    """`python3 -m mcp_server.server` -- stdio transport."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError as exc:
            response = _error(None, -32700, "parse error: %s" % exc)
        else:
            try:
                response = (handle(message) if isinstance(message, dict)
                            else _error(None, -32600, "invalid request: expected a JSON object"))
            except Exception as exc:  # noqa: BLE001 -- one bad message must not end the session
                response = _error(message.get("id") if isinstance(message, dict) else None,
                                  -32603, "internal error: %s" % exc)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
