"""Agent-framework adapters for CDP (Phase 9, 7.4).

Home for integration points into agent frameworks other than Claude Code --
LangGraph and ADK today, both commonly used together in one agent (ADK for
the runtime/session model, LangGraph for the graph/state-machine model), so
this is one package with sibling entry points (`agent_adapter/langgraph.py`,
`agent_adapter/adk.py`) rather than two adapters pretending to share a shape.

This module is the shared, SDK-free core: it reuses `mcp_server.tools`'
three functions (`cdp_scan`/`cdp_query`/`cdp_status` -- already the answer to
"which CDP surface does an L4 consumer, an RCA or reviewer agent, need") and
pulls each one's description from `cdp help --json` (`cdp/cli.py` `cmd_help`,
Phase 1 M1.4) rather than hand-writing one, so a tool's description cannot
drift from the CLI it wraps. `langgraph.py`/`adk.py` are thin: each converts
this module's `TOOL_SPECS` into its own SDK's native tool object and imports
that SDK only inside the conversion function (`litellm_adapter`'s
`_complete` precedent), so this module itself needs neither installed.

Lives outside `cdp/` core: this package may depend on
`langgraph`/`langchain-core`/`google-adk` (`pip install cdp[agent]`);
`cdp/` itself never imports any of them (enforced by
`tests/test_core_purity.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from cdp import helpdoc
from cdp.cli import _parser
from mcp_server import tools as mcp_tools

#: `mcp_server.tools.TOOLS`' keys are also `cdp help --json`'s command names
#: for scan/query/status -- no renaming needed between the CLI surface and
#: the tool surface.
_HELP_COMMAND_OF_TOOL = {"cdp_scan": "scan", "cdp_query": "query", "cdp_status": "status"}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    func: Callable[..., Any]


def _command_summaries() -> Dict[str, str]:
    surface = helpdoc.describe(_parser())
    return {c["name"]: c["summary"] for c in surface["commands"]}


def tool_specs() -> Dict[str, ToolSpec]:
    """The three tools, described by the live CLI rather than by hand.

    Raises if `cdp help --json`'s command list no longer names `scan`,
    `query` or `status` -- the same "cannot drift silently" guarantee
    `cmd_help` already gives the CLI itself, extended to this adapter.
    """
    summaries = _command_summaries()
    specs = {}
    for tool_name, func in mcp_tools.TOOLS.items():
        command = _HELP_COMMAND_OF_TOOL[tool_name]
        if command not in summaries:
            raise KeyError(
                "cdp help --json no longer names a %r command -- agent_adapter's "
                "%s tool cannot source its description" % (command, tool_name)
            )
        specs[tool_name] = ToolSpec(name=tool_name, description=summaries[command], func=func)
    return specs
