"""Data only — rule 1."""

from code_scanner.languages.profile import DocStyle, LanguageProfile, NameStrategy, VisibilityRule

PROFILE = LanguageProfile(
    name="csharp",
    grammar="csharp",
    extensions=(".cs",),
    function_nodes=frozenset({
        "method_declaration", "constructor_declaration", "destructor_declaration",
        "local_function_statement", "lambda_expression",
    }),
    signature_only_nodes=frozenset(),
    type_nodes=frozenset({
        "class_declaration", "struct_declaration", "interface_declaration",
        "enum_declaration", "record_declaration",
    }),
    type_container_nodes=frozenset(),
    comment_nodes=frozenset({"comment"}),
    string_nodes=frozenset({"string_literal", "verbatim_string_literal", "raw_string_literal"}),
    call_nodes=frozenset({"invocation_expression", "object_creation_expression"}),
    parameter_nodes=frozenset({"parameter"}),
    param_excludes=frozenset(),
    branch_nodes=frozenset({
        "if_statement", "for_statement", "foreach_statement", "while_statement",
        "do_statement", "catch_clause", "switch_expression_arm", "switch_section",
        "conditional_expression", "binary_expression",
    }),
    branch_operators=frozenset({"&&", "||", "??"}),
    nesting_nodes=frozenset({
        "if_statement", "for_statement", "foreach_statement", "while_statement",
        "do_statement", "try_statement", "switch_statement", "switch_expression",
    }),
    assignment_nodes=frozenset({"variable_declarator", "assignment_expression"}),
    assign_target_field="name",
    assign_value_field="value",
    decorator_nodes=frozenset({"attribute"}),
    import_nodes=frozenset({"using_directive"}),
    import_source_field="name",
    string_content_field="string_literal_content",
    interpolation_nodes=frozenset({"interpolation"}),
    name_field="name",
    name_strategy=NameStrategy.DIRECT,
    body_field="body",
    doc_style=DocStyle.PREFIXED_COMMENT,
    doc_prefixes=("///",),
    visibility=VisibilityRule.MODIFIER,
    modifier_field="modifier",
)
