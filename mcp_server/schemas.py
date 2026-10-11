"""Tool descriptions and JSON schemas -- separated from `server.py` so the
at-rest token cost can be measured with zero `mcp` SDK dependency (7.1's own
acceptance line: "MCP server at a few tools with a measured at-rest token cost"; now five).

These are exactly what a real MCP client keeps loaded for the life of a
session -- the plan's own reference point (`phase_9_plan.md`) is a 13-tool
server measured at 49.2k tokens permanently resident. Five tools, kept small
descriptions, is the answer; this file is what proves the number rather than
asserting it.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from cdp import guide
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
            "Run a full CDP scan of a repository and write queryable state. "
            "Deterministic, no model calls. Run once before `cdp_query`/"
            "`cdp_status` against a repository that has never been scanned, "
            "or after structural changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "path to the repository to scan"},
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
            "Bring a scanned repository's index up to the current commit (no model calls; "
            "incremental). Use when a `cdp_query`/`cdp_status` answer says `behind` > 0. "
            "Needs a clean working tree; commit or stash first, or the answer stays as of the "
            "indexed commit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"repo": {"type": "string", "description": "path to an already-scanned repository"}},
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    "cdp_help": {
        "description": guide.MCP_HELP_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "a query kind, a command, 'recipes', or empty for the overview"}},
            "additionalProperties": False,
        },
    },
    "cdp_status": {
        "description": (
            "Coverage, freshness and any in-flight run's task state for an "
            "already-scanned repository -- the cheap check before trusting "
            "an answer as complete."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "path to the repository"},
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
