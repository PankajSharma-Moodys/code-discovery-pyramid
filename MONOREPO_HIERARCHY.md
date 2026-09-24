# MONOREPO_HIERARCHY — why the mesh happens, and a path-based fix

Budget: ~150 lines. Design only — no code in this pass.

## 0. Verdict

The mesh isn't a layout bug (that's `ATLAS_REDESIGN.md`'s problem, already fixed). It's a
**missing grouping level**: everything the scanner finds under one repo root is flattened
into a single altitude ladder (`AltitudeSwitcher.tsx:14` — only `L3` "Packages" and `L2`
"Modules"), so a monorepo with N submodules × M packages each renders as one N·M-node graph
with no boundary between submodules. Adding rungs above L3 that mirror the directory tree —
without requiring any manifest — is a directory-prefix clustering pass, not a new data source.

## 1. Evidence

- `graphLayout.ts:buildGraph` takes one flat `RawGraph` and lays it out with no notion of a
  parent group; every node is a peer of every other node in FA2/dagre.
- `nodeId.ts:17` altitudes are hardcoded to exactly `L3/L2/L1`, one rung per *type* of rollup,
  not per *directory depth*. There is no rung for "this subtree vs. that subtree."
- `RepoPicker.tsx` treats each `cdp`-scanned repo as an independent, mutually exclusive
  selection (a flat dropdown over `GET /api/repos`) — confirmed by reading the whole
  component. Nothing nests one scanned tree inside another.
- Repo-wide grep for `submodule|workspace|monorepo` (`web/api/*.py`, `web/frontend/src`)
  returns zero hits about *boundary detection* — `Workspace` in this codebase means "the cdp
  scan for one repo," an unrelated sense of the word. Confirmed empirically, not assumed.
- You confirmed the boundaries in your monorepo aren't reliably manifest-declared (no
  guaranteed `.gitmodules`/workspace file) — plain folder structure, so the fix has to work
  from paths alone.

## 2. Design: cluster by directory prefix, not by declared structure

Every node the scanner already emits carries (or can carry) the file path it came from. Build
the hierarchy from that path alone:

1. **Group nodes by path prefix, one directory segment at a time**, starting from the repo
   root. `projects/checkout/payments-svc/src/order.py` groups first under `projects/`, then
   `projects/checkout/`, then `projects/checkout/payments-svc/`, and only *inside* that does
   the existing L3 package rollup take over.
2. **Collapse pass-through segments.** If a directory has exactly one child directory and no
   files of its own (a common `src/` or a lone-submodule wrapper folder), skip it as a rung —
   it adds a click with no decision behind it. This is why the ladder isn't hardcoded to
   exactly 3 layers: a shallow monorepo gets 1 extra rung, a deeply nested one gets 4 or 5,
   each real fork in the tree gets exactly one rung.
3. **Stop clustering once a subtree is small enough to read.** Reuse the existing size
   discipline instead of inventing a new one: if a directory's descendant package/module count
   is under the range `AltitudeSwitcher` already renders comfortably (L2 tops out at 353 nodes
   today per `graphEncoding.ts:191`), stop descending and hand it straight to L3/L2 as today.
   A monorepo with one giant submodule and nine tiny ones shouldn't force nine pointless clicks.
4. This is a pure function of the path strings the scanner already has — no `.gitmodules`, no
   workspace manifest, no per-ecosystem special-casing. It degrades gracefully: a repo with no
   real substructure collapses to today's exact two rungs (rule 2 removes every prefix rung).

## 3. The actual mesh fix: roll up cross-boundary edges, don't hide them

Grouping alone doesn't fix the mesh if every underlying edge still gets drawn between the new
group nodes — that's still N·M edges, just relabeled. At each rung, **replace all edges between
two groups with one aggregated edge**, sized/labeled by count (the existing `edgeWidth`/`count`
channel in `graphEncoding.ts:141-161` already encodes exactly this kind of magnitude — reuse
it, don't add a second visual language). Drilling into a group re-expands its internal edges
and its *external* edges to sibling groups collapse back down to single aggregates pointing at
the sibling's box. This is the same "inside X / ✕" scope model `AltitudeSwitcher.tsx:56-69`
already has for one level — it needs to become a breadcrumb *stack*, not a single scope, so you
can walk back up more than one level without returning to the unfiltered root.

## 4. Where each piece lives

- **Server** (new): the directory-prefix clustering pass (§2) and the edge-rollup aggregation
  (§3) belong next to the existing L3 rollup computation — same reasoning path (`web/api`),
  not the client. The client should not reimplement grouping logic the server already owns for
  L3; it should receive already-grouped nodes/edges for whatever rung is active, exactly like
  today's `/api/graph?level=`.
- **Client**: `AltitudeSwitcher` grows from a fixed 2-button ladder to a dynamic breadcrumb
  whose rung count matches what the server computed for *this* repo (rule 2 means this varies
  per monorepo, so the ladder can't stay a static array like `ALTITUDES` today). `RepoPicker`
  stops being a flat mutually-exclusive list once one "repo" *is* the monorepo root — the
  top-most rung of the new ladder replaces what the picker currently does for that case,
  though multiple genuinely separate `cdp` scans (unrelated repos) still need the picker's
  current flat behavior. Those are two different pickers doing different jobs today merged
  into one; worth flagging explicitly rather than quietly conflating them.

## 5. Stress test (adversarial cases against this design)

- **Asymmetric depth**: one submodule 6 folders deep, another flat. Rule 2/3 handle this
  per-subtree already — no global "always N layers" assumption to break.
- **A file at the boundary itself** (e.g. a root-level `shared_utils.py` alongside
  `projects/`). It has no submodule prefix — it must attach to the *root* group as a direct
  member, not get silently dropped because it doesn't fit the tree cleanly.
  Grouping-by-prefix naturally puts it one level up from any subfolder; needs to be checked
  against real output, not assumed correct.
- **Cross-cutting edges that dominate a rung**: if two projects share so many edges that the
  rolled-up edge is nearly as visually dense as the mesh it replaced (e.g. a shared internal
  library imported by everything), a single fat edge per pair is honest but the *edge* itself
  can become the new mesh at the project layer specifically. Confidence/count-based width
  already differentiates magnitude — this likely holds, but is the one part of §3 to check
  against your repo's real fan-out numbers before trusting it, not a repo this scanner's own
  fixtures can validate (this codebase itself has no deep submodule nesting to test against).

## 6. Phasing

1. Server: path-prefix clustering + per-rung edge rollup, exposed as `/api/graph?level=` rungs
   the client can enumerate (count + names), not hardcoded ids.
2. Client: breadcrumb-stack ladder replacing the fixed `ALTITUDES` array; existing L3/L2
   behavior becomes the bottom two rungs, unchanged.
3. Split `RepoPicker`'s "switch to an unrelated scanned repo" job from "go to the monorepo
   root," once real usage shows whether that distinction matters in practice.
