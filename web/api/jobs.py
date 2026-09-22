"""In-process single-flight registry for `POST /api/run`/`POST /api/refresh`
(`WEB_RESEARCH.md` §7.2.4). Mutations shell out to `cdp run`/`cdp refresh`
rather than calling `supervisor`/`refresh` in-process: the subprocess
inherits the real lock (`cdp/lock.py`), `--resume`'s lease/rejoin logic, and
the repo-mismatch guard for free, and a crashed CLI invocation cannot take
the web server down with it.

The registry itself is process-local memory, not a store table -- acceptable
for a localhost dev tool per §7.2.6, and it is *why* `run --resume` is always
passed through: a server restart loses this dict, but a new `cdp run
--resume` rejoins the same `run_id` via the CLI's own lease logic
(`cli.py:1521-1590`) instead of double-running against a still-live process.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Job:
    def __init__(
        self, job_id: str, kind: str, process: "subprocess.Popen[bytes]",
        repo: str, state_dir: str, command: List[str], log_path: Path,
    ) -> None:
        self.job_id = job_id
        self.kind = kind
        self.process = process
        self.repo = repo
        self.state_dir = state_dir
        self.command = command
        self.log_path = log_path
        self.started_at = time.time()

    def is_running(self) -> bool:
        return self.process.poll() is None

    @property
    def pid(self) -> int:
        return self.process.pid

    @property
    def returncode(self) -> Optional[int]:
        """`None` while running, the process exit code once it isn't --
        `poll()` is the same non-blocking check `is_running` uses, so calling
        both never blocks on a still-running subprocess."""
        return self.process.poll()


_lock = threading.Lock()
_jobs: Dict[Tuple[str, str], Job] = {}


def _key(repo: str, state_dir: str) -> Tuple[str, str]:
    """Resolved repo path + state dir string identify the single-flight slot
    -- the same `(repo, state_dir)` pair `resolve_state_dir` (`store_reader.py`)
    turns into one `index.db`, so two POSTs against the same on-disk state
    always see each other regardless of how the caller spelled the path."""
    return (str(Path(repo).expanduser().resolve()), state_dir)


def spawn_or_join(kind: str, repo: str, state_dir: str, extra_args: List[str]) -> Tuple[Job, bool]:
    """Returns `(job, joined)`. `joined=True` means a job for this
    `(repo, state_dir)` was already in flight and nothing new was spawned --
    the caller gets that job's handle back instead of a second process racing
    the first one (§7.2.4's single-flight semantics, not a queue)."""
    key = _key(repo, state_dir)
    with _lock:
        existing = _jobs.get(key)
        if existing is not None and existing.is_running():
            return existing, True

        job_id = uuid.uuid4().hex[:12]
        log_fd, log_path_str = tempfile.mkstemp(prefix="cdp-web-%s-%s-" % (kind, job_id), suffix=".log")
        log_path = Path(log_path_str)
        command = [
            sys.executable, "-m", "cdp", kind,
            "--repo", repo, "--state-dir", state_dir, *extra_args,
        ]
        log_handle = open(log_fd, "wb")
        process = subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT)
        job = Job(job_id, kind, process, repo, state_dir, command, log_path)
        _jobs[key] = job
        return job, False


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        for job in _jobs.values():
            if job.job_id == job_id:
                return job
    return None
