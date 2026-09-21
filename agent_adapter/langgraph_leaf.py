"""LangGraph leaf runner (Phase 9, 7.4 follow-up).

The Claude Code leaf (`agents/cdp-leaf.md`) works because a Claude Code
subagent can call `Write` itself -- the model is the one that lands the patch
at `.cdp/patches/inbox/<node>.json`. A LangGraph node has no such tool by
default, and does not need one: the node is a plain Python function you
already control end-to-end, so `run_leaf()` puts the write on the host side
of the line instead of the model's. The model only has to produce output
that conforms to the patch schema; validation happens before anything ever
reaches disk, using the same `cdp.schema` validator `cdp validate` uses, so
an out-of-vocabulary or malformed patch never gets a chance to fold.

A patch that fails to parse or validate is written as `"status": "failed"`
with an `"error"` string -- the same escape hatch `agents/cdp-leaf.md`
documents for a leaf that could not complete its scope -- rather than raising,
so one bad leaf does not take down a wave `cdp run --wave-all` is driving.

`langchain_core`/`langgraph` are imported only inside `run_leaf`, not at
module load (`agent_adapter/langgraph.py`'s precedent, `litellm_adapter`'s
`_complete` before that): verified importable in this environment ($ python3
-c "import langchain_core" -> ModuleNotFoundError), so this is written
against the documented `.with_structured_output()` shape but not run against
the real package.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from cdp.schema import Validator, schema_path, validate_patch

_SKILL_ROOT = Path(__file__).resolve().parent.parent


def _validated_or_failed(node: str, run_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    validator = Validator.load(schema_path(_SKILL_ROOT))
    errors = validate_patch(patch, validator)
    if errors:
        return {
            "schema_version": "1.0.0",
            "node": node,
            "run_id": run_id,
            "status": "failed",
            "error": "schema validation failed: %s" % "; ".join(errors),
        }
    return patch


def run_leaf(prompt_path: Path, inbox_path: Path, *, model: Any = None) -> None:
    """Read the leaf prompt at `prompt_path`, drive a LangGraph-bound model
    to produce a schema-valid patch, and write it to `inbox_path`.

    `model` is any LangChain chat model (e.g. `ChatAnthropic(...)`); passing
    `None` is only useful for testing the schema-validation path without a
    live model call.
    """
    prompt = prompt_path.read_text()
    node, run_id = _node_and_run_id(prompt)

    if model is None:
        raise ValueError("run_leaf needs a LangChain chat model")

    try:
        from langchain_core.messages import HumanMessage

        structured_model = model.with_structured_output(_patch_schema(), include_raw=False)
        result = structured_model.invoke([HumanMessage(content=prompt)])
        patch = result if isinstance(result, dict) else json.loads(result)
    except Exception as exc:  # model call or parse failed -- report, don't raise
        patch = {
            "schema_version": "1.0.0",
            "node": node,
            "run_id": run_id,
            "status": "failed",
            "error": "leaf model call failed: %s" % exc,
        }
    else:
        patch = _validated_or_failed(node, run_id, patch)

    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    inbox_path.write_text(json.dumps(patch, indent=2))


def _patch_schema() -> Dict[str, Any]:
    validator = Validator.load(schema_path(_SKILL_ROOT))
    return validator.schema


def _node_and_run_id(prompt: str) -> Tuple[str, str]:
    """Best-effort extraction for the failure-path patch's `node`/`run_id`
    fields; a leaf prompt names both, e.g. as front-matter or inline text.
    Real leaves get these fields from the model's own structured output --
    this is only the fallback used when that output could not be parsed."""
    node, run_id = "unknown", "unknown"
    for line in prompt.splitlines():
        if line.startswith("node:"):
            node = line.split(":", 1)[1].strip()
        elif line.startswith("run_id:"):
            run_id = line.split(":", 1)[1].strip()
    return node, run_id
