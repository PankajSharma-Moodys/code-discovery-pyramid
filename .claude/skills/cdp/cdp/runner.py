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
(the same `.cdp/patches/inbox/<node>.json` convention a human agent already
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

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


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
        try:
            proc = subprocess.run(
                self.command + [str(prompt_path), str(patch_path)],
                timeout=self.timeout_s,
                capture_output=True,
            )
        except subprocess.TimeoutExpired:
            return RunResult(ok=False, wall_ms=_elapsed_ms(start),
                              error="timed out after %ss" % self.timeout_s)
        except OSError as exc:
            return RunResult(ok=False, wall_ms=_elapsed_ms(start), error=str(exc))
        if proc.returncode != 0:
            return RunResult(ok=False, wall_ms=_elapsed_ms(start),
                              error="exit %d: %s" % (proc.returncode,
                                                       proc.stderr.decode("utf-8", "replace")[:500]))
        return RunResult(ok=True, wall_ms=_elapsed_ms(start))


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
