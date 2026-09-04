# RESEARCH.md — `code-scanner`

Architecture decisions for a CLI tool that scans a codebase and reports on its quality.

**Status:** design phase, no implementation code written. Claims marked *Verified* were executed on this machine on 2026-09-04.

**Load-bearing ideas:** §3 languages-as-data · §4 an explicit measured population · §6 framework neutrality. Appendix A is the lookup table that makes §3 fast to build; §13 is the build order and its gates.

---

## 0. Scope — what ships

Four of the seven menu features, against a required two or three.

| Feature | Status | Milestone |
| --- | --- | --- |
| Cyclomatic complexity | Ships | M2 (§5) |
| Code smell detection | Ships | M2 (§5) — 3 sub-smells; `long_parameter_list` weighted lowest, see §6 |
| Documentation coverage | Ships | M2 (§5) |
| Security scanning | Ships | M3 (§7) — **source code only** |
| Quality scoring | Ships | M4 (§8) — the bonus pick |
| Code duplication | Deferred | §12 |
| Dependency analysis | Deferred | §12 |

Core requirements are covered by §4 (traversal, ignore rules, language detection, LOC/comment/blank, function and type counts) and §9 (JSON + HTML/Markdown/CSV). Bonus items claimed: quality scoring, data visualisations (§9), unit tests (§10), this document, model strategy (§13). Not attempted: worktree comparison, custom command, Skill.

**Two claims are narrower than they may read:**

- **Security covers source code, not the repository.** Secrets in `application.yml` or `.env` are not found (§7) — for a Spring or FastAPI app, the more likely location.
- **Complexity is understated for annotation-driven frameworks.** `@Transactional`, `@PreAuthorize` and `Depends()` move branching where a syntax tree cannot see it (§7).

**Cut order if the schedule slips.** §4's module/role model and §6's framework neutrality are not menu features — they exist to make the menu features correct, which makes them the right things to sacrifice:

> Cut §6 Layer 4 (packs) → §6 Layer 2 (relative thresholds) → §4's directory-grouping fallback. **Never cut a menu feature to preserve infrastructure.**

---

## 1. The shape of the problem

The requirement list looks like eight features. It is mostly one:

| Requirement | What it actually needs |
| --- | --- |
| Lines of code / comments / blanks | Comment node spans |
| Function & type counts | Function/type node types |
| Cyclomatic complexity | Branch node types, per function subtree |
| Code smells | Function subtree + nesting node types |
| Documentation coverage | Doc node/prefix + visibility rule |
| Security: dangerous calls | Call nodes + callee text |
| Security: hardcoded secrets | String literal nodes + assignment targets |

All of them want **a syntax tree and a small set of node-type names**. Only discovery and reporting sit outside that. So the leverage is a parsing substrate that makes them one tree walk, plus making language support a data-entry problem.

A second axis the brief does not mention matters as much: **repository shape**. A scanner correct on one flat directory is still useless on a 40-module Maven repo, where a global number is unactionable and where test and generated code — routinely half the lines — quietly move it. That is not being wrong; it is being right about the wrong population (§4).

---

## 2. Decision: Python 3.14 + tree-sitter

**Verified on this machine:**

```
pyenv local 3.14.7
pip install tree-sitter tree-sitter-language-pack   # prebuilt wheels, no C toolchain
→ 171 grammars; python, javascript, typescript, tsx, go, java, rust,
  ruby, csharp, cpp, php, kotlin, swift all load
```

Probed before anything was designed around it. `.python-version` is pinned to `3.14.7`; system Python here is 3.9.6 (EOL) and would not have worked.

### Alternatives rejected

| Option | Attraction | Why rejected |
| --- | --- | --- |
| Regex-only, `cloc`-style | Trivial, language-agnostic | Cannot count functions reliably (nested, anonymous, decorated) or compute complexity at all — fails half the requirement list by construction |
| Per-language native parsers (`ast`, TS compiler API, `go/ast`) | Highest accuracy per language | N runtimes, N analyzers, N sets of bugs. Fine at two languages, unmanageable at ten |
| TypeScript + web-tree-sitter | Node 26.8.1 installed; `npx` beats `pipx`; better HTML story | Grammar logistics — you assemble WASM grammars yourself instead of getting 171 from one wheel. The report is a small part of the build; the grammar set is the whole build |
| Go / Rust | Static binary, fastest execution | CGO/FFI grammar wiring is the slowest setup of the three, and execution speed is not the bottleneck (§9) |
| Wrapping Semgrep / SonarQube | Free correctness | Defeats the exercise |

**Accepted cost:** Python packaging. Distribution is `pipx`/`uv tool install`, not a binary drop.

---

## 3. The central abstraction: `LanguageProfile`

**No analyzer may know what language it is looking at.** Analyzers consume a profile; adding a language means adding a data record and a fixture, never touching analyzer code.

```python
@dataclass(frozen=True)
class LanguageProfile:
    name: str                      # "python"
    grammar: str                   # tree-sitter-language-pack key
    extensions: tuple[str, ...]    # (".py", ".pyi")

    function_nodes: frozenset[str] # {"function_definition", "lambda"}
    type_nodes:     frozenset[str] # {"class_definition"}      — Finding B
    comment_nodes:  frozenset[str] # {"comment"}
    string_nodes:   frozenset[str] # {"string"}
    call_nodes:     frozenset[str] # {"call"}
    param_nodes:    frozenset[str] # {"parameters"}
    branch_nodes:   frozenset[str] # decision points → complexity
    nesting_nodes:  frozenset[str] # constructs that increase nesting depth

    body_field: str = "body"       # field holding a function body — Finding A
    doc_style: DocStyle            # FIRST_STRING_IN_BODY | DOC_NODE | PREFIXED_COMMENT | NONE
    doc_prefixes: tuple[str, ...]  # ("/**",) — used by PREFIXED_COMMENT
    visibility: VisibilityRule     # NAME_PREFIX | NAME_CASE | MODIFIER | EXPORT | UNKNOWN
    dangerous_calls: frozenset[str]
```

`body_field`, `doc_style`, `doc_prefixes` and `visibility` were all forced by Appendix A. Three of them would otherwise have surfaced as wrong numbers rather than errors — which is why the grammar extraction happened during design and not at M2.

This is ground rule 1 (§11). The failure it prevents: someone hits a Ruby edge case, writes `if lang == "ruby"` inside the complexity analyzer, and six weeks later there are eleven of those and nobody can add a language.

### Node types, not tree-sitter queries

tree-sitter's native idiom is `.scm` query files — more expressive, and the right long-term tool. Rejected for now: every grammar names its nodes differently, so you debug s-expressions per language instead of shipping, while a flat `frozenset[str]` is reviewable at a glance. Queries remain an escape hatch for patterns needing shape rather than node identity.

Cost: **node names drift between grammar versions.** Mitigated by pinning the language pack and by golden fixtures (§10) that fail loudly on a rename.

---

## 4. Pipeline

```
discover → classify → parse → analyze → aggregate → score → render
             │          │        │                             │
        ignore rules  degrade  per-file,                  JSON ─┴─> HTML/MD/CSV
                      on fail  independent
```

Each file is analyzed independently and returns a small `FileReport`; **the AST is discarded inside the worker**, so peak memory is O(workers), not O(repository).

### Discovery — delegate to git

If the target is a git work tree, enumerate with `git ls-files --cached --others --exclude-standard`. This gets gitignore semantics exactly right for free: nested per-directory `.gitignore` files, negations, `.git/info/exclude`, global excludes. Nesting is not exotic — multi-module Gradle repos carry one per module — and a single-file matcher silently gets it wrong.

Non-git directories fall back to a `pathspec` walk with built-in defaults: `.git`, `node_modules`, `vendor`, `dist`, `build`, `target`, `__pycache__`, `.venv`, `*.min.js`, lockfiles.

Skipped either way: binaries (null byte in first 8 KB) and files > 1 MB. Both are counted and reported — a silent skip is a lie about coverage.

### Modules — one heuristic, zero build-system parsing

On a 40-module Maven repo a single flat score is unactionable: nobody can be assigned "the repository is a C". The actionable unit is the module.

**A module is any directory containing a build manifest**; every file belongs to its nearest enclosing one.

| Manifest | Ecosystem |
| --- | --- |
| `pom.xml` | Maven |
| `build.gradle{,.kts}` | Gradle |
| `package.json` | npm/pnpm/yarn |
| `go.mod` · `Cargo.toml` | Go · Cargo |
| `pyproject.toml`, `setup.py` | Python |
| `*.csproj`, `*.fsproj` | .NET |

Explicitly **not** parsing `<modules>` from the aggregator POM or `include ':a:b'` from `settings.gradle` — the first is Maven-only XML, the second a DSL not reliably parseable without executing it. A filename table makes a pnpm monorepo, a Cargo workspace and a Go multi-module repo work for free.

**When discovery yields fewer than two modules, the rollup key falls back to top-level source directory** (`app/routers`, `app/services`). A typical FastAPI or Django project is one `pyproject.toml` over an `app/` package, so the module ranking would otherwise collapse to a single row — correct and worthless. Modules were never the goal; partitioning the repo into units a person can own is. The JSON records `"grouping": "manifest" | "directory"`.

Accepted imprecision: a `package.json` inside test fixtures registers as a module, and Maven `<modules>` can point outside the parent. Both are visible in `modules[]` rather than silent; `--module-manifest` and `--no-modules` override.

### File role — the metric-correctness problem

`src/test/java` is 30–50% of a typical Java repo. Test norms differ: long methods are fine, `password = "hunter2"` in a fixture is not a leaked credential. Generated code is worse — protobuf stubs are enormous, comment-free and machine-shaped, and one generated module can swing a 40-module score by ten points. **This is the most likely way this tool reports a confidently wrong number.**

| Role | Assigned by |
| --- | --- |
| `test` | `**/src/test/**`, `**/tests?/**`, `*Test.java`, `*_test.go`, `test_*.py`, `*.spec.ts`, `*_spec.rb` |
| `generated` | `**/generated/**`, `**/target/generated-sources/**`, `*.pb.go`, `*_pb2.py`, `**/migrations/**`, `**/alembic/versions/**`, plus a content sniff |
| `vendored` | `**/vendor/**`, `**/third_party/**`, `**/node_modules/**` |
| `production` | everything else |

The content sniff — `@Generated`, `Code generated by`, `DO NOT EDIT` in the first five lines — catches generated code in normal source paths like `src/generated/java`, which no path rule would touch. Migrations need the explicit path entry because neither mechanism catches them: Alembic, Django and Rails migrations are machine-authored and often the largest directory in the repo, but they are hand-edited afterwards and carry no marker.

**Only `role == production` contributes to the quality score.** Everything else is counted, broken out and visible — never scored.

Role patterns are config, not constants: some shops put integration tests in `src/it/java`, and a `testing/` module that ships to consumers is production code despite the name.

```toml
[roles]
test      = ["**/src/it/**", "**/*IT.java"]   # replaces built-ins
generated = ["+**/openapi/**"]                # '+' appends instead

[score]
include_roles = ["production"]                # default
```

### Filtering: three wants, three layers

"Exclude tests" means three separable things. Which layer a filter lives in determines what is recoverable afterwards.

| Want | Mechanism | Cost |
| --- | --- | --- |
| Tests shouldn't affect my score | Default. Nothing to type. | — |
| Don't show them to me | `report results.json --role production` | Re-render, no rescan |
| Don't even read them | `scan --exclude-role test,generated` | Faster; **lossy** |

The middle row is a re-render only because ground rule 2 forces the renderer to be a pure function of the JSON; as a scan-time flag it would cost a four-minute rescan per change of mind. The third row is deliberately lossy — excluded files survive only as a count under `scan.excluded` — and is named differently to make it feel different.

### Defaults announce themselves

"Which files did this actually score?" is the first question anyone asks of a quality number, so the scope is stated unprompted on every run and `score.scope` is a JSON field rather than an implicit convention:

```
Scanned 12,481 files across 40 modules  (2m 14s)
  production 7,102   test 4,918   generated 402   vendored 59
Score 74 (C) — computed over 7,102 production files
       tests, generated and vendored code excluded
```

### Language classification

Extension → profile, with a content-sniff tiebreaker for ambiguous cases (`.h` C vs C++, `.m` ObjC vs MATLAB, `.ts` vs `.tsx`). Each file records `detection: "extension" | "sniff"`.

### Degradation, never failure

tree-sitter returns a tree with `ERROR` nodes rather than throwing.

- `ERROR` nodes covering >20% of the file → `parse_status: "degraded"`
- Grammar missing or parse unusable → `parse_status: "unparsed"`, line counting only

Either way the file appears in the output with a reason, is **excluded from the score**, and is counted in the report. A scanner that quietly scores a file it could not read is worse than one that crashes.

---

## 5. Metrics

### Line classification — per-line, not per-pattern

`line.strip().startswith("//")` gets mixed lines wrong. Instead: one classification slot per line, mark every line touched by a comment node span, then resolve.

```
blank    ← whitespace only
comment  ← touched by a comment node AND no other content
code     ← everything else (code + trailing comment counts as code)
```

This matches `cloc`/`tokei` and yields a hard invariant:

> **`code + comment + blank == total_lines`, for every file, always.**

One property test covers the entire classifier — multi-line comments, docstrings, mixed lines. First test to write.

### Cyclomatic complexity

`M = 1 + |decision points|` within each function's subtree. Decision points: `if`, `elif`/`else if`, loops, `case`/`when` arms, `catch`, `&&`, `||`, `??`, ternaries, comprehension guards.

**`else` is not a decision point** — it adds no independent path. The most common bug in hand-rolled complexity tools, so it is asserted in a fixture.

Node types come from `profile.branch_nodes`. `a && b && c` is one nested `binary_expression` chain in most grammars, so the analyzer counts operator *occurrences*, not operator nodes.

### Function length is the body span

Length is measured over `profile.body_field`, **not the declaration node**. Most grammars put modifiers, decorators and annotations inside the declaration:

```java
@GetMapping("/users/{id}")          // 4 annotations, 11 lines
@PreAuthorize("hasRole('ADMIN')")
@Operation(summary = "Fetch a user")
@ApiResponses({ /* 8 lines */ })
public ResponseEntity<User> getUser(@PathVariable Long id) { … }   // 5-line body
```

Declaration span reports 20 and trips the long-function smell on *every* endpoint of a Swagger-annotated controller; body span reports 5. Annotation lines still count toward file LOC — they are code — just not toward function length.

`body_field` exists for an unrelated reason (Finding A: excluding bodyless signatures). Both follow from one rule: **the body is the unit of analysis.**

### Parameter counting

Count `formal_parameter`-kind children specifically, never the raw child count of the parameter-list node — annotations, defaults and type arguments are all nested children, so `@PathVariable Long id` is one parameter that naively counts as several. Silent when wrong.

### Nesting depth

Depth of `profile.nesting_nodes` only, **not raw AST depth**. Raw depth counts expression nesting (`a + (b * (c - d))`) and says nothing about readability. What matters is how many control-flow constructs you are inside.

### Documentation coverage

Documented public functions ÷ public functions, over production files only.

**Public** is `profile.visibility`:

| Rule | Languages | Test |
| --- | --- | --- |
| `NAME_PREFIX` | python | name does not begin `_` |
| `NAME_CASE` | go | name begins uppercase |
| `MODIFIER` | java, csharp, cpp | `public` in the modifiers node |
| `EXPORT` | javascript, typescript, tsx | declaration carries `export` |
| `UNKNOWN` | ruby, rust | see below |

`UNKNOWN` is not a gap to fill later. Ruby's `private` is a method call evaluated at runtime, and Rust's `pub(crate)` is conditional visibility — no tree walk resolves either correctly. Those languages count all functions public and report `approximate: true`, which is "degrade, never lie" applied to a metric rather than a parse.

**Documented** is `profile.doc_style`: first-string-in-body (Python), a `doc_comment` node (Rust), or a prefix-matched comment immediately preceding the declaration (Java `/**`, C# `///`).

Two guards:

- **Coverage is `null`, not `0`, when there are no public functions.** A module of private helpers is not undocumented. Null is excluded from the score and from means.
- **Test and generated files are excluded**, like every scored metric.

### Smells

| Smell | Default threshold |
| --- | --- |
| Long function | > 50 lines |
| Deep nesting | > 4 |
| Long parameter list | > 5 |
| High complexity | > 10 |

All thresholds live in `.codescanner.toml` with these as documented defaults. **No magic numbers in analyzer code** (ground rule 4) — every one of these is a matter of taste, and a threshold you cannot change is a number you cannot argue with.

### The perverse-incentive check

A smell that rewards the worse pattern is worse than no smell, because teams optimise for the number. Dependency injection is the sharpest case:

```java
// Constructor injection — recommended. 8 params → flagged.
public OrderService(A a, B b, C c, D d, E e, F f, G g, H h) { … }

// Field injection — discouraged, same coupling. 8 fields → invisible.
@Autowired private A a;  @Autowired private B b;  …
```

Identical coupling; the metric punishes the good version. Two config knobs were tried — `exclude_constructors` for Spring, then `count = "required"` for FastAPI, which injects through endpoint parameters rather than constructors — and each fixed one framework and missed the other. **Both are rejected; §6 replaces them.**

The durable result is smaller than either knob: **`long_parameter_list` is the most framework-sensitive of the four smells and therefore carries the least signal**, so it is weighted lowest in the score (§8).

> **Every smell must be checked against "what does a team doing the right thing look like to this rule?" before it ships.**

---

## 6. Framework neutrality

Two frameworks produced two config knobs. Extrapolate to Django, Rails, NestJS, Micronaut and the config file becomes a list of frameworks — ground rule 1's rot relocated from code into config. Relocating a problem is not solving it.

**Why frameworks break metrics:** every metric here assumes *a human chose the shape*. Complexity 20 means someone wrote twenty branches; eight parameters means someone chose eight collaborators. A framework voids that — the DI container dictates the arity, the router dictates the decorator stack, the generator dictates the file. The metric measures accurately; it just attributes the framework's choices to the team.

So the axis is not "is this Spring" but **authored vs. dictated**, which has generic tests. Four layers; prefer the earliest that works.

### Layer 1 — Fix the metric, not the exceptions

Of the four problems frameworks exposed, the two solved generically are closed and the two patched with knobs are not:

| Problem | Fix | Framework knowledge |
| --- | --- | --- |
| Annotations inflate function length | length = body span | **none** — fixes Java, Python, Rust at once |
| `@Value`/`getenv` read as secrets | literal must be direct RHS | **none** — closes the whole class |
| DI inflates parameter count | `exclude_constructors` | Spring-shaped; failed on FastAPI |
| DI inflates parameter count | `count = "required"` | FastAPI-shaped; fails on Spring |

> **When a framework breaks a metric and the fix names the framework, the metric is usually what is wrong.**

Applied to `long_parameter_list`: it proxies "too many collaborators", but it moves when the *injection style* changes while coupling stays identical. The neutral metric is collaborator count at the declaration level — constructor arguments, injected fields and module imports alike — which covers all three styles with no framework knowledge. A metric redesign rather than a config change, so it is future work, recorded here so the knobs do not look like a solution.

### Layer 2 — Calibrate against the codebase

Zero framework knowledge. If every endpoint takes six parameters, six is the local baseline and carries no information; the one taking nineteen is the finding.

```
flagged  ⟺  value > max(absolute_floor, p95 within (language, role, grouping))
```

Two lenses, both reported, neither impersonating the other:

- **Absolute thresholds** — "bad by an external standard" → drives the **score**
- **Relative outliers** — "unusual for this codebase" → drives the **ranking**

Each fails alone: relative-only lets a uniformly bad codebase report itself healthy, absolute-only reproduces the framework problem. This is the highest-leverage mechanism here, because whatever conventions a framework imposes it imposes uniformly, so they vanish into the baseline and genuine outliers stand out.

**Cost:** two-pass aggregation, which the single-pass pipeline in §4 does not do. Percentiles need the population before any file can be judged. Quarantined in `aggregate/calibrate.py` and scheduled at M4.

### Layer 3 — A generic "dictated" predicate

Still no framework names:

> A declaration whose decorator or annotation resolves to a **third-party import** rather than a locally-defined symbol is framework-shaped, not author-shaped.

We already parse imports and see decorators. This catches `@router.get`, `@app.route`, `@Autowired`, `@Injectable`, `@Entity` **without knowing any of them exist**. Such findings are reported with `attribution: "dictated"` and excluded from the score.

Partial: it misses modern Spring constructor injection, which carries no annotation — the container uses an implicit sole-constructor rule. Layer 3 narrows the residue, it does not eliminate it.

### Layer 4 — Framework packs, as auto-activated data

For what Layers 1–3 cannot reach. Four constraints:

1. **Packs are data, never code** — a new framework is a TOML file, not a release.
2. **Packs auto-activate from manifests already parsed in §4.** `pom.xml` declaring `spring-boot-starter` activates the Spring pack. **The user never configures a framework.**
3. **A pack may only suppress findings, never create them.** Worst case is a miss, never invented noise.
4. **Packs are versioned and fixture-tested independently.**

Constraint 3 is load-bearing: it lets a pack be wrong without being dangerous, which is what makes shipping packs defensible at all.

### What this buys, and what it does not

Buys: no user-facing framework configuration; framework support is a data file plus a fixture; the ranking that drives action needs no framework knowledge. The §5 knobs become Spring and FastAPI pack contents.

Does not buy: escape. No layering makes `@Transactional` visible to a syntax tree. The achievable claim is narrower — framework knowledge never enters analyzer code, never enters user config, and cannot manufacture noise when wrong.

---

## 7. Security scanning

Two detectors, both exploiting the AST in ways a regex scanner cannot.

### Hardcoded secrets

Three signals, descending precision:

1. **Assignment name** — a string literal that is the **direct right-hand side** of an assignment to an identifier matching `password|secret|api_key|token|private_key|credential`.

   "Direct RHS" is the precision control, not a detail. A literal nested *anywhere* in the RHS would fire on the standard way every framework reads a secret from the environment — `os.getenv("SECRET_KEY")`, `Field(..., env="DB_PASSWORD")`, `@Value("${db.password}")` — none of which is a hardcoded credential. Requiring the literal to *be* the RHS closes that class while still catching `SECRET_KEY = "dev-secret-change-me"`.
2. **Known token shapes** — `AKIA[0-9A-Z]{16}`, `ghp_…`, `-----BEGIN … PRIVATE KEY-----`, Slack/Stripe prefixes, JWT structure. Low recall, near-zero false positives.
3. **Shannon entropy** — > 4.0 bits/char on string literals ≥ 20 chars.

All three run over **string literal nodes from the tree**, never raw file text, which removes the dominant false-positive source in regex secret scanners.

Entropy is the noisy one (hashes, UUIDs, base64 fixtures, minified blobs). Controls: allow-lists for UUID/hex-digest/fixed-length base64, and confidence demotion for any file whose `role` is not `production` — reusing §4's role classification rather than adding a second definition of "test code".

**Placeholders are references, not secrets.** A literal that is entirely an interpolation — `${…}`, `#{…}`, `{{…}}`, `%(…)s` — is never a finding. Defence in depth behind the direct-RHS rule.

### Dangerous calls

Per-language deny-list in `profile.dangerous_calls`, matched against callee text: `eval`, `exec`, `os.system`, `subprocess.*(shell=True)`, `pickle.loads`, `yaml.load` without a loader, `innerHTML`, `child_process.exec`, `document.write`.

### False positives are the product risk

A scanner that cries wolf gets disabled, and then has negative value. Three controls:

- Every finding carries `confidence: high | medium | low`
- Findings below the configured floor are **reported but not scored**
- Inline suppression: `# scanner:ignore[secret]` on or above the line

### Stated limitations

**No dataflow or taint tracking.** Linter-grade. It will not find an injection flowing across three functions.

**Annotation-driven frameworks hide control flow from the complexity metric.** `@Transactional` is an implicit try/catch/rollback, `@PreAuthorize` a branch expressed as a SpEL string, `@Retryable` and `@Cacheable(condition=…)` branches, and AOP aspects never appear in the method at all — so a Spring method reporting complexity 1 may branch substantially. Modelling framework semantics is out of scope; it has no natural boundary. It is a spectrum: FastAPI understates less, because much of its hidden logic lands in Pydantic `@field_validator` methods that are ordinary scanned code. Code generation biases the other way — Lombok's `@Data` methods do not exist in source, so those classes under-report.

**Config files are not scanned, and that is where secrets live.** `application.yml`, `.env`, `*.tfvars` have no grammar, land as `unparsed`, and the detectors never see them — so for a Spring app we miss the most likely leak location. The fix is small but is a genuinely different code path (§12). Until it lands the coverage claim is "source code", not "repository".

---

## 8. Quality score

Composite scores fail when the weights are arbitrary and the number is unfalsifiable. Three responses.

**Normalize by size.** Raw counts punish large repositories for being large. Every input is a density or ratio.

**Penalty model, not a weighted average.**

```
score = clamp(100 − P_complexity − P_smells − P_docs − P_security, 0, 100)

P_complexity = 25 · saturate(pct_functions_over_threshold / 0.15)
             +  5 · saturate((p95_complexity − 10) / 20)
P_smells     = 15 · saturate(smells_per_kloc / 10)
P_docs       = 10 · saturate((0.80 − doc_coverage) / 0.80)   # null → term omitted
P_security   = min(60, Σ severity_weight)   critical=25, high=10, medium=3, low=0

saturate(x) = min(x, 1.0)
grade: A ≥ 90 · B ≥ 80 · C ≥ 70 · D ≥ 60 · F < 60
```

Complexity, smells and docs **saturate** — one catastrophic file should not zero a 500 kLOC repo, because a score that bottoms out stops distinguishing bad from worse. Security deliberately does not: a committed AWS key is categorically different from a long function. The `min(60, …)` cap exists only so repositories with secrets remain rankable against each other.

`p95_complexity` is included because means hide exactly the functions you need to find — 400 trivial functions and 3 monsters has a fine mean and a real problem.

Documentation is weighted lowest at 10: undocumented code is a real but recoverable cost. When `doc_coverage` is `null` the term is **omitted, not zeroed**, and the rest are not rescaled.

### The score must decompose

```json
"score": {
  "value": 78, "grade": "C",
  "scope": {"roles": ["production"], "files": 7102, "code": 412903,
            "excluded": {"test": 4918, "generated": 402, "vendored": 59,
                         "degraded": 3, "unparsed": 1}},
  "penalties": {"complexity": 11.2, "smells": 6.0, "docs": 4.0, "security": 5.0},
  "inputs": {"pct_functions_over_threshold": 0.067, "p95_complexity": 14,
             "smells_per_kloc": 3.0, "doc_coverage": 0.48,
             "security_findings": {"high": 0, "medium": 1}}
}
```

"You are a C" changes nothing; "you lost 11 points to complexity, driven by 6.7% of functions over threshold" is a work item. `scope` is there for the same reason: a number whose denominator you cannot see is one you have to take on faith.

### Two numbers, not one fudged one

Every module scores independently over its own production files. The repository score is computed globally over all production files — **not** as a mean of module scores. LOC-weighting reproduces the problem modules were introduced to solve; equal-weighting lets a 3-file module outvote a 300-file one. Both sound defensible and both are wrong.

The module ranking is the actionable artifact: "acme-platform is a C" is not assignable, "acme-legacy-billing is a D and the other 39 are B or better" is.

---

## 9. Output contract

**JSON is primary. Every report format is a pure function of it** — renderers may not read source or touch an AST (ground rule 2). The result is reproducible from a stored file, two runs can be diffed, and CI consumes JSON without rendering.

```json
{
  "schema_version": "1.0",
  "tool": {"name": "code-scanner", "version": "0.1.0"},
  "scan": {"root": "/repos/acme-platform", "started_at": "2026-09-04T11:02:33Z",
           "duration_ms": 134210, "discovery": "git-ls-files",
           "grouping": "manifest", "detail": "threshold",
           "files_scanned": 12481, "files_excluded": 0, "files_skipped": 96,
           "files_degraded": 3, "files_unparsed": 1,
           "by_role": {"production": 7102, "test": 4918,
                       "generated": 402, "vendored": 59}},
  "score": {"value": 74, "grade": "C", "scope": {...}, "penalties": {...}},

  "modules": [
    {"id": "acme-core", "path": "acme-core", "manifest": "pom.xml",
     "ecosystem": "maven",
     "score": {"value": 81, "grade": "B", "penalties": {...}},
     "totals": {"files": 412, "code": 38210, "comment": 6104, "blank": 7002,
                "functions": 1840, "types": 210, "doc_coverage": 0.68},
     "by_role": {"production": 260, "test": 148, "generated": 4, "vendored": 0}}
  ],

  "languages": [
    {"name": "java", "files": 6208, "code": 402911, "comment": 88140, "blank": 71002,
     "functions": 38401, "types": 6210, "mean_complexity": 3.4, "p95_complexity": 14,
     "doc_coverage": 0.71, "doc_coverage_approximate": false}
  ],

  "files": [
    {"path": "acme-core/src/main/java/com/acme/Handler.java",
     "module": "acme-core", "language": "java", "role": "production",
     "parse_status": "ok", "detection": "extension",
     "lines": {"total": 320, "code": 240, "comment": 40, "blank": 40},
     "counts": {"functions": 12, "types": 1, "public": 8, "documented": 5},
     "doc_coverage": 0.625,
     "functions": [
       {"name": "handleRequest", "line": 42, "end_line": 118, "length": 76,
        "complexity": 17, "params": 7, "max_nesting": 5,
        "public": true, "documented": false}
     ],
     "types": [{"name": "Handler", "kind": "class", "line": 20}],
     "smells": [{"kind": "long_function", "line": 42, "value": 76, "threshold": 50}],
     "security": [{"kind": "hardcoded_secret", "line": 91, "severity": "high",
                   "confidence": "high", "detector": "assignment_name",
                   "message": "String literal assigned to 'api_key'"}]}
  ]
}
```

`schema_version` ships from day one — versioning after the fact is not possible. `module` and `role` sit on every file record, not just aggregates, because that is what makes `report --role production` a re-render rather than a rescan.

### Output size is a design constraint

A 50k-file monorepo with a record per function is a 100 MB+ JSON — slow to write, hostile to `jq`, unattachable to a CI run.

Default: every file gets `lines` and `counts`, but the detail arrays are emitted **only for functions that breached a threshold**. `counts.functions` preserves the aggregate so no metric is lost. `--full` overrides; `--summary` drops `files[]` entirely for CI. The choice is recorded as `scan.detail` so a consumer can tell which shape it was handed.

### HTML report: self-contained, no CDN

Single file, inline CSS, **hand-rolled inline SVG** charts. No Chart.js, no D3, no network fetch — this report gets emailed and opened offline, and one that renders a blank rectangle without network has failed at the only moment it mattered.

Structure is **module-first**: score gauge and scope banner, then modules ranked worst-first, then drill-down. Sorting ascending puts the work queue at the top of the page. Charts: score gauge, module ranking, LOC-by-language split by role, complexity histogram, top-N offender tables. Legible in light and dark; never hue alone.

**Target is correct, not impressive.** M4 is scoped to charts that are accurate, accessible and readable — not to a polished dashboard. This is the milestone most able to absorb unbounded effort while carrying the schedule risk for the score and all four output formats (§13), so the visual bar is fixed here deliberately rather than left open.

### CLI

```
code-scanner scan <path>   [--out results.json] [--html report.html]
                           [--config .codescanner.toml] [--jobs N]
                           [--include GLOB] [--exclude GLOB]
                           [--exclude-role test,generated]
                           [--detail threshold|full|summary] [--fail-under 70]

code-scanner report <results.json>
                           [--html report.html] [--md report.md] [--csv out.csv]
                           [--role production] [--module acme-core]
                           [--top 20] [--fail-under 70]
```

`scan` reads code and writes JSON; `report` reads JSON and writes documents. The split is ground rule 2 as a process boundary rather than a convention, it puts every slicing option on the cheap side, and it makes all three required formats one interface with three implementations. CI runs `scan --summary --fail-under 70` with no rendering at all.

`argparse` over Typer/Click — two subcommands do not justify a dependency; the list stays at four.

### Performance

`ProcessPoolExecutor` over files, chunked. Python 3.14 ships a supported free-threaded build, but the installed 3.14.7 is the GIL build and tree-sitter's GIL behaviour is not worth betting on.

The bottleneck is expected to be I/O and process startup, not parsing — tree-sitter is C. **This is an assumption, not a measurement**, and gets measured at M1 before anyone optimizes.

---

## 10. Testing strategy

The risk in a metrics tool is not "does it run" but **"are the numbers right"** — and wrong numbers are silent. Per-language node-type sets drift without failing.

**Golden fixtures.** `tests/fixtures/<lang>/sample.<ext>` plus `expected.json`; the test asserts the whole `FileReport`. Each is small, hand-written and deliberately contains the edge cases: nested functions, an `else` branch (which must not raise complexity), a multi-line comment, a mixed code+comment line, a lambda, a decorated method. Adding a language without a fixture is a rule violation, not an oversight.

**Two annotated-framework fixtures**, Java and Python, because they break different things:

- *Spring-shaped Java* — a controller with more annotation lines than body lines, a constructor with eight injected parameters, a `@Value("${db.password}")` field, an anonymous inner class containing a method.
- *FastAPI-shaped Python* — an endpoint whose signature exceeds its body, four `Depends()` parameters, `SECRET_KEY = os.getenv("SECRET_KEY")` beside a real `SECRET_KEY = "dev-secret"`, an `alembic/versions/` file, and a single `pyproject.toml` to exercise directory grouping.

Together they pin every regression §4–§7 were changed to prevent, all of which fail as wrong numbers rather than exceptions.

**A multi-module fixture from M1.** Three manifests, `src/main` and `src/test` trees, one `DO NOT EDIT` file in a normal source path, a nested `.gitignore`. Asserts module assignment, all four roles, and a production-only scored population.

**Property tests.**
- `code + comment + blank == total_lines` — every file, every language
- `documented ≤ public ≤ functions`; `doc_coverage` is `null` exactly when `public == 0`
- `0 ≤ score ≤ 100`, grade consistent with score
- `complexity ≥ 1` for every function
- `score.scope.files == count(role == production and parse_status == ok)` — rule 5 as an assertion
- a directory of only-ignored files yields a valid empty report

**Failure paths.** Truncated file, binary masquerading as `.py`, empty file, no trailing newline, symlink loop, unreadable permissions. Every one produces a report entry, never an exception.

---

## 11. Ground rules (`CLAUDE.md`)

Six rules, each earned from a specific failure this design is preventing.

1. **Languages are data.** Adding a language means a `LanguageProfile` record and a golden fixture. Writing `if language == "…"` in an analyzer means a missing profile field. *Prevents: the abstraction rotting into a switch statement.*

2. **Renderers read JSON only.** No renderer opens a source file or touches an AST. If the HTML needs a number, that number belongs in the JSON. *Prevents: JSON and HTML disagreeing; non-reproducible results.*

3. **Degrade, never lie.** Parse failures produce `parse_status: degraded|unparsed`, are excluded from the score, and are surfaced. Never a crash, never a silent zero. *Prevents: a clean score on a repo we mostly failed to read.*

4. **Thresholds are config.** Every threshold, weight and severity has a documented default in config. No magic numbers in analyzer code. *Prevents: unarguable numbers.*

5. **Every number states its scope.** Anything scored records what it was computed over. A metric that cannot name its denominator does not ship. *Prevents: tests or generated code quietly moving a score.*

6. **No framework names in the analyzers.** `grep -ril "spring\|fastapi\|django\|rails\|nest" code_scanner/` returns empty. Framework knowledge lives in `packs/*.toml` or nowhere, and a pack may only suppress findings. Fix the metric first (§6); reach for a pack only when Layers 1–3 have failed. *Prevents: knob-per-framework drift.*

---

## 12. Deferred, with reasons

**Config-file secret scanning.** Highest-value deferred item and the only one closing a *correctness* gap rather than adding a feature — §7 cannot claim repository coverage without it. Scope is small: a text-mode pass applying the shape and entropy detectors, without an AST, over `*.yml`, `*.properties`, `*.env`, `*.tfvars`. Deferred only because it is a second code path with no `LanguageProfile` behind it, and introducing that shape before the AST path is proven would blur the cleanest seam in the architecture. First thing after M5.

**Code duplication.** Orthogonal and demos well ("12% duplicated"), but needs its own pipeline: token normalization, k-gram shingling, winnowing, clone-class clustering. A day on its own plus a tuning problem to make results non-noisy — the one feature that can consume the schedule and still land unconvincing.

**Dependency analysis / circular imports.** Highest cost, least generality on the menu. Import *syntax* is easy from the AST; import *resolution* is the work, and it is per-language and per-build-system (`tsconfig` paths, namespace packages, monorepo aliases). Unresolved imports produce a graph that is confidently wrong, which is worse than no graph. Deferred indefinitely.

---

## 13. Build plan

Vertical slices — every milestone ends with a runnable command producing valid JSON, so the deliverable is never half-built. **Acceptance is a command that exits 0, not a judgement call**; prose gates are where agent-driven builds drift, because nothing can fail.

| | Milestone | Gate — must exit 0 |
| --- | --- | --- |
| **M0** | Walking skeleton | `scan tests/fixtures/python --out - \| check-jsonschema --schemafile schema/result.schema.json -` |
| **M1** | Profiles, modules, roles | `pytest tests/test_{discovery,roles,modules}.py` — 10 languages load; `scan tests/fixtures/multimodule` finds 3 modules and classifies `src/test/**` as `test` |
| **M2** | Complexity, smells, docs | `pytest tests/test_golden.py` — every fixture matches `expected.json` exactly, including `else`-is-not-a-branch and a private-helpers-only file reporting `doc_coverage: null` |
| **M3** | Security | `pytest tests/test_security.py` — planted secrets all found **and** `scan tests/fixtures/clean` yields zero findings |
| **M4** | Score + reports + calibration | `--fail-under 101` exits 1 and `--fail-under 0` exits 0; `report --html -` contains no `http`; `pytest tests/test_relative.py` — a repo where every function has 8 params yields no outliers and one at 19 |
| **M4a** | Framework neutrality | `grep -ril "spring\|fastapi\|django" code_scanner/` empty; Spring and FastAPI fixtures yield zero `long_parameter_list` findings with packs active, and the findings reappear under `--no-packs` |
| **M5** | Harden | `pytest` green; `scan <large real repo>` completes without exception |

Two gates do unusual work. M3's *zero findings on a deliberately clean fixture* is the only test constraining false positives, which §7 argues is the real product risk. M4's `grep http` on rendered HTML mechanically enforces the no-CDN decision — an untested rule is a preference.

**Ordering rationale.** M0 proves the schema before any analysis exists, because the schema is what everything else must agree with. M1 stresses the profile abstraction across ten languages *and* the module/role model across a multi-module fixture **before** analyzers are built on them — both are expensive to retrofit, so this is the cheapest moment to discover either is wrong.

**Model strategy:** strongest model for M0/M1 (schema and the profile abstraction — expensive to reverse); fastest model for M2/M3 profile records and fixtures (high volume, low ambiguity, verified by golden tests).

---

## 14. Open risks

Risks that remain live. Items resolved by the design are not repeated here.

| Risk | Mitigation |
| --- | --- |
| Node names drift between grammar versions | Pin the language pack; golden fixtures fail loudly on rename |
| Entropy detector too noisy to trust | Confidence floor, allow-lists, role demotion; tune against a real repo at M3 |
| Annotation-heavy code reads as artificially simple | Unfixable without framework semantics. False *positives* are removed (§5, §6); the understatement remains and is stated in §7 |
| Secrets missed in `application.yml` | Known gap; §7 scopes the claim to source code; first item after M5 |
| Relative thresholds need two-pass aggregation | Real cost, accepted; quarantined in `aggregate/calibrate.py`, scheduled at M4 rather than retrofitted |
| A framework pack hides a real finding | Packs may only suppress, so the failure mode is a miss, not noise; versioned and fixture-tested |
| C++ function naming via nested declarators | Hardest language, scheduled last; degrades to `<anonymous>` names rather than blocking |
| Module heuristic misfires | Visible in `modules[]` rather than silent; `--no-modules` / `--module-manifest` escape hatches |
| Scope creep via the feature menu | §12 defers with reasons; §0 fixes the cut order |
| Python distribution friction | Accepted. `pipx`/`uv tool install`; not solving packaging |

---

## Appendix A — Grammar ground truth

*Verified 2026-09-04 against `tree-sitter 0.26.0` / `tree-sitter-language-pack 1.16.1`.* Every grammar enumerates its own node kinds (`Language.node_kind_count` / `node_kind_for_id`), so these are extracted facts. The probe was run, recorded here, and deleted.

| Language | Kinds | Language | Kinds | Language | Kinds |
| --- | --- | --- | --- | --- | --- |
| python | 123 | java | 142 | csharp | 219 |
| javascript | 114 | rust | 163 | cpp | 223 |
| typescript | 177 | ruby | 134 | go | 107 |
| tsx | 184 | | | | |

### Five findings that changed the design

**A. Bodyless declarations look exactly like functions.** TypeScript has `function_signature`, `method_signature`, `call_signature`, `function_type`; Rust has `function_signature_item`; Go has `function_type` and `method_elem`. All are type-level declarations with no body. Counting them inflates function counts — catastrophically on `.d.ts` files, which are entirely signatures — and each adds a phantom complexity-1 function.

Fix generalizes rather than enumerating per-language exclusions: **a function node counts only if it has a body**, via `profile.body_field`. One rule, ten languages.

**B. "Class" is not universal.** Go has `struct_type`/`interface_type`; Rust has `struct_item`, `enum_item`, `trait_item`, `impl_item`; C has neither. Reporting "classes: 0" for a well-structured Go module is a false signal. The field is `type_nodes`, the metric is `types`, and `kind` is retained per record so a Java class and a Rust trait stay distinguishable.

**C. Comment node names are not uniform.** python/javascript/go/csharp/cpp use one `comment`; java and rust use `line_comment` + `block_comment`. Confirms `comment_nodes` must be a set.

**D. Documentation is detected three structurally different ways.** Python uses first-string-in-body; Rust has a dedicated `doc_comment` node; Java and C# use an ordinary comment distinguished only by prefix (`/**`, `///`). Hence `DocStyle` has three variants. A single-strategy design would have silently reported 0% documentation coverage for Java.

**E. Keyword bucketing is unsafe in both directions.** The probe bucketed by substring: Java's `method_invocation` and `method_reference` landed under "function" when both are *calls*; Ruby's `heredoc_body` landed under "comment" when it is a string. It also *omitted* things — Python's `decorated_definition`, the wrapper holding decorators around a `function_definition`, matches no keyword and never appeared, yet it determines whether decorators count toward length.

So: **extraction for recall, human review for precision, fixtures for regression.** Treat this appendix as a shortlist, never the answer.

Wrapper nodes are the specific hazard, because they shift *spans* rather than *counts* and so break metrics without breaking detection. Python's decorators sit outside `function_definition`; Java's annotations sit inside `method_declaration` — same language feature, opposite grammar shape, opposite defect. The body-span rule (§5) is correct for both, which is why it is a rule and not a Java workaround.

### Derived profiles

Curated from the enumeration. `branch_nodes` and `nesting_nodes` are filled in at M2 alongside each language's fixture.

| Language | `function_nodes` | `type_nodes` | `comment_nodes` | `call_nodes` | `param_nodes` |
| --- | --- | --- | --- | --- | --- |
| python | `function_definition`, `lambda` | `class_definition` | `comment` | `call` | `parameters`, `lambda_parameters` |
| javascript | `function_declaration`, `function_expression`, `arrow_function`, `generator_function{,_declaration}`, `method_definition` | `class_declaration`, `class` | `comment` | `call_expression`, `new_expression` | `formal_parameters` |
| typescript / tsx | as javascript — **minus all `*_signature` and `*_type`** | + `interface_declaration`, `enum_declaration`, `abstract_class_declaration` | `comment` | `call_expression`, `new_expression` | `formal_parameters` |
| go | `function_declaration`, `method_declaration` | `struct_type`, `interface_type`, `type_declaration` | `comment` | `call_expression` | `parameter_list` |
| java | `method_declaration`, `constructor_declaration`, `compact_constructor_declaration`, `lambda_expression` | `class_declaration`, `interface_declaration`, `enum_declaration`, `record_declaration` | `line_comment`, `block_comment` | `method_invocation`, `object_creation_expression` | `formal_parameters` |
| rust | `function_item`, `closure_expression` | `struct_item`, `enum_item`, `trait_item`, `impl_item` | `line_comment`, `block_comment`, `doc_comment` | `call_expression`, `macro_invocation` | `parameters`, `closure_parameters` |
| ruby | `method`, `singleton_method`, `lambda` | `class`, `module`, `singleton_class` | `comment` | `call` | `method_parameters`, `block_parameters` |
| csharp | `method_declaration`, `constructor_declaration`, `destructor_declaration`, `local_function_statement`, `lambda_expression` | `class_declaration`, `struct_declaration`, `interface_declaration`, `enum_declaration`, `record_declaration` | `comment` | `invocation_expression`, `object_creation_expression` | `parameter_list` |
| cpp | `function_definition`, `lambda_expression` | `class_specifier`, `struct_specifier`, `enum_specifier` | `comment` | `call_expression`, `new_expression` | `parameter_list` |

**C++ is hardest and is scheduled last.** `function_definition` holds the body, but the name lives inside a `function_declarator` possibly wrapped in pointer, reference, template and trailing-return declarators. Counting and complexity work regardless of naming, so the degradation path is `<anonymous>` names rather than a blocked release.

**Java's second-hardest case** is anonymous inner classes: `object_creation_expression` carrying a `class_body` contains real method declarations. The descend-and-collect walk handles this only if it does not stop at the first type boundary — which the Java fixture must assert.

---

## Appendix B — Module layout

Ground rules 1, 2 and 6 are architectural claims, and a claim living only in prose is a preference. This layout makes each of them a one-line check.

```
code_scanner/
├── cli.py               # argparse; scan + report subcommands
├── config.py            # .codescanner.toml → Config; all thresholds and weights
├── model.py             # FileReport, ModuleReport, ScanResult — shared vocabulary
│
├── discover/
│   ├── walk.py          # git ls-files, pathspec fallback, binary/size skips
│   ├── modules.py       # manifest table → module assignment
│   └── roles.py         # path rules + generated-content sniff
│
├── languages/
│   ├── profile.py       # LanguageProfile, DocStyle, VisibilityRule
│   └── defs/            # one file per language. DATA ONLY. Rule 1.
│
├── parse/
│   ├── session.py       # grammar loading, per-process parser cache
│   ├── lines.py         # per-line classification; owns the LOC invariant
│   └── walk.py          # single AST traversal → raw observations
│
├── analyze/
│   ├── complexity.py    smells.py    docs.py
│   └── security/        secrets.py   dangerous_calls.py
│
├── packs/               # framework knowledge. DATA ONLY. Rule 6.
│   ├── loader.py        # manifest → active packs; suppress-only enforcement
│   └── defs/            # spring.toml  fastapi.toml  django.toml …
│
├── aggregate/
│   ├── rollup.py        # file → module → language → repo
│   ├── calibrate.py     # second pass: distributions → relative thresholds (§6 L2)
│   └── score.py         # penalty model; owns `scope`. Rule 5.
│
└── render/              # reads ScanResult ONLY. Rule 2.
    ├── json_out.py  html.py  markdown.py  csv_out.py
    └── charts.py        # inline SVG. No CDN, no JS.

schema/result.schema.json
tests/fixtures/<lang>/{sample.ext,expected.json}
tests/fixtures/{multimodule,spring,fastapi,clean}/
```

Each rule becomes greppable: `grep -rE "from (parse|analyze)" render/` empty is rule 2; any `def` or `if` in `languages/defs/` violates rule 1; framework names outside `packs/defs/` violate rule 6. Pack definitions are TOML rather than Python precisely because a data file cannot accidentally grow logic.

`model.py` is the only vocabulary shared across stages, so an accidentally-crossed stage boundary shows up as an unexpected import. `aggregate/calibrate.py` is the single deliberate exception to §4's per-file model — relative thresholds need the whole population — and keeping it in one named module makes that exception visible rather than diffuse.

**Pinned dependencies** — four, all verified installing from wheels on Python 3.14.7:

```
tree-sitter==0.26.0            tree-sitter-language-pack==1.16.1
pathspec (gitignore fallback)  jinja2 (HTML templating)
```

---

## Appendix C — Result schema

`schema/result.schema.json` is a real JSON Schema file written at M0, *before* the analyzers — it is the contract every stage agrees on and the thing the M0 gate validates against. An example cannot fail a build; a schema can, and it is what stops the JSON writer and the renderers from silently diverging as fields are added.

Invariants encoded beyond field types:

- `lines.code + lines.comment + lines.blank == lines.total`
- `score.value` ∈ [0, 100]; `grade` ∈ {A,B,C,D,F} and consistent with `value`
- `role` ∈ {production, test, generated, vendored}; `parse_status` ∈ {ok, degraded, unparsed}
- `score.scope` is **required**, not optional — rule 5 made structural
- every `files[].module` resolves to a `modules[].id`
- `schema_version` required and pinned per release

Versioning: additive changes bump minor; removals or semantic changes bump major; the renderer refuses an unrecognised major rather than rendering a plausible-looking wrong report.
