"""Wires `tools.py` + `schemas.py` to the real `mcp` SDK's `Server`.

Not exercised end-to-end this session: the `mcp` PyPI package is not
installed in this environment, so the SDK-facing half below (`create_server`,
`main`) is written against its documented `Server`/stdio-transport shape but
has not itself been run against a real MCP client. Per
`PHASE/EXECUTION_RULES.md` R-E6 (design for the uncertainty rather than
guessing further): `tools.py`/`schemas.py` carry no such risk -- they are
plain functions and dicts, fully tested in `mcp_server/tests/test_tools.py`
against a real scan -- and this file is a thin, mechanical adapter over them.
Treat `create_server`/`main` as unverified until run against the installed
SDK; everything they call is verified.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from . import tools as tools_mod
from .schemas import TOOL_SCHEMAS


def _call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name not in tools_mod.TOOLS:
        raise ValueError("unknown tool %r -- one of %s" % (name, sorted(tools_mod.TOOLS)))
    return tools_mod.TOOLS[name](**arguments)


def create_server() -> "Any":
    """Builds a real `mcp.server.Server` registered with the three tools.

    Raises `ImportError` with a clear message if the `mcp` SDK is not
    installed -- fail loudly (`PHASE/FINDINGS.md` F16's own posture) rather
    than degrading silently into a server with no tools.
    """
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError as exc:
        raise ImportError(
            "the `mcp` SDK is required to run the real server -- "
            "`pip install cdp[mcp]`"
        ) from exc

    server = Server("cdp")

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        return [
            Tool(name=name, description=schema["description"], inputSchema=schema["inputSchema"])
            for name, schema in TOOL_SCHEMAS.items()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        result = _call(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, sort_keys=True))]

    return server


def main() -> None:
    """`python3 -m mcp_server.server` -- stdio transport, the SDK's default."""
    import asyncio

    from mcp.server.stdio import stdio_server

    server = create_server()

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
