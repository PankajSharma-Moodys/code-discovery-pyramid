"""Data only — rule 1."""

from code_scanner.languages.profile import (
    DangerousCall, DocStyle, LanguageProfile, NameStrategy, VisibilityRule,
)

PROFILE = LanguageProfile(
    name="ruby",
    grammar="ruby",
    extensions=(".rb",),
    function_nodes=frozenset({"method", "singleton_method", "lambda"}),
    signature_only_nodes=frozenset(),
    type_nodes=frozenset({"class", "module", "singleton_class"}),
    type_container_nodes=frozenset(),
    comment_nodes=frozenset({"comment"}),
    string_nodes=frozenset({"string", "bare_string", "heredoc_body"}),  # heredoc_body, not comment (RESEARCH E)
    call_nodes=frozenset({"call"}),
    parameter_nodes=frozenset({
        "identifier", "optional_parameter", "keyword_parameter", "splat_parameter",
        "hash_splat_parameter", "block_parameter",
    }),
    param_excludes=frozenset(),
    branch_nodes=frozenset({
        "if", "elsif", "unless", "for", "while", "until", "rescue", "when", "binary",
    }),
    branch_operators=frozenset({"&&", "||", "and", "or"}),
    nesting_nodes=frozenset({"if", "unless", "for", "while", "until", "begin", "case"}),
    assignment_nodes=frozenset({"assignment"}),
    assign_target_field="left",
    assign_value_field="right",
    decorator_nodes=frozenset(),
    import_nodes=frozenset({"call"}),  # require/require_relative are ordinary calls in Ruby
    import_source_field="",
    string_content_field="string_content",
    interpolation_nodes=frozenset({"interpolation"}),
    name_field="name",
    name_strategy=NameStrategy.DIRECT,
    body_field="body",
    doc_style=DocStyle.NONE,
    visibility=VisibilityRule.UNKNOWN,  # `private` is a runtime method call — approximate: true
    dangerous_calls=(
        DangerousCall("eval", severity="critical"),
        DangerousCall("system", severity="high"),
        DangerousCall("Marshal.load", severity="high"),
    ),
)
