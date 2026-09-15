# `core`

6 tracked files, 67 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/core`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** `web` (2 refs)

## Data models

- WidgetRepository reads and writes WidgetEntity; no table name is stated in source, so the binding is left to the persistence framework's default. — `core/src/main/java/COM/Example/mini/core/WidgetRepository.java:7`
- Table 'widget' is written from WidgetEntity in core. — `core/src/main/java/COM/Example/mini/core/WidgetEntity.java:8`

## Side effects

- core reads from the database, across 1 site(s). — `core/src/main/java/COM/Example/mini/core/WidgetRepository.java:7`

## Ownership

- The schema for 'widget' is owned by core, defined across 1 migration(s). — `core/src/main/resources/db/V001__create_widget.sql:1`

## Naming

- 1 source files declare a package whose text and directory path differ only in case (e.g. directory 'COM/Example/mini/core' declares 'package com.example.mini.core'). Any path-to-package inference produces names that match nothing; on a case-insensitive filesystem this is invisible. — `core/src/main/java/COM/Example/mini/core/Widget.java:6`

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `Widget` | class | 1 | `core/src/main/java/COM/Example/mini/core/Widget.java:6` |
| `Widget` | class | 1 | `core/src/test/java/com/example/mini/core/Widget.java:4` |
| `WidgetRepository` | interface | 1 | `core/src/main/java/COM/Example/mini/core/WidgetRepository.java:7` |
| `WidgetEntity` | class | 0 | `core/src/main/java/COM/Example/mini/core/WidgetEntity.java:10` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/core` | 6 | 67 | structural only |
