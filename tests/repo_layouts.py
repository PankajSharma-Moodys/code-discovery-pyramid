"""Real-world repo layouts and index invariants (F2).

The 8 fixture repos are one flat commit each; the defects in DEFECTS.md live in
the layouts they lack. This module builds those layouts as temp git repos and
offers invariant checkers that any test can run after it has written state.

Builders return a `Repo`. `Cdp` is a throwaway machine home plus a scan target;
it drives the CLI the way a user does and opens the store the way a query does.

Checkers return a list of problem strings (empty = holds), so a test asserts
`assertEqual(problems, [])`. The defects each one guards:

    check_refresh_equals_scan          A10 (subfolder), A11 (whitespace), A12 (dirty leak),
                                       A14 (excludes), C3 (derived counts), M8 (links)
    check_no_silent_loss               L3 (answers), L5, L8, I1, I5, I7
    check_derived_claims_live          L1 (root patch), L2 (abandoned scope)
    check_answering_snapshot           A1, A3, A9, A13 (dirty/other-branch/stale answers)
    check_fold_green                   state is exactly fold(patches)+xref: `verify` and
                                       `fold --check` pass (refresh/collect/rollback wrote the view)

Typical use:

    repo = java_inheritance(tmp)
    cdp = Cdp(tmp, repo.path)
    cdp.scan()
    repo.write("src/.../Base.java", ...); repo.commit("edit")
    cdp.refresh()
    assert check_refresh_equals_scan(cdp) == []
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from helpers import SKILL_ROOT, have_git
from cdp.util import CdpError

RUN_PY = SKILL_ROOT / "run.py"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "cdp", "GIT_AUTHOR_EMAIL": "cdp@example.invalid",
    "GIT_COMMITTER_NAME": "cdp", "GIT_COMMITTER_EMAIL": "cdp@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


class Repo:
    """A git working tree. `path` is where files live; `git` runs git in it."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self._n = 0

    def git(self, *args: str, check: bool = True, **env_extra: str) -> str:
        env = dict(os.environ, **_GIT_ENV, **env_extra)
        proc = subprocess.run(["git", "-C", str(self.path), "-c", "commit.gpgsign=false", *args],
                              capture_output=True, text=True, env=env)
        if check and proc.returncode != 0:
            raise AssertionError("git %s failed: %s" % (" ".join(args), proc.stderr))
        return proc.stdout.strip()

    def write(self, rel: str, text: str) -> Path:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def read(self, rel: str) -> str:
        return (self.path / rel).read_text()

    def commit(self, message: str = "change") -> str:
        """Stage everything and commit. Each commit gets a distinct, fixed date."""
        self._n += 1
        date = "2025-01-%02dT00:00:00+00:00" % (1 + self._n % 28)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message,
                 GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def branch(self) -> str:
        return self.git("rev-parse", "--abbrev-ref", "HEAD")


def new_repo(tmp, name: str = "repo") -> Repo:
    path = Path(tmp) / name
    path.mkdir(parents=True)
    repo = Repo(path)
    repo.git("init", "-q", "-b", "main")
    return repo


def pom(artifact: str, modules: Iterable[str] = ()) -> str:
    mods = "".join("<module>%s</module>" % m for m in modules)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
            '  <modelVersion>4.0.0</modelVersion>\n'
            '  <groupId>com.example</groupId>\n'
            '  <artifactId>%s</artifactId>\n'
            '  <version>1.0.0</version>\n%s</project>\n'
            % (artifact, ("  <modules>%s</modules>\n" % mods) if mods else ""))


BASE_JAVA = """package com.example.svc;

public abstract class Base {
    protected int inherited() {
        return 1;
    }

    int packagePrivate() {
        return 2;
    }
}
"""

CHILD_JAVA = """package com.example.svc;

import java.util.List;

public class Child extends Base implements Provisioner {
    private final List<String> names;

    Child(List<String> names) {
        this.names = names;
    }

    public int run() {
        return inherited() + packagePrivate() + getPriority();
    }

    @Override
    public int getPriority() {
        return 7;
    }
}
"""

PROVISIONER_JAVA = """package com.example.svc;

public interface Provisioner {
    int getPriority();
}
"""

JUNIT_JAVA = """package com.example.svc;

import org.junit.jupiter.api.Test;

class ChildTest {
    @Test
    void runsAllParts() {
        new Child(java.util.List.of()).run();
    }
}
"""


def java_inheritance(tmp, name: str = "repo") -> Repo:
    """One Maven module: a superclass with a package-private method, a subclass
    calling both through inheritance, an interface method, a constructor and a
    package-private JUnit 5 test (B1/B2/B3/B6/B7)."""
    repo = new_repo(tmp, name)
    src = "src/main/java/com/example/svc/"
    repo.write("pom.xml", pom("svc"))
    repo.write(src + "Base.java", BASE_JAVA)
    repo.write(src + "Child.java", CHILD_JAVA)
    repo.write(src + "Provisioner.java", PROVISIONER_JAVA)
    repo.write("src/test/java/com/example/svc/ChildTest.java", JUNIT_JAVA)
    repo.commit("initial")
    return repo


def _module_java(pkg: str, cls: str, method: str) -> str:
    return ("package com.example.%s;\n\npublic class %s {\n    public int %s() {\n"
            "        return 1;\n    }\n}\n" % (pkg, cls, method))


def multi_module(tmp, name: str = "repo") -> Repo:
    """A root pom with modules `a` and `b`, each its own manifest and class."""
    repo = new_repo(tmp, name)
    repo.write("pom.xml", pom("parent", ["a", "b"]))
    for mod, cls in (("a", "Alpha"), ("b", "Beta")):
        repo.write("%s/pom.xml" % mod, pom(mod))
        repo.write("%s/src/main/java/com/example/%s/%s.java" % (mod, mod, cls),
                   _module_java(mod, cls, "go"))
    repo.commit("initial")
    return repo


def subfolder_module(tmp, name: str = "mono") -> Repo:
    """A monorepo whose git root is not the scan root: scan `repo.path / "sql-pool"`
    (its own identity, by design) with a sibling module beside it (A2/A10)."""
    repo = new_repo(tmp, name)
    repo.write("sql-pool/pom.xml", pom("sql-pool"))
    repo.write("sql-pool/src/main/java/com/example/pool/Pool.java", _module_java("pool", "Pool", "acquire"))
    repo.write("sql-pool/src/main/java/com/example/pool/Lease.java", _module_java("pool", "Lease", "renew"))
    repo.write("catalog/pom.xml", pom("catalog"))
    repo.write("catalog/src/main/java/com/example/catalog/Catalog.java",
               _module_java("catalog", "Catalog", "list"))
    repo.commit("initial")
    return repo


def add_worktree(repo: Repo, branch: str, name: Optional[str] = None) -> Repo:
    """A linked worktree on a new branch (A3/A4/A8). Shares the git common dir."""
    wt = repo.path.parent / (name or ("wt-" + branch.replace("/", "-")))
    repo.git("worktree", "add", "-q", "-b", branch, str(wt))
    return Repo(wt)


def dirty(repo: Repo, rel: str, append: str) -> None:
    """Leave an uncommitted edit to a tracked file."""
    repo.write(rel, repo.read(rel) + append)


def whitespace_only_commit(repo: Repo, rel: str, blank_lines: int = 5) -> str:
    """Insert blank lines at the top of a file and commit: every line moves down,
    no token changes (A11)."""
    repo.write(rel, "\n" * blank_lines + repo.read(rel))
    return repo.commit("whitespace only")


def rename(repo: Repo, old: str, new: str) -> str:
    (repo.path / new).parent.mkdir(parents=True, exist_ok=True)
    repo.git("mv", old, new)
    return repo.commit("rename %s" % old)


def rebased_history(repo: Repo) -> Dict[str, str]:
    """`feature` has two commits; `main` moves on; `feature` is rebased onto it.
    Returns the old and new tips. Anything keyed on a pre-rebase SHA is now
    unreachable from HEAD."""
    base = repo.head()
    repo.git("checkout", "-q", "-b", "feature")
    repo.write("rebase_f1.txt", "one\n")
    repo.commit("feature 1")
    repo.write("rebase_f2.txt", "two\n")
    old_tip = repo.commit("feature 2")
    repo.git("checkout", "-q", "main")
    repo.write("rebase_main.txt", "main\n")
    main_tip = repo.commit("main moves on")
    repo.git("checkout", "-q", "feature")
    repo.git("rebase", "-q", "main")
    return {"base": base, "old_tip": old_tip, "main_tip": main_tip, "new_tip": repo.head()}


def commit_series(repo: Repo, rel: str, n: int) -> List[str]:
    """`n` commits that each append a method to a Java file (a short replay)."""
    shas = []
    for i in range(n):
        text = repo.read(rel)
        idx = text.rindex("}")
        repo.write(rel, text[:idx] + "\n    public int extra%d() {\n        return %d;\n    }\n}\n" % (i, i))
        shas.append(repo.commit("add extra%d" % i))
    return shas


MUTATING = frozenset({"scan", "refresh", "collect", "answer", "rollback", "compact", "fold", "run", "gc"})


class Cdp:
    """A throwaway CDP machine home and the directory it scans.

    `target` is what `--repo` points at: the repo root, a worktree, or a
    subfolder of the git root."""

    autocheck = True  # every state-writing command is followed by `check_fold_green`

    def __init__(self, tmp, target: Path, home: Optional[Path] = None) -> None:
        self.target = Path(target).resolve()
        self.home = Path(home) if home else Path(tmp) / ("home-%s" % self.target.name)

    def run(self, *args: str, check: bool = True, repo: bool = True) -> subprocess.CompletedProcess:
        cmd = [sys.executable, str(RUN_PY), *args]
        if repo:
            cmd += ["--repo", str(self.target)]
        cmd += ["--state-dir", str(self.home)]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, CDP_HOME=str(self.home)))
        if check and proc.returncode != 0:
            raise AssertionError("cdp %s -> rc %s\n%s%s" % (" ".join(args), proc.returncode, proc.stdout, proc.stderr))
        if self.autocheck and proc.returncode == 0 and args and args[0] in MUTATING:
            problems = check_fold_green(self, full=args[0] in ("compact", "rollback", "gc"))
            if problems:
                raise AssertionError("after `cdp %s`: %s" % (" ".join(args[:2]), "; ".join(problems)))
        return proc

    def scan(self, *extra: str, check: bool = True) -> subprocess.CompletedProcess:
        return self.run("scan", "--quiet", *extra, check=check)

    def refresh(self, check: bool = True) -> subprocess.CompletedProcess:
        return self.run("refresh", "--quiet", check=check)

    def query_json(self, *args: str) -> dict:
        return json.loads(self.run("query", *args, "--json").stdout)

    def open(self):
        """`(backend, query.Store)` selected exactly as a query selects it."""
        from cdp.query import Store
        from cdp.session import open_store, paths_for
        backend = open_store(paths_for(self.target, self.home))
        return backend, Store(backend)

    def answering_snapshot(self) -> Optional[Dict]:
        """The snapshot row a query would answer from (None = "scan needed")."""
        backend, _ = self.open()
        try:
            if not backend.has_selection():
                return None
            try:
                sid = backend.snapshot_id()
            except CdpError:  # "scan needed": nothing answers
                return None
            return next((s for s in backend.list_snapshots() if s["id"] == sid), None)
        finally:
            backend.close()

    def artifacts(self, names: Iterable[str] = ("inventory", "extract", "graph", "partition", "xref",
                                                 "dataflow", "schedule")) -> Dict:
        backend, store = self.open()
        try:
            out = {n: backend.read_artifact(n) for n in names}
            out["claims"] = _derived_view(backend.read_artifact("state") or {})
            return out
        finally:
            backend.close()

    def inject_model_patch(self, node: str, claims: List[Dict], unknowns: Optional[List[Dict]] = None,
                           generation: Optional[int] = None, run_id: Optional[str] = None) -> None:
        """Append a leaf-style patch to the live snapshot's log and re-fold, the way
        `collect` does, without a model or an inbox. Claims need real anchors."""
        from cdp import state as state_mod
        from cdp import rollback as rollback_mod
        from cdp.session import next_generation, stamp_claims
        backend, store = self.open()
        try:
            stamp_claims(claims, store.inventory.get("head"))  # as `collect` does
            patches = backend.load_patches()
            patch = {
                "schema_version": "1.0.0", "node": node, "author_kind": "llm", "status": "complete",
                "run_id": run_id or store.manifest.get("run_id", "cdp-test"),
                "generation": generation or next_generation(patches, node),
                "claims": claims, "unknowns": unknowns or [],
            }
            backend.append_patch(patch, node.replace("/", "__"))
            folded = state_mod.fold(
                backend.load_patches(), store.xref, store.partition, repo=self.target,
                excluded_run_ids=rollback_mod.load_excluded_run_ids(backend), extraction=store.extraction)
            backend.write_artifact("state", folded)
        finally:
            backend.close()
        if self.autocheck:
            problems = check_fold_green(self)
            if problems:
                raise AssertionError("after inject_model_patch: " + "; ".join(problems))


def _derived_view(state: Dict) -> List[Dict]:
    """The claims of a state, minus fields that legitimately differ between a refresh
    and a fresh scan of the same commit (stamps naming the run that made them)."""
    volatile = {"claim_reviewed_at", "anchor_verified_at", "source_node"}
    rows = [{k: v for k, v in c.items() if k not in volatile} for c in state.get("claims", [])]
    return sorted(rows, key=lambda c: json.dumps(c, sort_keys=True))


# ------------------------------------------------------------------ invariants

_VOLATILE_KEYS = {"generated_at", "created_at"}


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in _VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def _diff(name: str, a, b, limit: int = 3) -> List[str]:
    """Human-readable differences between two JSON values, first `limit` per artifact."""
    if a == b:
        return []
    out: List[str] = []

    def walk(path, x, y):
        if len(out) >= limit:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x or k not in y:
                    out.append("%s%s: only in %s" % (path, k, "fresh scan" if k in y else "refresh"))
                else:
                    walk("%s%s." % (path, k), x[k], y[k])
        elif isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
            for i, (p, q) in enumerate(zip(x, y)):
                walk("%s[%d]." % (path, i), p, q)
        elif x != y:
            out.append("%s: refresh=%s fresh=%s" % (path.rstrip("."), json.dumps(x)[:80], json.dumps(y)[:80]))

    walk("", a, b)
    if isinstance(a, list) and isinstance(b, list) and len(a) != len(b):
        out.insert(0, "%d entries after refresh vs %d in a fresh scan" % (len(a), len(b)))
    return ["%s: %s" % (name, line) for line in out[:limit]] or ["%s differs" % name]


def check_refresh_equals_scan(cdp: Cdp, tmp=None) -> List[str]:
    """(a) The index `refresh` leaves at HEAD equals a fresh scan of the same commit.

    Run it after `cdp.refresh()`. The tree must be clean (a refresh target always is).
    The fresh scan goes to a second, empty machine home."""
    mine = _strip(cdp.artifacts())
    with tempfile.TemporaryDirectory(prefix="cdp-fresh-") as fresh_home:
        fresh = Cdp(fresh_home, cdp.target, home=Path(fresh_home) / "home")
        fresh.scan()
        theirs = _strip(fresh.artifacts())
    problems: List[str] = []
    for name in mine:
        problems += _diff(name, mine[name], theirs[name])
    return problems


def model_claims(backend) -> List[Dict]:
    """Every claim a model or a human wrote that the log still holds and the fold still reads:
    not rolled back, and not in a generation a later one superseded (a rewrite is not a loss)."""
    from cdp import generations
    from cdp import rollback as rollback_mod
    excluded = rollback_mod.load_excluded_run_ids(backend)
    patches = [p for p in backend.load_patches() if p.get("author_kind") != "python" and not excluded.matches(p)]
    live = {id(p) for p in generations.live_leaf_patches(patches).values()}
    live |= {id(p) for p, _ in generations.live_answer_claims(patches).values()}
    rows: List[Dict] = []
    for patch in patches:
        if id(patch) in live and patch.get("status") == "complete":
            rows += patch.get("claims") or []
    return rows


def model_claim_ids(backend) -> List[str]:
    return [c["id"] for c in model_claims(backend)]


def check_no_silent_loss(cdp: Cdp, before_ids: Optional[Iterable[str]] = None) -> List[str]:
    """(b) A fold drops a model-written claim only through a rollback (excluded run), a
    demotion (`unknowns[].demoted_from`) or a merge into a live claim with the same subject
    and kind -- never silently.

    Without `before_ids`, every model claim still in the log must be live (or accounted for).
    With it (ids live before some operation), those must still be."""
    from cdp import rollback as rollback_mod
    backend, store = cdp.open()
    try:
        state = backend.read_artifact("state") or {}
        live = {c["id"] for c in state.get("claims", [])}
        live_keys = {(c["subject"], c["kind"]) for c in state.get("claims", [])}
        demoted = {u.get("demoted_from") for u in state.get("unknowns", []) if u.get("demoted_from")}
        excluded = rollback_mod.load_excluded_run_ids(backend)
        rolled_back = set()
        by_id = {}
        for patch in backend.load_patches():
            for c in patch.get("claims") or []:
                by_id[c["id"]] = c
                if str(patch.get("run_id")) in excluded:
                    rolled_back.add(c["id"])
        wanted = list(before_ids) if before_ids is not None else model_claim_ids(backend)
        lost = []
        for cid in sorted(set(wanted)):
            c = by_id.get(cid, {})
            if cid in live or cid in demoted or cid in rolled_back:
                continue
            if (c.get("subject"), c.get("kind")) in live_keys:
                continue
            lost.append("model claim %s is neither live, demoted, rolled back nor merged" % cid)
        return lost
    finally:
        backend.close()


def check_derived_claims_live(cdp: Cdp) -> List[str]:
    """Every claim a fresh scan derives for this commit is live in the answering index
    (a model patch, an abandoned scope or a compact must not remove them)."""
    backend, _ = cdp.open()
    try:
        live = {c["id"] for c in (backend.read_artifact("state") or {}).get("claims", [])}
    finally:
        backend.close()
    with tempfile.TemporaryDirectory(prefix="cdp-fresh-") as fresh_home:
        fresh = Cdp(fresh_home, cdp.target, home=Path(fresh_home) / "home")
        fresh.scan()
        want = {c["id"] for c in fresh.artifacts()["claims"]}
    missing = sorted(want - live)
    return (["%d of %d derived claims are not live, e.g. %s" % (len(missing), len(want), missing[0])]
            if missing else [])


def check_answering_snapshot(cdp: Cdp) -> List[str]:
    """(c) The snapshot a query answers from is HEAD (with a matching working tree) or a clean
    ancestor of HEAD -- never another branch's, nor a dirty scan of a different tree."""
    from cdp import snapshot as snapshot_mod
    from cdp.util import run_git
    snap = cdp.answering_snapshot()
    if snap is None:
        return []  # "scan needed" is an honest answer
    head = (run_git(cdp.target, "rev-parse", "HEAD") or "").strip()
    sha = snap["commit_sha"]
    _, current, _ = snapshot_mod.resolve_snapshot(cdp.target, head)
    if sha == current:
        return []
    if snap["ephemeral"]:
        return ["answers come from dirty snapshot %s, which does not match the current tree (%s)"
                % (sha[:20], current[:20])]
    ok = subprocess.run(["git", "-C", str(cdp.target), "merge-base", "--is-ancestor", sha, head],
                        capture_output=True).returncode == 0
    return [] if ok else ["answers come from %s, which is not HEAD (%s) or an ancestor of it" % (sha[:12], head[:12])]


def check_fold_green(cdp: Cdp, full: bool = False) -> List[str]:
    """(d) The materialized state is exactly fold(patches)+xref: `verify` and `fold --check` both
    pass (run after any refresh/scan/collect/answer/rollback/compact/lenient run). Skips a repo
    that has no index yet."""
    problems: List[str] = []
    # `full` (after compact/rollback/gc): the re-fold from the cold archive as well must agree
    for cmd in (("verify",), ("fold", "--check")) + ((("verify", "--full"),) if full else ()):
        saved, cdp.autocheck = cdp.autocheck, False
        try:
            proc = cdp.run(*cmd, check=False)
        finally:
            cdp.autocheck = saved
        if proc.returncode != 0:
            fails = [l.strip() for l in (proc.stdout + proc.stderr).splitlines() if l.startswith("FAIL") or "error" in l.lower()]
            problems.append("`cdp %s` rc=%s: %s" % (" ".join(cmd), proc.returncode, "; ".join(fails[:3]) or "failed"))
    return problems


def check_all(cdp: Cdp) -> List[str]:
    """(a), (b) and (c) together, for tests that just want everything checked after a write."""
    return (check_answering_snapshot(cdp) + check_no_silent_loss(cdp) + check_derived_claims_live(cdp)
            + check_fold_green(cdp))


needs_git = unittest.skipUnless(have_git(), "needs git")
