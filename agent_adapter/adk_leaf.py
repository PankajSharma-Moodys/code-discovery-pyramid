"""ADK leaf runner (Phase 9, 7.4 follow-up).

Mirrors `agent_adapter.langgraph_leaf`'s host-owned-write design, in ADK's own
idiom: instead of binding the model to a structured-output schema, the leaf
agent is given one `FunctionTool`, `submit_patch`, and told (via its
instruction) to call it exactly once with its finished patch. The tool
implementation -- not the model -- validates against `cdp.schema` and writes
`.cdp/patches/inbox/<node>.json`, so a malformed or out-of-vocabulary patch is
turned into a `"status": "failed"` patch rather than a bad file on disk.

`google.adk` is imported only inside `run_leaf`, not at module load
(`agent_adapter/adk.py`'s precedent): verified importable in this environment
($ python3 -c "import google.adk" -> ModuleNotFoundError), so this is written
against ADK's documented `FunctionTool`/`Runner` shape but not run against the
real package.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from cdp.schema import Validator, schema_path, validate_patch

_SKILL_ROOT = Path(__file__).resolve().parent.parent


def _node_and_run_id(prompt: str) -> Tuple[str, str]:
    node, run_id = "unknown", "unknown"
    for line in prompt.splitlines():
        if line.startswith("node:"):
            node = line.split(":", 1)[1].strip()
        elif line.startswith("run_id:"):
            run_id = line.split(":", 1)[1].strip()
    return node, run_id


def _make_submit_patch_tool(inbox_path: Path, node: str, run_id: str):
    """Build the `submit_patch` tool the leaf agent is told to call once.

    Closes over `inbox_path`/`node`/`run_id` rather than taking them as tool
    arguments, so the model cannot mis-supply the destination path -- the one
    thing this tool is trusted with is validating and writing the patch body
    it is given, nothing about where.
    """

    def submit_patch(patch_json: str) -> str:
        """Submit the finished patch for this scope, as a JSON string
        matching the CDP patch schema. Call this exactly once, when done."""
        try:
            patch = json.loads(patch_json)
        except json.JSONDecodeError as exc:
            patch = {
                "schema_version": "1.0.0",
                "node": node,
                "run_id": run_id,
                "status": "failed",
                "error": "patch was not valid JSON: %s" % exc,
            }
        else:
            validator = Validator.load(schema_path(_SKILL_ROOT))
            errors = validate_patch(patch, validator)
            if errors:
                patch = {
                    "schema_version": "1.0.0",
                    "node": node,
                    "run_id": run_id,
                    "status": "failed",
                    "error": "schema validation failed: %s" % "; ".join(errors),
                }

        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        inbox_path.write_text(json.dumps(patch, indent=2))
        return "patch written to %s" % inbox_path

    return submit_patch


def run_leaf(prompt_path: Path, inbox_path: Path, *, agent: Any = None) -> None:
    """Read the leaf prompt at `prompt_path`, run it through an ADK `agent`
    equipped with a `submit_patch` tool, and let that tool write the patch to
    `inbox_path`.

    `agent` is any ADK `Agent`/`LlmAgent`-like object whose `tools` list this
    function extends with `submit_patch` before running it; passing `None`
    raises rather than silently no-op'ing, since a leaf that never runs a
    model can never produce a patch.
    """
    if agent is None:
        raise ValueError("run_leaf needs an ADK agent")

    prompt = prompt_path.read_text()
    node, run_id = _node_and_run_id(prompt)

    from google.adk.tools import FunctionTool

    submit_patch = _make_submit_patch_tool(inbox_path, node, run_id)
    agent.tools = list(getattr(agent, "tools", [])) + [FunctionTool(func=submit_patch)]

    try:
        agent.run(prompt)
    except Exception as exc:  # the agent itself failed before calling the tool
        if not inbox_path.exists():
            patch = {
                "schema_version": "1.0.0",
                "node": node,
                "run_id": run_id,
                "status": "failed",
                "error": "leaf agent run failed: %s" % exc,
            }
            inbox_path.parent.mkdir(parents=True, exist_ok=True)
            inbox_path.write_text(json.dumps(patch, indent=2))
