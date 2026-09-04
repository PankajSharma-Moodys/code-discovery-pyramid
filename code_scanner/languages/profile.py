"""LanguageProfile: the data record that lets analyzers stay language-blind (rule 1).

Adding a language means adding a record here (well, in languages/defs/) and a golden
fixture — never an `if language == "…"` in an analyzer. See RESEARCH.md §3 and
PLAN.md §2 for the field-by-field rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DocStyle(Enum):
    FIRST_STRING_IN_BODY = "first_string_in_body"  # python
    DOC_NODE = "doc_node"                            # rust: doc_comment
    PREFIXED_COMMENT = "prefixed_comment"             # java /**, csharp ///
    NONE = "none"


class VisibilityRule(Enum):
    NAME_PREFIX = "name_prefix"   # python: not leading "_"
    NAME_CASE = "name_case"       # go: leading uppercase
    MODIFIER = "modifier"         # java, csharp, cpp: "public" in modifiers
    EXPORT = "export"             # javascript, typescript, tsx
    UNKNOWN = "unknown"           # ruby, rust — approximate: true


class NameStrategy(Enum):
    DIRECT = "direct"                        # name_field on the declaration node itself
    DECLARATOR_DESCENT = "declarator_descent"  # cpp: descend through pointer/ref/template declarators
    ENCLOSING_BINDING = "enclosing_binding"   # js/ts arrow functions: name from variable_declarator etc (D13.1)


@dataclass(frozen=True)
class DangerousCall:
    """A deny-listed call. Argument-sensitive predicates (R21) use arg_name/arg_value/absent_arg."""

    callee: str
    severity: str = "high"
    arg_name: str | None = None
    arg_value: str | None = None
    absent_arg: str | None = None  # flags only when this argument is NOT present
    message: str = ""


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    grammar: str
    extensions: tuple[str, ...]

    function_nodes: frozenset[str]
    signature_only_nodes: frozenset[str]  # bodyless type-level decls, always excluded (Finding A / R14)
    type_nodes: frozenset[str]
    type_container_nodes: frozenset[str]  # R2: match only when no listed descendant matches
    comment_nodes: frozenset[str]
    string_nodes: frozenset[str]
    call_nodes: frozenset[str]

    parameter_nodes: frozenset[str]       # R6: the specific child kinds that ARE a parameter
    param_excludes: frozenset[str]        # R6: self/cls, *args/**kwargs by field or text

    branch_nodes: frozenset[str]
    branch_operators: frozenset[str]      # R15: occurrences within a generic binary_expression node
    nesting_nodes: frozenset[str]

    assignment_nodes: frozenset[str]
    assign_target_field: str
    assign_value_field: str

    decorator_nodes: frozenset[str]
    import_nodes: frozenset[str]
    import_source_field: str

    string_content_field: str | None      # R22: entropy measured over content, not quotes
    interpolation_nodes: frozenset[str]    # R23: structural placeholder guard

    name_field: str
    name_strategy: NameStrategy

    body_field: str
    doc_style: DocStyle
    doc_prefixes: tuple[str, ...] = ()
    doc_nodes: frozenset[str] = field(default_factory=frozenset)

    visibility: VisibilityRule = VisibilityRule.UNKNOWN
    modifier_field: str | None = None
    export_ancestors: tuple[str, ...] = ()

    dangerous_calls: tuple[DangerousCall, ...] = ()


# Populated at import time by languages/registry.py from languages/defs/*.py.
