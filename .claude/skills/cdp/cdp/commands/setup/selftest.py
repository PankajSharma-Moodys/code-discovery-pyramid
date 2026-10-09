"""`cdp selftest`."""

from __future__ import annotations

from .._common import Spec

import sys

from ...selftest import MIN_TESTS, VOLATILE_FILE, check_determinism, run_golden, tests_ran
from ...util import CdpError, SKILL_ROOT
from pathlib import Path


SPEC = Spec(
    group='setup',
    usage='selftest [--determinism <repo>] [--golden] [--min-tests N]',
    what='Runs the bundled test suite (or the reproducibility/golden gates).',
    next='—',
)


def register(add) -> None:
    stest = add("selftest", "run the bundled tests")
    stest.add_argument("--min-tests", type=int, default=MIN_TESTS,
                       help="fail if fewer than this many tests ran (default: %d)" % MIN_TESTS)
    stest.add_argument("--determinism", metavar="REPO",
                       help="instead of the suite, run the reproducibility gate "
                            "against an arbitrary repository")
    stest.add_argument("--golden", metavar="REPO",
                       help="instead of the suite, diff output against the stored "
                            "baseline for this repository")
    stest.add_argument("--bless", action="store_true",
                       help="with --golden: overwrite the baseline with current output")
    stest.add_argument("--golden-name", metavar="SLUG",
                       help="with --golden: baseline directory name, overriding <repo>@<sha>")
    stest.set_defaults(func=cmd_selftest)


def cmd_selftest(args) -> int:
    """Run the bundled tests.

    Spawned as a subprocess with `cwd` set to the tests directory rather than
    discovered in-process: the test modules import `helpers`, which needs to be
    importable, and in-process discovery silently found zero tests instead of
    saying so. A test runner that reports success having run nothing is the
    worst possible outcome for a self-test.

    The subprocess fixed the import, but `unittest discover` still exits 0 when
    it discovers nothing — so the original failure mode survived the fix. The
    floor below closes it: a suite that shrinks past `--min-tests` fails and
    says which number it saw, rather than reporting a green empty run.
    """
    import subprocess

    target = getattr(args, "determinism", None)
    if target:
        repo = Path(target).expanduser().resolve()
        if not repo.is_dir():
            raise CdpError("not a directory: %s" % repo)
        print("determinism  scanning %s twice" % repo)
        problems = check_determinism(repo)
        if problems:
            for problem in problems:
                print("  %s" % problem, file=sys.stderr)
            raise CdpError(
                "%d reproducibility problem(s) on %s: two scans of one commit "
                "must produce byte-identical state." % (len(problems), repo)
            )
        print("ok    two scans of %s agree byte-for-byte (%s excepted)"
              % (repo, VOLATILE_FILE))
        return 0

    golden_target = getattr(args, "golden", None)
    if golden_target:
        repo = Path(golden_target).expanduser().resolve()
        if not repo.is_dir():
            raise CdpError("not a directory: %s" % repo)
        code, report = run_golden(repo, bless=getattr(args, "bless", False),
                                  name=getattr(args, "golden_name", None))
        print(report, file=sys.stderr if code else sys.stdout)
        return code

    if getattr(args, "bless", False):
        raise CdpError("--bless is only meaningful with --golden")

    tests = SKILL_ROOT / "tests"
    if not tests.is_dir():
        raise CdpError("no tests bundled with this skill at %s" % tests)
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", ".", "-t", ".", "-v"],
        cwd=str(tests),
        stderr=subprocess.PIPE,
        text=True,
    )
    # unittest writes its report to stderr. Echo it verbatim; we only parse the
    # count line, and a parse failure must not swallow the report.
    sys.stderr.write(proc.stderr)
    ran = tests_ran(proc.stderr)
    if ran is None:
        raise CdpError(
            "could not determine how many tests ran; refusing to report success. "
            "unittest output did not contain a 'Ran N test(s)' line."
        )
    floor = getattr(args, "min_tests", MIN_TESTS)
    if ran < floor:
        raise CdpError(
            "selftest ran %d test(s), below the floor of %d. Either tests were "
            "lost or --min-tests needs raising deliberately." % (ran, floor)
        )
    if proc.returncode == 0:
        print("ok    %d tests" % ran)
    return proc.returncode
