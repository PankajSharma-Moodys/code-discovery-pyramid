"""`cdp docs`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import query as query_mod
from ...session import open_store, render_docs
from pathlib import Path


SPEC = Spec(
    group='core',
    usage='docs [--out DIR]',
    what='Renders `00-overview.md`, `modules/<module>.md`, `dataflow.md`, `unknowns.md`, `CLAUDE.md`.',
    next='next: open `<out>/00-overview.md`, or `query stats`.',
)


def register(add) -> None:
    d = add("docs", "render the markdown artifacts")
    d.add_argument("--out", default=None, help="output directory (default: <state-dir>/docs)")
    d.set_defaults(func=cmd_docs)


@locked(shared=True)
def cmd_docs(args) -> int:
    paths = paths_from_args(args)
    store = query_mod.Store(open_store(paths))
    out = Path(args.out).expanduser().resolve() if args.out else paths.work / "docs"
    for path in render_docs(store, out):
        print(path)
    print("next      open %s/00-overview.md, or cdp query stats" % out)
    store.close()
    return 0
