# How To — Agent Adapters (ADK / LangGraph) (`agent_adapter/`)

```bash
pip install cdp[agent]
```

Read-only tool surface (queries `cdp query`/`cdp scan`/`cdp status`):

```python
from agent_adapter import tool_specs                 # {name: spec} for cdp_query/cdp_scan/cdp_status
from agent_adapter.langgraph import as_langgraph_tools
from agent_adapter.adk import as_adk_tools
```

Leaf runner (a wave's leaf node, driven by `cdp install --framework
{langgraph,adk}` — see [runner-protocol-leaf-dispatch](../runner-protocol-leaf-dispatch/)
for the wave/lease side): the host, not the model, writes the patch file.

```python
from agent_adapter.langgraph_leaf import run_leaf
run_leaf(prompt_path, inbox_path, model=my_chat_model)   # e.g. ChatAnthropic(...)

from agent_adapter.adk_leaf import run_leaf
run_leaf(prompt_path, inbox_path, agent=my_adk_agent)     # ADK Agent/LlmAgent
```
