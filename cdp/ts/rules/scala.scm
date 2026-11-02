; Rules for Scala declarations. Same capture vocabulary as java.scm; roles in emit_map.json (lang_overrides.scala)
(class_definition name: (identifier) @name) @definition.class
(trait_definition name: (identifier) @name) @definition.trait
(object_definition name: (identifier) @name) @definition.object
(enum_definition name: (identifier) @name) @definition.enum
((function_definition name: (identifier) @name) @definition.ctor (#eq? @name "this"))
((function_definition name: (identifier) @name) @definition.method (#not-eq? @name "this"))
(function_declaration name: (identifier) @name) @definition.method
(val_definition pattern: (identifier) @name) @definition.field
(var_definition pattern: (identifier) @name) @definition.field
(val_declaration (identifier) @name) @definition.field
(var_declaration (identifier) @name) @definition.field
(class_parameter name: (identifier) @name) @definition.cparam
(class_parameter ["val" "var"] name: (identifier) @name) @definition.cparamval

(parameter name: (identifier) @param.name type: (_) @param.type) @param
(function_definition return_type: (_) @ret) @decl
(function_declaration return_type: (_) @ret) @decl
(val_definition type: (_) @ftype) @decl
(var_definition type: (_) @ftype) @decl
(val_declaration type: (_) @ftype) @decl
(var_declaration type: (_) @ftype) @decl
(class_parameter type: (_) @ftype) @decl
(_ (modifiers (access_modifier) @vis)) @decl
(_ (annotation) @decorator) @decl
(_ extend: (extends_clause [(type_identifier) (generic_type) (stable_type_identifier) (projected_type) (annotated_type) (infix_type) (compound_type) (singleton_type)] @supertype)) @decl
(class_definition "case" class_parameters: (class_parameters (class_parameter name: (identifier) @name) @definition.cparamval))
