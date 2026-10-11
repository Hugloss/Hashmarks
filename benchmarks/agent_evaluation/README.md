# Agent-evaluation fixtures

This directory contains **development measurement infrastructure**, not installed Hashmarks product state.

Hashmarks is repository intelligence. Synthetic repositories, corpora, packets, and worker outputs are used to measure how external consumers behave with and without Hashmarks evidence. They do not define runtime APIs, agent workflow authority, execution policy, or compatibility obligations.

Canonical synthetic fixture inputs are owned by the evaluation code that materializes them into a caller-supplied run directory. Generated blind inputs, packets, worker outputs, and result files are not committed as parallel repository state. Real-world retained qualification evidence, when exact external provenance matters, belongs in the repository-quality evidence surface rather than in a generated fixture mirror.

New product behavior must still pass the product-admission contract in `docs/reference/PRODUCT_BOUNDARY.md`; benchmark wins do not authorize moving consumer workflow into Hashmarks.


## Frozen backend navigation source-evidence ablation (B35–B39)

A **Hashmarks-side, evaluation-only** exporter produces two canonical
`discover_repository_declarations` observations on **one synced repository
snapshot**: selected backend source syntax without navigation and the
same source syntax with `include_evidence_navigation=True`. This freezes
inputs for an externally owned experimental A/B. It does **not** invoke
an agent, call MCP, supply a host-visible receipt, grade patches, or estimate
whether navigation helps.

Input JSON (caller supplies real, source-admitted Python files):

```json
{
  "schema": "hashmarks.backend-navigation-cases.v1",
  "cases": [
    {
      "id": "backend-config-navigation",
      "prompt": "Locate the configuration declaration and explain what evidence is missing.",
      "paths": ["src/backend/settings.py"],
      "model_fields": true,
      "environment_reads": true
    }
  ]
}
```

From an initialized checkout:

```sh
uv run -m scripts.agent_evaluation.backend_navigation_ablation \
  --repo /path/to/snapshot \
  --manifest /path/to/cases.json \
  --output /tmp/backend-navigation-frozen.json
```

**B35:** bounded, explicit 1–16 case manifests reject invalid flags, duplicate
IDs, noncanonical paths, extra fields, and absent source before producing an
authoritative comparison. There is no automatic task selection or grader oracle.

**B36:** both arms use the **same CodeMap instance and sync** and the
existing source-bound backend provider. Paired input/member revision and
repository identity equality are required. No source files are rewritten.

**B37:** the exporter strips *only* the optional `evidence_navigation`
value and compares all other source facts, ranges, concepts, roles, and
qualifiers. Any divergent source fact rejects the pair. A
`source_facts_identity` digest binds the two arms to one fact set.
The arms are named **`syntax-only`** and **`navigation`**;
`syntax-only` is **not** an agent-without-Hashmarks baseline.

**B38:** per-arm canonical UTF-8 byte sizes and SHA-256 observation IDs
permit self-consistency validation. A final `export_identity` protects
against accidental field changes. These are **not signed receipts**,
independent repository attestations, or proof a tool response reached a
model. The validator cannot rule out a malicious producer that rewrites all
content and recomputes hashes.

**B39:** the exporter records
`exposure=exported-not-host-attested`,
`host_visible=not-established`, `agent_used=not-established`,
`agent_result=not-measured`; the overall report states
`paired_correctness=not-measured`. An agentsCookbook trial must establish
its own current-source/host capture, model-visible delivery, usage,
behavioral outcome, independent grading and paired identity before claiming
any benefit, and must never project the Hashmarks packet as native MCP
delivery by default.

The export is bounded to 4 MiB and may contain source member paths, key
**names**, and prompt text. Review and protect it as repository information.
The hash is not secrecy or authentication. This evaluation module is **not
installed in the Hashmarks product**, and Hashmarks does not acquire agent
routing, execution, comparison grading, or any new MCP operation.

## agentsCookbook-owned native Codex and OpenCode benchmark

### Benchmark ownership

Hashmarks does **not** own or implement this benchmark. Hashmarks is one subject
under test. The benchmark harness, frozen experiment definitions, admission,
execution evidence, independent grading, receipts, and reporting are owned by
the adjacent **agentsCookbook** checkout.

The Hashmarks `make benchmark*` targets are convenience entry points only. They
delegate to agentsCookbook while binding this Hashmarks checkout as the subject
source:

```text
Hashmarks checkout
    make benchmark*
         |
         v
agentsCookbook
    benchmark harness / experiment authority
         |
         +-- bare
         +-- exact admitted Hashmarks executable
         +-- exact admitted Enola executable
```

For native OpenCode and Codex trials, agentsCookbook supplies the selected
subject as a temporary **trial-scoped MCP exposure**. Project or user MCP
registration is not benchmark authority and is not required for either benchmark
arm. Each host remains authoritative for its model, provider, authentication,
permissions, and normal user configuration; agentsCookbook owns only the
experiment-scoped subject overlay and independently proves the exact executable,
workspace binding, and exposure identity before agent work.

Start from this Hashmarks checkout with the adjacent `agentsCookbook` checkout:

```sh
make init
make benchmark-show
make benchmark-check
make benchmark
make benchmark-report
```

`make benchmark` runs one pinned localization task through six conditions: native
OpenCode and native Codex, each with bare, Hashmarks MCP, and Enola MCP access.
`make benchmark BENCHMARK=matrix` runs all three matrix tasks (18 trials).
`make benchmark BENCHMARK=cycle` runs an adapted TypeScript cycle task three
times per condition (18 trials). `make benchmark-show` lists definitions without
running agents. `make benchmark-check` prepares every selected native arm and
stops before any model call if source, subject, model, MCP binding, or oracle
setup is unavailable. It cannot prove remote model authentication; first confirm
each native CLI works interactively. Set `BENCH_AGENT=opencode-native` or
`BENCH_AGENT=codex-native` to select one native CLI.

The experiments and runner live in the adjacent `agentsCookbook` checkout; set
`AGENTS_COOKBOOK=/path/to/checkout` if it is elsewhere. Each `make benchmark`
invocation creates a fresh local run under `BENCH_ROOT` and prints its path.
`make benchmark-report` reads the latest run for the selected `BENCHMARK` mode,
including its original agent selection. Use `BENCH_RUN=<printed-run-id>` to
resume or report a specific run; resume only with the same model, MCP, and
harness setup. Start a new run after changing them. `BENCH_PARTIAL=1` explicitly
reports verified receipts available so far; a normal report requires every
selected definition. `BENCH_PYTHON` selects the agentsCookbook interpreter,
including when Hashmarks' `.venv` is active.

The run uses your installed native CLI model/provider/auth settings. Check that
`codex` and `opencode` already work interactively. Native Codex requires a
`model` in your `~/.codex/config.toml`, and native OpenCode requires a configured
model. The benchmark never chooses or rewrites either host's model/provider/auth
configuration.

Neither native host needs a pre-existing Hashmarks or Enola MCP registration
for benchmark execution. agentsCookbook resolves the selected subject from the
benchmark environment, records its exact identity, disables unrelated subject
entries for the trial where the host supports that control, and injects the selected
stdio MCP command against the disposable trial workspace. End-user host registration
such as `hashmarks install --opencode` remains useful outside the benchmark but does
not select the benchmark executable.

The benchmark puts this checkout's `.venv/bin` first on `PATH` and proves the
selected Hashmarks executable, exposure digest, and workspace binding before agent
work. A missing subject executable, changed exposure identity, or unprovable workspace
binding yields `INCOMPLETE` before scored work. Native host configuration can still
supply model/provider/authentication choices, but stale or unrelated MCP registration
cannot silently choose the subject under test. Enola hooks are excluded; only the
explicit MCP exposure varies between arms.

For external harnesses such as Harbor, Hashmarks exposes a diagnostic-only readiness
projection:

```sh
hashmarks --workspace . doctor --mcp
```

The nested `hashmarks.mcp-readiness.v1` object reports the local stdio launch
projection and canonical MCP contract identity. It is intentionally **not** admission
authority: agentsCookbook or another external evaluator must still independently
verify the exact executable, workspace binding, and host-visible catalog.

The earlier `codex-agent-economics` evaluation remains available through its
separate Make targets. The native matrix compares subject assistance within each
agent/model configuration; its scores do not certify either product. The adapted
cycle task separately counts behavior success and module dependency cycles. See the suite
READMEs in `agentsCookbook/benchmarks/suites/repository-intelligence/` for exact
pinned source and oracle semantics.
