# PLAN.md — implementation plan for `code-scanner`

Build order, plus every ruling `RESEARCH.md` leaves open or gets wrong. Scope is unchanged (§0 stands).

**How to read:** §1 is the defect register, **sorted by the milestone that must honour it** — at M2 you read the M2 rows and nothing else. §2–§4 are the three artifacts M0 cannot ship without. §5 is the build order. IDs are stable and citable in commits.

`✓` = re-verified on this machine at the pinned versions. `RESEARCH.md` Appendix A is a shortlist, **not ground truth** — nine of its claims below are wrong.

---

## 1. Defect register

### M0 — schema, config, CLI

| ID | Defect | Ruling |
| --- | --- | --- |
| **R1** ✓ | §8's worked example is arithmetically wrong in **three of its four** penalty terms: complexity 11.2 (should be 12.17 — the p95 term was dropped), smells 6.0 (4.5), security 5.0 (3.0), docs 4.0 ✓. Its parts sum to 73.8; it states 78; the formula gives 76.3. | It is the only end-to-end numeric example in either document, so it is the oracle an implementer hand-checks against — and they will "fix" the formula to match it. **Formula is normative; delete the example's numbers.** Corrected computation becomes assertion #1 of `tests/test_score.py`. |
| **R5** | The schema cannot hold what §6/§7 produce: no `attribution` (L3 "dictated"), no `suppressed_by` (L4 packs), no `outliers[]` (L2 relative lens), no `scan.packs_active`, no `lines.approximate`. | Add all five at M0. Appendix C says the schema precedes the analyzers; these are knowable now and cost a major version bump at M4a otherwise. M4a's gate as written ("zero findings with packs active") can only be passed by **deleting** findings — i.e. by lying. Suppressed findings stay visible with a reason. |
| **R16** | Every constant is configurable (D8), so two runs with different `.codescanner.toml` produce different scores and byte-identical JSON structure. | `scan.config` records the **resolved** values used, plus `config_source` and `config_digest` (sha256). §8's entire argument is falsifiability; a score you cannot reproduce fails it. |
| **R11** ✓ | `total_lines` is undefined. `"a\nb\n"` → `splitlines()` = 2 but tree-sitter `end_point.row` = 2; `"a\nb"` → 2 and 1. | Spans come from tree-sitter, the line array from text — mixing them is a one-line error on **every file with a trailing newline**. Define `total = len(splitlines())`, forbid `end_point.row` arithmetic for line totals, fixture the no-trailing-newline case. |
| **R20** | Score rounding undefined. 73.8 → 73 or 74, at a grade boundary. | `[score] rounding = "half_up"`. Grade computed from the **rounded** value. |
| **R19** | Config discovery undefined — cwd, scan root, or upward walk. | Scan root, then upward to the repo root, first match wins. Determines whether CI and local runs score the same repo identically. |
| **R18** | No decode policy for non-UTF-8 source. | `errors="replace"`, file marked `lines.approximate` (R/D14 convention). Never raises. |
| **R17** | §9 claims two runs can be diffed, but `files[]` order under `ProcessPoolExecutor` is completion order. | Sort `files[]` by path before emit. |
| **R27** | CLI block omits `--no-modules`, `--module-manifest` (§4), `--no-packs` (§13), `--quiet`, `--version`. | Add to the §9 surface. |
| **D3** | §9's sample `scope` is inconsistent with §10's invariant. | Invariant stands, sample is wrong: `scope.files ≤ by_role.production`, and `scope.files + Σ scope.excluded == scan.files_scanned`. A file excluded for both role and parse status counts **once, under its role**. Name `scope.excluded.degraded` distinctly from `scan.files_degraded` — they are different populations. |
| **D4** | Empty scored population → all penalties 0 → **100/A**. | `score.value: null`, `grade: null`. **Appendix C (`value ∈ [0,100]`, `grade ∈ {A..F}`) and §10's `0 ≤ score ≤ 100` must be amended to nullable in the same change** — both are written at M0, so otherwise the M0 gate rejects M4's output. `--fail-under` on null exits 0; `[score] fail_on_empty = false` opts into failing, so a CI job whose scan path breaks does not go green forever. |
| **D5** | `-` is used by two §13 gates, defined nowhere in §9; the §4 banner would corrupt the stream. | `-` = stdout for `--out/--html/--md/--csv`. **All human output to stderr unconditionally.** `--quiet` suppresses the banner. |
| **D8** | §8's `0.15`, `10`, `20`, `0.80`, the weights, severity weights, `min(60,·)` and grade cutoffs are inline in `aggregate/score.py`. | All become `[score]` keys. `p95_knee = "@thresholds.high_complexity"` is a **reference, not a copy** — raising the smell threshold to 15 must move the score's knee with it. |
| **D2** ✓ | All three of §11's rule-greps pass vacuously (wrong paths; missing dir → exit 2, empty stdout → "empty" → pass). Rule 6 as written **forbids the packs §6 L4 mandates**. | Corrected commands in **§4a**. My previous replacements were also broken ✓ — `-E` with `\|` is a literal pipe and matched nothing under **both** BSD grep and ugrep. Scope the exclusion to `--exclude-dir=packs`, **not** `defs`: a framework name in `languages/defs/` is a genuine rule-1 smell. `scripts/check_rules.sh` must call `/usr/bin/grep -E` (this shell's `grep` is ugrep 7.8.4 ✓) and **fail on a missing directory**. |
| **D10** | `--full`/`--summary` prose vs `--detail` CLI block. | `--detail` canonical, the others alias. |

### M1 — profile, discovery, roles, modules

| ID | Defect | Ruling |
| --- | --- | --- |
| **D1** | `LanguageProfile` lacks the fields §5–§7 require; §13 freezes it at M1. Without them M2/M3 must widen it mid-flight or write `if language == …`. | Corrected field spec in **§2**. My earlier list said "nine fields" three times and named fourteen across eight rows — the spec below is authoritative. |
| **R2** ✓ | Appendix A's `type_nodes` **guarantee double-counting**. Go `type Foo struct{}` → `type_declaration` → `type_spec` → `struct_type`, and Appendix A lists both `type_declaration` and `struct_type`: every struct and interface counts twice, every alias once. Rust counts `struct Foo` + two `impl` blocks as three types, and `impl Clone for Foo` is not a type at all. | Match `type_container_nodes` only when no listed descendant matches — or drop Go to `{type_declaration}` and drop Rust's `impl_item`. A profile decision, fixtured at M1, not discovered at M2. |
| **R14** ✓ | Appendix A finding A ("no body → not a function") **deletes every Java interface and abstract method** — verified, they have no `body` field. Those are the most consistently Javadoc'd code in a Java repo, so repo doc coverage *rises* when you add a well-documented API. Interface methods also carry no `modifiers` node, so `MODIFIER` visibility never sees `public`. | Split the rule. Bodyless **type-level declarations** (`function_signature`, `method_signature`, `call_signature`, `function_type`, `function_signature_item`, `method_elem`) are excluded — that is what finding A was for. Bodyless **method declarations in an interface or abstract class** are counted, are public by default, and stay in the doc denominator. |
| **R28** ✓ | RESEARCH's own *Verified* numbers do not reproduce. §2's "171 grammars" is **371**. Appendix A's Kinds counts are exact **only** as unique *named* kinds (python 123 named / 275 raw; cpp 223 / 575) — a raw `node_kind_count` reading makes nine of ten look wrong. | Record the extraction method with the table. Re-extract at M1 and commit the enumeration **as a fixture**, so a grammar bump fails loudly. |
| **R25** | JS/TS have `html_comment` (`<!-- -->` is legal in scripts) alongside `comment`. Appendix A lists only `comment`, so those lines classify as `code` — invariant intact, number wrong. | Add to `comment_nodes` for javascript/typescript/tsx. |
| **R9** | `.pyi` is in §3's python extensions, but PEP 484 stubs are `def f() -> int: ...` — which **has** a body, so finding A does not save them. A stub-heavy package reports hundreds of complexity-1 functions at 0% doc coverage. | `[roles] stub_extensions = [".pyi", ".d.ts"]` → role `generated`. |
| **D12.1** ✓ | **Withdrawn — my previous ruling was inverted and would have introduced the bug.** `git ls-files` is already cwd-relative *and* cwd-scoped (verified: from `app/` it emits `a.py`, `sub/b.py`, and correctly omits `root.py`). The prescribed `git -C <root>` enumerates the **whole repository** when you asked to scan one subdirectory — a wrong denominator for every metric. | Run with `cwd = <scan target>`; take output as target-relative. Fixture: scanning a subdirectory reports exactly the files under it. |
| **R7** | §4's ">20% ERROR nodes → degraded" is unimplementable as stated. ERROR nodes nest — a 27-byte broken file yields four, summing to 118% of the file. "20% of what" (bytes, lines, node count) is unspecified, and the answer decides which files are scored. | Union of **top-most** `ERROR`/`MISSING` byte ranges ÷ file size. `[parse] degraded_error_ratio = 0.20`. |
| **R29** ✓ | Python 3.14 removed `fork` as a default everywhere, not only on darwin (`spawn` verified here). | Parser cache initialises **lazily inside the worker** on every platform. A worker exception is caught at the worker boundary and returned as `parse_status: "unparsed"` with a reason — rule 3 is decided here, gated at M5. |
| **R30** ✓ | `Point.column` is a **byte** offset; `Point.row` is a line index. | Row-based line classification is safe with non-ASCII source. Any column arithmetic is not — forbid it. |
| **D14** | An `unparsed` file has no comment spans, so every non-blank line classifies as `code` and it reports `comment: 0`. Invariant holds, schema validates, number wrong. | `lines.approximate: true` whenever `parse_status != "ok"`; excluded from comment-ratio aggregates. (Direction note: this inflates `code`, it does not deflate the repo's comment count in a flattering direction — my earlier claim was backwards.) |
| **D12.2** | 1 MB cap / 8 KB binary sniff are constants. | Config keys. |

### M2 — complexity, smells, docs

| ID | Defect | Ruling |
| --- | --- | --- |
| **R10** ✓ | **Python docstrings classify as `code`.** A docstring is a `string` node whose parent is `block` — not a comment node — so §5's rule buckets it as code. `code + comment + blank == total` still holds while the comment ratio of every Python repo is wrong. `cloc`, the stated reference, counts them as comments. | `[lines] docstring_as_comment = true`. Lines covered by a doc-position string with no other content classify as `comment`. Fixture it in both directions. |
| **R12** ✓ | **Java `default:` and `case 1:` are both `switch_label`** — one node type, verified. A `frozenset[str]` cannot distinguish them, so every switch with a default arm over-counts complexity by exactly 1. | Identical in kind to §5's `else` rule and needs identical treatment: `default` is **not** a decision point. Requires text or field inspection, not set membership. Assert in the Java and C# fixtures. |
| **R13** ✓ | **`else if` chains inflate nesting depth.** Java parses `else if` as `if_statement[alternative=if_statement]` — verified, a 3-arm chain is 3 nested `if_statement`s. Flat, readable code reports `max_nesting: 5` at five arms and trips `deep_nesting` (default 4). | An `if_statement` reached via the `alternative` field does not increment depth. |
| **R15** ✓ | §5's stated reason for counting operator *occurrences* is false. `a && b && c \|\| d` is **three** `binary_expression` nodes, one per operator — not "one nested chain". Counting nodes would work fine. | The conclusion (count occurrences) is right; the *reason* is node-kind genericity — Java's `&&` and `\|\|` are both a generic `binary_expression`, whereas Python has a discriminating `boolean_operator`. An implementer following the stated reasoning builds a text scanner. |
| **R6** ✓ | §5's parameter rule is Java-shaped and does not transfer. `@PathVariable Long id` is **one** `formal_parameter` with a nested `modifiers` child — the "naively counts as several" hazard does not exist in Java. Python is the real hazard: parameter children are `identifier`, `default_parameter`, `typed_default_parameter`, `list_splat_pattern`, `dictionary_splat_pattern`, so a plain parameter is a bare `identifier` and the naive count is *correct*. | `parameter_nodes` per language **plus** `param_excludes`. Rule `self`/`cls` and `*args`/`**kwargs` explicitly — otherwise the same 5-collaborator design is 6 params in Python and 5 in Java against a shared `> 5` default, and only the **absolute** threshold feeds the score. |
| **R8** | §9's function record is `{line: 42, end_line: 118, length: 76}` — length computed from the **declaration** start, contradicting §5's body-span rule. And `length` = `end − start` or `+1` is undefined; a one-line body has length 0 and `> 50` is off by one at every boundary. | `line` = declaration (what a human jumps to); `body_line`/`body_end_line` added; `length` = body span, `end − start + 1`. Fixture the one-line body. |
| **D13.2** | My earlier ruling — "outer length excludes the inner subtree" — contradicts §9's own record and makes a 300-line function containing five closures report short, defeating `long_function` exactly where it matters. "Matches every mainstream tool" was asserted and is false. | Split the three metrics: **length** = contiguous body span, nested functions **included**; **complexity** = subtree decision points **minus** nested function subtrees; **max_nesting** = resets at each function node. |
| **D13.1** | My earlier ruling — exclude all anonymous node kinds from `public` — creates the bug it was preventing. ✓ `export const f = () => {}` is an `arrow_function` with **no** `name` field; the name sits on the enclosing `variable_declarator`. Excluding it collapses doc coverage across javascript, typescript and tsx. | The test is **"has no resolvable name"**, not "is an anonymous node kind". Name resolvable from an enclosing binding (`variable_declarator.name`, `pair.key`, `assignment.left`) ⇒ named ⇒ normal `visibility` rule. Only genuinely unnamed callbacks (`arr.map(x => …)`) leave the `public` denominator. This is `ENCLOSING_BINDING` (§2) doing double duty. |
| **D13.3** | — | Nesting depth resets at each function node. |
| **D13.6** | — | Module with zero production files: `score: null`, sorts last, never rendered as a grade. |
| **D12.3** | §9's per-file `doc_coverage` vs §5's "production only". | Computed for every role; only *aggregation* is production-only. |

### M3 — security

| ID | Defect | Ruling |
| --- | --- | --- |
| **R21** | **D11 is withdrawn as a misread** — rule 4 scopes to "threshold, weight and severity"; a deny-list is language data under rule 1, and §3 places it deliberately. The real defect: two of §7's nine dangerous calls — `subprocess.*(shell=True)` and `yaml.load` without a loader — are **argument-sensitive predicates**, and `frozenset[str]` "matched against callee text" cannot express either. | `dangerous_calls` becomes a record: `{callee, arg_name, arg_value, absent_arg}`. Otherwise the tool flags every `subprocess.run(...)` — the false-positive class §7 names as the product risk. Config override stays available but is a feature, not the fix. |
| **R22** | §7's entropy thresholds ("≥ 20 chars", "> 4.0 bits/char") over a raw `string` node measure the quotes and the `f` prefix too. Python `string` has `string_start`/`string_content`/`string_end` children. | `string_content_field` in the profile; entropy measured over content. |
| **R23** | §7 specifies the interpolation guard as **text patterns** (`${…}`, `#{…}`, `{{…}}`, `%(…)s`), contradicting its own "never raw file text" rule two paragraphs earlier. | `interpolation_nodes` in the profile; the guard is structural. Text patterns remain only for languages with no interpolation node. |
| **R24** | `SECRET = "a" "b"` parses as `concatenated_string`, not `string`, so implicit concatenation escapes the direct-RHS detector. | Add to `string_nodes`. |
| **D9** | §8 weights severities; nothing maps a detector to one. | `[security.severity]` keyed `(detector, confidence)`. **§7 demotes *confidence* for non-production roles, not severity** — one axis, and the table is already keyed on it. |

### M4 / M4a — score, calibration, render, packs

| ID | Defect | Ruling |
| --- | --- | --- |
| **R4** | **§6 Layer 2 contradicts itself.** §6 states two lenses "neither impersonating the other" — absolute drives the *score*, relative the *ranking* — then gives one predicate: `flagged ⟺ value > max(absolute_floor, p95)`. Under it, a value above the absolute threshold but below p95 is unflagged and therefore unscored, which is exactly the "uniformly bad codebase reports itself healthy" failure §6 rejects one paragraph later. This is the design's self-declared highest-leverage mechanism. | **Two independent booleans per finding.** `smells[]` absolute and scored; `outliers[]` relative and ranked (schema field per R5). M4's gate tests the relative lens while §5's `> 5` says all of them are smells — both true, and the JSON must express both. |
| **R3** | Three of the four score inputs cannot name their denominator — rule 5 violated by the score itself. `p95_complexity`: no percentile method (nearest-rank vs interpolation differ by a whole point on small n), no population (§8 repo-wide, §9 per-language), no `n` minimum. `smells_per_kloc`: instances or functions-with-≥1? kLOC of `code`, of ok-parsed, of all scanned? A 2× spread on a 15-point term. `pct_functions_over_threshold`: which threshold, and are R6/D13.1's lambdas in the denominator? | Each of `languages[]`, `modules[].totals` and `score.inputs` carries its own `scope`. `p95` = nearest-rank, `[calibrate] min_population = 20`, documented population. |
| **D7** | §13's no-CDN gate greps `http`. The interesting failure is not `xmlns` — it is that the report renders **scanned-repo data**: file paths, function names, and §7 finding messages containing literal URLs, so the gate fires on a real repo regardless of the renderer. **My replacement was also broken** — `href=` bans the in-page drill-down §9 mandates, `src=` bans `data:` URIs. | Assert on *fetchable* references only:<br>`! grep -nEi '(src\|href)[[:space:]]*=[[:space:]]*"(https?:\|//)' report.html`<br>`! grep -nEi '@import\|url\([[:space:]]*["'"'"']?(https?:\|//)\|fetch\(\|<script' report.html`<br>`<script>` banned outright (§9 promises no JS). |
| **R26** | §4 sells `report --role test` as "re-render, no rescan", but the default `--detail threshold` drops non-breaching functions, so **no aggregate is recoverable**. It is a display filter, not a re-derivation. | `report` exits non-zero naming the missing detail rather than rendering a correct-looking partial. Applies to `--role`, `--module` and `--top` alike. |

---

## 2. `LanguageProfile` — corrected spec (M1)

Beyond §3's fields. Populate for all ten languages at M1, including the three not consumed until M4.

| Field | Why | Note |
| --- | --- | --- |
| `assignment_nodes`, `assign_target_field`, `assign_value_field` | §7 direct-RHS rule | ✓ python `assignment{left,right}`; java `variable_declarator{name,value}` |
| `parameter_nodes`, `param_excludes` | §5 param counting | R6 — python needs bare `identifier` in the set |
| `branch_operators` | §5 operator occurrences | R15 — reason is node-kind genericity, not chaining |
| `modifier_field`, `export_ancestors` | `MODIFIER` / `EXPORT` visibility | Java `modifiers` is a **child node, not a field**, and holds annotations. TS `export` is **two ancestors up** (`arrow_function` ← `variable_declarator` ← `lexical_declaration` ← `export_statement`) ✓ — a scalar `export_marker` cannot express it |
| `doc_nodes` | `DOC_NODE` style | Rust's `doc_comment` is reported as a **child of `line_comment`**, so detection is "preceding `line_comment` with a `doc` field", not a sibling node. *Unverified by me — confirm at M1.* For LOC purposes a doc comment **is** a comment |
| `decorator_nodes`, `import_nodes`, `import_source_field` | §6 L3 dictated predicate | §6 asserts "we already parse imports"; nothing in §3/§4 does. Absorbs `wrapper_nodes` |
| `name_field`, `name_strategy` | naming | Three variants: `DIRECT`, `DECLARATOR_DESCENT` (C++), **`ENCLOSING_BINDING`** ✓ (D13.1) |
| `string_content_field`, `interpolation_nodes` | §7 entropy + placeholder guard | R22, R23 |
| `type_container_nodes` | R2 | Matched only when no listed descendant matches |

---

## 3. Config inventory (M0)

Rule 4 is unenforceable if the surface accretes a key per milestone — there is never a moment when the file is known complete. Ship all of it at M0, commented, including keys no analyzer reads until M4a.

```toml
[scan]     max_file_bytes=1048576  binary_sniff_bytes=8192  detail="threshold"
           jobs=0  follow_symlinks=false                                    # D12.2
[parse]    degraded_error_ratio=0.20                                        # R7
[lines]    docstring_as_comment=true                                        # R10
[modules]  enabled=true  manifests=[…§4 table…]  min_for_manifest_grouping=2
[roles]    test=[] generated=[] vendored=[]        # replace; "+" appends    §4
           generated_markers=["@Generated","Code generated by","DO NOT EDIT"]
           generated_sniff_lines=5  stub_extensions=[".pyi",".d.ts"]        # R9
[thresholds] long_function=50 deep_nesting=4 long_parameter_list=5
             high_complexity=10                                             §5
[score]    include_roles=["production"]
           w_complexity=25  complexity_pct_knee=0.15
           w_p95=5  p95_knee="@thresholds.high_complexity"  p95_span=20     # D8 — a reference, not a copy
           w_smells=15  smells_per_kloc_knee=10
           w_docs=10  doc_target=0.80  security_cap=60
           severity_weights={critical=25,high=10,medium=3,low=0}
           grades={A=90,B=80,C=70,D=60}  rounding="half_up"                 # R20
           empty_population="null"  fail_on_empty=false                     # D4
[calibrate] enabled=true percentile=0.95 method="nearest_rank"
            min_population=20                                               # R3 — ranking only, never the score
[security] confidence_floor="medium"  entropy_min_bits=4.0  entropy_min_chars=20
           entropy_allowlist=["uuid","hex_digest","base64_fixed"]
           secret_name_pattern="password|secret|api_key|token|private_key|credential"
           suppress_marker="scanner:ignore"  role_demotes_confidence=true   # D9
[security.severity]  assignment_name.high="high"  token_shape.high="critical"
                     entropy.medium="medium"                                # D9
[security.dangerous_calls.<lang>]                                           # R21 override, "+" convention
[packs]    enabled=true                                                     §6 L4
```

## 4. Schema deltas (M0)

`score.value`/`grade` nullable (D4) · `lines.approximate` (D14) · `files[].smells[].attribution` and `.suppressed_by` (R5) · `files[].outliers[]` (R4) · `scan.packs_active` (R5) · `scan.config` + `config_source` + `config_digest` (R16) · `functions[].body_line`/`body_end_line` (R8) · per-aggregate `scope` on `languages[]`, `modules[].totals`, `score.inputs` (R3).

## 4a. `scripts/check_rules.sh` (M0)

The six ground rules are RESEARCH §11. Three are mechanically checkable; all three shipped vacuous (D2). Corrected — `/usr/bin/grep -E` because this shell's `grep` is ugrep 7.8.4 ✓, and bare `|` because `\|` under `-E` is a literal pipe that matches nothing ✓:

```sh
set -eu
for d in code_scanner/render code_scanner/languages/defs code_scanner; do
  [ -d "$d" ] || { echo "FAIL: $d missing — check is vacuous"; exit 1; }   # D2
done
! /usr/bin/grep -rE "(from|import).*\b(parse|analyze)\b" code_scanner/render/          # rule 2
! /usr/bin/grep -rE "^[[:space:]]*(def|if|for|while) " code_scanner/languages/defs/    # rule 1
! /usr/bin/grep -rilE "spring|fastapi|django|rails|nest" code_scanner/ \
      --exclude-dir=packs                                                             # rule 6
```

Rule 6 excludes `packs/` only — the one tree §6 L4 authorises. `languages/defs/` stays **in** scope: a framework name there is a genuine rule-1 violation.

---

## 5. Milestones

| | Deliverables | Gate |
| --- | --- | --- |
| **M0**<br>*7%* | venv · `pyproject.toml` (4 runtime + dev group) · `schema/result.schema.json` **with §4's deltas** · full `.codescanner.toml` · `model.py` incl. `Observations` · `config.py` · `cli.py` · `render/json_out.py` · line-count-only python path · `scripts/check_rules.sh` | `pytest tests/test_schema.py`; `scripts/check_rules.sh` exits 0 |
| **M1**<br>*18%* | `languages/profile.py` (§2 spec) · `defs/` ×10 · `parse/session.py` · `parse/lines.py` · `discover/{walk,modules,roles}.py` · `aggregate/rollup.py` · pool fan-out · multimodule fixture · **committed grammar enumeration fixture** (R28) | `pytest tests/test_{discovery,roles,modules}.py` — 10 grammars load; 3 modules, 4 roles, `DO NOT EDIT` sniff, nested `.gitignore`; **subdirectory scan reports only files under it** (D12.1); LOC property test ×10 |
| **M2a**<br>*12%* | `parse/walk.py` → `Observations` · `analyze/complexity.py` · branch/nesting sets for python + java | `pytest tests/test_golden.py -k "python or java"` **plus a walk-count assertion: one traversal per file, not one per analyzer** |
| **M2b**<br>*17%* | `analyze/{smells,docs}.py` · 8 remaining profiles · 10 golden fixtures | `pytest tests/test_golden.py` — all ten exact, incl. `else`, `default:` (R12), else-if nesting (R13), docstrings (R10), interface methods (R14), one-line body (R8) |
| **M3**<br>*12%* | `analyze/security/{secrets,dangerous_calls}.py` · direct-RHS on §2's fields · token shapes · entropy over `string_content` · `# scanner:ignore` · D9 table | `pytest tests/test_security.py` — every planted secret found **and** `scan tests/fixtures/clean` yields zero findings. The suite's only false-positive constraint; not relaxed |
| **M4**<br>*19%* | `aggregate/score.py` · `aggregate/calibrate.py` (two booleans, R4) · `render/{html,markdown,csv_out}.py` + `charts.py` | `--fail-under 101` exits 1, `0` exits 0; D7's fetch-only greps empty; `pytest tests/test_relative.py`; R1's corrected score assertion |
| **M4a**<br>*9%* | `packs/loader.py` (suppress-only in code) · `packs/defs/{spring,fastapi}.toml` · L3 predicate · 2 framework fixtures | `scripts/check_rules.sh`; framework fixtures yield zero `long_parameter_list`, findings **present with `suppressed_by`** (not deleted), reappearing unsuppressed under `--no-packs` |
| **M5**<br>*6%* | Failure paths: truncated, binary-as-`.py`, empty, no trailing newline, symlink loop, unreadable, non-UTF-8 · runtime-import audit (exactly 4) | `pytest` green; `scan <large real repo>` without exception |

**Golden-fixture provenance (M2b).** A 12-function Java `expected.json` is not credibly hand-written, but one generated by the code under test asserts only self-agreement. The asserted edge cases above are **hand-written first and must fail against a stub**; bulk is generated once and reviewed in the same change. No `--update-golden`.

---

## 6. Schedule

**Critical path:** M0 → M1 → M2a → M2b → M3 → M4. Only M4a can move.

**The two that overrun:** M2 (29% combined, and where wrong numbers are born — split so slippage shows at M2a); M4's HTML, where §9 fixes the bar at correct/accessible/readable and it is not renegotiated for polish.

**Cut order** (§0, unchanged): §6 Layer 4 → §6 Layer 2 → §4's directory grouping. **Never cut a menu feature to preserve infrastructure.** So M4a drops first, calibration second. §2's profile fields stay regardless — they make reinstating L3 a code change, not a migration.
