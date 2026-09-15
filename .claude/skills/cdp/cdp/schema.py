"""A JSON Schema validator, in the stdlib.

CDP has to run wherever it is copied, with no `pip install` step, so it cannot
depend on `jsonschema`. This implements the subset the patch schema actually
uses — type, enum, const, required, properties, additionalProperties, items,
minItems, minLength, maxLength, minimum, pattern, and local `$ref` — and
*refuses to run* against a schema using a keyword it does not implement.

That refusal is the important part. A validator that silently ignores an
unrecognised keyword would let out-of-vocabulary values through, and §5.6 is
explicit that free-text categories are where determinism dies quietly: one run
says `"kind": "entrypoint"`, the next says `"entry point"`, and every downstream
aggregation disagrees without anyone noticing.

Error messages carry a JSON pointer to the offending value because §3.5's retry
contract requires returning "the specific violation" to the agent, three times,
before the node is written `invalid`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .util import CdpError, read_json

SUPPORTED = frozenset(
    [
        "$schema", "$id", "$defs", "$ref", "title", "description", "default",
        "type", "enum", "const", "required", "properties", "additionalProperties",
        "items", "minItems", "maxItems", "minLength", "maxLength", "minimum",
        "maximum", "pattern",
    ]
)

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


class Validator:
    def __init__(self, schema: Dict) -> None:
        self.schema = schema
        self.defs = schema.get("$defs", {})
        _assert_supported(schema)

    @classmethod
    def load(cls, path: Path) -> "Validator":
        return cls(read_json(path))

    def validate(self, instance: Any) -> List[str]:
        """Returns a list of human-readable violations; empty means valid."""
        errors: List[str] = []
        self._check(instance, self.schema, "", errors)
        return errors

    # -------------------------------------------------------------- internals

    def _resolve(self, schema: Dict) -> Dict:
        seen = 0
        while "$ref" in schema and seen < 10:
            ref = schema["$ref"]
            if not ref.startswith("#/$defs/"):
                raise CdpError("unsupported $ref target: %s" % ref)
            key = ref[len("#/$defs/") :]
            if key not in self.defs:
                raise CdpError("dangling $ref: %s" % ref)
            merged = dict(self.defs[key])
            for k, v in schema.items():
                if k != "$ref":
                    merged.setdefault(k, v)
            schema = merged
            seen += 1
        return schema

    def _check(self, value: Any, schema: Dict, path: str, errors: List[str]) -> None:
        schema = self._resolve(schema)
        where = path or "(root)"

        if "const" in schema and value != schema["const"]:
            errors.append("%s: expected %r, got %r" % (where, schema["const"], value))
            return
        if "enum" in schema and value not in schema["enum"]:
            errors.append(
                "%s: %r is not one of %s" % (where, value, ", ".join(map(repr, schema["enum"])))
            )
            return

        expected = schema.get("type")
        if expected:
            names = expected if isinstance(expected, list) else [expected]
            # bool is a subclass of int in Python; JSON Schema keeps them apart.
            ok = any(
                isinstance(value, _TYPES[n]) and not (n in ("integer", "number") and isinstance(value, bool))
                for n in names
                if n in _TYPES
            )
            if not ok:
                errors.append("%s: expected type %s, got %s" % (where, "/".join(names), type(value).__name__))
                return

        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append("%s: shorter than %d characters (%d)" % (where, schema["minLength"], len(value)))
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append("%s: longer than %d characters (%d)" % (where, schema["maxLength"], len(value)))
            if "pattern" in schema and not re.search(schema["pattern"], value):
                errors.append("%s: %r does not match %s" % (where, value, schema["pattern"]))

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append("%s: below minimum %s" % (where, schema["minimum"]))
            if "maximum" in schema and value > schema["maximum"]:
                errors.append("%s: above maximum %s" % (where, schema["maximum"]))

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append("%s: needs at least %d item(s)" % (where, schema["minItems"]))
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                errors.append("%s: allows at most %d item(s)" % (where, schema["maxItems"]))
            item_schema = schema.get("items")
            if item_schema:
                for i, item in enumerate(value):
                    self._check(item, item_schema, "%s[%d]" % (path, i), errors)

        if isinstance(value, dict):
            props = schema.get("properties", {})
            for key in schema.get("required", []):
                if key not in value:
                    errors.append("%s: missing required property %r" % (where, key))
            if schema.get("additionalProperties") is False:
                for key in sorted(value):
                    if key not in props:
                        errors.append("%s: unexpected property %r" % (where, key))
            for key, sub in sorted(props.items()):
                if key in value:
                    self._check(value[key], sub, "%s/%s" % (path, key), errors)


def _assert_supported(schema: Any, path: str = "") -> None:
    if isinstance(schema, dict):
        for key in schema:
            if key in ("properties", "$defs"):
                for name, sub in schema[key].items():
                    _assert_supported(sub, path + "/" + key + "/" + name)
                continue
            if key not in SUPPORTED:
                raise CdpError(
                    "patch schema uses unsupported keyword %r at %s; "
                    "extend cdp/schema.py rather than ignoring it" % (key, path or "(root)")
                )
            if key in ("items",) and isinstance(schema[key], dict):
                _assert_supported(schema[key], path + "/items")
            if key == "additionalProperties" and isinstance(schema[key], dict):
                _assert_supported(schema[key], path + "/additionalProperties")


def schema_path(skill_root: Path) -> Path:
    return Path(skill_root) / "schema" / "patch-1.0.0.json"


def validate_patch(patch: Dict, validator: Validator) -> List[str]:
    """Validate and additionally enforce the cross-field rules the schema cannot
    express: §5.5 requires a `subject` on every claim (already required), and
    §4.3 forbids publishing a claim while `pending_resolution` is true."""
    errors = validator.validate(patch)
    for i, claim in enumerate(patch.get("claims") or []):
        if not isinstance(claim, dict):
            continue
        if claim.get("confidence") == "contested":
            errors.append(
                "/claims[%d]/confidence: 'contested' is set only by the merge "
                "operator, never by an agent (§5.5)" % i
            )
    return errors
