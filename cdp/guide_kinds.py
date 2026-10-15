"""The query-kind guide: ONE source for what each `query` kind answers.

Every surface is generated from this table -- the MCP `cdp_query` schema, `SKILL.md`,
`cdp help`, `docs/CDP_REFERENCE.md` (see `guide.py`) -- and `query.dispatch` uses
`APPLIES` to reject parameters a kind ignores. Each kind has the three parts a
caller needs: **What** (answers / does not index / how to read it), **How**
(parameters, worked examples), **Where** (which question, what next).
`tests/test_guide.py` fails if any part is missing or a surface drifts.

Placeholders like `<symbol>` in examples are bound to a fixture by the tests that
run every example.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

ROLES = ("test", "build", "ci", "config", "docs", "asset", "schema", "source")
CLAIM_KINDS = ("entrypoint", "public_api", "data_model", "config", "side_effect",
               "test_behaviour", "ownership", "visibility", "deployable", "naming",
               "dependency")
DEFAULT_BUDGET = 200
DEFAULT_MAX_HOPS = 8
VIEWS = ("count", "list", "compact", "detail")
FORMATS = ("text", "json")
MATCHES = ("substring", "exact", "regex")

#: MCP parameter -> (CLI flag, one-line meaning). `term` is per kind (`KINDS[k]["term"]`).
PARAMS: Dict[str, Tuple[str, str]] = {
    "term": ("<term>", "the name this kind looks up (see each kind)"),
    "budget": ("--budget", "row cap, none by default; 0 = no rows"),
    "exclude_role": ("--exclude-role", "drop rows whose file has these roles (%s)"
                                       % ", ".join(ROLES)),
    "include_tests": ("--include-tests", "keep test-role files (dropped by default)"),
    "include_library": ("--include-library", "`claims`: keep third-party `library:` subjects (dropped by default)"),
    "claim_kind": ("--kind", "`claims`: only claims of this kind"),
    "module": ("--module", "`claims`: only claims whose module contains this text"),
    "subject": ("--subject", "`claims`: only claims whose subject contains this text"),
    "frm": ("--from", "`paths`: paths through any node containing this text (with `to`, it must come first)"),
    "to": ("--to", "`paths`: paths through any node containing this text (with `frm`, it must come after)"),
    "exact": ("--exact", "`match=exact`"),
    "match": ("--match", "`substring` (default), `exact` or `regex` (case-sensitive; `search` greps source)"),
    "view": ("--view", "`count`, `list` (name + file:line), `compact` (all facts) or `detail` (full); "
                       "default list if broad, else compact"),
    "format": ("--format", "`text` (default for count/list) or `json`"),
    "offset": ("--offset", "skip N rows (see `next`)"),
    "filter": ("--filter", "wide `list`/`count`: rows whose line matches a Python `re` regex, pre-cap"),
    "max_tokens": ("--max-tokens", "token cap (default 3000; 0 none)"),
    "max_hops": ("--max-hops", "`trace`: how many edges to walk (default %d)" % DEFAULT_MAX_HOPS),
    "as_of": ("--as-of", "replay the claim log up to this commit (sha); "
                         "structure stays current"),
}

#: Parameters every kind accepts.
ALWAYS = ("as_of",)

_B = ("budget", "exclude_role", "include_tests")

KINDS: Dict[str, Dict] = {
    "trace": {
        "summary": "reading list for an entry point: every file on its call chain, cited",
        "what": "The minimal cited file set needed to understand an entry point: the "
                "files its call/persist/publish edges reach (including the `@Subscribe` handlers of an "
                "EventBus event it posts), each with the edge that put it there.",
        "not": "Not logic: no parameters or branches. DI/reflection wiring leaves no edge, so a "
               "short trail is not proof of 'calls nothing'. Edges tagged `medium` come from "
               "imports or interface/override fan-out (can reach, not does). A class term (`TenantController`) is not one "
               "entry point: each public member is walked and the list is capped at 40 files (round-robin, nearest "
               "first; the cap and the unlisted count are stated, and `--budget` does not lift it) - trace a "
               "member or a route for a whole chain.",
        "read": "`resolved_as` says what the term matched (route, source or symbol); `files` are "
                "the reading list in walk order; `hops_exhausted` true means raise --max-hops; "
                "`elided: 0` means the list is complete. A route path shared by several verbs is traced "
                "for every verb (`verbs`; a file only some verbs reach is tagged `(POST only)`). "
                "The entry point (`resolved_as`) and each hop row that cites one definition (`defines X`) carry "
                "that symbol's annotations (verbatim text + `file:line`), annotated parameters and owner-class "
                "annotations; a hop with no single cited symbol shows none.",
        "term": "REQUIRED. A route path (`/orders`; all its verbs) or `VERB /path` (`POST /orders`; one), a dataflow source, "
                "a class (`OrderResource`: its public members) or a member (`OrderResource#place`); "
                "substring, first match wins in that order.",
        "uses": ("term",) + _B + ("max_hops",),
        "required": ("term",),
        "examples": ["query trace <route>", "query trace <method> --max-hops 4 --exclude-role test"],
        "where": "Start here for 'how does X work / what do I read / what breaks if I change X'.",
        "next": "Read only the cited line ranges; `symbol` on a hop for its callers; "
                "`table`/`config` for what the chain persists or reads.",
    },
    "symbol": {
        "summary": "definition site(s) and every use of a class/method (callers)",
        "what": "Where a class, method or constant is defined (with line extent) and every "
                "site that uses it: the transpose of the resolved import and call tables.",
        "not": "Not dynamic dispatch, reflection or DI wiring. `used_by` of an interface "
               "lists its implementers' callers only where the call resolves. A class's "
               "`used_by` includes its `new X(..)` sites (an implicit default constructor "
               "counts as the class). Java: a call on a type variable resolves through its "
               "declared bound(s) only; an inferred generic method result (`<T> T pick()`) stays untyped. "
               "C#: `x.M()`, `new X(..)`, `new(..)`, `: base(..)`, method groups and extension methods resolve through "
               "declared types, `var`, `await`, collections/LINQ and explicit `M<T>()` arguments; a lambda parameter is "
               "typed only for LINQ-style stages and Moq `Setup`/`Verify`; overloads share one symbol and are told apart "
               "only by argument count (an interface method can win over an extension of the same name), and a "
               "NuGet-typed receiver leaves no edge. "
               "Python: calls, references, decorators and `from x import f` resolve for `f()`, `self.m()`, `mod.f()`, "
               "`Class(..)` (to `__init__`), and `obj.m()` only when `obj`'s class is known (`self`, annotation, "
               "`x = Class()`, a callee's annotated/inferred return, isinstance); an untyped parameter's calls, "
               "`getattr`, dispatch through a list of modules and decorator-built wrappers are not found.",
        "read": "`defined_range` is `file:start-end` (read exactly that); `used_by_count` is the "
                "true total even when the list is budgeted (several matches split the budget evenly, "
                "and a cut one gives `see_all`, the exact command for every use); `collision` true means "
                "several definitions share the name. "
                "Each definition also shows its annotations (verbatim text + `file:line`), annotated parameters "
                "and the owner class's annotations (Java). "
                "A method's `body` row (one per overload) lists the members it `calls`, the exceptions it declares "
                "(`throws`, Java) and its string-literal count (`literals`, from the code text).",
        "term": "REQUIRED. Fully-qualified name, a suffix (`OrderService`), or `Class#method`; "
                "case-insensitive substring (exact last-name matches first) unless `exact`; "
                "`Class#method` is always exact.",
        "uses": ("term",) + _B + ("exact",),
        "required": ("term",),
        "examples": ["query symbol <symbol>", "query symbol <method> --exclude-role test"],
        "where": "'Where is X defined / who calls X / who uses X'. Prefer over grep.",
        "next": "`trace` from a caller or `file` for the defining file's outline.",
    },
    "file": {
        "summary": "what one file defines and touches (outline)",
        "what": "One file's module, language, role, LOC, every definition with line extent, "
                "and its I/O edges (tables, config, HTTP, events).",
        "not": "Not file contents. Use it to pick the line range to Read.",
        "read": "`defines` is the outline with `line`..`end_line`; `io_edges` are what the file "
                "reads/writes/calls out to. "
                "Each definition lists its annotations (verbatim text + `file:line`), annotated parameters and "
                "the owner class's annotations (Java). "
                "Each method also gives the members it `calls`, the exceptions it declares (`throws`, Java) and "
                "its string-literal count (`literals`); one line per method.",
        "term": "REQUIRED. A repo-relative path or any substring of one (`exact`: the path or a trailing `dir/file`); an absolute path "
                "inside another scanned repo is routed to that repo's store.",
        "uses": ("term",) + _B + ("exact",),
        "required": ("term",),
        "examples": ["query file <file>"],
        "where": "'What does this file do / what is in it' -- before opening it.",
        "next": "Read the cited ranges; `symbol` on a definition for its users.",
    },
    "module": {
        "summary": "one build module: size, dependencies, dependents, claims",
        "what": "A build module's files, LOC, languages, roles, what it depends on and who "
                "depends on it (observed vs declared), its scopes and claim tally.",
        "not": "Not per-file detail (use `file`). `exclude_role` does not apply.",
        "read": "`declared_only` = in the build file but never imported; `observed_only` = "
                "imported but undeclared.",
        "term": "REQUIRED. Module name or substring.",
        "uses": ("term", "budget"),
        "required": ("term",),
        "examples": ["query module <module>"],
        "where": "'What does module M do / depend on / who depends on it'.",
        "next": "`file` for one of its files; `stats` for the module list.",
    },
    "routes": {
        "summary": "the HTTP surface: verb, path, handler, citation",
        "what": "Every HTTP route with verb, path (constants resolved; a Dropwizard module's "
                "`server.applicationContextPath` prefixed), handler and the annotation/constant "
                "sites that declare it.",
        "not": "Not outbound HTTP calls; not routes built at runtime. Unresolved constants "
               "are listed, not guessed.",
        "read": "`declared_via` shows the constant expression; `unresolved_constants` non-empty "
                "means the path is partial. "
                "Each route also shows its handler's annotations (verbatim text + `file:line`), annotated "
                "parameters and owner-class annotations, a few lines per route (`--json` has all). "
                "`inputs` lists what the handler reads from the request (`@PathVariable`, `@RequestParam`, "
                "`@RequestHeader`, `@RequestBody`, JAX-RS `*Param`): kind, name, type, `required`/`default` "
                "when the annotation states them.",
        "term": "OPTIONAL. Substring of the route path, the verb, `VERB /path` or the handler class/method "
                "(`/orders`, `POST`, `OrderResource`; each row's `matched_via` says which); `exact` "
                "matches the whole name; omit for all.",
        "uses": ("term",) + _B + ("exact",),
        "required": (),
        "examples": ["query routes", "query routes <route>"],
        "where": "'What endpoints exist / which handler serves /x'.",
        "next": "`trace <route>` for everything the endpoint reaches.",
    },
    "table": {
        "summary": "who owns (migration), writes and reads a database table",
        "what": "Per table: owning module and migration DDL, writers, readers, each with a "
                "citation. The union is 'what breaks if I change this table'.",
        "not": "Only tables seen in migrations, persistence/read code and SQL in annotations; not SQL "
               "built in method bodies or constants (`search` finds those).",
        "read": "`migrations` = schema owner; `writers`/`readers` group the sites by who touches the table "
                "(SQL scripts are one group: site and file counts, a few `file:line`); `entity_users` are "
                "the uses of the entity class outside the DbContext and migrations (reads and writes not told "
                "apart); `evidence` is the cited sites. SQL in annotations (Spring Data `@Query`, `@NamedQuery`, "
                "JDBI `@SqlQuery`/`@SqlUpdate`, MyBatis `@Select`/`@Insert`/`@Update`/`@Delete`) makes the "
                "annotated method a writer (INSERT/UPDATE/DELETE/MERGE) or reader (SELECT/JOIN); JPQL "
                "reaches the table through its entity's `@Table(name=..)`. "
                "Each code writer/reader group shows its annotations (verbatim text + `file:line`), annotated "
                "parameters and owner-class annotations (e.g. `@Table(name=..)`); script groups show none.",
        "term": "OPTIONAL. Substring of the table name (`order` also matches `orders`) unless `exact`; omit for all.",
        "uses": ("term",) + _B + ("exact",),
        "required": (),
        "examples": ["query table", "query table <table>"],
        "where": "'Who writes/reads table T', 'which tables does X touch' (with `trace`).",
        "next": "`symbol` on a writer; `trace` from the route that reaches it.",
    },
    "config": {
        "summary": "config keys and env vars: where declared, every site that reads them",
        "what": "Each config key / env var with its declarations, values and read sites (config "
                "files, Docker `ENV`, `${VAR:-default}` placeholders, Python (`os.environ[..]`/`.get`, `os.getenv`, `environ`/`getenv` imports, keys held in constants, `django.conf.settings.X`, pydantic `BaseSettings` fields)/JS/Go env reads, Java "
                "`System.getenv`/`getProperty`/`Long.getLong`/`getenv().getOrDefault`, `@Value`; C# `IConfiguration` indexer/`GetValue`/`GetSection`/`GetConnectionString`, `Environment.GetEnvironmentVariable`, `appsettings*.json` keys as `A:B`).",
        "not": "Not values set outside the repo (deploy-time env). A key built at run time is listed "
               "under `(dynamic)`, not by name. Java reads through a provider (`configProvider.getValue(KEY)`, "
               "`env.getProperty(\"k\")`) and calls to wrapper methods that pass a literal/constant key on "
               "to `System.getenv`/a provider are found; a provider whose type and names never mention "
               "config/properties/env, or a wrapper reached only through an interface, is not.",
        "read": "`declared` vs `read` sites; `values` are the literal defaults seen. Keys are ranked "
                "by read sites; `read_count` is the true total, `keys_elided`/`sites_elided` count what "
                "the budget cut (raise `budget` or pass a term to see every site). "
                "Each read site shows its reader's annotations (verbatim text + `file:line`), annotated "
                "parameters and owner-class annotations.",
        "term": "OPTIONAL. Substring of the key name (`MINI_DB`, `billing.url`; `exact`: whole key); omit for all keys "
                "(most-read first, a few citations each; pass a term to see every site).",
        "uses": ("term",) + _B + ("exact",),
        "required": (),
        "examples": ["query config <config-key>"],
        "where": "'Where is setting K read / what does the service read from env'.",
        "next": "`symbol` on a reader; `file` for the declaring file.",
    },
    "paths": {
        "summary": "traced dataflow paths from a source to a sink (A -> B)",
        "what": "End-to-end paths (trigger, hops with channel and citation) between a source "
                "and a sink, e.g. route -> service -> repository -> table.",
        "not": "Only paths the dataflow graph closed; 0 paths does not mean unconnected. "
               "Nodes are classes, so `Class#method` matches the class.",
        "read": "`hops` in order, each `--channel--> node  file:line`; `confidence` is the "
                "weakest hop.",
        "term": "NOT USED: pass `frm`/`to` (CLI `--from`/`--to`).",
        "uses": ("frm", "to", "budget"),
        "required": (),
        "examples": ["query paths --from <route>", "query paths --from <route> --to <table>"],
        "where": "'How does data get from A to B' -- when A and B are an entry point and a sink.",
        "next": "`trace` when 0 paths (walks edges without needing a closed path).",
    },
    "search": {
        "summary": "free-text fallback across claims, symbols, constants, unknowns and files",
        "what": "Substring search over claim subjects/statements, symbol names, constant "
                "values, unknown questions, file paths and the source text of source-role files (code search), ranked by closeness.",
        "not": "Not tests, config, docs, binary, over-size or generated files' text, and no match across two lines; "
               "an empty answer says what was and was not searched.",
        "read": "`counts` are true totals; each list is budget-split fairly. "
                "An `annotations` bucket matches annotation name, fqn, verbatim text and argument values, "
                "whitespace ignored (`search @Every`, `search 60s`); rows are `owner  @text  file:line`. "
                "A `code` bucket matches source lines (case-insensitive substring, one line at a time) and cites the "
                "enclosing member (else the type, else the file): `owner  file:line  text`. It replaces grep for "
                "literals, log messages, inline SQL and comments; `as_of.code_note` says when the tree has uncommitted edits.",
        "term": "REQUIRED. Any text.",
        "uses": ("term",) + _B,
        "required": ("term",),
        "examples": ["query search <word>"],
        "where": "Only when no specific kind fits. Prefer symbol/file/table/config/routes.",
        "next": "Re-ask with the specific kind on a hit.",
    },
    "claims": {
        "summary": "reviewed claims, filtered by kind, module or subject",
        "what": "The claim log: structural facts and model/human claims with confidence "
                "and evidence anchors.",
        "not": "Deterministic scans yield few claims; no model review means few "
                "interpretive ones (see `coverage`).",
        "read": "`confidence` and `verdict` per claim; every claim has evidence `file:line`. Scheduled "
                "jobs (`--kind entrypoint`) state their interval, cron, start delay, misfire policy and "
                "concurrency from the annotation arguments.",
        "term": "OPTIONAL shorthand for `claim_kind`; do not combine with a different "
                "`claim_kind`.",
        "uses": ("term", "claim_kind", "module", "subject") + _B + ("include_library",),
        "required": (),
        "examples": ["query claims --kind entrypoint", "query claims --subject <table>"],
        "where": "'What do we claim about X / list all entrypoints/dependencies'.",
        "next": "`symbol`/`file` for context on a claim's subject.",
    },
    "unknowns": {
        "summary": "what the index could not determine, with what would resolve it",
        "what": "Open questions grouped by scope node, each with `needs_*` describing what "
                "would resolve it.",
        "not": "Completeness of unknowns is unknowable; it lists what was noticed.",
        "read": "Grouped by `source_node`; resolve with `answer`.",
        "term": "OPTIONAL. Filter to scope nodes containing this text (`root/web`).",
        "uses": ("term",) + _B,
        "required": (),
        "examples": ["query unknowns", "query unknowns <module>"],
        "where": "'What don't we know / what should I ask a human'.",
        "next": "`cdp answer` to record the human answer.",
    },
    "conflicts": {
        "summary": "claims that contradict each other, plus near-misses",
        "what": "Subjects where two claims disagree, and near-misses that almost merged.",
        "not": "Only conflicts between recorded claims.",
        "read": "`count` conflicts, `near_miss_count` near-misses.",
        "term": "NOT USED.",
        "uses": ("budget",),
        "required": (),
        "examples": ["query conflicts"],
        "where": "'Is anything contradictory / which facts are contested'.",
        "next": "`claims --subject <s>` for both sides.",
    },
    "stats": {
        "summary": "census: files, languages, modules, symbols, routes, claims, coverage",
        "what": "Whole-repo counts, the head commit, resolution rates and declared-vs-observed "
                "module dependency divergence.",
        "not": "Counts only; never budgeted and never filtered (so it is a safe first call).",
        "read": "`resolution` = how many imports resolved; `coverage.fraction` < 1 means "
                "absence in other answers is 'not examined'.",
        "term": "NOT USED.",
        "uses": (),
        "required": (),
        "examples": ["query stats"],
        "where": "First call on an unfamiliar repo: shape and module list.",
        "next": "`routes`, `module <m>`, `trace <entry>`.",
    },
    "coverage": {
        "summary": "what fraction of tracked files was examined, and what was skipped",
        "what": "Coverage fraction, per-node status, skipped files and node errors.",
        "not": "Never budgeted or filtered.",
        "read": "`warning` set means every absence elsewhere is 'unexamined', not 'absent'.",
        "term": "NOT USED.",
        "uses": (),
        "required": (),
        "examples": ["query coverage"],
        "where": "Before saying 'there is no X'.",
        "next": "`stats`; `status` for freshness.",
    },
}

#: kind -> parameters it accepts (plus `ALWAYS`); everything else is rejected.
# Every projected kind takes the answer-size parameters; `match` goes wherever a term or text filter
# (`frm`/`to`, `subject`, `module`) is matched. `stats`/`coverage` are never projected.
for _kind, _spec in KINDS.items():
    if _kind not in ("stats", "coverage"):
        _spec["uses"] = tuple(_spec["uses"]) + ("view", "format", "max_tokens", "offset", "filter") + (
            ("match",) if set(_spec["uses"]) & {"term", "frm", "to", "subject", "module"} else ())

APPLIES: Dict[str, Tuple[str, ...]] = {k: tuple(v["uses"]) + ALWAYS for k, v in KINDS.items()}

#: Question -> kind, the decision table SKILL.md and the MCP description share.
FLOW: List[Tuple[str, str]] = [
    ("how does X work / what do I read / what breaks if X changes", "trace"),
    ("where is X defined / who calls X", "symbol"),
    ("what is in this file", "file"),
    ("what does module M do / depend on", "module"),
    ("what endpoints exist", "routes"),
    ("who reads/writes table T; which tables does a route touch", "table"),
    ("where is config key / env var K read", "config"),
    ("how does data get from A to B", "paths"),
    ("what do we not know / what should a human answer", "unknowns"),
    ("what do we claim about X; list all entrypoints/dependencies", "claims"),
    ("is anything contradictory", "conflicts"),
    ("shape of the repo; did the scan cover it", "stats"),
    ("is it safe to say 'there is no X'", "coverage"),
    ("none of the above", "search"),
]
