"""Data only — rule 1. C++ is hardest and scheduled last (Appendix A) — degrades to
<anonymous> names via DECLARATOR_DESCENT rather than blocking."""

from code_scanner.languages.profile import DocStyle, LanguageProfile, NameStrategy, VisibilityRule

PROFILE = LanguageProfile(
    name="cpp",
    grammar="cpp",
    extensions=(".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h"),
    function_nodes=frozenset({"function_definition", "lambda_expression"}),
    signature_only_nodes=frozenset(),
    type_nodes=frozenset({"class_specifier", "struct_specifier", "enum_specifier"}),
    type_container_nodes=frozenset(),
    comment_nodes=frozenset({"comment"}),
    string_nodes=frozenset({"string_literal", "raw_string_literal", "concatenated_string"}),
    call_nodes=frozenset({"call_expression", "new_expression"}),
    parameter_nodes=frozenset({"parameter_declaration", "variadic_parameter_declaration"}),
    param_excludes=frozenset(),
    branch_nodes=frozenset({
        "if_statement", "for_statement", "for_range_loop", "while_statement",
        "do_statement", "catch_clause", "case_statement", "conditional_expression", "binary_expression",
    }),
    branch_operators=frozenset({"&&", "||"}),
    nesting_nodes=frozenset({
        "if_statement", "for_statement", "for_range_loop", "while_statement",
        "do_statement", "try_statement", "switch_statement",
    }),
    assignment_nodes=frozenset({"init_declarator", "assignment_expression"}),
    assign_target_field="declarator",
    assign_value_field="value",
    decorator_nodes=frozenset(),
    import_nodes=frozenset({"preproc_include"}),
    import_source_field="path",
    string_content_field=None,
    interpolation_nodes=frozenset(),
    name_field="declarator",
    name_strategy=NameStrategy.DECLARATOR_DESCENT,
    body_field="body",
    doc_style=DocStyle.PREFIXED_COMMENT,
    doc_prefixes=("/**", "///"),
    visibility=VisibilityRule.UNKNOWN,  # public:/private: sections, not a per-declaration modifier
)
