#!/usr/bin/env python3
"""M6.2 graded benchmark harness. Out of core, per phase_6_plan.md's
'Modules touched' note. Not imported by cdp/ itself.

Two arms (baseline: grep/read/glob only; cdp: baseline + cdp query/docs via
Bash), reader model != judge model, judged against gold_facts with a
verbatim-quote requirement. See PHASE/M6_2_BENCHMARK_DESIGN.md for the design
this implements.
"""
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = "/Users/sharmp49/git/code_scanner"
STATE_DIR = "/tmp/m62_scratch"
READER_MODEL = "sonnet"
JUDGE_MODEL = "opus"
RESULTS_DIR = Path(__file__).parent / "results"
QUESTIONS_FILE = Path(__file__).parent / "questions.json"

CDP_SYSTEM_PROMPT = (
    "You may run `python3 -m cdp.cli query <subcommand> --repo "
    f"{REPO} --state-dir {STATE_DIR}` and `python3 -m cdp.cli docs "
    f"--repo {REPO} --state-dir {STATE_DIR}` via Bash to look up structural "
    "facts about the repository (symbols, routes, modules, stats, unknowns). "
    "cwd for that command must be /Users/sharmp49/hackathon/code_scanner. "
    "You may also use Read/Grep/Glob directly on the repo. Prefer cdp query "
    "over grepping when it can answer the question."
)


def run_claude(question, arm, cwd):
    base_args = [
        "claude", "-p", question,
        "--output-format", "json",
        "--model", READER_MODEL,
    ]
    if arm == "baseline":
        args = base_args + ["--tools", "Read,Grep,Glob"]
    else:
        args = base_args + [
            "--tools", "Read,Grep,Glob,Bash",
            "--allowedTools", "Bash(*cdp.cli*)",
            "--append-system-prompt", CDP_SYSTEM_PROMPT,
        ]
    t0 = time.time()
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=180)
    wall = time.time() - t0
    try:
        data = json.loads(proc.stdout)
    except Exception:
        data = {"result": proc.stdout, "is_error": True, "stderr": proc.stderr}
    data["_wall_s"] = wall
    return data


def run_judge(qid, question, gold_facts, answer_text):
    prompt = (
        "You are grading an AI assistant's answer to a factual question about "
        "a codebase, against a list of gold atomic facts a human verified by "
        "reading the source directly.\n\n"
        f"Question: {question}\n\n"
        f"Gold atomic facts (each must be checked independently): {json.dumps(gold_facts)}\n\n"
        f"Answer to grade:\n{answer_text}\n\n"
        "For EACH gold fact, decide: covered (answer states it correctly), "
        "partial (answer is close/incomplete/hedged but not wrong), or absent "
        "(answer omits it or contradicts it). For each verdict, quote the "
        "exact substring of the answer that justifies it (empty string if "
        "absent). Respond with ONLY a JSON object: "
        '{"verdicts": [{"fact": "...", "verdict": "covered|partial|absent", "quote": "..."}]}'
    )
    args = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", JUDGE_MODEL,
        "--tools", "",
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
    try:
        data = json.loads(proc.stdout)
        result_text = data.get("result", "")
        m = re.search(r"\{.*\}", result_text, re.S)
        verdicts = json.loads(m.group(0))["verdicts"] if m else []
    except Exception as e:
        verdicts = [{"fact": f, "verdict": "absent", "quote": "", "_judge_error": str(e)} for f in gold_facts]
    return verdicts


def coverage_of(verdicts):
    if not verdicts:
        return 0.0
    score = sum(1.0 if v["verdict"] == "covered" else 0.5 if v["verdict"] == "partial" else 0.0 for v in verdicts)
    return score / len(verdicts)


FILE_LINE_RE = re.compile(r"([A-Za-z0-9_./\-]+\.[A-Za-z]{1,6}):(\d+)")


def citation_validity(answer_text):
    cites = FILE_LINE_RE.findall(answer_text)
    if not cites:
        return None  # no citations offered
    ok = 0
    for path, line in cites:
        p = Path(REPO) / path
        if not p.exists():
            p2 = Path(REPO) / path.lstrip("./")
            p = p2 if p2.exists() else p
        if p.exists():
            try:
                nlines = sum(1 for _ in open(p, "r", errors="ignore"))
                if int(line) <= max(nlines, 1):
                    ok += 1
            except Exception:
                pass
    return {"total": len(cites), "valid": ok}


def main():
    questions = json.loads(QUESTIONS_FILE.read_text())
    RESULTS_DIR.mkdir(exist_ok=True)
    results = []

    print(f"Running {len(questions)} questions x 2 arms ({2*len(questions)} reader calls)...", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {}
        for q in questions:
            futs[pool.submit(run_claude, q["question"], "baseline", REPO)] = (q["id"], "baseline")
            futs[pool.submit(run_claude, q["question"], "cdp", REPO)] = (q["id"], "cdp")
        by_q = {q["id"]: {"question": q, "baseline": None, "cdp": None} for q in questions}
        done = 0
        for fut in as_completed(futs):
            qid, arm = futs[fut]
            by_q[qid][arm] = fut.result()
            done += 1
            print(f"  [{done}/{len(futs)}] {qid} {arm} done", flush=True)

    print("Running judge pass...", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        judge_futs = {}
        for qid, rec in by_q.items():
            gold = rec["question"]["gold_facts"]
            for arm in ("baseline", "cdp"):
                ans = rec[arm].get("result", "") if rec[arm] else ""
                judge_futs[pool.submit(run_judge, qid, rec["question"]["question"], gold, ans)] = (qid, arm)
        judged = 0
        for fut in as_completed(judge_futs):
            qid, arm = judge_futs[fut]
            by_q[qid].setdefault("verdicts", {})[arm] = fut.result()
            judged += 1
            print(f"  [{judged}/{len(judge_futs)}] judged {qid} {arm}", flush=True)

    for qid, rec in by_q.items():
        row = {"id": qid, "category": rec["question"]["category"]}
        for arm in ("baseline", "cdp"):
            r = rec[arm] or {}
            answer = r.get("result", "")
            verdicts = rec.get("verdicts", {}).get(arm, [])
            row[f"{arm}_coverage"] = coverage_of(verdicts)
            usage = r.get("usage", {})
            row[f"{arm}_tokens"] = (usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                                     + usage.get("cache_read_input_tokens", 0))
            row[f"{arm}_cost_usd"] = r.get("total_cost_usd", 0)
            row[f"{arm}_wall_s"] = r.get("_wall_s", 0)
            row[f"{arm}_num_turns"] = r.get("num_turns", 0)
            if arm == "cdp":
                row["citation_validity"] = citation_validity(answer)
        results.append(row)

    out = {"reader_model": READER_MODEL, "judge_model": JUDGE_MODEL, "results": results, "raw": by_q}
    (RESULTS_DIR / "run.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"Wrote {RESULTS_DIR / 'run.json'}")


if __name__ == "__main__":
    main()
