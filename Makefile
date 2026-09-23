SHELL := /bin/sh
UV ?= uv
UV_SYNC := $(UV) sync --frozen
UV_RUN := $(UV) run --frozen
FILES ?= 10000
HOT_REQUESTS ?= 20
TEST_SHARDS ?= 64
DEV_BATCH_SIZE ?= 4
DEV_BATCH_START ?= 0
ARTIFACT_PYTHON ?= 3.14
OPENCODE ?= opencode
OPENCODE_MODEL ?=
OPENCODE_HOST_PYTHON ?= $(ARTIFACT_PYTHON)
OPENCODE_HOST_RECEIPT ?= dist/opencode-mcp-host-gate.json
CLAUDE ?= claude
CLAUDE_MODEL ?=
CLAUDE_HOST_PYTHON ?= $(ARTIFACT_PYTHON)
CLAUDE_HOST_RECEIPT ?= dist/claude-mcp-host-gate.json
CODEX ?= codex
CODEX_MODEL ?=
CODEX_HOST_PYTHON ?= $(ARTIFACT_PYTHON)
CODEX_HOST_RECEIPT ?= dist/codex-mcp-host-gate.json
CODEX_HOST_DANGEROUS ?= 0
PI ?= pi
PI_MODEL ?=
PI_HOST_PYTHON ?= $(ARTIFACT_PYTHON)
PI_HOST_RECEIPT ?= dist/pi-mcp-host-gate.json
DIAGNOSTIC_PYTHON ?= python3
DIAGNOSTIC_SHARDS ?= 64
DIAGNOSTIC_BATCH ?= 0
DIAGNOSTIC_BATCH_LIMIT ?= 8
DIAGNOSTIC_SHARD ?= 0
DIAGNOSTIC_EXTRA_MARKER ?=
RUFF_DEBT_PREVIOUS_BASELINE ?=

.PHONY: help evaluation-help lock lock-check init setup bootstrap check baseline start stop doctor compile map map-status map-watch agent-runner-journal-help lint ruff ruff-check ruff-format-check source-hygiene typecheck ty-check pyright-check precommit hooks-install lint-debt lint-debt-summary lint-debt-json lint-debt-gate test test-native test-diagnostic test-diagnostic-capabilities test-diagnostic-batch test-diagnostic-shard test-profile test-shard-plan test-shard dev-check dev-check-batch dev-check-tests artifact-check mcp-opencode-check mcp-claude-check mcp-codex-check mcp-pi-check mcp-host-status mcp-concurrency-stress release-check verify metrics metrics-fast metrics-scale metrics-500k metrics-agent metrics-agent-corpus metrics-fresh-multi-repo metrics-blind-worker-ab metrics-worker-behavior-ab metrics-worker-inspection-ab metrics-worker-multistep-ab metrics-worker-failed-verification-ab metrics-agent-economics metrics-bm25-economics metrics-bm25-constrained metrics-agent-suite metrics-agent-trace metrics-agent-experiment metrics-agent-experiment-set metrics-agent-trace-normalize metrics-agent-regret metrics-agent-regret-suite metrics-compare clean-metrics

help:
	@printf '%s\n' \
	  'Hashmarks developer commands' \
	  '' \
	  '  make lock           Intentionally refresh committed uv.lock and sync the test environment' \
	  '  make lock-check     Check pyproject.toml ↔ committed uv.lock convergence without rewriting' \
	  '  make init           Materialize the test environment from committed uv.lock' \
	  '  make setup          Prepare local test environment and runtime doctor' \
	  '  make test           Run authoritative normal OSS tests; HASHMARKS_CONSTRAINED_HOST=1 selects hosted diagnostics' \
	  '  make test-diagnostic  Run all capability-aware hosted diagnostic shards (never release authority)' \
	  '  make test-diagnostic-batch DIAGNOSTIC_BATCH=0  Run a bounded hosted diagnostic batch' \
	  '  make test-diagnostic-shard DIAGNOSTIC_SHARD=12  Run one hosted diagnostic shard' \
	  '  make test-diagnostic-capabilities  Show hosted capability inventory' \
	  '  make test-profile   Run full suite and report slowest 25 tests >=1s' \
	  '  make check          Junior-friendly local check: setup + compile + CodeMap + tests' \
	  '  make bootstrap      Offline runtime-only bootstrap (CI/prepared environments)' \
	  '  make baseline       Bootstrap + quick metrics baseline' \
	  '  make start          Bootstrap and start the identity daemon' \
	  '  make stop           Stop the identity daemon' \
	  '  make doctor         Show resolved runtime/daemon state' \
	  '  make compile        Compile Hashmarks source, scripts, benchmarks, and tests' \
	  '  make map            Sync the derived repository CodeMap' \
	  '  make map-status     Show CodeMap generation/staleness' \
	  '  make map-watch      Maintain CodeMap incrementally in foreground' \
	  '  make lint           Run the canonical project Ruff check' \
	  '  make ruff           Run all Ruff diagnostics locally (check + format)' \
	  '  make ruff-check     Run blocking Ruff correctness/import checks' \
	  '  make ruff-format-check  Run non-blocking Ruff formatting diagnostic' \
	  '  make source-hygiene Run dependency-free LF + Python syntax checks' \
	  '  make typecheck      Run ty and Pyright on live repository Python' \
	  '  make precommit      Run all configured pre-commit hooks on tracked files' \
	  '  make hooks-install  Install the local Git pre-commit hook' \
	  '  make lint-debt      Show current Ruff complexity debt inventory' \
	  '  make lint-debt-summary  Show concise current Ruff debt diagnostic' \
	  '  make lint-debt-json  Show exact current Ruff debt JSON (diagnostic)' \
	  '  make lint-debt-gate Enforce that legacy Ruff debt never increases' \
	  '  make test-shard-plan  Show deterministic bounded pytest shards (TEST_SHARDS=64)' \
	  '  make test-shard TEST_SHARD=0  Run exactly one deterministic shard' \
	  '  make dev-check-batch DEV_BATCH=0  Run one resumable group of deterministic shards' \
	  '  make dev-check-tests DEV_BATCH_START=0  Resume bounded test batches from one batch index' \
	  '  make dev-check      One-command developer PASS/FAIL: sync + doctor + compile + CodeMap + bounded tests' \
	  '  make artifact-check Build wheel/sdist and smoke-test each in a clean isolated environment' \
	  '  make mcp-opencode-check  Qualify the installed MCP wheel through a real OpenCode host' \
	  '  make mcp-claude-check  Qualify the installed MCP wheel through Claude Code' \
	  '  make mcp-codex-check  Qualify the installed MCP wheel through Codex CLI' \
	  '  make mcp-pi-check  Qualify the installed MCP wheel through Pi + pi-mcp-adapter' \
	  '  make mcp-host-status  Inspect project-local OpenCode/Claude/Codex/Pi MCP integration state' \
	  '  make mcp-concurrency-stress  Stress concurrent MCP-style readers during live repository mutation' \
	  '  make release-check  Local release preflight; does not replace canonical artifact/readback proof' \
	  '  make verify         Alias for make dev-check' \
	  '  make metrics-fast   Quick baseline without daemon benchmarks' \
	  '  make metrics-500k   Explicit heavy 500k repository-intelligence baseline' \
	  '  make metrics        Quick 10k repository-intelligence baseline including daemon + impact metrics' \
	  '  make metrics-scale  100k repository-intelligence baseline' \
	  '  make evaluation-help  Show external-agent/research evaluation targets' \
	  '' \
	  'Override FILES/HOT_REQUESTS, e.g. make metrics FILES=50000 HOT_REQUESTS=50'

evaluation-help:
	@printf '%s\n' \
	  'Hashmarks external-agent / research evaluation targets' \
	  '' \
	  'These targets measure external consumers; they are not installed product APIs or agent workflow authority.' \
	  '  make metrics-agent' \
	  '  make metrics-agent-corpus' \
	  '  make metrics-fresh-multi-repo' \
	  '  make metrics-blind-worker-ab' \
	  '  make metrics-worker-behavior-ab' \
	  '  make metrics-worker-inspection-ab' \
	  '  make metrics-worker-multistep-ab' \
	  '  make metrics-worker-failed-verification-ab' \
	  '  make metrics-agent-economics' \
	  '  make metrics-context-economics-csv  Project Codex economics evidence to CSV' \
	  '  make splunk-csv-dogfood  Stream masked Splunk CSV into bounded evidence' \
	  '  make metrics-bm25-economics' \
	  '  make metrics-agent-suite' \
	  '  make metrics-agent-trace' \
	  '  make metrics-agent-experiment' \
	  '  make metrics-agent-experiment-set' \
	  '  make metrics-agent-regret' \
	  '  make metrics-agent-regret-suite' \
	  '  make codex-agent-economics-preflight' \
	  '  make codex-agent-economics'

lock:
	@$(UV) lock
	@$(UV_SYNC) --group test
	@printf '%s\n' 'Hashmarks committed uv.lock refreshed and test environment synced.'

lock-check:
	@$(UV) lock --check
	@printf '%s\n' 'Hashmarks pyproject.toml and committed uv.lock are converged.'

init:
	@$(UV_SYNC) --group test
	@printf '%s\n' 'Hashmarks dependency environment ready from committed uv.lock.'

setup: init
	@$(MAKE) --no-print-directory doctor >/dev/null
	@printf '%s\n' 'Hashmarks setup ready. Run: make test   or   make check'

bootstrap:
	@test -f uv.lock || (echo "committed uv.lock is missing; restore the repository checkout before bootstrap" >&2; exit 2)
	@$(UV_SYNC) --offline --group test
	@$(MAKE) --no-print-directory doctor >/dev/null
	@printf '%s\n' 'Hashmarks bootstrap ready (offline, committed locked supply).'

baseline: metrics

start: bootstrap
	@$(UV_RUN) --offline hashmarks daemon start --workspace .

stop:
	@$(UV_RUN) --offline hashmarks daemon stop --workspace .

doctor:
	@$(UV_RUN) --offline hashmarks doctor --workspace . --mode local

compile:
	@$(UV_RUN) --offline python -m compileall -q hashmarks scripts benchmarks tests

map:
	@$(UV_RUN) --offline hashmarks --workspace . map sync

map-status:
	@$(UV_RUN) --offline hashmarks --workspace . map status

map-watch:
	@$(UV_RUN) --offline hashmarks --workspace . map watch

agent-runner-journal-help: bootstrap
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.agent_runner_journal --help

ruff-check:
	@UV_PROJECT_ENVIRONMENT=.ruff-venv $(UV_RUN) --only-group lint ruff check .

ruff-format-check:
	@UV_PROJECT_ENVIRONMENT=.ruff-venv $(UV_RUN) --only-group lint ruff format --check .

ruff: ruff-check ruff-format-check

lint: ruff

source-hygiene:
	@git ls-files -z -- '*.py' '*.pyi' | xargs -0 -r python3 -m scripts.source_hygiene
	@git diff --check

ty-check:
	@$(UV_RUN) --python 3.11 --group typing ty check .

pyright-check:
	@$(UV_RUN) --python 3.11 --group typing pyright

typecheck: ty-check pyright-check

precommit:
	@UV_PROJECT_ENVIRONMENT=.pre-commit-venv $(UV_SYNC) --only-group hooks
	@.pre-commit-venv/bin/pre-commit run --all-files

hooks-install:
	@UV_PROJECT_ENVIRONMENT=.pre-commit-venv $(UV_SYNC) --only-group hooks
	@.pre-commit-venv/bin/pre-commit install

lint-debt:
	@UV_PROJECT_ENVIRONMENT=.ruff-venv $(UV_RUN) --only-group lint python -m scripts.ruff_debt

lint-debt-summary:
	@UV_PROJECT_ENVIRONMENT=.ruff-venv $(UV_RUN) --only-group lint python -m scripts.ruff_debt --summary-only

lint-debt-json:
	@UV_PROJECT_ENVIRONMENT=.ruff-venv $(UV_RUN) --only-group lint python -m scripts.ruff_debt --json; status=$$?; test $$status -eq 0 -o $$status -eq 1

lint-debt-gate:
	@UV_PROJECT_ENVIRONMENT=.ruff-venv $(UV_RUN) --only-group lint python -m scripts.ruff_debt --baseline ruff-debt-baseline.json $(if $(strip $(RUFF_DEBT_PREVIOUS_BASELINE)),--previous-baseline "$(RUFF_DEBT_PREVIOUS_BASELINE)",)

test:
	@if [ "$${HASHMARKS_CONSTRAINED_HOST:-0}" = "1" ]; then \
		$(MAKE) --no-print-directory test-diagnostic; \
	else \
		$(MAKE) --no-print-directory test-native; \
	fi

test-native:
	@$(UV_RUN) --offline --no-sync --group test python -m pytest -q

test-diagnostic-capabilities:
	@$(DIAGNOSTIC_PYTHON) -m scripts.hosted_diagnostic --capabilities

test-diagnostic:
	@$(DIAGNOSTIC_PYTHON) -m scripts.hosted_diagnostic \
	  --shards $(DIAGNOSTIC_SHARDS) \
	  --extra-marker '$(DIAGNOSTIC_EXTRA_MARKER)'

test-diagnostic-batch:
	@start=$$(( $(DIAGNOSTIC_BATCH) * $(DIAGNOSTIC_BATCH_LIMIT) )); \
	$(DIAGNOSTIC_PYTHON) -m scripts.hosted_diagnostic \
	  --shards $(DIAGNOSTIC_SHARDS) \
	  --start $$start \
	  --limit $(DIAGNOSTIC_BATCH_LIMIT) \
	  --extra-marker '$(DIAGNOSTIC_EXTRA_MARKER)'

test-diagnostic-shard:
	@$(DIAGNOSTIC_PYTHON) -m scripts.hosted_diagnostic \
	  --shards $(DIAGNOSTIC_SHARDS) \
	  --start $(DIAGNOSTIC_SHARD) \
	  --limit 1 \
	  --extra-marker '$(DIAGNOSTIC_EXTRA_MARKER)'

test-profile:
	@$(UV_RUN) --offline --no-sync --group test python scripts/qualification_filesystem.py
	@$(UV_RUN) --offline --no-sync --group test python -m pytest -q --durations=25 --durations-min=1.0

test-shard-plan:
	@$(UV_RUN) --offline python scripts/test_shards.py --shards $(TEST_SHARDS)

test-shard:
	@test -n "$$TEST_SHARD" || (echo "TEST_SHARD is required (0-based)" >&2; exit 2)
	@FILES=`$(UV_RUN) --offline python scripts/test_shards.py --shards $(TEST_SHARDS) --shard $$TEST_SHARD`; \
	$(UV_RUN) --offline --no-sync --group test python -m pytest -q $$FILES

check: setup
	@printf '%s\n' '=== HASHMARKS LOCAL CHECK ==='
	@printf '%s\n' '[1/3] Compile'
	@$(MAKE) --no-print-directory compile
	@printf '%s\n' '[2/3] CodeMap'
	@$(MAKE) --no-print-directory map >/dev/null
	@printf '%s\n' '[3/3] Tests'
	@$(MAKE) --no-print-directory test
	@printf '%s\n' 'HASHMARKS LOCAL CHECK: PASS'

dev-check: setup
	@printf '%s\n' '=== HASHMARKS DEV CHECK ==='
	@printf '%s\n' '[1/4] Compile'
	@$(MAKE) --no-print-directory compile
	@printf '%s\n' '[2/4] Ruff debt no-growth gate'
	@$(MAKE) --no-print-directory lint-debt-gate
	@printf '%s\n' '[3/4] CodeMap sync'
	@$(MAKE) --no-print-directory map >/dev/null
	@printf '%s\n' '[4/4] Deterministic resumable pytest batches ($(TEST_SHARDS) shards, $(DEV_BATCH_SIZE) shards/batch)'
	@$(MAKE) --no-print-directory dev-check-tests
	@VERSION=`$(UV_RUN) --offline hashmarks version`; \
	printf '\n%s\n' '========================================' " HASHMARKS DEV CHECK: PASS ($$VERSION)" ' Setup:       PASS' ' Compile:     PASS' ' Ruff debt:   PASS (no growth)' ' CodeMap:     PASS' ' Tests:       PASS' '========================================'

dev-check-batch:
	@test -n "$(DEV_BATCH)" || (echo "DEV_BATCH is required (0-based)" >&2; exit 2)
	@set -e; \
	batch=$(DEV_BATCH); \
	start=$$((batch * $(DEV_BATCH_SIZE))); \
	if [ $$start -ge $(TEST_SHARDS) ]; then \
		echo "DEV_BATCH $$batch starts beyond TEST_SHARDS=$(TEST_SHARDS)" >&2; exit 2; \
	fi; \
	end=$$((start + $(DEV_BATCH_SIZE))); \
	if [ $$end -gt $(TEST_SHARDS) ]; then end=$(TEST_SHARDS); fi; \
	printf '\n=== DEV TEST BATCH %s: shards %s..%s ===\n' "$$batch" "$$start" "$$((end - 1))"; \
	i=$$start; \
	while [ $$i -lt $$end ]; do \
		printf '%s\n' "--- TEST SHARD $$((i + 1))/$(TEST_SHARDS) ---"; \
		if ! TEST_SHARD=$$i $(MAKE) --no-print-directory test-shard; then \
			printf '\n%s\n' '========================================' ' HASHMARKS DEV BATCH: FAIL' " Failed shard: $$i/$(TEST_SHARDS)" " Reproduce batch: make dev-check-batch DEV_BATCH=$$batch" " Reproduce: make test-shard TEST_SHARD=$$i" '========================================'; \
			exit 1; \
		fi; \
		i=$$((i + 1)); \
	done; \
	printf '=== DEV TEST BATCH %s: PASS ===\n' "$$batch"

dev-check-tests:
	@set -e; \
	batch=$(DEV_BATCH_START); \
	while [ $$((batch * $(DEV_BATCH_SIZE))) -lt $(TEST_SHARDS) ]; do \
		if ! $(MAKE) --no-print-directory dev-check-batch DEV_BATCH=$$batch; then \
			printf '\n%s\n' '========================================' ' HASHMARKS DEV CHECK: FAIL' " Failed stage: dev test batch $$batch" " Reproduce only this batch: make dev-check-batch DEV_BATCH=$$batch" " Resume after it passes: make dev-check-tests DEV_BATCH_START=$$((batch + 1))" '========================================'; \
			exit 1; \
		fi; \
		batch=$$((batch + 1)); \
	done

artifact-check:
	@set -eu; \
	rm -rf dist .artifact-check-wheel .artifact-check-sdist; \
	trap 'rm -rf .artifact-check-wheel .artifact-check-sdist' EXIT INT TERM; \
	$(UV) build --out-dir dist; \
	wheel=$$(find dist -maxdepth 1 -type f -name '*.whl' -print -quit); \
	sdist=$$(find dist -maxdepth 1 -type f -name '*.tar.gz' -print -quit); \
	test -n "$$wheel" -a -n "$$sdist"; \
	$(UV) venv --python $(ARTIFACT_PYTHON) .artifact-check-wheel >/dev/null; \
	$(UV) pip install --offline --python .artifact-check-wheel/bin/python "$$wheel" >/dev/null; \
	.artifact-check-wheel/bin/python -I scripts/installed_artifact_smoke.py; \
	$(UV) venv --python $(ARTIFACT_PYTHON) .artifact-check-sdist >/dev/null; \
	$(UV) pip install --offline --python .artifact-check-sdist/bin/python "$$sdist" >/dev/null; \
	.artifact-check-sdist/bin/python -I scripts/installed_artifact_smoke.py; \
	printf '%s\n' 'Hashmarks installed-artifact qualification: PASS (wheel + sdist).'

mcp-host-status:
	@$(UV_RUN) --offline --no-sync python scripts/mcp_host_status.py --workspace .

mcp-concurrency-stress:
	@$(UV_RUN) --offline --no-sync python scripts/mcp_concurrency_stress.py

mcp-opencode-check:
	@test -n "$(OPENCODE_MODEL)" || (echo "OPENCODE_MODEL is required; choose a tool-capable model from: opencode models" >&2; exit 2)
	@$(UV_RUN) --offline --no-sync python scripts/host_qualification/opencode_mcp_host_gate.py \
	  --uv "$(UV)" \
	  --opencode "$(OPENCODE)" \
	  --model "$(OPENCODE_MODEL)" \
	  --python "$(OPENCODE_HOST_PYTHON)" \
	  --receipt "$(OPENCODE_HOST_RECEIPT)"

mcp-claude-check:
	@$(UV_RUN) --offline --no-sync python scripts/host_qualification/claude_mcp_host_gate.py \
	  --uv "$(UV)" \
	  --claude "$(CLAUDE)" \
	  --model "$(CLAUDE_MODEL)" \
	  --python "$(CLAUDE_HOST_PYTHON)" \
	  --receipt "$(CLAUDE_HOST_RECEIPT)"

mcp-codex-check:
	@$(UV_RUN) --offline --no-sync python scripts/host_qualification/codex_mcp_host_gate.py \
	  --uv "$(UV)" \
	  --codex "$(CODEX)" \
	  --model "$(CODEX_MODEL)" \
	  --python "$(CODEX_HOST_PYTHON)" \
	  $(if $(filter 1 true yes,$(CODEX_HOST_DANGEROUS)),--dangerous-bypass,) \
	  --receipt "$(CODEX_HOST_RECEIPT)"

mcp-pi-check:
	@test -n "$(PI_MODEL)" || (echo "PI_MODEL is required; choose a model from: pi --list-models" >&2; exit 2)
	@$(UV_RUN) --offline --no-sync python scripts/host_qualification/pi_mcp_host_gate.py \
	  --uv "$(UV)" \
	  --pi "$(PI)" \
	  --model "$(PI_MODEL)" \
	  --python "$(PI_HOST_PYTHON)" \
	  --receipt "$(PI_HOST_RECEIPT)"

release-check: dev-check artifact-check
	@printf '\n%s\n' \
	  '========================================' \
	  ' HASHMARKS RELEASE CHECK: LOCAL PREFLIGHT PASS' \
	  ' Canonical promotion still requires deterministic artifact,' \
	  ' exact-parent replay/package proof, persistence, and readback.' \
	  '========================================'

verify: dev-check

metrics: bootstrap
	@$(UV_RUN) --offline python scripts/metrics.py --files $(FILES) --hot-requests $(HOT_REQUESTS)

metrics-fast: bootstrap
	@$(UV_RUN) --offline python scripts/metrics.py --files $(FILES) --hot-requests $(HOT_REQUESTS) --skip-daemon

metrics-scale:
	@$(MAKE) metrics FILES=100000 HOT_REQUESTS=20

metrics-500k:
	@$(MAKE) metrics FILES=500000 HOT_REQUESTS=20

metrics-agent: bootstrap
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent --files 1000 --budget 1000

metrics-agent-corpus: bootstrap
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent_corpus --workspace . --corpus benchmarks/agent_tasks.json --budget 1200

metrics-fresh-multi-repo: bootstrap
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_fresh_multi_repo \
	  --root .hashmarks/benchmarks/fresh-multi-repo \
	  --budget 1200 --limit 20 \
	  --min-file-recall 1 --min-symbol-recall 1 --max-fallback-rate 0 \
	  --output .hashmarks/metrics/fresh-multi-repo-latest.json

metrics-blind-worker-ab: bootstrap
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_blind_worker_ab \
	  --root .hashmarks/benchmarks/blind-worker-ab \
	  --limit 20 \
	  --output .hashmarks/metrics/blind-worker-ab-latest.json

metrics-worker-behavior-ab: bootstrap
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_worker_behavior_ab \
	  --root .hashmarks/benchmarks/worker-behavior-ab \
	  --limit 20 \
	  --output .hashmarks/metrics/worker-behavior-ab-latest.json

metrics-worker-inspection-ab: bootstrap
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_worker_inspection_ab \
	  --root .hashmarks/benchmarks/worker-inspection-ab \
	  --limit 20 \
	  --output .hashmarks/metrics/worker-inspection-ab-latest.json

metrics-worker-multistep-ab: bootstrap
	$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_worker_multistep_ab \
	  --root .hashmarks/benchmarks/worker-multistep-ab \
	  --output .hashmarks/metrics/worker-multistep-ab-latest.json

metrics-worker-failed-verification-ab: bootstrap
	$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_worker_failed_verification_ab \
	  --root .hashmarks/benchmarks/worker-failed-verification-ab \
	  --output .hashmarks/metrics/worker-failed-verification-ab-latest.json

metrics-agent-economics: bootstrap
	$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent_economics \
	  --root .hashmarks/benchmarks/agent-economics \
	  --mode paired \
	  --output .hashmarks/metrics/agent-economics-latest.json

metrics-bm25-economics: bootstrap
	$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_bm25_economics \
	  --root .hashmarks/benchmarks/bm25-economics \
	  --output .hashmarks/metrics/bm25-economics-latest.json

metrics-bm25-constrained: bootstrap
	$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_bm25_constrained --root .hashmarks/benchmarks/bm25-constrained --output .hashmarks/metrics/bm25-constrained-latest.json

metrics-agent-suite: bootstrap
	@test -n "$(OH_GOON)" || (echo "OH_GOON is required, e.g. make metrics-agent-suite OH_GOON=/path/to/oh-goon" >&2; exit 2)
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent_suite \
	  --repo "hashmarks=.::benchmarks/agent_tasks.json" \
	  --repo "oh-goon=$(OH_GOON)::benchmarks/external/oh_goon_1267_0_49_agent_tasks.json" \
	  --budget 1200 --limit 20 \
	  --min-file-recall 1 --min-symbol-recall 1 --max-fallback-rate 0 \
	  --max-average-find-ms 60 --max-average-context-ms 80 \
	  --output .hashmarks/metrics/agent-suite-latest.json

metrics-agent-trace: bootstrap
	@test -n "$(TRACE_FILES)" || (echo "TRACE_FILES is required" >&2; exit 2)
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent_trace $(TRACE_FILES) $(foreach v,$(TRACE_VERDICTS),--verdict $(v)) $(foreach u,$(TRACE_USAGES),--usage $(u)) --strict --output .hashmarks/metrics/agent-trace-latest.json

metrics-agent-experiment: bootstrap
	@test -n "$(EXPERIMENT)" || (echo "EXPERIMENT is required" >&2; exit 2)
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent_experiment "$(EXPERIMENT)" --strict-raw-evidence --output .hashmarks/metrics/agent-experiment-latest.json

metrics-agent-experiment-set: bootstrap
	@test -n "$(EXPERIMENT_SET)" || (echo "EXPERIMENT_SET is required" >&2; exit 2)
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent_experiment_set "$(EXPERIMENT_SET)" --output .hashmarks/metrics/agent-experiment-set-latest.json

metrics-agent-trace-normalize: bootstrap
	@test -n "$(RUNNER_LOG)" || (echo "RUNNER_LOG is required" >&2; exit 2)
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.normalize_agent_trace "$(RUNNER_LOG)" --output .hashmarks/metrics/agent-trace-normalized-latest.json

metrics-agent-regret: bootstrap
	@test -n "$(TRACE)" || (echo "TRACE is required" >&2; exit 2)
	@test -n "$(EVIDENCE)" || (echo "EVIDENCE is required" >&2; exit 2)
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent_regret "$(TRACE)" "$(EVIDENCE)" --output .hashmarks/metrics/agent-regret-latest.json

metrics-agent-regret-suite: bootstrap
	@test -n "$(REGRET_SUITE)" || (echo "REGRET_SUITE is required" >&2; exit 2)
	@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent_regret_suite "$(REGRET_SUITE)" --output .hashmarks/metrics/agent-regret-suite-latest.json

metrics-compare:
	@test -n "$(BASE)" || (echo "BASE is required, e.g. make metrics-compare BASE=.hashmarks/metrics/baseline-old.json" >&2; exit 2)
	@$(UV_RUN) --offline python scripts/compare_metrics.py --baseline "$(BASE)" --current .hashmarks/metrics/latest.json

clean-metrics:
	@rm -rf .hashmarks/metrics

.PHONY: codex-agent-economics-preflight codex-agent-economics
codex-agent-economics-preflight:
	$(UV_RUN) --offline python -m scripts.agent_evaluation.codex_agent_economics --preflight --output .hashmarks/metrics/codex-agent-preflight.json

codex-agent-economics:
	$(UV_RUN) --offline python -m scripts.agent_evaluation.codex_agent_economics --root .hashmarks/benchmarks/codex-agent-economics --output .hashmarks/metrics/codex-agent-economics-latest.json

.PHONY: codex-selective-scout-economics
codex-selective-scout-economics:
	$(UV_RUN) --offline python -m scripts.agent_evaluation.codex_selective_scout_economics --root .hashmarks/benchmarks/codex-selective-scout --output .hashmarks/metrics/codex-selective-scout-latest.json

.PHONY: codex-economics-matrix-plan
codex-economics-matrix-plan:
	$(UV_RUN) --offline python -m scripts.agent_evaluation.codex_economics_matrix --plan-only \
	  --variant cheap-native:CHEAP_MODEL:low:native \
	  --variant cheap-hashmarks:CHEAP_MODEL:low:hashmarks \
	  --variant cheap-selective:CHEAP_MODEL:low:selective-real \
	  --variant strong-native:STRONG_MODEL:medium:native \
	  --output .hashmarks/metrics/codex-economics-matrix-plan.json

.PHONY: metrics-context-economics-csv splunk-csv-dogfood
metrics-context-economics-csv:
	@test -n "$$REPORT" || (echo "REPORT is required: path to codex-agent-economics JSON" >&2; exit 2)
	@$(UV_RUN) --offline --no-sync python -m scripts.agent_evaluation.context_economics_csv \
	  --input "$$REPORT" \
	  --raw-csv "$${RAW_CSV:-.hashmarks/benchmarks/context-economics-raw.csv}" \
	  --summary-csv "$${SUMMARY_CSV:-.hashmarks/benchmarks/context-economics-summary.csv}"

splunk-csv-dogfood:
	@test -n "$$SPLUNK_CSV" || (echo "SPLUNK_CSV is required: path to masked Splunk CSV export" >&2; exit 2)
	@$(UV_RUN) --offline --no-sync python -m scripts.agent_evaluation.splunk_csv_dogfood \
	  --input "$SPLUNK_CSV" \
	  --output "${OUTPUT:-.hashmarks/benchmarks/splunk-csv-dogfood.json}" \
	  ${WORKSPACE:+--workspace "$WORKSPACE"} \
	  ${PATH_MAPPING:+--path-mapping "$PATH_MAPPING"}
