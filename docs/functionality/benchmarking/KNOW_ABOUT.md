# Know About — Benchmarking (`benchmarks/`)

- Out-of-core by design (`benchmarks/run_benchmark.py`,
  `benchmarks/run_live_holdout.py`) — never imported by `cdp/`.
- `--allowedTools` pattern matching is a leading-literal match, not substring
  — a model that prefixes its command with `cd ... &&` silently defeats an
  allowlist scoped too narrowly, making an experimental arm behave like the
  baseline without erroring.
- A benchmark harness running with cwd inside the CDP repo itself risks the
  reader model reading the benchmark's own gold-answer file directly off
  disk — must scope tools tightly enough (`--tools Bash` only, forcing every
  answer through the real query surface) to prevent contamination.
