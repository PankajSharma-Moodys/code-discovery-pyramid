"""Data only — rule 1. See languages/profile.py for field semantics."""

from code_scanner.languages.profile import (
    DangerousCall, DocStyle, LanguageProfile, NameStrategy, VisibilityRule,
)

PROFILE = LanguageProfile(
    name="python",
    grammar="python",
    extensions=(".py",),
    function_nodes=frozenset({"function_definition", "lambda"}),
    signature_only_nodes=frozenset(),
    type_nodes=frozenset({"class_definition"}),
    type_container_nodes=frozenset(),
    comment_nodes=frozenset({"comment"}),
    string_nodes=frozenset({"string", "concatenated_string"}),
    call_nodes=frozenset({"call"}),
    parameter_nodes=frozenset({
        "identifier", "default_parameter", "typed_default_parameter", "typed_parameter",
        "list_splat_pattern", "dictionary_splat_pattern",
    }),
    param_excludes=frozenset({"self", "cls"}),
    branch_nodes=frozenset({
        "if_statement", "elif_clause", "for_statement", "while_statement",
        "except_clause", "conditional_expression", "boolean_operator", "if_clause",
    }),
    branch_operators=frozenset({"and", "or"}),
    nesting_nodes=frozenset({
        "if_statement", "elif_clause", "for_statement", "while_statement",
        "try_statement", "with_statement",
    }),
    assignment_nodes=frozenset({"assignment"}),
    assign_target_field="left",
    assign_value_field="right",
    decorator_nodes=frozenset({"decorator"}),
    import_nodes=frozenset({"import_statement", "import_from_statement"}),
    import_source_field="module_name",
    string_content_field="string_content",
    interpolation_nodes=frozenset({"interpolation"}),
    name_field="name",
    name_strategy=NameStrategy.DIRECT,
    body_field="body",
    doc_style=DocStyle.FIRST_STRING_IN_BODY,
    visibility=VisibilityRule.NAME_PREFIX,
    dangerous_calls=(
        DangerousCall("eval", severity="critical"),
        DangerousCall("exec", severity="critical"),
        DangerousCall("os.system", severity="high"),
        DangerousCall("subprocess.run", arg_name="shell", arg_value="True", severity="high"),
        DangerousCall("subprocess.Popen", arg_name="shell", arg_value="True", severity="high"),
        DangerousCall("subprocess.call", arg_name="shell", arg_value="True", severity="high"),
        DangerousCall("pickle.loads", severity="high"),
        DangerousCall("yaml.load", absent_arg="Loader", severity="high"),
    ),
)
