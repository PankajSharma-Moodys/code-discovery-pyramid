#!/usr/bin/env python3
"""Live-model holdout (M9.3, 6.8 -- the "not built" half `PHASE/FINDINGS.md`
named: the deterministic T3-rate A/B is the cheap, always-on gate; this is
the real coverage-based A/B the plan's own prose leans toward, built at the
user's explicit request after being told its real cost).

Unlike `cdp holdout` (pure SQL over already-scanned state), lessons only
affect leaf *dispatch* (`build_prompt`/tiering), so a real A/B needs the
held-out module scanned and leaf-dispatched TWICE with a real model -- once
with `--lessons none`, once with the cut pinned -- before the resulting
states can be benchmarked. Out of core, same posture as `run_benchmark.py`
(M6.2): not imported by `cdp/`.

Uses its own scratch trajectory DB (`--trajectory-db`), never the real
`~/.cdp/trajectories.db` -- this script seeds a synthetic lesson to A/B, and
must not contaminate the real corpus or its holdout-repo bookkeeping.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "/Users/sharmp49/git/code_scanner/sql-pool/sql-pool-api"
LEAF_MODEL = "haiku"
READER_MODEL = "haiku"
JUDGE_MODEL = "sonnet"
QUESTIONS_FILE = Path(__file__).parent / "holdout_live_questions.json"
LEAF_RUNNER = str(ROOT / "scripts" / "claude_leaf_runner.sh")


def cdp(args, **kw):
    return subprocess.run(
        [sys.executable, "-m", "cdp.cli"] + args, cwd=ROOT, capture_output=True, text=True, **kw
    )


def scan_and_dispatch(state_dir, trajectory_db, lessons_arg):
    r = cdp(["scan", "--repo", REPO, "--state-dir", state_dir, "--quiet"])
    if r.returncode != 0:
        raise SystemExit("scan failed: %s" % r.stderr)
    env_note = {"CDP_TRAJECTORY_DB": trajectory_db}
    import os
    env = dict(os.environ, **env_note)
    args = ["run", "--wave-all", "--repo", REPO, "--state-dir", state_dir,
            "--runner-cmd", "%s %s %s" % (LEAF_RUNNER, LEAF_MODEL, REPO)]
    args += lessons_arg
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, "-m", "cdp.cli"] + args, cwd=ROOT, capture_output=True, text=True, env=env
    )
    print("  dispatch (%s): %.1fs\n%s" % (state_dir, time.time() - t0, r.stdout.strip()))
    if r.returncode != 0:
        raise SystemExit("cdp run failed: %s" % r.stderr)


CDP_SYSTEM_PROMPT_TMPL = (
    "You may run `python3 -m cdp.cli query <subcommand> --repo {repo} "
    "--state-dir {state_dir}` and `python3 -m cdp.cli docs --repo {repo} "
    "--state-dir {state_dir}` via Bash to look up structural facts about the "
    "repository (symbols, routes, modules, stats, unknowns). cwd for that "
    "command must be {root}. Prefer cdp query over grepping."
)


def run_claude(question, state_dir):
    prompt_ctx = CDP_SYSTEM_PROMPT_TMPL.format(repo=REPO, state_dir=state_dir, root=ROOT)
    args = [
        "claude", "-p", question, "--output-format", "json", "--model", READER_MODEL,
        # Bash-only, no Read/Grep/Glob: this harness lives inside the very
        # repo `cdp` scans (unlike M6.2's `run_benchmark.py`, whose target was
        # a different checkout), so any filesystem tool can read
        # `holdout_live_questions.json` and its gold facts directly --
        # contamination found live in this session's first real run (arm A's
        # answer literally cited "the benchmark questions in the repository").
        # Bash restricted to cdp.cli closes that path: the model can only
        # answer from what `cdp query`/`docs` actually returns.
        "--tools", "Bash",
        "--allowedTools", "Bash(*cdp.cli*)",
        "--append-system-prompt", prompt_ctx,
    ]
    t0 = time.time()
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=180)
    wall = time.time() - t0
    try:
        data = json.loads(proc.stdout)
    except Exception:
        data = {"result": proc.stdout, "is_error": True, "stderr": proc.stderr}
    data["_wall_s"] = wall
    return data


def run_judge(question, gold_facts, answer_text):
    prompt = (
        "You are grading an AI assistant's answer to a factual question about "
        "a codebase, against a list of gold atomic facts a human verified by "
        "reading the source directly.\n\n"
        f"Question: {question}\n\n"
        f"Gold atomic facts (each must be checked independently): {json.dumps(gold_facts)}\n\n"
        f"Answer to grade:\n{answer_text}\n\n"
        "For EACH gold fact, decide: covered (answer states it correctly), "
        "partial (answer is close/incomplete/hedged but not wrong), or absent "
        "(answer omits it or contradicts it). Respond with ONLY a JSON object: "
        '{"verdicts": [{"fact": "...", "verdict": "covered|partial|absent"}]}'
    )
    args = ["claude", "-p", prompt, "--output-format", "json", "--model", JUDGE_MODEL, "--tools", ""]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
    try:
        data = json.loads(proc.stdout)
        result_text = data.get("result", "")
        m = re.search(r"\{.*\}", result_text, re.S)
        verdicts = json.loads(m.group(0))["verdicts"] if m else []
    except Exception as e:
        verdicts = [{"fact": f, "verdict": "absent", "_judge_error": str(e)} for f in gold_facts]
    return verdicts


def coverage_of(verdicts):
    if not verdicts:
        return 0.0
    score = sum(1.0 if v["verdict"] == "covered" else 0.5 if v["verdict"] == "partial" else 0.0 for v in verdicts)
    return score / len(verdicts)


def benchmark_state(state_dir, questions):
    rows = []
    for q in questions:
        ans = run_claude(q["question"], state_dir)
        text = ans.get("result", "")
        verdicts = run_judge(q["question"], q["gold_facts"], text)
        cov = coverage_of(verdicts)
        rows.append({"id": q["id"], "coverage": cov, "verdicts": verdicts, "answer": text})
        print("    %-4s coverage %.2f" % (q["id"], cov))
    return rows


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectory-db", required=True, help="scratch trajectory DB, never the real one")
    args = ap.parse_args()

    questions = json.loads(QUESTIONS_FILE.read_text())

    from cdp.trajectory import TrajectoryStore
    with TrajectoryStore(args.trajectory_db) as t:
        t.record_promotion(
            run_id="live-holdout-seed", node="root/(files+2)",
            promotion={"promotion": "import_channel_hint", "pattern": "com.rms.auth.framework",
                       "channel": "internal_org_root"},
        )
        t.record_promotion(
            run_id="live-holdout-seed", node="root/(files+2)",
            promotion={"promotion": "import_channel_hint", "pattern": "org.mapstruct",
                       "channel": "internal_org_root"},
        )
        version = t.cut_lessons()
        print("seeded and cut lesson-set v%d (2 import_channel_hint promotions)" % version)

    print("dispatching arm A (--no-lessons)...")
    scan_and_dispatch("/tmp/live_holdout_a", args.trajectory_db, ["--no-lessons"])
    print("dispatching arm B (--lessons v%d)..." % version)
    scan_and_dispatch("/tmp/live_holdout_b", args.trajectory_db, ["--lessons", str(version)])

    print("benchmarking arm A (none)...")
    rows_a = benchmark_state("/tmp/live_holdout_a", questions)
    print("benchmarking arm B (lessons v%d)..." % version)
    rows_b = benchmark_state("/tmp/live_holdout_b", questions)

    cov_none = sum(r["coverage"] for r in rows_a) / len(rows_a)
    cov_lessons = sum(r["coverage"] for r in rows_b) / len(rows_b)
    passed = cov_lessons >= cov_none
    print("\nholdout-live  v%d: coverage %.3f (none) -> %.3f (lessons) -- %s"
          % (version, cov_none, cov_lessons, "PROMOTE" if passed else "REJECT"))

    metric = {"coverage_none": cov_none, "coverage_lessons": cov_lessons,
              "questions": len(questions), "rows_a": rows_a, "rows_b": rows_b}
    Path("benchmarks/results").mkdir(exist_ok=True)
    Path("benchmarks/results/live_holdout.json").write_text(json.dumps(metric, indent=2, default=str))

    if passed:
        with TrajectoryStore(args.trajectory_db) as t:
            t.promote_cut(version, repo_id="github.com/moodys-ma-platform/unified-store",
                          metric={"coverage_none": cov_none, "coverage_lessons": cov_lessons})
        print("promoted v%d in the scratch trajectory DB" % version)


if __name__ == "__main__":
    main()
