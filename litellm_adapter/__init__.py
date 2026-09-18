"""LiteLLM runner for CDP (Phase 9, 7.2).

One adapter, roughly 100 providers plus local models via Ollama/vLLM --
highest coverage per unit of work of the distribution items. Lives outside
`cdp/` core: this package may depend on `litellm` (`pip install
cdp[litellm]`); `cdp/` itself never imports it (enforced by
`tests/test_core_purity.py`).

`LiteLLMRunner` implements `cdp/runner.py`'s `Runner` protocol
(`run(prompt_path, patch_path) -> RunResult`), so `cdp run --runner-cmd
"python3 -m litellm_adapter <model>"` drives it exactly like any other
subprocess runner -- `cdp run`/`cdp doctor` do not know it exists.

`preflight(model)` is the answer to this phase's own stress test ("LiteLLM
to a local 8B that collapses -- `doctor` catches it. Verify the adapter
surfaces `doctor`'s verdict before a full run, not after."): it runs the
real `cdp doctor` harness against `tests/fixtures/minirepo` with this model
before a caller commits to a full `cdp run`, and returns the aggregate
verdict rather than silently proceeding.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from cdp.doctor import _extract_json
from cdp.runner import RunResult

REPO_ROOT = Path(__file__).resolve().parent.parent
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"

SYSTEM_NOTE = (
    "Respond with exactly one JSON object matching the schema described "
    "in the prompt. No prose, no code fence."
)


def _complete(model: str, prompt_text: str, timeout_s: float = 300, **litellm_kwargs: Any) -> Any:
    """The only line in this package that touches the `litellm` SDK.

    Isolated per `PHASE/EXECUTION_RULES.md` R-E6 / the `mcp_server.server`
    precedent: `litellm` is not installed in this environment (verified:
    `python3 -c "import litellm"` raises `ModuleNotFoundError`), so this
    function is written against the SDK's documented `completion(...)`
    shape but not run against it. Everything else in this module is fully
    tested without `litellm` present.
    """
    try:
        import litellm
    except ImportError as exc:
        raise ImportError(
            "litellm_adapter needs the `litellm` package -- pip install cdp[litellm]"
        ) from exc
    return litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_NOTE},
            {"role": "user", "content": prompt_text},
        ],
        timeout=timeout_s,
        **litellm_kwargs,
    )


class LiteLLMRunner:
    """`Runner` protocol implementation (`cdp/runner.py`) over any of
    LiteLLM's ~100 providers, including local models via Ollama/vLLM."""

    def __init__(self, model: str, timeout_s: float = 300, **litellm_kwargs: Any) -> None:
        self.model = model
        self.timeout_s = timeout_s
        self.litellm_kwargs = litellm_kwargs

    def run(self, prompt_path: Path, patch_path: Path) -> RunResult:
        start = time.monotonic()
        try:
            prompt_text = Path(prompt_path).read_text(encoding="utf-8")
        except OSError as exc:
            return RunResult(ok=False, wall_ms=_elapsed_ms(start), error=str(exc))

        try:
            response = _complete(self.model, prompt_text, timeout_s=self.timeout_s, **self.litellm_kwargs)
        except Exception as exc:  # noqa: BLE001 -- runner.py Rule 1: no exception escapes run()
            return RunResult(ok=False, wall_ms=_elapsed_ms(start), error="%s: %s" % (type(exc).__name__, exc))

        try:
            raw = response.choices[0].message.content or ""
        except (AttributeError, IndexError) as exc:
            return RunResult(ok=False, wall_ms=_elapsed_ms(start), error="unrecognised response shape: %s" % exc)

        patch = _extract_json(raw)
        if patch is None:
            # A well-formed-but-wrong patch is `collect`'s problem, not the
            # runner's (runner.py docstring) -- but *unparseable* JSON means
            # nothing was written, so patch_path correctly stays absent and
            # `cdp run` classifies this call as empty/yield-collapse.
            return RunResult(ok=True, wall_ms=_elapsed_ms(start), tokens=_tokens(response))

        try:
            Path(patch_path).write_text(json.dumps(patch), encoding="utf-8")
        except OSError as exc:
            return RunResult(ok=False, wall_ms=_elapsed_ms(start), error=str(exc))

        return RunResult(ok=True, wall_ms=_elapsed_ms(start), tokens=_tokens(response))


def _tokens(response: Any) -> Optional[int]:
    usage = getattr(response, "usage", None)
    total = getattr(usage, "total_tokens", None) if usage is not None else None
    return int(total) if isinstance(total, (int, float)) else None


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def preflight(model: str, timeout_s: float = 300) -> Dict[str, Any]:
    """Run the real `cdp doctor` harness against `tests/fixtures/minirepo`
    with this model, in a scratch state dir, before a caller wires this
    model into a full `cdp run`. Returns the aggregate verdict dict
    (`cdp/doctor.py`'s `aggregate()` shape) plus `ok`, this preflight's own
    pass/fail: schema-valid on every scope and no yield collapse.

    Shells out to the real CLI (`cdp scan` then `cdp doctor`) rather than
    re-deriving inventory/extraction/xref/schedule here, the same reuse
    argument D42 already makes about `query.dispatch`: this is the one
    place doctor's five metrics are computed, and duplicating that wiring
    would be a second copy that drifts.
    """
    runner_cmd = "%s -m litellm_adapter --model %s" % (sys.executable, model)
    with tempfile.TemporaryDirectory(prefix="cdp-litellm-preflight-") as tmp:
        state_dir = Path(tmp) / ".cdp"
        scan = subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(state_dir), "--quiet"],
            capture_output=True, text=True, timeout=timeout_s, cwd=str(REPO_ROOT),
        )
        if scan.returncode != 0:
            return {"ok": False, "error": "preflight scan failed: %s" % scan.stderr[-2000:]}

        doctor = subprocess.run(
            [sys.executable, "-m", "cdp", "doctor", "--repo", str(MINIREPO),
             "--state-dir", str(state_dir), "--model", model, "--runner-cmd", runner_cmd,
             "--timeout", str(int(timeout_s))],
            capture_output=True, text=True, timeout=timeout_s * 4, cwd=str(REPO_ROOT),
        )
        report_path = state_dir / "doctor" / ("%s.json" % model)
        if not report_path.exists():
            return {"ok": False, "error": "preflight doctor run produced no report: %s" % doctor.stderr[-2000:]}

        agg = json.loads(report_path.read_text(encoding="utf-8"))
        agg["ok"] = bool(agg.get("schema_validity_rate")) and not agg.get("yield_collapse_rate")
        return agg


def _run_argv(argv: Optional[list] = None) -> int:
    """`python3 -m litellm_adapter --model M prompt.md patch.json` -- the
    `SubprocessRunner` protocol (`command + [prompt_path, patch_path]`),
    matching `scripts/claude_leaf_runner.sh`'s shape.
    `python3 -m litellm_adapter --preflight --model M` prints `preflight`'s
    verdict and exits nonzero on failure, for a caller to check before
    wiring this model into `cdp run --runner-cmd`.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="litellm_adapter")
    parser.add_argument("--model", required=True)
    parser.add_argument("--preflight", action="store_true",
                         help="run cdp doctor against tests/fixtures/minirepo and print the verdict")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("prompt_path", nargs="?")
    parser.add_argument("patch_path", nargs="?")
    args = parser.parse_args(argv)

    if args.preflight:
        agg = preflight(args.model, timeout_s=args.timeout)
        print(json.dumps(agg, indent=2))
        return 0 if agg.get("ok") else 1

    if not args.prompt_path or not args.patch_path:
        parser.error("prompt_path and patch_path are required unless --preflight is given")

    result = LiteLLMRunner(args.model, timeout_s=args.timeout).run(Path(args.prompt_path), Path(args.patch_path))
    if not result.ok:
        sys.stderr.write("litellm_adapter: %s\n" % result.error)
        return 1
    return 0
