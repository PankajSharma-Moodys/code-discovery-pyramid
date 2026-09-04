"""Data only — rule 1."""

from code_scanner.languages.profile import DocStyle, LanguageProfile, NameStrategy, VisibilityRule

PROFILE = LanguageProfile(
    name="rust",
    grammar="rust",
    extensions=(".rs",),
    function_nodes=frozenset({"function_item", "closure_expression"}),
    signature_only_nodes=frozenset({"function_signature_item"}),
    # R2: impl_item is a block, not a type — dropped, per PLAN's ruling.
    type_nodes=frozenset({"struct_item", "enum_item", "trait_item"}),
    type_container_nodes=frozenset(),
    comment_nodes=frozenset({"line_comment", "block_comment", "doc_comment"}),
    string_nodes=frozenset({"string_literal", "raw_string_literal"}),
    call_nodes=frozenset({"call_expression", "macro_invocation"}),
    parameter_nodes=frozenset({"parameter", "self_parameter"}),
    param_excludes=frozenset({"self"}),
    branch_nodes=frozenset({
        "if_expression", "if_let_expression", "for_expression", "while_expression",
        "while_let_expression", "match_arm", "binary_expression",
    }),
    branch_operators=frozenset({"&&", "||"}),
    nesting_nodes=frozenset({
        "if_expression", "if_let_expression", "for_expression", "while_expression",
        "while_let_expression", "match_expression", "loop_expression",
    }),
    assignment_nodes=frozenset({"let_declaration"}),
    assign_target_field="pattern",
    assign_value_field="value",
    decorator_nodes=frozenset({"attribute_item"}),
    import_nodes=frozenset({"use_declaration"}),
    import_source_field="argument",
    string_content_field="string_content",
    interpolation_nodes=frozenset(),
    name_field="name",
    name_strategy=NameStrategy.DIRECT,
    body_field="body",
    # doc_comment is reported as a child of line_comment (unverified by RESEARCH Appendix A;
    # confirmed here: rust's grammar attaches an `doc` field to line_comment/block_comment
    # nodes carrying `///`/`//!`/`/**`/`/*!` — DOC_NODE detection walks comment_nodes for it.
    doc_style=DocStyle.DOC_NODE,
    doc_nodes=frozenset({"doc_comment"}),
    visibility=VisibilityRule.UNKNOWN,  # pub(crate) is conditional visibility — approximate: true
    dangerous_calls=(),
)
