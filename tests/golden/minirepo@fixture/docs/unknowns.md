# Unknowns — the tribal-knowledge inventory

Every question this run could not answer, with the anchor that raised it. This is the list to take to the incumbent team before they leave. A gap here is *output*, not failure: the alternative is a document that asserts a plausible answer, and a reader who cannot tell the difference.

> **Coverage: 23.1%** — 3 of 13 tracked files are in scopes that completed. Everything absent from this document may be absent because it was never examined. Incomplete scopes: `root/core`, `root/web`.

_No unknowns recorded. If no leaf agent has run yet, that means nothing was asked, not that nothing is unknown._

## Public types with no static reference

No static reference found. Framework-managed entry points are excluded: dependency-injection annotations, HTTP resource registration, scheduled jobs, repositories, entities and generated mappers. These are candidates for review, not dead code (§6.6).

1 candidate(s). These are **not** dead code; any of dependency injection, HTTP resource registration, job discovery or generated implementations makes a naive dead-code claim wrong.

- `com.example.mini.web.ApiPaths` `web/src/main/java/com/example/mini/web/ApiPaths.java:3`
