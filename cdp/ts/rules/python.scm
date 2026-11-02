; Rules for Python declarations. Same capture vocabulary as java.scm; roles in emit_map.json (lang_overrides.python)
(class_definition name: (identifier) @name) @definition.class
(function_definition name: (identifier) @name) @definition.function
(assignment left: (identifier) @name) @definition.attr
(assignment left: (identifier) @name type: (_)) @definition.field
(assignment left: (identifier) @name type: (_) @fin (#match? @fin "Final")) @definition.constant
(assignment left: (identifier) @name (#match? @name "^[A-Z0-9_]*[A-Z][A-Z0-9_]*$")) @definition.constant

(parameters (identifier) @param.name @param)
(parameters (default_parameter name: (identifier) @param.name) @param)
(parameters (typed_parameter (identifier) @param.name type: (_) @param.type) @param)
(parameters (typed_parameter (list_splat_pattern (identifier) @param.name) type: (_) @param.type) @param)
(parameters (typed_parameter (dictionary_splat_pattern (identifier) @param.name) type: (_) @param.type) @param)
(parameters (typed_default_parameter name: (identifier) @param.name type: (_) @param.type) @param)
(parameters (list_splat_pattern (identifier) @param.name) @param)
(parameters (dictionary_splat_pattern (identifier) @param.name) @param)

(function_definition return_type: (_) @ret) @decl
(assignment type: (_) @ftype) @decl
(decorated_definition (decorator) @decorator) @decl
(class_definition superclasses: (argument_list [(identifier) (attribute) (subscript) (call)] @supertype (#not-eq? @supertype "object"))) @decl
