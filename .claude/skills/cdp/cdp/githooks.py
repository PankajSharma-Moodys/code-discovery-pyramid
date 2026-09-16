"""M3.8: `post-commit` / `post-checkout` hooks that auto-run `cdp refresh`.

Opt-in only -- nothing here runs unless `cdp githook install` is invoked, and
`cdp` remains fully usable with the hooks absent (`refresh` is still just a
command). The installed script embeds the absolute interpreter (`sys.executable`)
and repo path at install time, per `phase_3_plan.md` M3.8: a relative `python3`
or a relied-upon cwd both break under a GUI git client or CI runner that invokes
hooks with an unrelated `PATH`/cwd.

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

import sys
from pathlib import Path
from typing import List, Optional

from .util import CdpError, is_git_repo, run_git

MARKER = "# cdp-managed-git-hook -- installed by `cdp githook install`"
HOOK_NAMES = ("post-commit", "post-checkout")

COST_NOTE = (
    "cost      every commit/branch-switch now reruns `cdp refresh` inline. "
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


def _script(name: str, python: str, repo: Path) -> str:
    call = '"%s" -m cdp.cli refresh --repo "%s" --quiet' % (python, repo)
    if name == "post-checkout":
        # git's own contract: $3 is 1 for a branch/ref checkout, 0 for a
        # file-level restore (`git checkout -- <path>`). Only the former
        # moves HEAD, so only the former is worth a refresh -- this is the
        # exact distinction M3.8's acceptance criterion names.
        body = (
            'if [ "$3" != "1" ]; then\n'
            "    exit 0\n"
            "fi\n"
            "%s\n" % call
        )
    else:
        body = "%s\n" % call
    return "#!/bin/sh\n%s\n%sexit 0\n" % (MARKER, body)


def install(repo: Path) -> List[str]:
    if not is_git_repo(repo):
        raise CdpError("not a git repository: %s" % repo)
    hdir = hooks_dir(repo)
    if hdir is None:
        raise CdpError("could not resolve the git hooks directory for %s" % repo)
    hdir.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    for name in HOOK_NAMES:
        target = hdir / name
        if target.exists() and MARKER not in target.read_text(errors="replace"):
            raise CdpError(
                "%s already exists and was not installed by cdp; refusing to "
                "overwrite it. Remove it, or chain `cdp refresh --repo %s "
                "--quiet` into it by hand, then re-run `cdp githook install`."
                % (target, repo)
            )
        target.write_text(_script(name, sys.executable, repo))
        target.chmod(0o755)
        lines.append("installed %s" % target)
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
