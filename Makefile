# `make check` is the single command every later phase must keep green.
#
# PHASE/phase_0_plan.md M0.5. The gates, and what each one catches that the
# others do not:
#
#   selftest      the bundled suite, with a floor on the test count so it
#                 cannot report success having run nothing
#   distribution  .claude/skills/cdp/ is byte-identical to the source tree
#   determinism   two scans of one commit agree byte-for-byte
#   fold          state.json = fold(merge, patches/, xref.json), and the merge
#                 is order-independent -- which determinism alone cannot show,
#                 since an order-dependent merge is deterministic-but-arbitrary
#   golden        the answers did not change
#
# Set TARGET_REPO to run the gates against real non-fixture input as well:
#
#   make check TARGET_REPO=/path/to/repo
#
# PHASE/TARGET.md pins the target this baseline was captured from.

PYTHON ?= python3
CDP    := $(PYTHON) -m cdp.cli
FIXTURE := tests/fixtures/minirepo
FIXTURE_SLUG := minirepo@fixture

.PHONY: check check-fast selftest distribution determinism fold golden \
        bless bless-fixture check-self clean help

## check: every gate. Green is the contract for every later phase.
check: selftest determinism fold golden
	@echo
	@echo "OK    all gates green$(if $(TARGET_REPO), (including $(TARGET_REPO)),, fixture only -- set TARGET_REPO for real input)"

## check-fast: everything except the scans. For a tight edit loop.
check-fast: selftest

## selftest: the bundled suite. Fails below cdp.cli.MIN_TESTS.
selftest:
	@echo "== selftest =="
	@$(CDP) selftest

## distribution: the vendored skill copy has not drifted. (Also inside selftest.)
distribution:
	@echo "== distribution =="
	@$(PYTHON) -m unittest discover -s tests -t tests -k VendoredCopy -v

## determinism: two scans of one commit agree.
determinism:
	@echo "== determinism (fixture) =="
	@$(PYTHON) scripts/fixture_gate.py determinism
ifneq ($(TARGET_REPO),)
	@echo "== determinism ($(TARGET_REPO)) =="
	@$(CDP) selftest --determinism "$(TARGET_REPO)"
endif

## fold: the fold invariant and order-independence, on a real scan.
fold:
	@echo "== fold --check (fixture) =="
	@$(PYTHON) scripts/fixture_gate.py fold
ifneq ($(TARGET_REPO),)
	@echo "== fold --check ($(TARGET_REPO)) =="
	@rm -rf .cdp-check && $(CDP) scan --repo "$(TARGET_REPO)" --state-dir .cdp-check --quiet \
	  && $(CDP) fold --check --repo "$(TARGET_REPO)" --state-dir .cdp-check && rm -rf .cdp-check
endif

## golden: output still matches the blessed baseline.
golden:
	@echo "== golden (fixture) =="
	@$(PYTHON) scripts/fixture_gate.py golden
ifneq ($(TARGET_REPO),)
	@echo "== golden ($(TARGET_REPO)) =="
	@$(CDP) selftest --golden "$(TARGET_REPO)"
endif

## bless: re-capture every baseline. Never run by check; always explicit.
bless: bless-fixture
ifneq ($(TARGET_REPO),)
	@$(CDP) selftest --golden "$(TARGET_REPO)" --bless
endif

bless-fixture:
	@$(PYTHON) scripts/fixture_gate.py bless

## check-self: demonstrate PHASE/FINDINGS.md F1. Expected to FAIL, and is not
## part of `check`: this repository has two modules named `core` since M0.1
## vendored a second copy of the fixture, and cdp/graph.py:180 resolves
## duplicate basenames out of a set.
check-self:
	@echo "== determinism (this repository -- expected to be flaky, see FINDINGS.md F1) =="
	@for i in 1 2 3 4 5 6; do \
	  $(CDP) selftest --determinism . >/dev/null 2>&1 && echo "  run $$i: agreed" || echo "  run $$i: DIFFERED"; \
	done

clean:
	@rm -rf .cdp .cdp-check
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +

help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'
