SHELL := /bin/sh
UV ?= uv
UV_SYNC := $(UV) sync --frozen
DEV_SYNC := $(UV_SYNC) --extra mcp --group test
UV_RUN := $(UV) run --frozen
RUFF_RUN := UV_PROJECT_ENVIRONMENT=.ruff-venv $(UV_RUN) --offline --only-group lint ruff
FILES ?= 10000
HOT_REQUESTS ?= 20
TEST_SHARDS ?= 64
DEV_BATCH_SIZE ?= 4
DEV_BATCH_START ?= 0
ARTIFACT_PYTHON ?= 3.14
CHATGPT_MCP_HASHMARKS ?= $(abspath .venv/bin/hashmarks)
CHATGPT_MCP_WORKSPACE ?= $(CURDIR)
CHATGPT_MCP_SOURCE_ROOT ?= $(CURDIR)
DIAGNOSTIC_PYTHON ?= python3
DIAGNOSTIC_BATCH ?= 0
DIAGNOSTIC_BATCH_LIMIT ?= 8
DIAGNOSTIC_SHARD ?= 0
AGENTS_COOKBOOK ?= ../agentsCookbook
RUFF_DEBT_PREVIOUS_BASELINE ?=
RUFF_AUTOFIX_SELECT ?= E4,E7,E9,I,T201

.PHONY: help benchmark benchmark-check benchmark-report evaluation-help lock lock-check init setup bootstrap check start stop doctor compile map map-status map-watch agent-runner-journal-help hygiene ruff-available format format-check agent-finish agent-preflight lint ruff ruff-check ruff-format-check source-hygiene typecheck ty-check pyright-check precommit hooks-install lint-debt lint-debt-summary lint-debt-json test test-native test-diagnostic test-diagnostic-capabilities test-diagnostic-batch test-diagnostic-shard test-profile test-shard-plan test-shard dev-check dev-check-batch dev-check-tests artifact-check mcp-opencode-check mcp-claude-check mcp-codex-check mcp-pi-check mcp-chatgpt-handoff mcp-host-status mcp-concurrency-stress release-prepare release-check metrics metrics-fast metrics-scale metrics-500k metrics-derived-authority metrics-agent metrics-agent-corpus metrics-fresh-multi-repo metrics-blind-worker-ab metrics-worker-behavior-ab metrics-worker-inspection-ab metrics-worker-multistep-ab metrics-worker-failed-verification-ab metrics-agent-economics metrics-bm25-economics metrics-bm25-constrained metrics-agent-suite metrics-agent-trace metrics-agent-experiment metrics-agent-experiment-set metrics-agent-trace-normalize metrics-agent-regret metrics-agent-regret-suite metrics-compare clean-metrics

help:
	@printf '%s\n' \
	  'Hashmarks developer commands' \
	  '' \
	  '  make lock           Intentionally refresh committed uv.lock and sync the test environment' \
	  '  make lock-check     Check pyproject.toml ↔ committed uv.lock convergence without rewriting' \
	  '  make init           Materialize the locked test + MCP development environment' \
	  '  make setup          Prepare local test environment and runtime doctor' \
	  '  make test           Run authoritative normal OSS tests; HASHMARKS_CONSTRAINED_HOST=1 selects hosted diagnostics' \
	  '  make test-diagnostic  Run all capability-aware hosted diagnostic shards (never release authority)' \
	  '  make test-diagnostic-batch DIAGNOSTIC_BATCH=0  Run a bounded hosted diagnostic batch' \
	  '  make test-diagnostic-shard DIAGNOSTIC_SHARD=12  Run one hosted diagnostic shard' \
	  '  make test-diagnostic-capabilities  Show hosted capability inventory' \
	  '  make test-profile   Run full suite and report slowest 25 tests >=1s' \
	  '  make dependency-dogfood  Check genuine uv/Maven dependency add, change, and removal evidence' \
	  '  make check          Junior-friendly local check: setup + compile + CodeMap + tests' \
	  '  make bootstrap      Offline runtime-only bootstrap (CI/prepared environments)' \
	  '  make start          Bootstrap and start the identity daemon' \
	  '  make stop           Stop the identity daemon' \
	  '  make doctor         Show resolved runtime/daemon state' \
	  '  make compile        Compile Hashmarks source, scripts, benchmarks, and tests' \
	  '  make map            Sync the derived repository CodeMap' \
	  '  make map-status     Show CodeMap generation/staleness' \
	  '  make map-watch      Maintain CodeMap incrementally in foreground' \
	  '  make lint           Run full Ruff/format and current zero-debt size gate' \
	  '  make ruff           Run blocking Ruff correctness/import + format checks' \
	  '  make ruff-check     Run the full configured Ruff rule set' \
	  '  make ruff-format-check  Verify canonical Ruff formatting' \
	  '  make source-hygiene Run dependency-free LF + Python syntax checks' \
	  '  make typecheck      Run ty and Pyright on live repository Python' \
	  '  make precommit      Run all configured pre-commit hooks on tracked files' \
	  '  make hooks-install  Install the local Git pre-commit hook' \
	  '  make lint-debt      Enforce zero current Ruff complexity debt and file-size excess' \
	  '  make lint-debt-summary  Show concise current Ruff debt diagnostic' \
	  '  make lint-debt-json  Show exact current Ruff debt JSON (diagnostic)' \
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
	  '  make mcp-chatgpt-handoff  Qualify exact stdio MCP command/catalog for Secure MCP Tunnel' \
	  '  make mcp-host-status  Inspect project-local OpenCode/Claude/Codex/Pi MCP integration state' \
	  '  make mcp-concurrency-stress  Stress concurrent MCP-style readers during live repository mutation' \
	  '  make release-prepare VERSION=X.Y.Z  Prepare normal release version/request files and refresh uv.lock' \
	  '  make release-check  Local release preflight; native Linux/WSL + Windows qualification runs in CI' \
	  '  make metrics-fast   Quick baseline without daemon benchmarks' \
	  '  make metrics-500k   Explicit heavy 500k repository-intelligence baseline' \
	  '  make metrics-derived-authority  Measure controlled + uv/Maven explicit-packet economics before retention' \
	  '  make metrics        Quick 10k repository-intelligence baseline including daemon + impact metrics' \
	  '  make metrics-scale  100k repository-intelligence baseline' \
	  '  make benchmark      Delegate benchmark execution to the sibling agentsCookbook checkout' \
	  '  make benchmark-check  Delegate benchmark readiness to agentsCookbook' \
	  '  make benchmark-report  Delegate benchmark reporting to agentsCookbook' \
	  '  make evaluation-help  Show external-agent/research evaluation targets' \
	  '' \
	  'Override FILES/HOT_REQUESTS, e.g. make metrics FILES=50000 HOT_REQUESTS=50'

benchmark:
	@$(MAKE) --no-print-directory -C "$(AGENTS_COOKBOOK)" benchmark

benchmark-check:
	@$(MAKE) --no-print-directory -C "$(AGENTS_COOKBOOK)" benchmark-check

benchmark-report:
	@$(MAKE) --no-print-directory -C "$(AGENTS_COOKBOOK)" benchmark-report

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
	@$(DEV_SYNC)
	@printf '%s\n' 'Hashmarks committed uv.lock refreshed and test + MCP environment synced.'

lock-check:
	@$(UV) lock --check
	@printf '%s\n' 'Hashmarks pyproject.toml and committed uv.lock are converged.'

init:
	@$(DEV_SYNC)
	@printf '%s\n' 'Hashmarks dependency environment ready from committed uv.lock (test + MCP).'

setup: init
	@$(MAKE) --no-print-directory doctor >/dev/null
	@printf '%s\n' 'Hashmarks setup ready. Run: make test   or   make check'

bootstrap:
	@test -f uv.lock || (echo "committed uv.lock is missing; restore the repository checkout before bootstrap" >&2; exit 2)
	@$(DEV_SYNC) --offline
	@$(MAKE) --no-print-directory doctor >/dev/null
	@printf '%s\n' 'Hashmarks bootstrap ready (offline, committed locked supply).'

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

hygiene:
	@echo "=== PORTABLE REPOSITORY HYGIENE ==="
	@bash ./scripts/agent-hygiene.sh
	@echo "PORTABLE HYGIENE PASS"

ruff-available:
	@$(RUFF_RUN) --version

format:
	@echo "=== FORMAT ==="
	@$(RUFF_RUN) format .

format-check:
	@echo "=== AUTHORITATIVE FORMAT CHECK ==="
	@$(RUFF_RUN) format --check --diff .
	@git diff --check
	@echo "AUTHORITATIVE FORMAT CHECK PASS"

agent-finish:
	@echo "=== AGENT FINISH ==="
	@$(MAKE) --no-print-directory hygiene
	@set -e; \
		$(RUFF_RUN) check --fix --select $(RUFF_AUTOFIX_SELECT) .; \
		$(RUFF_RUN) format .; \
		git diff --check; \
		$(RUFF_RUN) format --check --diff .; \
		$(RUFF_RUN) check .; \
		echo "AGENT FORMAT STATUS: VERIFIED"; \
		echo "AGENT FULL RUFF STATUS: VERIFIED"

agent-preflight: agent-finish
	@$(MAKE) --no-print-directory lint-debt

ruff-check:
	@$(RUFF_RUN) check .

ruff-format-check:
	@$(RUFF_RUN) format --check --diff .

ruff: ruff-check ruff-format-check

lint: ruff lint-debt

.PHONY: dependency-dogfood
dependency-dogfood:
	@$(UV_RUN) --offline --no-sync --group test python -m pytest -v tests/test_dependency_dogfood.py

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
	  $(if $(strip $(DIAGNOSTIC_SHARDS)),--shards $(DIAGNOSTIC_SHARDS),) \
	  $(if $(strip $(DIAGNOSTIC_EXTRA_MARKER)),--extra-marker '$(DIAGNOSTIC_EXTRA_MARKER)',)

test-diagnostic-batch:
	@start=$$(( $(DIAGNOSTIC_BATCH) * $(DIAGNOSTIC_BATCH_LIMIT) )); \
	$(DIAGNOSTIC_PYTHON) -m scripts.hosted_diagnostic \
	  $(if $(strip $(DIAGNOSTIC_SHARDS)),--shards $(DIAGNOSTIC_SHARDS),) \
	  --start $start \
	  --limit $(DIAGNOSTIC_BATCH_LIMIT) \
	  $(if $(strip $(DIAGNOSTIC_EXTRA_MARKER)),--extra-marker '$(DIAGNOSTIC_EXTRA_MARKER)',)

test-diagnostic-shard:
	@$(DIAGNOSTIC_PYTHON) -m scripts.hosted_diagnostic \
	  $(if $(strip $(DIAGNOSTIC_SHARDS)),--shards $(DIAGNOSTIC_SHARDS),) \
	  --start $(DIAGNOSTIC_SHARD) \
	  --limit 1 \
	  $(if $(strip $(DIAGNOSTIC_EXTRA_MARKER)),--extra-marker '$(DIAGNOSTIC_EXTRA_MARKER)',)

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
	@printf '%s\n' '[2/4] CodeMap sync'
	@$(MAKE) --no-print-directory map >/dev/null
	@printf '%s\n' '[3/4] Deterministic resumable pytest batches ($(TEST_SHARDS) shards, $(DEV_BATCH_SIZE) shards/batch)'
	@$(MAKE) --no-print-directory dev-check-tests
	@printf '%s\n' '[4/4] Current Ruff and size gates'
	@$(MAKE) --no-print-directory lint
	@VERSION=`$(UV_RUN) --offline hashmarks version`; \
	printf '\n%s\n' '========================================' " HASHMARKS DEV CHECK: PASS ($$VERSION)" ' Setup:       PASS' ' Compile:     PASS' ' Ruff:        PASS (zero debt)' ' CodeMap:     PASS' ' Tests:       PASS' '========================================'

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
	artifact_check_dir=$$(mktemp -d); \
	trap 'rm -rf -- "$$artifact_check_dir"' EXIT HUP INT TERM; \
	$(UV) build --out-dir "$$artifact_check_dir"; \
	set -- "$$artifact_check_dir"/*.whl; \
	test "$$#" -eq 1 && test -f "$$1"; \
	wheel=$$1; \
	set -- "$$artifact_check_dir"/*.tar.gz; \
	test "$$#" -eq 1 && test -f "$$1"; \
	sdist=$$1; \
	$(UV) venv --python $(ARTIFACT_PYTHON) "$$artifact_check_dir/wheel-env" >/dev/null; \
	$(UV) pip install --offline --python "$$artifact_check_dir/wheel-env/bin/python" "$$wheel" >/dev/null; \
	"$$artifact_check_dir/wheel-env/bin/python" -I scripts/installed_artifact_smoke.py; \
	$(UV) venv --python $(ARTIFACT_PYTHON) "$$artifact_check_dir/sdist-env" >/dev/null; \
	$(UV) pip install --offline --python "$$artifact_check_dir/sdist-env/bin/python" "$$sdist" >/dev/null; \
	"$$artifact_check_dir/sdist-env/bin/python" -I scripts/installed_artifact_smoke.py; \
	printf '%s\n' 'Hashmarks installed-artifact qualification: PASS (wheel + sdist).'

mcp-host-status:
	@$(UV_RUN) --offline --no-sync python scripts/mcp_host_status.py

mcp-concurrency-stress:
	@$(UV_RUN) --offline --no-sync python scripts/mcp_concurrency_stress.py \
	  $(if $(strip $(MCP_STRESS_RECEIPT)),--receipt "$(MCP_STRESS_RECEIPT)",)

mcp-opencode-check:
	@$(UV_RUN) --offline --no-sync python scripts/host_qualification/opencode_mcp_host_gate.py \
	  --uv "$(UV)" \
	  $(if $(strip $(OPENCODE)),--opencode "$(OPENCODE)",) \
	  $(if $(strip $(OPENCODE_MODEL)),--model "$(OPENCODE_MODEL)",) \
	  $(if $(strip $(OPENCODE_HOST_PYTHON)),--python "$(OPENCODE_HOST_PYTHON)",) \
	  $(if $(strip $(OPENCODE_HOST_RECEIPT)),--receipt "$(OPENCODE_HOST_RECEIPT)",)

mcp-claude-check:
	@$(UV_RUN) --offline --no-sync python scripts/host_qualification/claude_mcp_host_gate.py \
	  --uv "$(UV)" \
	  $(if $(strip $(CLAUDE)),--claude "$(CLAUDE)",) \
	  $(if $(strip $(CLAUDE_MODEL)),--model "$(CLAUDE_MODEL)",) \
	  $(if $(strip $(CLAUDE_HOST_PYTHON)),--python "$(CLAUDE_HOST_PYTHON)",) \
	  $(if $(strip $(CLAUDE_HOST_RECEIPT)),--receipt "$(CLAUDE_HOST_RECEIPT)",)

mcp-codex-check:
	@$(UV_RUN) --offline --no-sync python scripts/host_qualification/codex_mcp_host_gate.py \
	  --uv "$(UV)" \
	  $(if $(strip $(CODEX)),--codex "$(CODEX)",) \
	  $(if $(strip $(CODEX_MODEL)),--model "$(CODEX_MODEL)",) \
	  $(if $(strip $(CODEX_HOST_PYTHON)),--python "$(CODEX_HOST_PYTHON)",) \
	  $(if $(filter 1 true yes,$(CODEX_HOST_DANGEROUS)),--dangerous-bypass,) \
	  $(if $(strip $(CODEX_HOST_RECEIPT)),--receipt "$(CODEX_HOST_RECEIPT)",)

mcp-pi-check:
	@$(UV_RUN) --offline --no-sync python scripts/host_qualification/pi_mcp_host_gate.py \
	  --uv "$(UV)" \
	  $(if $(strip $(PI)),--pi "$(PI)",) \
	  $(if $(strip $(PI_HOST_PYTHON)),--python "$(PI_HOST_PYTHON)",) \
	  $(if $(strip $(PI_HOST_RECEIPT)),--receipt "$(PI_HOST_RECEIPT)",)

mcp-chatgpt-handoff:
	@test -x "$(CHATGPT_MCP_HASHMARKS)" || { \
	  echo "Hashmarks executable is not available: $(CHATGPT_MCP_HASHMARKS); run make init or override CHATGPT_MCP_HASHMARKS" >&2; \
	  exit 2; \
	}
	@$(UV_RUN) --offline --no-sync python scripts/host_qualification/chatgpt_secure_mcp_tunnel_handoff.py \
	  --hashmarks "$(CHATGPT_MCP_HASHMARKS)" \
	  --workspace "$(CHATGPT_MCP_WORKSPACE)" \
	  $(if $(strip $(CHATGPT_MCP_SOURCE_ROOT)),--source-root "$(CHATGPT_MCP_SOURCE_ROOT)",) \
	  $(if $(strip $(CHATGPT_MCP_HANDOFF_RECEIPT)),--output "$(CHATGPT_MCP_HANDOFF_RECEIPT)",)

release-prepare:
	@test -n "$(VERSION)" || (echo "VERSION is required, e.g. make release-prepare VERSION=X.Y.Z" >&2; exit 2)
	@$(UV_RUN) --offline --no-sync python scripts/release_prepare.py --version "$(VERSION)"
	@$(UV) lock
	@$(UV) lock --check
	@printf '%s\n' \
	  'Release mechanics prepared and uv.lock refreshed.' \
	  'Next: replace the Development placeholder in CHANGELOG.md, review the diff, then run make release-check.'

release-check:
	@$(MAKE) --no-print-directory lock-check
	@$(UV_RUN) --offline --no-sync python scripts/release_contract.py validate-release-candidate --normal-only
	@$(MAKE) --no-print-directory dev-check
	@$(MAKE) --no-print-directory artifact-check
	@printf '\n%s\n' \
	  '========================================' \
	  ' HASHMARKS RELEASE CHECK: LOCAL PREFLIGHT PASS' \
	  ' Pull-request CI owns native Linux/WSL + Windows standalone qualification.' \
	  ' Publish owns exact-source release aggregation and GitHub Release publication.' \
	  '========================================'

metrics: bootstrap
	@$(UV_RUN) --offline python scripts/metrics.py --files $(FILES) --hot-requests $(HOT_REQUESTS)

metrics-fast: bootstrap
	@$(UV_RUN) --offline python scripts/metrics.py --files $(FILES) --hot-requests $(HOT_REQUESTS) --skip-daemon

metrics-scale:
	@$(MAKE) metrics FILES=100000 HOT_REQUESTS=20

metrics-500k:
	@$(MAKE) metrics FILES=500000 HOT_REQUESTS=20

metrics-derived-authority: bootstrap
	@$(UV_RUN) --offline python -m benchmarks.derived_authority_economics \
	  --iterations 100 --scale 64 \
	  --real-iterations 25 \
	  --fixture-root tests/fixtures/dependency_dogfood \
	  --output .hashmarks/metrics/derived-authority-economics-latest.json

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
