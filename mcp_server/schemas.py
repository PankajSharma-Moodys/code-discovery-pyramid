"""Tool descriptions and JSON schemas -- separated from `server.py` so the
at-rest token cost can be measured with zero `mcp` SDK dependency (7.1's own
acceptance line: "MCP server at 3 tools with a measured at-rest token cost").

These are exactly what a real MCP client keeps loaded for the life of a
session -- the plan's own reference point (`phase_9_plan.md`) is a 13-tool
server measured at 49.2k tokens permanently resident. Three tools, kept small
descriptions, is the answer; this file is what proves the number rather than
asserting it.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from cdp.prompts import CHARS_PER_TOKEN_EST

TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "cdp_query": {
        "description": (
            "Ask a scanned CDP store a typed question about a repository's "
            "structure -- symbols, files, modules, routes, config, call "
            "traces, unknowns, conflicts, coverage. `repo` must already be "
            "scanned (`cdp_scan` first). Cheaper and more reliable than "
            "grepping the repository yourself."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "path to the repository"},
                "kind": {
                    "type": "string",
                    "enum": [
                        "symbol", "file", "module", "routes", "table", "config",
                        "paths", "trace", "search", "claims", "unknowns",
                        "conflicts", "stats", "coverage",
                    ],
                    "description": "which question to ask",
                },
                "term": {"type": "string", "description": "the symbol/file/module/search text this kind needs"},
                "budget": {"type": "integer", "description": "row cap across every list in the answer"},
                "claim_kind": {"type": "string", "description": "`claims` only: filter by claim kind"},
                "module": {"type": "string", "description": "`claims` only: filter by module"},
                "subject": {"type": "string", "description": "`claims` only: filter by subject"},
                "frm": {"type": "string", "description": "`paths` only: source symbol"},
                "to": {"type": "string", "description": "`paths` only: target symbol"},
                "max_hops": {"type": "integer", "description": "`trace` only: how far to walk"},
                "as_of": {"type": "string", "description": "replay claims as of this commit"},
                "state_dir": {"type": "string", "description": "override the resolved state directory"},
            },
            "required": ["repo", "kind"],
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
                "state_dir": {"type": "string", "description": "override the resolved state directory"},
                "max_leaf_files": {"type": "integer"},
                "max_leaf_loc": {"type": "integer"},
                "max_concurrent": {"type": "integer"},
                "max_hops": {"type": "integer"},
                "workers": {"type": "integer"},
            },
            "required": ["repo"],
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
                "state_dir": {"type": "string", "description": "override the resolved state directory"},
            },
            "required": ["repo"],
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
