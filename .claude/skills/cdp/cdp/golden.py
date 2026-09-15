"""Golden baseline: what the pipeline said, before the refactors.

Phases 1 onward rewrite `state.fold`, every JSON write and `verify`. The
determinism gate proves a rewrite is *reproducible*; it says nothing about
whether it still produces the same answers. This module captures the answers.

Two design decisions, both load-bearing:

**The diff is printed, not merely asserted.** A regression test whose failure
message is `False != True` costs more than it saves: the reader has to
reconstruct, by hand, which of several thousand claims moved. `compare()`
returns a unified diff per artifact.

**Everything environment-derived is normalised away.** `inventory["repo"]` is an
absolute path (`inventory.py:85`), so an unnormalised baseline passes only on
the machine that blessed it. The commit SHA and `run_id` are normalised for the
same reason one level up: they change on every commit, and a baseline that must
be re-blessed on every commit is a baseline nobody keeps green. What remains is
a function of repository *content*, which is what a regression is a change in.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#: Artifacts always stored in full, because they are what queries are answered
# from and a hash tells the reader nothing about what moved.
ALWAYS_FULL = ("state.json", "graph.json", "partition.json")

#: Above this, non-essential artifacts are stored as hashes rather than bodies.
# The Phase 0 stress test asks what happens when a target produces an enormous
# golden set; this is the answer, applied per-artifact so the decision is
# visible in the stored baseline rather than made silently at capture time.
FULL_BODY_LIMIT = 2_000_000  # bytes, per artifact

#: Excluded outright: the only file whose difference carries no information
# (`cli.py` writes a timestamp into it and says so).
EXCLUDED = ("manifest.json",)

_PLACEHOLDER_REPO = "<REPO>"
_PLACEHOLDER_HEAD = "<HEAD>"
_PLACEHOLDER_TIME = "<TIME>"

_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)


def normalise_text(text: str, repo: Path, head: Optional[str]) -> str:
    """Strip machine-, checkout- and commit-specific substrings.

    Order matters: the longest, most specific replacements first, so that a
    12-character `run_id` prefix does not partially rewrite the 40-character
    SHA it was derived from.
    """
    repo_str = str(repo)
    out = text.replace(repo_str, _PLACEHOLDER_REPO)
    # JSON-escaped form of the same path, for values embedded in encoded strings.
    out = out.replace(repo_str.replace("\\", "\\\\"), _PLACEHOLDER_REPO)
    if head and head != "unpinned":
        for candidate in (head, head[:12], head[:8], head[:7]):
            if len(candidate) >= 7:
                out = out.replace(candidate, _PLACEHOLDER_HEAD)
    out = _TIMESTAMP_RE.sub(_PLACEHOLDER_TIME, out)
    return out


def canonical(obj) -> str:
    """One JSON spelling, so a diff shows semantic change and not formatting."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def capture(artifacts: Dict[str, str], repo: Path, head: Optional[str]) -> Dict[str, str]:
    """Normalise a `{relative name: text}` map into its storable form.

    Artifacts over `FULL_BODY_LIMIT` and outside `ALWAYS_FULL` are reduced to a
    digest. The reduction is recorded in the stored value itself, so a reader of
    the golden directory can see that a body was elided rather than missing.
    """
    out: Dict[str, str] = {}
    for name, text in artifacts.items():
        if Path(name).name in EXCLUDED:
            continue
        norm = normalise_text(text, repo, head)
        if Path(name).name not in ALWAYS_FULL and len(norm) > FULL_BODY_LIMIT:
            out[name] = "%s\n%s bytes, body elided (over FULL_BODY_LIMIT)\n" % (
                _digest(norm), len(norm)
            )
        else:
            out[name] = norm
    return out


def write(golden_dir: Path, captured: Dict[str, str]) -> None:
    """Materialise a baseline, replacing whatever was there.

    Total rather than incremental: a blessed baseline must not retain artifacts
    that the current pipeline no longer produces, or the next comparison
    silently passes over a deleted query.
    """
    import shutil

    if golden_dir.exists():
        shutil.rmtree(golden_dir)
    for name, text in sorted(captured.items()):
        path = golden_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def read(golden_dir: Path) -> Dict[str, str]:
    if not golden_dir.is_dir():
        return {}
    return {
        str(p.relative_to(golden_dir)): p.read_text(encoding="utf-8")
        for p in sorted(golden_dir.rglob("*"))
        if p.is_file()
    }


def compare(expected: Dict[str, str], actual: Dict[str, str]) -> List[str]:
    """Return one human-readable report per differing artifact.

    Empty means the baseline holds.
    """
    reports: List[str] = []
    for name in sorted(set(expected) - set(actual)):
        reports.append(
            "%s: in the baseline, not produced by this run.\n"
            "  The pipeline stopped emitting an artifact it used to emit." % name
        )
    for name in sorted(set(actual) - set(expected)):
        reports.append(
            "%s: produced by this run, absent from the baseline.\n"
            "  If this is intended, re-bless; otherwise the run wrote "
            "something unexpected." % name
        )
    for name in sorted(set(expected) & set(actual)):
        want, got = expected[name], actual[name]
        if want == got:
            continue
        diff = list(
            difflib.unified_diff(
                want.splitlines(keepends=True),
                got.splitlines(keepends=True),
                fromfile="baseline/%s" % name,
                tofile="current/%s" % name,
                n=2,
            )
        )
        shown, hidden = diff[:120], max(0, len(diff) - 120)
        body = "".join(shown)
        if hidden:
            body += "  ... %d more diff line(s); the first differences are above\n" % hidden
        reports.append("%s:\n%s" % (name, body))
    return reports


def summarise(reports: List[str], limit: int = 6) -> str:
    """A bounded report. An unbounded one is scrolled past, not read."""
    if not reports:
        return "ok    golden baseline holds"
    head = "\n\n".join(reports[:limit])
    tail = ""
    if len(reports) > limit:
        tail = "\n\n... and %d more differing artifact(s)" % (len(reports) - limit)
    return "%d artifact(s) differ from the golden baseline:\n\n%s%s" % (
        len(reports), head, tail
    )


def slug(repo_name: str, head: Optional[str]) -> str:
    """Directory name for a baseline: `<repo>@<sha12>`, or `@unpinned`."""
    if head and head != "unpinned":
        return "%s@%s" % (repo_name, head[:12])
    return "%s@unpinned" % repo_name
