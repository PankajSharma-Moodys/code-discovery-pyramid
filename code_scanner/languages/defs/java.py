"""Data only — rule 1."""

from code_scanner.languages.profile import (
    DangerousCall, DocStyle, LanguageProfile, NameStrategy, VisibilityRule,
)

PROFILE = LanguageProfile(
    name="java",
    grammar="java",
    extensions=(".java",),
    function_nodes=frozenset({
        "method_declaration", "constructor_declaration",
        "compact_constructor_declaration", "lambda_expression",
    }),
    signature_only_nodes=frozenset(),  # R14: interface/abstract methods keep their bodyless method_declaration
    type_nodes=frozenset({
        "class_declaration", "interface_declaration", "enum_declaration", "record_declaration",
    }),
    type_container_nodes=frozenset(),
    comment_nodes=frozenset({"line_comment", "block_comment"}),
    string_nodes=frozenset({"string_literal", "string_interpolation"}),
    call_nodes=frozenset({"method_invocation", "object_creation_expression"}),
    parameter_nodes=frozenset({"formal_parameter", "spread_parameter", "receiver_parameter"}),
    param_excludes=frozenset(),
    branch_nodes=frozenset({
        "if_statement", "for_statement", "enhanced_for_statement", "while_statement",
        "do_statement", "catch_clause", "switch_label", "ternary_expression", "binary_expression",
    }),
    branch_operators=frozenset({"&&", "||"}),
    nesting_nodes=frozenset({
        "if_statement", "for_statement", "enhanced_for_statement", "while_statement",
        "do_statement", "try_statement", "switch_expression",
    }),
    assignment_nodes=frozenset({"variable_declarator", "assignment_expression"}),
    assign_target_field="name",
    assign_value_field="value",
    decorator_nodes=frozenset({"annotation", "marker_annotation"}),
    import_nodes=frozenset({"import_declaration"}),
    import_source_field="",
    string_content_field="string_fragment",
    interpolation_nodes=frozenset({"string_interpolation"}),
    name_field="name",
    name_strategy=NameStrategy.DIRECT,
    body_field="body",
    doc_style=DocStyle.PREFIXED_COMMENT,
    doc_prefixes=("/**",),
    visibility=VisibilityRule.MODIFIER,
    modifier_field="modifiers",
    dangerous_calls=(
        DangerousCall("Runtime.getRuntime().exec", severity="high"),
        DangerousCall("ObjectInputStream.readObject", severity="high"),
        DangerousCall("ProcessBuilder", severity="medium"),
    ),
)
