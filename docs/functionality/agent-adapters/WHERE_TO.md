# Where To — Agent Adapters (ADK / LangGraph) (`agent_adapter/`)

| | |
|---|---|
| Core (tool adapters) | `agent_adapter/__init__.py` (`tool_specs`), `agent_adapter/langgraph.py`, `agent_adapter/adk.py` |
| Core (leaf runners) | `agent_adapter/langgraph_leaf.py` (`run_leaf`, `_validated_or_failed`), `agent_adapter/adk_leaf.py` (`run_leaf`, `_make_submit_patch_tool`) |
| Tests | `agent_adapter/tests/test_agent_adapter.py` |
