"""LangGraph tool wrapper (Phase 9, 7.4).

`build_langgraph_tools()` converts `agent_adapter.tool_specs()` into a list
of `langchain_core.tools.StructuredTool` -- LangGraph agents consume
LangChain tools directly, there is no separate LangGraph-native tool type.
`StructuredTool.from_function` builds its args schema from the wrapped
function's own type hints (`mcp_server.tools.cdp_query` etc. are already
fully annotated), so no schema is hand-duplicated here.

`langchain_core` is imported only inside this function, not at module load
(`litellm_adapter`'s `_complete` precedent, `PHASE/EXECUTION_RULES.md` R-E6):
verified importable in this environment ($ python3 -c "import langchain_core"
-> ModuleNotFoundError), so this is written against the documented
`StructuredTool.from_function(func, name, description)` shape but not run
against the real package.
"""

from __future__ import annotations

from typing import Any, List

from agent_adapter import tool_specs


def build_langgraph_tools() -> List[Any]:
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise ImportError(
            "agent_adapter.langgraph needs langchain-core -- pip install cdp[agent]"
        ) from exc
    return [
        StructuredTool.from_function(func=spec.func, name=spec.name, description=spec.description)
        for spec in tool_specs().values()
    ]
