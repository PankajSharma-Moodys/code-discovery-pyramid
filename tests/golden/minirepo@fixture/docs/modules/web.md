# `web`

4 tracked files, 49 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/web`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `core` (2 refs)

**Imported by:** nothing in this repository

## Entry points

- WebApplication declares a process entry point in web; it is one of the repository's separately-startable units. — `web/src/main/java/com/example/mini/web/WebApplication.java:5`
- GET /v1/widgets is served by WidgetResource#list in web (declared via the constant ${ApiPaths.WIDGETS}). — `web/src/main/java/com/example/mini/web/ApiPaths.java:5` `web/src/main/java/com/example/mini/web/WidgetResource.java:19`
- GET /v1/widgets/{id} is served by WidgetResource#get in web (declared via the constant ${ApiPaths.WIDGETS}/{id}). — `web/src/main/java/com/example/mini/web/ApiPaths.java:5` `web/src/main/java/com/example/mini/web/WidgetResource.java:24`

## Dependencies (stated)

- web imports core at 2 distinct sites. — `web/src/main/java/com/example/mini/web/WidgetResource.java:3` `web/src/main/java/com/example/mini/web/WidgetResource.java:4`

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ApiPaths` | class | 0 | `web/src/main/java/com/example/mini/web/ApiPaths.java:3` |
| `WebApplication` | class | 0 | `web/src/main/java/com/example/mini/web/WebApplication.java:3` |
| `WidgetResource` | class | 0 | `web/src/main/java/com/example/mini/web/WidgetResource.java:11` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/web` | 4 | 49 | structural only |
