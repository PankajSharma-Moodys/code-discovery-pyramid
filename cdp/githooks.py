"""M3.8: `post-commit` / `post-checkout` / `post-merge` / `post-rewrite` hooks that auto-run
`cdp refresh` (commit, branch switch, pull and rebase).

Opt-in only -- nothing here runs unless `cdp githook install` is invoked, and
`cdp` remains fully usable with the hooks absent (`refresh` is still just a
command). The installed script embeds the absolute interpreter (`sys.executable`,
falling back to `python3`) and the absolute path of this checkout's `run.py`, so
it works without `PYTHONPATH` and under a GUI git client or CI runner with an
unrelated `PATH`/cwd. The repository is *not* embedded: hooks are shared by every
worktree of a repository, so the script asks git for the top level of the worktree
it fires in.

**Never clobbers a hook it did not install.** Every script this module writes
carries `MARKER` on its own line; `install` refuses to overwrite a hook file
that lacks it, and `uninstall` only removes a file that has it. A repository
that already has its own `post-commit` keeps it, untouched, and the operator
is told to chain manually rather than losing it silently.

**Fails open, like `hook.py`.** The installed script always exits 0 -- neither
hook gates the git operation it fires after, so a nonzero exit buys nothing but
a scary message, and `refresh`'s own `cdp: <message>` on stderr (never scanned
yet, dirty tree, no git history) is left to print normally rather than
suppressed, because these hooks fire once per commit/checkout, not once per
file read (`hook.py`'s docstring on why *that* hook must stay silent does not
apply here).
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import List, Optional

from .util import CdpError, is_git_repo, run_git

MARKER = "# cdp-managed-git-hook -- installed by `cdp githook install`"
HOOK_NAMES = ("post-commit", "post-checkout", "post-merge", "post-rewrite")

COST_NOTE = (
    "cost      every commit, branch switch, pull and rebase now reruns `cdp refresh` inline. "
    "Cost scales with files changed since the last refresh, not repo size -- "
    "an 8-month, 544-file span over one real module took ~12s (PHASE/TARGET.md). "
    "Uninstall with `cdp githook uninstall` if that is not acceptable for this repo."
)


def hooks_dir(repo: Path) -> Optional[Path]:
    """Respects `core.hooksPath` and worktrees via `git rev-parse --git-path
    hooks`, rather than assuming `<repo>/.git/hooks` -- the same reason `refresh`
    is rename-aware: a GUI client or a relocated `$GIT_DIR` is the common case,
    not the edge case, for anyone who would enable this."""
    out = run_git(repo, "rev-parse", "--git-path", "hooks")
    if out is None:
        return None
    return (repo / out.strip()).resolve()


RUN_PY = Path(__file__).resolve().parent.parent / "run.py"


def _script(name: str, python: str, repo: Optional[Path] = None, state_dir: Optional[Path] = None) -> str:
    """The hook script. `repo` is accepted for older callers and ignored: the
    worktree is resolved when the hook fires, never at install time. `state_dir`
    (an install-time `--state-dir`) is baked in so a commit refreshes that store."""
    call = '"$py" "%s" refresh --repo "$root" --quiet' % RUN_PY
    if state_dir is not None:
        call += " --state-dir %s" % shlex.quote(str(state_dir))
    guard = ""
    if name == "post-checkout":
        # git's own contract: $3 is 1 for a branch/ref checkout, 0 for a
        # file-level restore (`git checkout -- <path>`). Only the former
        # moves HEAD, so only the former is worth a refresh.
        guard = 'if [ "$3" != "1" ]; then\n    exit 0\nfi\n'
    body = (
        guard +
        'py="%s"\n[ -x "$py" ] || py=python3\n'
        'root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0\n'
        '%s\n' % (python, call)
    )
    return "#!/bin/sh\n%s\n%sexit 0\n" % (MARKER, body)


def install(repo: Path, state_dir: Optional[Path] = None) -> List[str]:
    if not is_git_repo(repo):
        raise CdpError("not a git repository: %s" % repo)
    hdir = hooks_dir(repo)
    if hdir is None:
        raise CdpError("could not resolve the git hooks directory for %s" % repo)

    # Atomic: every target is checked before the first is written, so a refusal
    # leaves the hooks directory exactly as it was.
    foreign = [hdir / name for name in HOOK_NAMES
               if (hdir / name).exists() and MARKER not in (hdir / name).read_text(errors="replace")]
    if foreign:
        raise CdpError(
            "%s already exists and was not installed by cdp; refusing to "
            "overwrite it (nothing was installed). Remove it, or chain `cdp refresh "
            "--repo %s --quiet` into it by hand, then re-run `cdp githook install`."
            % (", ".join(str(t) for t in foreign), repo))
    hdir.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    for name in HOOK_NAMES:
        target = hdir / name
        temp = hdir / (".%s.cdp-tmp" % name)
        temp.write_text(_script(name, sys.executable, state_dir=state_dir))
        temp.chmod(0o755)
        temp.replace(target)
        lines.append("installed %s" % target)
    lines.append("scope     one set of hooks serves every worktree of this repository")
    lines.append(COST_NOTE)
    return lines


def uninstall(repo: Path) -> List[str]:
    if not is_git_repo(repo):
        raise CdpError("not a git repository: %s" % repo)
    hdir = hooks_dir(repo)
    if hdir is None:
        raise CdpError("could not resolve the git hooks directory for %s" % repo)

    lines: List[str] = []
    for name in HOOK_NAMES:
        target = hdir / name
        if target.exists() and MARKER in target.read_text(errors="replace"):
            target.unlink()
            lines.append("removed    %s" % target)
        else:
            lines.append("skipped    %s (not installed by cdp)" % target)
    return lines
