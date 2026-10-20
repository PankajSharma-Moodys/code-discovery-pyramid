"""Tool descriptions and JSON schemas -- separated from `server.py` so the
at-rest token cost can be measured with zero `mcp` SDK dependency (7.1's own
acceptance line: "MCP server at a few tools with a measured at-rest token cost"; now six).

These are exactly what a real MCP client keeps loaded for the life of a
session -- the plan's own reference point (`phase_9_plan.md`) is a 13-tool
server measured at 49.2k tokens permanently resident. Six tools, kept small
descriptions, is the answer; this file is what proves the number rather than
asserting it.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from cdp import guide, linkview
from cdp.prompts import CHARS_PER_TOKEN_EST

TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "cdp_query": {
        "description": guide.mcp_query_description(),
        "inputSchema": {
            "type": "object",
            "properties": guide.mcp_properties(),
            "required": ["repo", "kind"],
            "additionalProperties": False,
        },
    },
    "cdp_scan": {
        "description": (
            "Full CDP scan of a repository (no model calls). Run once before `cdp_query`/"
            "`cdp_status` on an unscanned repository, or after structural changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "repo path"},
                "max_leaf_files": {"type": "integer", "minimum": 1},
                "max_leaf_loc": {"type": "integer", "minimum": 1},
                "max_concurrent": {"type": "integer", "minimum": 1},
                "max_hops": {"type": "integer", "minimum": 0},
                "workers": {"type": "integer", "minimum": 1},
            },
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    "cdp_refresh": {
        "description": (
            "Incrementally bring a scanned repository's index to the current commit (no model calls). "
            "Use when an answer says `behind` > 0. Needs a clean working tree."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"repo": {"type": "string", "description": "repo path"}},
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    "cdp_help": {
        "description": guide.MCP_HELP_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "query kind, command, 'recipes', or empty"}},
            "additionalProperties": False,
        },
    },
    "cdp_link": {
        "description": guide.MCP_LINK_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": list(linkview.ACTIONS)},
                "service": {"type": "string", "description": "repo name, path or identity prefix (action=query)"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
    "cdp_verify_diagram": {
        "description": (
            "Check a Mermaid diagram's edge citations against repo files before showing it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "repo path"},
                "diagram": {"type": "string", "description": "mermaid or answer with fences"},
            },
            "required": ["repo", "diagram"],
            "additionalProperties": False,
        },
    },
    "cdp_status": {
        "description": (
            "Coverage, freshness and in-flight task state of a scanned repository: "
            "the cheap check before trusting an answer as complete."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "repo path"},
            },
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
}


def estimate_at_rest_tokens() -> Dict[str, Any]:
    """chars/4 over each tool's `name` + `description` + `inputSchema`, the
    same crude estimator `cdp prompts --measure` already uses (not a real
    tokenizer) -- so this number and that one are comparable rather than two
    independently-invented units.

    This is what a real MCP client keeps resident for the life of a session,
    regardless of whether any tool is ever called -- the "at rest" the plan's
    49.2k-token reference point names.
    """
    per_tool = {}
    for name, schema in TOOL_SCHEMAS.items():
        payload = json.dumps({"name": name, **schema}, sort_keys=True)
        per_tool[name] = len(payload) // CHARS_PER_TOKEN_EST
    return {
        "tokens_est": sum(per_tool.values()),
        "per_tool": per_tool,
        "tool_count": len(TOOL_SCHEMAS),
    }
