"""Data only — rule 1."""

from code_scanner.languages.profile import (
    DangerousCall, DocStyle, LanguageProfile, NameStrategy, VisibilityRule,
)

PROFILE = LanguageProfile(
    name="javascript",
    grammar="javascript",
    extensions=(".js", ".jsx", ".mjs", ".cjs"),
    function_nodes=frozenset({
        "function_declaration", "function_expression", "arrow_function",
        "generator_function", "generator_function_declaration", "method_definition",
    }),
    signature_only_nodes=frozenset(),
    type_nodes=frozenset({"class_declaration", "class"}),
    type_container_nodes=frozenset(),
    comment_nodes=frozenset({"comment", "html_comment"}),  # R25
    string_nodes=frozenset({"string", "template_string"}),
    call_nodes=frozenset({"call_expression", "new_expression"}),
    parameter_nodes=frozenset({"identifier", "assignment_pattern", "rest_pattern", "object_pattern", "array_pattern"}),
    param_excludes=frozenset(),
    branch_nodes=frozenset({
        "if_statement", "for_statement", "for_in_statement", "while_statement",
        "do_statement", "catch_clause", "ternary_expression", "switch_case", "binary_expression",
    }),
    branch_operators=frozenset({"&&", "||", "??"}),
    nesting_nodes=frozenset({
        "if_statement", "for_statement", "for_in_statement", "while_statement",
        "do_statement", "try_statement", "switch_statement",
    }),
    assignment_nodes=frozenset({"variable_declarator", "assignment_expression"}),
    assign_target_field="name",
    assign_value_field="value",
    decorator_nodes=frozenset({"decorator"}),
    import_nodes=frozenset({"import_statement"}),
    import_source_field="source",
    string_content_field="string_fragment",
    interpolation_nodes=frozenset({"template_substitution"}),
    name_field="name",
    name_strategy=NameStrategy.ENCLOSING_BINDING,  # D13.1
    body_field="body",
    doc_style=DocStyle.PREFIXED_COMMENT,
    doc_prefixes=("/**",),
    visibility=VisibilityRule.EXPORT,
    export_ancestors=("variable_declarator", "lexical_declaration", "export_statement"),
    dangerous_calls=(
        DangerousCall("eval", severity="critical"),
        DangerousCall("document.write", severity="medium"),
        DangerousCall("child_process.exec", severity="high"),
        DangerousCall("innerHTML", severity="medium"),
        DangerousCall("new Function", severity="high"),
    ),
)
