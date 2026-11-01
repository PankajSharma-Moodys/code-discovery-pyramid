; Rules for Java declarations. Same capture vocabulary as typescript.scm; roles in emit_map.json (lang_overrides.java)
(class_declaration name: (identifier) @name) @definition.class
(interface_declaration name: (identifier) @name) @definition.interface
(enum_declaration name: (identifier) @name) @definition.enum
(record_declaration name: (identifier) @name) @definition.record
(annotation_type_declaration name: (identifier) @name) @definition.annotation
(method_declaration name: (identifier) @name) @definition.method
(annotation_type_element_declaration name: (identifier) @name) @definition.method
(constructor_declaration name: (identifier) @name) @definition.ctor
(compact_constructor_declaration name: (identifier) @name) @definition.ctor
(field_declaration declarator: (variable_declarator name: (identifier) @name) @definition.field)
(constant_declaration declarator: (variable_declarator name: (identifier) @name value: (_)) @definition.constant)
(field_declaration (modifiers "static" "final") declarator: (variable_declarator name: (identifier) @name value: (_)) @definition.constant)
(field_declaration (modifiers "final" "static") declarator: (variable_declarator name: (identifier) @name value: (_)) @definition.constant)
(enum_constant name: (identifier) @name) @definition.enumconst
(record_declaration parameters: (formal_parameters (formal_parameter name: (identifier) @name) @definition.component))

(formal_parameter type: (_) @param.type name: (_) @param.name) @param
(spread_parameter [(type_identifier) (generic_type) (integral_type) (floating_point_type) (boolean_type) (array_type) (scoped_type_identifier)] @param.type (variable_declarator name: (_) @param.name)) @param
(method_declaration type: (_) @ret) @decl
(annotation_type_element_declaration type: (_) @ret) @decl
(field_declaration type: (_) @ftype) @decl
(constant_declaration type: (_) @ftype) @decl
(formal_parameter type: (_) @ftype) @decl
(_ (modifiers ["public" "protected" "private"] @vis)) @decl
(_ (modifiers [(annotation) (marker_annotation)] @decorator)) @decl
(class_declaration (superclass (_) @supertype)) @decl
(_ interfaces: (super_interfaces (type_list (_) @supertype))) @decl
(interface_declaration (extends_interfaces (type_list (_) @supertype))) @decl
