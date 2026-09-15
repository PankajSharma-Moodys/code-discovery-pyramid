# tree — architecture overview

Reconstructed by CDP at commit `<HEAD>`. Every claim below carries a `file:line` citation that a Python verifier confirmed against the file.

> **Coverage: 23.1%** — 3 of 13 tracked files are in scopes that completed. Everything absent from this document may be absent because it was never examined. Incomplete scopes: `root/core`, `root/web`.

## Census

| | |
|---|---|
| Tracked files | 13 |
| Files on disk | 14 (**1.1x**) |
| Inventory source | `git` |
| Modules | 2 |
| Symbols declared | 18 |
| HTTP routes | 2 |

## Naming

The facts that cost a newcomer an afternoon and appear in no artifact.

- The build's root project is named 'mini-svc', which appears in no directory name; every module directory is '?...'. Build logs, metrics and the OpenAPI title use 'mini-svc'. — `settings.gradle:1`
- 1 source files declare a package whose text and directory path differ only in case (e.g. directory 'COM/Example/mini/core' declares 'package com.example.mini.core'). Any path-to-package inference produces names that match nothing; on a case-insensitive filesystem this is invisible. — `core/src/main/java/COM/Example/mini/core/Widget.java:6`

## Deployable units

- (root) is packaged as its own container image; its entry command is ["java", "-jar", "/app/web.jar"]. — `Dockerfile:4`
- WebApplication declares a process entry point in web; it is one of the repository's separately-startable units. — `web/src/main/java/com/example/mini/web/WebApplication.java:5`
- root declares a process entry point in (root); it is one of the repository's separately-startable units. — `Dockerfile:4`

## Module dependency graph

Built twice — from build manifests (**declared**) and from import statements (**observed**) — because the divergence between them is a finding, not an error to reconcile.

| Source | Inter-module edges |
|---|---|
| Declared (build manifests) | 1 |
| Observed (imports) | 1 |

Observed dependency levels (each depends only on those above it):

```
L0  (root), core
L1  web
```

Declared and observed graphs agree exactly. That is a good sign about this build's hygiene and an unusual one.

## Modules

| Module | Files | LOC | Depends on | Depended on by |
|---|---|---|---|---|
| [`core`](modules/core.md) | 6 | 67 | — | web |
| [`web`](modules/web.md) | 4 | 49 | core | — |

## HTTP surface

| Verb | Route | Handler | Declared as | Evidence |
|---|---|---|---|---|
| `GET` | `/v1/widgets` | `WidgetResource#list` | `${ApiPaths.WIDGETS}` | `web/src/main/java/com/example/mini/web/WidgetResource.java:19` `web/src/main/java/com/example/mini/web/ApiPaths.java:5` |
| `GET` | `/v1/widgets/{id}` | `WidgetResource#get` | `${ApiPaths.WIDGETS}/{id}` | `web/src/main/java/com/example/mini/web/WidgetResource.java:24` `web/src/main/java/com/example/mini/web/ApiPaths.java:5` |

## Where to go next

- [`unknowns.md`](unknowns.md) — what this run could not establish. Read it before trusting anything above.
- [`dataflow.md`](dataflow.md) — how a record actually travels, including edges no import expresses.
- `cdp query` — the same state, queryable. `query symbol DServer`, `query table server`, `query routes`, `query paths --to table:server`.
