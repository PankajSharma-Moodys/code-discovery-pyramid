"""Runner protocol (M5.1, `CDP_CLI_SCOPE.md` §F item 4.1).

    prompts -> [any LLM, any framework] -> inbox -> collect

A runner turns one prompt into one patch. `cdp run` (M5.3) is the only
caller; nothing here talks to cdp's stores, schema or partition — a runner
only ever sees a prompt file and a patch file path. This is the entire
interface a third-party runner needs; it should be writable from this
docstring alone, with no other source read.

Interface
---------
    result = runner.run(prompt_path, patch_path)

Input
-----
`prompt_path` -- path to the `.md` file `cdp prompts` already wrote for one
scope. Read it, decide however you like (call an LLM, ask a human, anything),
and write your answer.

Output
------
Write patch JSON, valid against `schema/patch-1.0.0.json`, to `patch_path`
verbatim — not a directory, not a derived name. `cdp run` chooses that path
(the same `<work dir>/patches/inbox/<node>.json` convention a human agent already
follows per `prompts.py`'s own instructions) and passes it in.

Return a `RunResult`:

    RunResult(
        ok,        # False only for a runner-level failure (crash, non-zero
                   # exit, timeout). Schema validity is `collect`'s job, not
                   # the runner's -- a well-formed-but-wrong patch is `ok=True`.
        wall_ms,   # elapsed wall-clock time for this one call, always set
        tokens,    # total tokens if knowable, else None -- a subprocess CLI
                   # often can't see this
        error,     # populated only when ok is False
    )

If `patch_path` does not exist when `run()` returns `ok=True`, that is
`empty` (yield collapse) for `cdp run` to classify — not a runner concern.

Rules
-----
1. No exception escapes `run()`. Catch everything; report failure in the
   result instead. The dispatch loop expects to keep going.
2. Never import anything outside the standard library. A runner that needs
   a framework runs in its own process, invoked through `SubprocessRunner`,
   not linked into `cdp`.
3. `run()` must tolerate concurrent calls for different scopes (no shared
   mutable state) -- a wave dispatches in parallel.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RunResult:
    ok: bool
    wall_ms: int
    tokens: Optional[int] = None
    error: Optional[str] = None


class SubprocessRunner:
    """Shells out to `command + [prompt_path, patch_path]` for any CLI."""

    def __init__(self, command: List[str], timeout_s: float = 300) -> None:
        self.command = list(command)
        self.timeout_s = timeout_s

    def run(self, prompt_path: Path, patch_path: Path) -> RunResult:
        start = time.monotonic()
        # Its own session: the command may be a wrapper (`bash script -> claude`), and a timeout
        # must end the whole tree, not just the wrapper, or an orphan writes its patch later and
        # races the retry.
        try:
            proc = subprocess.Popen(
                self.command + [str(prompt_path), str(patch_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        except OSError as exc:
            return RunResult(ok=False, wall_ms=_elapsed_ms(start), error=str(exc))
        try:
            _, stderr = proc.communicate(timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            return RunResult(ok=False, wall_ms=_elapsed_ms(start),
                              error="timed out after %ss" % self.timeout_s)
        except BaseException:  # KeyboardInterrupt (Ctrl-C) or anything else: leave nothing running
            _kill_tree(proc)
            raise
        if proc.returncode != 0:
            return RunResult(ok=False, wall_ms=_elapsed_ms(start),
                              error="exit %d: %s" % (proc.returncode, stderr.decode("utf-8", "replace")[:500]))
        return RunResult(ok=True, wall_ms=_elapsed_ms(start))


def _kill_tree(proc: "subprocess.Popen") -> None:
    """SIGKILL `proc`'s process group (it leads its own session) and reap it."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
    try:
        proc.communicate(timeout=5)
    except Exception:  # noqa: BLE001 -- already killed; nothing more to do for a stuck pipe
        pass


class FileRunner:
    """Drops the prompt, polls for the patch file -- today's manual
    `SKILL.md` loop, made explicit."""

    def __init__(self, poll_interval_s: float = 1.0, timeout_s: float = 3600) -> None:
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s

    def run(self, prompt_path: Path, patch_path: Path) -> RunResult:
        start = time.monotonic()
        deadline = start + self.timeout_s
        while True:
            if patch_path.exists():
                return RunResult(ok=True, wall_ms=_elapsed_ms(start))
            if time.monotonic() >= deadline:
                return RunResult(ok=False, wall_ms=_elapsed_ms(start),
                                  error="no patch written within %ss" % self.timeout_s)
            time.sleep(self.poll_interval_s)


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def read_usage(patch_path: Path) -> Dict:
    """What a runner left beside its patch as `<patch>.usage` (Claude's `--output-format json`
    result: `total_cost_usd`, `duration_ms`, `usage`), as `{cost_usd, tokens_in, tokens_out}`;
    {} when there is none or it is unreadable. The file is removed: it is not a patch."""
    path = Path(patch_path).with_suffix(".usage")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    if not isinstance(data, dict):
        return {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    tokens_in = sum(int(usage.get(k) or 0) for k in
                    ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    out = {"cost_usd": data.get("total_cost_usd"), "tokens_in": tokens_in or None,
           "tokens_out": usage.get("output_tokens")}
    return {k: v for k, v in out.items() if isinstance(v, (int, float))}
