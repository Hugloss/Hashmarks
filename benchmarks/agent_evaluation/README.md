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
`paired_correctness=not-measured`. An EvalShot trial must establish
its own current-source/host capture, model-visible delivery, usage,
behavioral outcome, independent grading and paired identity before claiming
any benefit, and must never project the Hashmarks packet as native MCP
delivery by default.

The export is bounded to 4 MiB and may contain source member paths, key
**names**, and prompt text. Review and protect it as repository information.
The hash is not secrecy or authentication. This evaluation module is **not
installed in the Hashmarks product**, and Hashmarks does not acquire agent
routing, execution, comparison grading, or any new MCP operation.

## EvalShot-owned native-agent benchmarks

Hashmarks is the repository-evidence subject under test. [EvalShot](https://github.com/Hugloss/EvalShot)
owns frozen experiments, native-agent adapters, execution, independent oracles,
scoring, receipts, and reports. agentsCookbook owns reusable Skills and guidance.
The coding agent owns tool choice and code decisions; Oh-Goon owns its execution
and certification workflows.

### Setup and thin aliases

Initialize this Hashmarks checkout with `make init`, including its locked MCP
extra. In the sibling EvalShot checkout, copy `.env.example` to `.env` and select
`HASHMARKS_BENCH_SOURCE` as this clean committed Hashmarks checkout. Select the
native agent, suite, and provider environment there. See
[EvalShot's benchmark guide](https://github.com/Hugloss/EvalShot/blob/main/benchmarks/README.md)
for the current commands, admission requirements, and native-host setup.

From Hashmarks:

```sh
make benchmark-check
make benchmark
make benchmark-report
```

These three targets delegate unchanged to EvalShot. `benchmark-check` checks
runtime wiring without inference; `benchmark` may invoke the configured model
provider. The aliases do not select a suite, bind a subject source, choose an
agent/model, or reinterpret campaign state. EvalShot's explicit `.env` owns
those selections. Set `EVALSHOT=/path/to/EvalShot` when the checkout is elsewhere.
Use EvalShot directly for new/resume, status, scoring, and other campaign commands;
Hashmarks does not duplicate those defaults or add another runner.

Native Codex/OpenCode trials receive the selected subject through EvalShot's
trial-scoped MCP exposure. User/project MCP registrations do not select the
benchmark subject. The host owns model/provider/authentication and normal
configuration. EvalShot observes and binds the actual executable, source,
workspace, configuration, and exposure before measured work.

### Evidence and historical identity

Current backend-navigation exports name `external-EvalShot` as the experiment
owner. That metadata participates in `export_identity`, so new exports receive
new identities. Retain historical exports and receipts with their original
bytes, owner metadata, and identities; the internal-consistency validator can
still inspect them. The metadata change neither regrades old results nor proves
host delivery, agent use, or correctness.

For external harnesses, `hashmarks --workspace . doctor --mcp` exposes the local
stdio launch projection and canonical MCP contract identity as
`hashmarks.mcp-readiness.v1`. This is diagnostic evidence. EvalShot or another
evaluator independently verifies executable/workspace/catalog binding and owns
experiment admission. Repository-only exports and readiness checks do not prove
that a model received the evidence or benefited from it.

The earlier evaluation tools in `scripts/agent_evaluation/` remain development
measurements, separate from the installed product and EvalShot's native-agent
campaign authority. Historical benchmark sources, receipts, and versioned schema
names retain their original provenance.
