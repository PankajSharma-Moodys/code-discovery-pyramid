"""Data only — rule 1."""

from code_scanner.languages.profile import DocStyle, LanguageProfile, NameStrategy, VisibilityRule

PROFILE = LanguageProfile(
    name="typescript",
    grammar="typescript",
    extensions=(".ts",),
    function_nodes=frozenset({
        "function_declaration", "function_expression", "arrow_function",
        "generator_function", "generator_function_declaration", "method_definition",
    }),
    # Appendix A finding A: exclude the bodyless type-level signature kinds.
    signature_only_nodes=frozenset({
        "function_signature", "method_signature", "call_signature",
        "construct_signature", "abstract_method_signature", "function_type", "index_signature",
    }),
    type_nodes=frozenset({
        "class_declaration", "interface_declaration", "enum_declaration", "abstract_class_declaration",
    }),
    type_container_nodes=frozenset(),
    comment_nodes=frozenset({"comment", "html_comment"}),
    string_nodes=frozenset({"string", "template_string"}),
    call_nodes=frozenset({"call_expression", "new_expression"}),
    parameter_nodes=frozenset({
        "required_parameter", "optional_parameter", "identifier", "rest_pattern",
    }),
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
    name_strategy=NameStrategy.ENCLOSING_BINDING,
    body_field="body",
    doc_style=DocStyle.PREFIXED_COMMENT,
    doc_prefixes=("/**",),
    visibility=VisibilityRule.EXPORT,
    export_ancestors=("variable_declarator", "lexical_declaration", "export_statement"),
)
