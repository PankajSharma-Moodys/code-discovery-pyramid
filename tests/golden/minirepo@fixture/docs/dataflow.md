# Data flow

How data travels through this application — the question the module dependency graph cannot answer. The topology below was walked by deterministic Python over typed channel edges; every hop carries the anchor of the edge it came from, so a hop with no evidence has nowhere to hide.

> **Coverage: 23.1%** — 3 of 13 tracked files are in scopes that completed. Everything absent from this document may be absent because it was never examined. Incomplete scopes: `root/core`, `root/web`.

## What is not traced

- **Runtime dependency injection.** The object graph the application assembles at startup is decided from types, not imports. What is reported here is the *declared* wiring; the runtime graph is a superset CDP cannot see.
- **Dynamic dispatch.** A call through an interface produces an edge to the interface. Implementations are candidates, not hops.
- **Reflection and string-keyed lookup.** Detected as a risk marker on the containing symbol, never traced through.
- **What the data means.** CDP maps where data goes, not what it is. It will not tell you whether `capacity_percent` is a fraction or a percentage.
