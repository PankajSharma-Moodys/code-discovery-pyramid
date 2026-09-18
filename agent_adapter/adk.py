"""ADK tool wrapper (Phase 9, 7.4).

`build_adk_tools()` converts `agent_adapter.tool_specs()` into a list of
`google.adk.tools.FunctionTool` -- ADK's own docs describe `FunctionTool` as
wrapping a plain Python function directly, inspecting its name, docstring,
signature and type hints to build the schema the model sees, rather than
taking an explicit schema argument. `mcp_server.tools`' three functions are
already fully annotated with real docstrings, so each is wrapped as-is;
`ToolSpec.description` (sourced from `cdp help --json`) is not passed through
separately, because `FunctionTool`'s constructor takes only `func` --
confirmed from ADK's public docs and GitHub source
(`google/adk-python`, `src/google/adk/tools/function_tool.py`), not from a
local install of the package.

`google.adk` is imported only inside this function, not at module load
(`litellm_adapter`'s `_complete` precedent, `PHASE/EXECUTION_RULES.md` R-E6):
verified importable in this environment ($ python3 -c "import google.adk" ->
ModuleNotFoundError), so this is written against the documented shape but
not run against the real package.
"""

from __future__ import annotations

from typing import Any, List

from agent_adapter import tool_specs


def build_adk_tools() -> List[Any]:
    try:
        from google.adk.tools import FunctionTool
    except ImportError as exc:
        raise ImportError(
            "agent_adapter.adk needs google-adk -- pip install cdp[agent]"
        ) from exc
    return [FunctionTool(func=spec.func) for spec in tool_specs().values()]
