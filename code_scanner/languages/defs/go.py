"""Data only — rule 1."""

from code_scanner.languages.profile import DocStyle, LanguageProfile, NameStrategy, VisibilityRule

PROFILE = LanguageProfile(
    name="go",
    grammar="go",
    extensions=(".go",),
    function_nodes=frozenset({"function_declaration", "method_declaration", "func_literal"}),
    signature_only_nodes=frozenset({"function_type", "method_elem"}),
    # R2: type_declaration wraps type_spec wraps struct_type/interface_type — count the
    # wrapper only, so struct/interface/alias each count once instead of struct+interface twice.
    type_nodes=frozenset({"type_declaration"}),
    type_container_nodes=frozenset({"struct_type", "interface_type"}),
    comment_nodes=frozenset({"comment"}),
    string_nodes=frozenset({"interpreted_string_literal", "raw_string_literal"}),
    call_nodes=frozenset({"call_expression"}),
    parameter_nodes=frozenset({"parameter_declaration", "variadic_parameter_declaration"}),
    param_excludes=frozenset(),
    branch_nodes=frozenset({
        "if_statement", "for_statement", "expression_case", "type_case",
        "communication_case", "binary_expression",
    }),
    branch_operators=frozenset({"&&", "||"}),
    nesting_nodes=frozenset({"if_statement", "for_statement", "select_statement", "type_switch_statement"}),
    assignment_nodes=frozenset({"short_var_declaration", "assignment_statement"}),
    assign_target_field="left",
    assign_value_field="right",
    decorator_nodes=frozenset(),
    import_nodes=frozenset({"import_declaration"}),
    import_source_field="path",
    string_content_field="interpreted_string_literal_content",
    interpolation_nodes=frozenset(),
    name_field="name",
    name_strategy=NameStrategy.DIRECT,
    body_field="body",
    doc_style=DocStyle.PREFIXED_COMMENT,
    doc_prefixes=("//",),
    visibility=VisibilityRule.NAME_CASE,
    dangerous_calls=(),
)
