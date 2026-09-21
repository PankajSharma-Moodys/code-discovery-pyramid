# Know About — Agent Adapters (ADK / LangGraph) (`agent_adapter/`)

- Both adapters wrap the identical 3-tool surface `mcp_server` already
  defines (sourced from `cdp help --json`, never hand-written) — a wider,
  mutating surface was a deliberate non-goal.
- Package is named `agent_adapter/`, not `langgraph_adapter/`, because ADK
  and LangGraph are commonly combined in one real agent and are separate
  integration shapes, not the same shim.
- `mcp_server`/`litellm_adapter`/`agent_adapter` package names are chosen to
  avoid shadowing their real PyPI dependency on `sys.path` (a literal `mcp/`
  directory at repo root would import itself before the real `mcp` package).
- `langgraph_leaf.py`/`adk_leaf.py` are a second, distinct integration shape
  from `langgraph.py`/`adk.py` above: those wrap read-only query tools for a
  model to call; the `_leaf` modules make a framework-driven node function as
  a wave leaf (Claude Code's leaf is `agents/cdp-leaf.md`, a subagent that
  calls `Write` itself). A LangGraph/ADK node has no such tool by default and
  does not need one — `run_leaf()` puts the patch write on the host side of
  the line instead of the model's: the model only has to produce output
  conforming to the patch schema, validated with the same `cdp.schema`
  validator `cdp validate` uses before anything reaches disk. A patch that
  fails to parse or validate is written as `"status": "failed"` with an
  `"error"` string (the same escape hatch `agents/cdp-leaf.md` documents),
  rather than raising, so one bad leaf does not take down a whole
  `cdp run --wave-all`.
- Both `_leaf` modules import their framework (`langchain_core`/`langgraph`,
  `google.adk`) only inside `run_leaf`, not at module load — neither package
  was importable in the environment they were written in, so both are
  written against each framework's documented shape (`.with_structured_output()`,
  `FunctionTool`/`Runner`) but not run against the real package yet.
