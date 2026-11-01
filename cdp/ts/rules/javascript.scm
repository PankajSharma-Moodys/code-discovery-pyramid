; Rules for JavaScript/JSX (no types). Same conventions as typescript.scm.
(class_declaration name: (identifier) @name) @definition.class
(function_declaration name: (identifier) @name) @definition.function
(generator_function_declaration name: (identifier) @name) @definition.function
(method_definition name: (_) @name) @definition.method
(field_definition property: (_) @name value: (_)? @init) @definition.field
(variable_declarator name: (identifier) @name value: (_)? @init) @definition.var

(formal_parameters (identifier) @param.name @param)
(formal_parameters (assignment_pattern left: (_) @param.name) @param)
(formal_parameters (rest_pattern) @param.name @param)
(formal_parameters (object_pattern) @param.name @param)
(formal_parameters (array_pattern) @param.name @param)
(arrow_function parameter: (identifier) @param.name @param)
(_ decorator: (decorator) @decorator) @decl
(_ (class_heritage (_) @supertype)) @decl
(lexical_declaration "const" (variable_declarator value: (string (string_fragment) @const.value)) @decl)
