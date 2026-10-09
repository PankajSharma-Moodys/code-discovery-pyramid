"""`cdp validate`."""

from __future__ import annotations

from .._common import Spec

from ...schema import Validator, schema_path, validate_patch
from ...util import SKILL_ROOT, read_json
from pathlib import Path


SPEC = Spec(
    group='setup',
    usage='validate <patch.json>',
    what='Validates a patch file against the schema.',
    next='—',
)


def register(add) -> None:
    v = add("validate", "validate a patch file against the schema")
    v.add_argument("path")
    v.set_defaults(func=cmd_validate)


def cmd_validate(args) -> int:
    validator = Validator.load(schema_path(SKILL_ROOT))
    errors = validate_patch(read_json(Path(args.path)), validator)
    if errors:
        for err in errors:
            print("FAIL  %s" % err)
        return 1
    print("ok    %s is a valid CDP patch" % args.path)
    return 0
