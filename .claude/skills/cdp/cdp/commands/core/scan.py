"""`cdp scan`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import dataflow as dataflow_mod, extract as extract_mod, partition as partition_mod, pipeline as pipeline_mod, schedule as schedule_mod


SPEC = Spec(
    group='core',
    usage='scan --repo <path>',
    what='Every deterministic phase (extract, graph, partition, dataflow, verify, docs) — no model calls, writes the one machine store (`CDP_HOME`, default `~/.cdp`; never the repo). Start here, always.',
    next='next: `query stats`, `query trace <entrypoint>`, or `prompts`. Flags: `--workers N`, `--exclude DIR`, `--no-docs`, `--quiet`.',
)


def register(add) -> None:
    s = add("scan", "run every deterministic phase and write queryable state")
    s.add_argument("--max-leaf-files", type=int, default=partition_mod.DEFAULT_MAX_FILES)
    s.add_argument("--max-leaf-loc", type=int, default=partition_mod.DEFAULT_MAX_LOC)
    s.add_argument("--max-concurrent", type=int, default=schedule_mod.DEFAULT_MAX_CONCURRENT)
    s.add_argument("--max-hops", type=int, default=dataflow_mod.DEFAULT_MAX_HOPS)
    s.add_argument("--workers", type=int, default=None,
                   help="parallel extraction workers (F9: default auto -- "
                        "sequential under %d parseable files, else cpu_count; "
                        "1 forces sequential)" % extract_mod.PARALLEL_MIN_FILES)
    s.add_argument("--exclude", action="append", default=None, metavar="NAME",
                   help="directory-name segment to exclude from the scan, in "
                        "addition to the built-in AI-tool/editor defaults "
                        "(.claude, .cursor, ...) and any .cdp.toml `exclude` "
                        "list -- repeatable")
    s.add_argument("--no-docs", dest="docs", action="store_false", default=True,
                   help="skip rendering <state-dir>/docs/ at the end of the scan")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(func=cmd_scan)


@locked(shared=False)
def cmd_scan(args) -> int:
    paths = paths_from_args(args)
    say = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    pipeline_mod.scan(
        paths,
        max_leaf_files=args.max_leaf_files, max_leaf_loc=args.max_leaf_loc,
        max_concurrent=args.max_concurrent, max_hops=args.max_hops, workers=args.workers,
        exclude=args.exclude, docs=args.docs, say=say,
    )
    return 0
