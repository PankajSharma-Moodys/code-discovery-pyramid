"""The command registry: one module per command, in `cdp help` order.

A command module exposes `register(add)`, which declares its parser, and a
`cmd_*` function that reads flags, calls an engine and prints. Commands import
engines and `_common` only; engines never import this package
(`tests/test_layering.py`).
"""

from __future__ import annotations

from .core import scan as c_scan
from .core import query as c_query
from .core import docs as c_docs
from .leaf import prompts as c_prompts
from .leaf import collect as c_collect
from .leaf import fold as c_fold
from .leaf import refresh as c_refresh
from .leaf import run as c_run
from .setup import doctor as c_doctor
from .learning import reflect as c_reflect
from .learning import lessons as c_lessons
from .learning import holdout as c_holdout
from .core import status as c_status
from .core import diff as c_diff
from . import link as c_link
from .maintenance import gc as c_gc
from .maintenance import compact as c_compact
from .leaf import verify as c_verify
from .maintenance import export as c_export
from .maintenance import rollback as c_rollback
from .leaf import answer as c_answer
from .setup import validate as c_validate
from .setup import githook as c_githook
from .setup import install as c_install
from .setup import selftest as c_selftest
from .setup import help as c_help

COMMANDS = (
    ("scan", c_scan),
    ("query", c_query),
    ("docs", c_docs),
    ("prompts", c_prompts),
    ("collect", c_collect),
    ("fold", c_fold),
    ("refresh", c_refresh),
    ("run", c_run),
    ("doctor", c_doctor),
    ("reflect", c_reflect),
    ("lessons", c_lessons),
    ("holdout", c_holdout),
    ("status", c_status),
    ("diff", c_diff),
    ("link", c_link),
    ("gc", c_gc),
    ("compact", c_compact),
    ("verify", c_verify),
    ("export", c_export),
    ("rollback", c_rollback),
    ("answer", c_answer),
    ("validate", c_validate),
    ("githook", c_githook),
    ("install", c_install),
    ("selftest", c_selftest),
    ("help", c_help),
)


GROUPS = (
    ("core", "Core loop"),
    ("leaf", "Leaf agents"),
    ("learning", "Learning"),
    ("link", "Cross-repo link"),
    ("maintenance", "Maintenance"),
    ("setup", "Setup & self-check"),
)


def specs():
    """Every command's `Spec`, grouped in `GROUPS` order."""
    found = []
    for _name, module in COMMANDS:
        found.extend(getattr(module, "SPECS", None) or [module.SPEC])
    return [(title, [s for s in found if s.group == key]) for key, title in GROUPS]


def register_all(add) -> None:
    for _name, module in COMMANDS:
        module.register(add)
