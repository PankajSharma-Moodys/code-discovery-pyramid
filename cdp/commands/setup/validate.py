"""`cdp validate`."""

from __future__ import annotations

from .._common import Spec

from ...schema import Validator, schema_path, validate_patch
from ...util import SKILL_ROOT, CdpError
import json
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
    path = Path(args.path)
    if not path.is_file():
        raise CdpError("%s: %s" % (args.path, "is a directory, not a patch file" if path.is_dir() else "no such file"))
    try:
        patch = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CdpError("%s is not valid JSON: %s" % (args.path, exc))
    validator = Validator.load(schema_path(SKILL_ROOT))
    errors = validate_patch(patch, validator)
    if errors:
        for err in errors:
            print("FAIL  %s" % err)
        return 1
    print("ok    %s is a valid CDP patch" % args.path)
    return 0
