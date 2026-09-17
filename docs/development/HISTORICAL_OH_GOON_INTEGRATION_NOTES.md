# Historical Hashmarks ↔ Oh-Goon integration notes

> **Historical, non-normative record.** This file preserves earlier documentation for archaeology and evidence. For current product behavior use `docs/reference/`, `docs/integration/`, and the root `README.md`.

---

# Hashmarks ↔ Oh-Goon integration boundary

## Current normative contract (Hashmarks v0.11.10+)

This section is normative. Older version-specific notes below are historical integration guidance and must not override it.

**Current external validation reference:** canonical Oh-Goon 1267.0.147, ZIP SHA-256 `e7c494892601892d1baa0988c653639af7fa294fa8b511b49bf4710c1abbc8ec`. Any older Oh-Goon versions below are historical evidence only and must not be used as the current interoperability baseline.

**Three planes:** Hashmarks is the repository-evidence plane; the coding agent/harness is the solution plane; Oh-Goon is the execution/certification control plane. Hashmarks answers what repository evidence says matters. The coding agent decides what change to make. Oh-Goon decides whether, where, and how admitted work may run and whether resulting execution evidence is certifiable.

For deterministic pytest shard handoff, Hashmarks continues to emit `hashmarks.test-shards.v3` membership with `isolated_process`. `hashmarks.repository-work-selection.v1` may wrap that unchanged plan and binds it to canonical repository content identity, exact selection-input identity, Hashmarks producer version/algorithm/implementation identity, and optional exact release-artifact SHA-256. Oh-Goon should verify both the inner plan identity and outer envelope identity, compare repository identity to its admitted source identity, preserve `isolated_process`, and reject stale/mismatched evidence before launch.

Oh-Goon may refine execution grouping after a timeout, but refinement must conserve the Hashmarks membership exactly: child union equals parent membership, with no omission or duplicate. Hashmarks v0.11.10 exposes the derived `hashmarks.test-shard-membership.v1` identity for this purpose; it is independent of grouping/order and changes or fails on omission/duplication. Oh-Goon can therefore compare the original parent/test-set membership to any refined grouping without implementing another selector. Hashmarks does not choose timeout budgets, retry policy, worker count, schedule, machine, process lifecycle, or environment recovery.

Before launch, a consumer can use `validate_work_selection_envelope()` for strict schema/authority conformance and optionally `validate_work_selection_repository_binding()` to re-prove the envelope against current repository bytes. Re-proof recomputes only Hashmarks-owned content/selection evidence; it does not grant Hashmarks process or admission authority. Unknown extension fields fail closed in v1, and producer artifact identity is provenance rather than a cryptographic signature, so Oh-Goon still owns trust/admission policy.

Terminology is qualified by plane: repository-content identity / CodeMap generation / repository-evidence provenance / verification-selection authority / repository-negative evidence belong to Hashmarks; admission/execution identity / execution provenance / verification-result authority / execution-recovery evidence / Game Tape / certification belong to Oh-Goon. Static cross-repository project topology is repository evidence, not Fleet scheduling.

Hashmarks should remain a standalone package. Oh-Goon should consume it as a pinned dependency and add only a thin policy/orchestration adapter.

## Ownership

Hashmarks owns:

- canonical file/directory/input/step/work identities;
- maintained change observation and daemon acceleration;
- dependency/impact evidence normalization;
- AFFECTED / VERIFIED_UNAFFECTED / UNKNOWN decisions;
- result identity baselines and post-run PASS promotion checks;
- optional standalone CLI convenience for other developers/agents.

Oh-Goon owns:

- Plan/Goon/Step orchestration;
- workspace/sandbox/process-tree authority;
- command execution, cancellation, egress and resource policy;
- which evidence channels/producers are trusted;
- whether a reusable result may be consumed in a particular Plan policy;
- Game Tape / provenance / certification reporting.

Do not copy Hashmarks internals into Oh-Goon and do not let Oh-Goon grow a second identity/cache implementation.

## Important execution rule

Inside Oh-Goon, use Hashmarks as a **library**, not `hashmarks impact run` as the process runner. `impact run` is a standalone convenience command. Oh-Goon already owns process execution and must keep that authority.

Recommended flow:

```text
Oh-Goon resolves work
        ↓
Hashmarks assess_one(work)
        ↓
VERIFIED_UNAFFECTED ──→ Oh-Goon records reuse/proof
        │
AFFECTED / UNKNOWN
        ↓
Oh-Goon executor runs the command under its normal sandbox/policy
        ↓
exit 0 ──→ Hashmarks promote_pass(pre_run_assessment)
              │
              ├─ promoted → Oh-Goon records PASS identity
              └─ stale/output-invalid → result is not reusable; rerun/fail by policy

nonzero/error ──→ Hashmarks record_result(... fail/error)
```

This preserves Oh-Goon's execution authority while gaining Hashmarks's result-validity proof.

## Trust policy

Repository-controlled declarations must not automatically become skip authority. Oh-Goon should construct `ImpactTrustPolicy` from its own trusted policy boundary:

- canonical/built-in Oh-Goon declarations may be trusted when appropriate;
- untrusted repository/PR declarations remain claims only;
- native evidence producers spawned/controlled by Oh-Goon can be delivered through `trust_eligible=True` integrations and explicit producer allowlists.

## Dependency strategy

During joint development, use a locked workspace/path or Git source while keeping Hashmarks in its own repository. Once released to the intended package registry, pin a compatible Hashmarks version in Oh-Goon and retain the exact resolved version in `uv.lock`.

Oh-Goon should expose the active Hashmarks `__version__`, daemon protocol/semantics, and WorkIdentity in diagnostic/Game Tape evidence so a reuse decision is reproducible.

## Agent reuse

This split supports all agent modes:

- Codex working inside Oh-Goon gets Hashmarks through the normal Oh-Goon dependency environment;
- an internal coding agent can directly run `uv run hashmarks ...` when useful;
- other agents/repositories can install/import Hashmarks without installing Oh-Goon;
- Oh-Goon can evolve orchestration/security independently without forking the identity engine.


## Optional agent CodeMap integration

Oh-Goon should keep CodeMap optional and derived. Do not run parsing inside Oh-Goon's executor or Hashmarks Identity daemon.

A useful local/agent session topology is:

```text
Hashmarks identity daemon    authoritative identity / Impact
Hashmarks map watcher        derived CodeMap maintenance
Oh-Goon                     orchestration / sandbox / execution policy
Agent                       asks Hashmarks for orient/find/context/source
```

Oh-Goon may start/manage the separate `hashmarks map watch` process for an agent workspace, but failure of that process must never weaken execution identity or certification. The agent can fall back to `hashmarks map sync`/repository search when CodeMap freshness or retrieval confidence is insufficient.

CodeMap may additionally expose `hashmarks map import-ownership` findings for repository-owned Python loader/module-cache hazards. Oh-Goon may present that evidence to an agent or QA surface, but Hashmarks does not execute/rewrite the import and Oh-Goon remains the execution/certification owner.


## Optional CodeMap enrichment for agents

Oh-Goon may expose Hashmarks CodeMap to coding/reviewer agents as a read-side accelerator. Slower native project evidence is explicitly refreshed outside execution/Identity latency with `hashmarks map enrich` (Nx, Pants, npm, Go, Cargo, Maven, Gradle, TypeScript, Pyright Type Server, Vitest/Vite, and declared cross-project links) or `hashmarks map import-scip`. Oh-Goon should record the Hashmarks/CodeMap generation and provider freshness in provenance, but must not treat CodeMap evidence as execution or skip authority.

Hashmarks 0.9 also exposes **positive-only native selection** (`impact select`). Oh-Goon may use pytest-testmon or Vitest/Vite selection as an extra reason to run work, but an omitted test must never become reusable solely because a selector omitted it. Reuse remains governed by normal Hashmarks WorkIdentity, completeness, trust, and result-promotion rules.


## Agent retrieval evaluation boundary (0.10.0)

Oh-Goon is now one of Hashmarks' retained external retrieval gates. This does not transfer any execution/certification authority to CodeMap: the corpus is read-only evaluation data used to ensure agent localization works on a materially different mixed backend/frontend repository. Oh-Goon/Codex/Pi runners may additionally emit `hashmarks.agent-trace.v2` records plus independent `hashmarks.agent-verdict.v1` grading evidence and `hashmarks.agent-model-usage.v1` provider token evidence so Hashmarks can compare real repository-search calls, file reads, and exact model-input tokens against a baseline without letting the agent self-attest task success or patch correctness.


## Canonical real-agent experiment handoff (0.10.4)

Oh-Goon/Codex/Pi evidence collection should now emit one `hashmarks.agent-experiment.v1` manifest per controlled comparison. The manifest is collection authority only: Oh-Goon remains execution/sandbox/provenance authority. Each run binds exact repository/task/model/runner identity, an activity trace, independent provider usage, an independent grader verdict, and the exact patch/output bytes graded. Strict ingestion also verifies retained raw provider/grader evidence SHA-256 digests. This prevents a later collector from mixing runs, swapping patches, or attaching a usage/verdict record to different bytes while still passing Hashmarks' token-saving gate.


## Multi-experiment evidence sets (0.10.5)

When Oh-Goon, Codex, Pi, or another runner produces several controlled experiments, aggregate them through `hashmarks.agent-experiment-set.v1` rather than concatenating reports. The set byte-binds every member experiment manifest and requires stable model/config/task-policy identities (plus stable runner/grader/provider/benchmark-protocol identities when declared). Reused run IDs or repeated repository/task/revision identities are rejected instead of counting as additional breadth.

Hashmarks exposes two different outcomes: an internally valid controlled aggregate and a broader/public breadth-eligible aggregate. The latter cannot be configured below 3 experiments, 3 distinct repositories, and 30 unique tasks. Oh-Goon should surface that distinction in provenance/Game Tape rather than presenting an internal controlled result as a general model-token claim. These floors are breadth policy only; Oh-Goon or a separate evaluation authority may require stronger statistical or domain-specific criteria.


## Replication handoff (0.10.6)

Oh-Goon/Codex/Pi may repeat the same controlled benchmark condition, but experiment-set v2 requires those repetitions to be explicitly grouped. Hashmarks uses them only to measure repeat variation; they do not inflate repository/task breadth. Any confidence interval is scoped to the exact retained experiments and cannot be promoted into a population claim without a separately justified statistical design.


## Retrieval-regret evidence (0.10.7)

Oh-Goon/Codex/Pi runners can retain ordinary agent traces while an independent grading/task authority emits `hashmarks.agent-retrieval-evidence.v1`. Hashmarks then measures how much exploration happened before the required repository evidence appeared, without trusting the candidate agent to label its own discoveries as useful. This is optimization telemetry only and does not transfer execution or grading authority to Hashmarks.


## Derived CodeMap surfaces (0.10.8)

Oh-Goon continues to consume ordinary Hashmarks CodeMap behavior unchanged. Internally, Hashmarks now records stable identities for content, symbol, relationship, outline and lexical surfaces. This creates the prerequisite for precise semantic invalidation without moving any execution authority into Hashmarks.


## Semantic invalidation shields (0.10.9)

Hashmarks can now distinguish source-byte churn from agent-facing semantic change. Oh-Goon receives no new execution authority or altered retrieval behavior; this reduces future derived invalidation while source locations remain exact.


## Multi-worktree reuse (0.10.10)

Multiple Oh-Goon/Codex worktrees at the same Git base can now share immutable Hashmarks CodeMap base evidence while each worktree keeps dirty paths local. This improves the planned parallel-worktree model without sharing mutable workspace state or execution authority.


## Query-route integration (0.10.11)

Oh-Goon/Codex/Pi can inspect `CodeMap.query_route()` when debugging retrieval decisions. Path/config/test queries avoid unnecessary native-definition expansion while relationship/identifier/conceptual queries retain semantic and graph-aware candidate expansion. The route is advisory evidence; it does not change Oh-Goon execution authority.


## Progressive context handoff (0.10.12)

Oh-Goon/Codex/Pi can now request `hashmarks context QUERY --level orient|outline|evidence|source`. These are progressively richer projections over the same CodeMap generation, not independent retrieval systems. Agents should prefer the cheapest competent level and escalate explicitly: candidate identities first, then structural outlines, then relationship evidence, and only then exact source. Lower levels cannot disclose implementation bodies, so an orchestration policy can mechanically cap exploration cost without relying on prompt discipline. Execution, sandbox, grading, and certification authority remain in Oh-Goon.


## Bounded rerank handoff (0.10.13)

Hashmarks now separates broad index-backed candidate generation from a bounded full-rerank working set. Ordinary queries keep all candidates; unusually broad queries retain a deterministic path-diverse subset before full scoring. This creates a safe future hook for a cheap local/model reranker without letting an external model scan the entire repository candidate surface. Oh-Goon continues to see only the final evidence/hits and retains all execution authority.


## Content-addressed context reuse (0.10.14)

Repeated Oh-Goon/Codex/Pi context requests can now reuse a Hashmarks CAS payload when repository, CodeMap generation, policy, query, disclosure, budget and ranked-hit identities match exactly. Cache provenance is returned as the context action hash plus result digest. Freshness metadata is always reconstructed for the current request. Exact source payloads are cached only when filesystem freshness is positively proven, so a cache hit cannot become stale implementation authority.


## Multi-agent shared retrieval (0.10.15)

When several Oh-Goon/Codex/Pi requests reach the same Hashmarks process concurrently with the same repository generation, policy and retrieval inputs, equivalent `find` and structural-context work can now join a single in-flight computation. Only the immutable final Hashmarks result is shared. Agent session history, intermediate exploration and mutable state are never part of the shared object. Exact source-level sharing requires positive filesystem freshness, preserving workspace isolation and source authority.

The same phase strengthens structural retrieval rather than hiding test-symbol crowding with ranking heuristics. Python type annotations now contribute derived relationships, so a method such as `CodeMap.context(...) -> ContextPack` can preserve the related `ContextPack` type as explicit evidence. The expansion is exact-name anchored and bounded, and the larger edge surface is backed by path/source indexes. Oh-Goon still consumes only derived evidence; execution/certification authority does not move into Hashmarks.


## Real-agent trace intake (0.10.16)

Oh-Goon/Codex/Pi wrappers no longer need to emit Hashmarks' canonical trace kinds directly. They may retain a `hashmarks.agent-runner-log.v1` containing native tool names plus an explicit `tool_map`. Hashmarks recomputes the normalization-policy identity, rejects undeclared tools and path escapes, preserves raw-log SHA-256 provenance, and emits the existing `hashmarks.agent-trace.v2` evidence contract. Mapping a tool to `null` is an explicit statement that the event is intentionally outside navigation accounting; silent dropping is not allowed.

A regret suite can then byte-bind many trace/evidence pairs and rank observed exploration opportunities such as late discovery of all required evidence, repeated queries, repeated reads, and irrelevant reads. Those categories overlap and are triage only. Oh-Goon remains execution/sandbox/provenance authority; independent graders remain correctness authority; provider usage remains exact model-token authority.


## Crash-safe runner journal handoff (0.10.17)

Oh-Goon may wrap a real Codex/Pi run with `scripts/agent_evaluation/agent_runner_journal.py`: initialize one journal with exact run/repository/model/tool-map identity, write every wrapper-observed tool invocation as an immutable sequence-numbered event, then finalize after the run. This avoids holding the whole trace in memory and makes dropped or duplicate wrapper events mechanically visible. The finalizer requires contiguous sequence numbers, validates path/timing/tool semantics through the same 0.10.16 normalizer, and can emit both the raw runner log and normalized v2 trace.

Oh-Goon remains responsible for deciding what constitutes one observed tool invocation and for recording genuine timing/token/byte data. Hashmarks does not intercept the agent process or guess runner semantics. The capture journal is provenance transport only; sandbox/execution authority remains in Oh-Goon, correctness remains with the independent grader, and model-token authority remains with provider usage evidence.

## Read-only Repository Understanding benchmark handoff (0.10.18)

Oh-Goon remains an external read-only benchmark corpus. Hashmarks does not mutate Oh-Goon source or QA authority. On the QA-bound 1267.0.62 blind checkout, PUBLIC questions drive retrieval and SECRET evidence paths are consulted only after retrieval for grading. The retained v0.10.17 condensed lane hit at least one expected evidence file on 61.9% of 147 questions; the accepted 0.10.18 control-surface mechanism reaches 72.1%. This benchmark authorizes retrieval optimization only, not candidate certification, Codex correctness, or model-token savings.

## Hashmarks 0.10.19 task-query integration

Agent wrappers should prefer `CodeMap.find_task(full_task)` when the input is a natural-language repository question or maintenance task. Exact identifier/path lookups should continue to use `find()` directly. `task_query_views()` can be recorded in navigation telemetry so a grader can distinguish query formulation from downstream retrieval. Oh-Goon remains the authority for QA/certification; Hashmarks receives no SECRET answer/evidence material during retrieval.

## Hashmarks 0.10.20 evidence-family integration

Oh-Goon remains an external read-only benchmark corpus. Hashmarks does not consume Oh-Goon SECRET answers at query time. The candidate-visible task text may trigger generic evidence families (for example privacy/security, CI/CD, dependency materialization, browser preflight, observability, workspace/snapshot, or capacity), and SECRET evidence is consulted only after retrieval for benchmark grading. No Oh-Goon source or artifact is modified by this phase.

## Hashmarks v0.10.40 failed-verification recovery evidence — historical benchmark

This section records a historical recovery experiment, not current integration guidance. Oh-Goon/agent harnesses may use failed verification as **their own** attempt-history signal and may query Hashmarks again for current repository evidence, but the failure itself is not Hashmarks repository authority. New integrations must not feed agent retry memory back into Hashmarks as a product responsibility.

## v0.10.47 Codex economics evidence
The Codex economics harness is a qualification surface, not runtime ranking authority. Oh-Goon may consume its frozen results as evidence about agent cost/correctness, but absence of an authenticated Codex executable must remain an explicit external-execution gate.

## v0.10.48 selective Codex scout evidence
Oh-Goon may consume the selective-scout artifact as evidence that ambiguity-triggered extra inference is bounded and explicitly costed. A scout recommendation is advisory evidence, not execution authority.

## v0.10.49 Codex economics matrix
Oh-Goon can consume the frozen matrix as a qualification artifact for agent-selection policy. It must not infer cost when Codex token telemetry is missing; rollout recovery is the authority fallback.

## v0.10.50 shared agent context service
For multi-agent harnesses, run Hashmarks as one warm daemon/MCP context authority and let workers query it. Do not initialize a separate CodeMap in every child process unless cold-start cost itself is under test. Keep SECRET grading corpora outside worker-visible repository bytes.

## v0.10.51 worker action map

Oh-Goon/Codex workers should consume `task_action_map()` when deciding where to edit and what to verify. `find_task()` remains the canonical evidence ranking and its ranks are retained in the action map. Certification/QA answer keys must never be mounted inside the candidate worker repository.

## v0.10.52 Codex/agent integration

For multi-agent execution, start one local CodeMap service per workspace and give every child only the socket endpoint. Children query action maps; they do not call `sync()` unless the root explicitly owns a freshness transition. This keeps repository identity centralized while worker traces and edits remain isolated.

## v0.10.53 failed-verification recovery — legacy boundary debt

Historical clients can still encounter `failed_edit_targets`, but **new Oh-Goon/Codex integrations must not use Hashmarks as failed-attempt memory**. The worker/agent owns which targets it already tried, why an attempt failed, and whether to retry or choose another candidate. Hashmarks supplies repository ownership, alternatives, ambiguity, freshness, and verification relevance only. `failed_edit_targets` is compatibility debt pending migration/removal; do not add new dependencies on it.

## v0.10.54 selective scout gate — legacy boundary debt

`task_decision_packet().scout.required` is historical agent-orchestration language and must not drive new integrations. New consumers should read repository ambiguity/candidate/discrimination evidence and make their own delegation decision. Whether to spawn a side agent, which model to use, and what context to give it are Oh-Goon/agent-harness responsibilities, not Hashmarks authority.

## v0.10.55 agent scoring

Oh-Goon should retain `hashmarks.agent-work-trace.v1` events for edit attempts, verification, reads/searches, action packets, and scouts. Certification claims should use `verified_solution`, while `work_score` is an explainable diagnostic score rather than a replacement for pass/fail verification.

## v0.10.56 verification command handoff

Workers should execute `task_decision_packet().verification_plan.argv` directly when `available=true`, from the declared working directory. They must record the actual return code/outcome in the work trace; the presence of a plan alone is never verification success.
