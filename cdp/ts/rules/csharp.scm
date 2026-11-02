; Rules for C# declarations (tree-sitter-c-sharp 0.23.5). Capture vocabulary as java.scm; roles in emit_map.json (lang_overrides.c_sharp)
(class_declaration name: (identifier) @name) @definition.class
(struct_declaration name: (identifier) @name) @definition.struct
(interface_declaration name: (identifier) @name) @definition.interface
(enum_declaration name: (identifier) @name) @definition.enum
(record_declaration name: (identifier) @name) @definition.record
(method_declaration name: (identifier) @name) @definition.method
(constructor_declaration name: (identifier) @name) @definition.ctor
(property_declaration name: (identifier) @name) @definition.field
(enum_member_declaration name: (identifier) @name) @definition.enumconst
(field_declaration (variable_declaration (variable_declarator name: (identifier) @name) @definition.field))
(field_declaration (modifier "const") (variable_declaration (variable_declarator name: (identifier) @name "=" (_)) @definition.constant))
(field_declaration (modifier "static") (modifier "readonly") (variable_declaration (variable_declarator name: (identifier) @name "=" (_)) @definition.constant))
(field_declaration (modifier "readonly") (modifier "static") (variable_declaration (variable_declarator name: (identifier) @name "=" (_)) @definition.constant))

(parameter type: (_) @param.type name: (identifier) @param.name) @param
(method_declaration returns: (_) @ret) @decl
(property_declaration type: (_) @ftype) @decl
(field_declaration (variable_declaration type: (_) @ftype)) @decl
(_ (modifier ["public" "protected" "private" "internal"] @vis)) @decl
(_ (attribute_list (attribute) @decorator)) @decl
(_ (base_list (_) @supertype)) @decl
(variable_declarator "=" . (_) @const.value) @decl
