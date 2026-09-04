"""argparse CLI: `scan` reads code and writes JSON; `report` reads JSON and writes documents (§9)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from code_scanner import __version__ as VERSION
from code_scanner.config import Config
from code_scanner.pipeline import run_scan
from code_scanner.render import json_out


def _err(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(msg, file=sys.stderr)


def _fail_under_exit_code(score_value: float | None, fail_under: float | None, fail_on_empty: bool) -> int:
    if fail_under is None:
        return 0
    if score_value is None:
        return 1 if fail_on_empty else 0
    return 1 if score_value < fail_under else 0


def _cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.path)
    config = Config.load(root, explicit_path=Path(args.config) if args.config else None)

    if args.detail:
        config.resolved.setdefault("scan", {})["detail"] = args.detail

    result = run_scan(root, config, detail=config.resolved["scan"]["detail"])

    if args.out:
        json_out.write(result, args.out)
    _err(
        f"Scanned {result.files_scanned} files ({result.duration_ms / 1000:.1f}s)",
        quiet=args.quiet,
    )

    if args.html:
        _err("error: --html on `scan` is not implemented until M4", quiet=args.quiet)
        return 2

    fail_on_empty = config.resolved["score"]["fail_on_empty"]
    return _fail_under_exit_code(result.score.value, args.fail_under, fail_on_empty)


def _cmd_report(args: argparse.Namespace) -> int:
    with open(args.results_json, encoding="utf-8") as f:
        data = json.load(f)

    if args.html or args.md or args.csv:
        _err("error: --html/--md/--csv on `report` are not implemented until M4", quiet=args.quiet)
        return 2

    fail_on_empty = data.get("scan", {}).get("config", {}).get("score", {}).get("fail_on_empty", False)
    return _fail_under_exit_code(data.get("score", {}).get("value"), args.fail_under, fail_on_empty)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="code-scanner")
    parser.add_argument("--version", action="version", version=f"code-scanner {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan a codebase and write a JSON result")
    scan.add_argument("path")
    scan.add_argument("--out", default=None)
    scan.add_argument("--html", default=None)
    scan.add_argument("--config", default=None)
    scan.add_argument("--jobs", type=int, default=0)
    scan.add_argument("--include", action="append", default=[])
    scan.add_argument("--exclude", action="append", default=[])
    scan.add_argument("--exclude-role", default=None)
    scan.add_argument("--detail", choices=["threshold", "full", "summary"], default=None)
    scan.add_argument("--fail-under", type=float, default=None)
    scan.add_argument("--no-modules", action="store_true")
    scan.add_argument("--module-manifest", action="append", default=[])
    scan.add_argument("--no-packs", action="store_true")
    scan.add_argument("--quiet", action="store_true")
    scan.set_defaults(func=_cmd_scan)

    report = sub.add_parser("report", help="read a JSON result and write documents")
    report.add_argument("results_json")
    report.add_argument("--html", default=None)
    report.add_argument("--md", default=None)
    report.add_argument("--csv", default=None)
    report.add_argument("--role", default=None)
    report.add_argument("--module", default=None)
    report.add_argument("--top", type=int, default=None)
    report.add_argument("--fail-under", type=float, default=None)
    report.add_argument("--quiet", action="store_true")
    report.set_defaults(func=_cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
