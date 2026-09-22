"""Agent-layer hookup tab support (`WEB_RESEARCH.md` §4 item 1) -- the web
seam over `cdp install --framework`, `cdp doctor --node` and `mcp_server`'s
three tools. Nothing here reimplements those; each function either derives a
read-only preview from the same constants `cdp.cli` uses, or is a thin
wrapper the endpoint layer shells out through.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def preview_install(target: Path, framework: str) -> Dict[str, Any]:
    """What `cdp install --framework <framework> <target>` would do, without
    doing it -- mirrors `cdp.cli.cmd_install`/`register_leaf_agent`
    (`cli.py:2785-2864`) read-only."""
    from cdp.cli import DIST_MEMBERS, SKILL_ROOT

    dest = target / ".claude" / "skills" / "cdp"
    leaf_agent_file: Optional[str] = None
    framework_note: Optional[str] = None

    if framework == "claude-code":
        leaf_agent_file = str(target / ".claude" / "agents" / "cdp-leaf.md")
    elif framework in ("langgraph", "adk"):
        module = "agent_adapter.%s_leaf" % framework
        framework_note = (
            "no files copied for --framework %s -- in %s, run:\n"
            "  pip install cdp[agent]\n"
            "  from %s import run_leaf" % (framework, target, module)
        )
    elif framework == "none":
        framework_note = "no agent registration for --framework none"

    agents_md = target / "AGENTS.md"
    source_agents_md = SKILL_ROOT / "AGENTS.md"
    if agents_md.exists():
        agents_md_action = "kept"
    elif source_agents_md.exists():
        agents_md_action = "written"
    else:
        agents_md_action = "none"

    return {
        "skill_dest": str(dest),
        "skill_members": list(DIST_MEMBERS),
        "leaf_agent_file": leaf_agent_file,
        "framework_note": framework_note,
        "agents_md_path": str(agents_md),
        "agents_md_action": agents_md_action,
    }


def mcp_tools() -> List[Dict[str, Any]]:
    """The three `mcp_server` tools, read from their single source of truth
    (`mcp_server/schemas.py`) rather than restated here."""
    from mcp_server.schemas import TOOL_SCHEMAS

    return [
        {"name": name, "description": schema["description"], "input_schema": schema["inputSchema"]}
        for name, schema in TOOL_SCHEMAS.items()
    ]


#: The exact invocation verified in `mcp_server/server.py`'s own `main()`
#: docstring: `python3 -m mcp_server.server` -- stdio transport, the SDK's
#: default. Not derived at runtime since it is a fixed fact about this repo's
#: layout, not something that varies per request.
MCP_CLIENT_CONFIG = json.dumps(
    {"mcpServers": {"cdp": {"command": "python3", "args": ["-m", "mcp_server.server"]}}},
    indent=2,
)


def cheapest_scope_node(partition: dict) -> str:
    """Default throwaway scope for the liveness check when the caller
    doesn't name one -- the smallest scope by file count, since the point is
    a cheap probe, not full coverage."""
    scopes = partition["scopes"]
    return min(scopes, key=lambda s: s["file_count"])["node"]
