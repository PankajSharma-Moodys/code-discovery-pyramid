; Rules for TypeScript/TSX. Definitions use @definition.* + @name; everything else is an
; auxiliary capture grouped by the node it describes (@decl / @param). Roles: emit_map.json
(class_declaration name: (type_identifier) @name) @definition.class
(abstract_class_declaration name: (type_identifier) @name) @definition.class
(interface_declaration name: (type_identifier) @name) @definition.interface
(enum_declaration name: (identifier) @name) @definition.enum
(type_alias_declaration name: (type_identifier) @name) @definition.type
(function_declaration name: (identifier) @name) @definition.function
(generator_function_declaration name: (identifier) @name) @definition.function
(function_signature name: (identifier) @name) @definition.function
(method_definition name: (_) @name) @definition.method
(method_signature name: (_) @name) @definition.method
(abstract_method_signature name: (_) @name) @definition.method
(public_field_definition name: (_) @name value: (_)? @init) @definition.field
(property_signature name: (_) @name) @definition.field
(variable_declarator name: (identifier) @name value: (_)? @init) @definition.var

(required_parameter pattern: (_) @param.name type: (type_annotation (_) @param.type)?) @param
(optional_parameter pattern: (_) @param.name type: (type_annotation (_) @param.type)?) @param
(_ return_type: (type_annotation (_) @ret)) @decl
(_ return_type: (type_predicate_annotation (_) @ret)) @decl
(_ type: (type_annotation (_) @ftype)) @decl
(_ (accessibility_modifier) @vis) @decl
(_ decorator: (decorator) @decorator) @decl
(_ (class_heritage (extends_clause value: (_) @supertype))) @decl
(_ (class_heritage (implements_clause (_) @supertype))) @decl
(interface_declaration (extends_type_clause type: (_) @supertype)) @decl
(lexical_declaration "const" (variable_declarator value: (string (string_fragment) @const.value)) @decl)
