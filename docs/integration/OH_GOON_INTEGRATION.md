# Hashmarks ↔ Oh-Goon integration contract

**Status: current normative integration guidance.**

## Three-plane model

Hashmarks and Oh-Goon are complementary systems with different authority.

- **Hashmarks** answers what repository evidence says matters: identity, topology, ownership, impact, freshness, verification relevance, and provenance.
- **The agent/human** decides what change to make and owns its reasoning, hypotheses, attempt history, and solution behavior.
- **Oh-Goon** decides whether work is admitted, how it runs, how processes/environments are controlled, and whether execution evidence is certifiable.

**Interoperability transfers evidence, never authority.**

## Hashmarks owns

- canonical repository/input/content identities;
- repository observation and freshness evidence;
- CodeMap and repository-derived ownership/impact evidence;
- deterministic repository-work/test membership selection;
- verification relevance and repository-bound verification descriptions;
- producer identity, provenance, evidence contexts, and consumer-conformance validation;
- evidence economics and qualification of Hashmarks-owned semantics.

## Oh-Goon owns

- admission and policy enforcement;
- work scheduling and placement;
- sandbox/workspace/runtime-environment authority;
- process launch and process-tree supervision;
- timeout, cancellation, retry, resume, and recovery policy;
- network/egress/resource policy;
- execution-result authority;
- certification and release promotion;
- Game Tape and execution-history ownership.

Hashmarks must never become Oh-Goon's execution motor. Oh-Goon must not create a second competing implementation of Hashmarks repository identity/intelligence.

## Agent responsibilities remain external

Hashmarks may expose repository ambiguity, alternative candidates, likely repair surfaces, and verification relevance. It does not own:

- solution reasoning or patch design;
- edit execution;
- attempt/failed-edit memory;
- delegation/scout/sub-agent choices;
- model routing or prompt/context strategy;
- interpretation of verification outcomes as a recovery strategy.

The agent can query Hashmarks again after repository bytes change, but its own workflow history does not become repository authority.

## Evidence across repair candidates

Obtain `codemap.tasks.evidence(task)` from each admitted candidate before the
agent reasons about that candidate. Preserve its packet identity, producer
identity, receipt and provenance together. A source capture remains the
execution layer's authority; a refreshed observation does not replace an older
capture or supply execution results.

`codemap.changes.task_delta(task, changed_paths, previous_evidence=packet)`
compares changes within one repository and CodeMap continuity cut. The previous
packet must match the task, repository identity, pre-sync generation, and bound
evidence context. The operation validates those claims before synchronization.
Use it after an external edit to that same repository, before another sync.
Repository identity is not universally a workspace identity: Git-backed roots
with the same base tree may share it, while Git-free roots are workspace-bound.
An equal Git-tree identity and generation can therefore admit an older packet
in a different root. A differing selected source revision remains qualified as
`previous_index_binding: "mismatch"`; `path_changes` describes the receiving
index's own before/after synchronization, not the difference between captures.
Those facts do not prove that the captures are interchangeable.

The execution layer still needs a fresh task packet from every newly admitted
attempt before reasoning, even when repository identities compare equal.
Consumers must not rewrite the previous packet's identities to make it
admissible. The external campaign may retain both packets as separate
observations linked by its own candidate/run provenance.

Verification membership and source correspondence are also separate. Reobserve
an earlier report against the new candidate using its original nominated source
revisions; changed implementation, test or configuration inputs remain a
`mismatch`. A new externally supplied report may name the same flat membership
with current revision claims and obtain `proven` source equivalence. Its source
observations and observation identity change; the member identity need not.
Neither matching source claims nor unchanged membership upgrades unknown
repository freshness or proves execution. Inputs outside the report's explicit
union are not inferred to be covered.

### Deterministic narrow dogfood workload

The existing `resolve_inputs` regression in `tests/test_hardening.py` exercises
native path glob semantics for `*`, `?`, and character classes, including a
nearby filename that must not match a single-character pattern. It provides a
small actual Hashmarks repair workload without adding an agent harness:

1. Export a reviewed source candidate to a disposable workspace and record its
   source/producer identities outside the source tree. Before opening or copying
   members, exclude native configuration by path metadata: `.codex/*`,
   `.opencode/*`, and root `opencode.json` / `opencode.jsonc`. Record the exact
   excluded paths in the external export receipt; retain the original native
   files. An export rejected by source admission remains rejected preparation:
   rebuild from the original source with the explicit exclusions instead of
   deleting native files from the rejected candidate or reclassifying them as
   ordinary source. The export has a fresh Git database, not the original
   repository's history or native stores.
   A bounded component subject must declare its exact selection before capture,
   retain the original package initialization and actual runtime dependencies,
   and account for every selected member during review. Label it as component
   qualification; copied dependency/build metadata does not make it a complete
   Hashmarks distribution or establish repository-wide review. Native checks
   must load the copied component rather than fall back to the original
   checkout or another installed Hashmarks package.
2. Establish the passing baseline with
   `uv run --frozen --offline --no-sync --group test python -m pytest -q tests/test_hardening.py -k resolve_inputs`.
3. Keep `hashmarks/paths.py::has_glob` unchanged. Only in that disposable
   candidate, replace `if not has_glob(pattern):` in
   `hashmarks/inputs.py::resolve_inputs` with
   `if not any(ch in pattern for ch in "*["):`. This introduces a second accepted
   classifier that omits `?`: public `Glob("src/?.py").as_pattern()` accepts the
   pattern while discovery misclassifies it as a literal and raises
   `FileNotFoundError`. Prove that failure and preserve the `*` and bracket-class
   controls. Record this as an intentional split-authority mutation, not a newly
   discovered upstream defect. Authorize repairs in `hashmarks/inputs.py` and
   the behavioral regression source; keep the canonical classifier and the
   operator-owned independent verifier outside those write roots.
4. Let the external agent review and propose a repair. The executor owns
   admitting/applying that proposal and running the same native regression.
5. Acquire fresh Hashmarks evidence from the repaired admitted candidate and
   retain the real verification result under the external execution owner.

This fixture qualifies neither an external Codex integration nor campaign
convergence by itself. Those require the external controller's actual Runs and
results. Hashmarks remains the repository observer throughout.

The [shared dogfood acceptance contract](https://github.com/oh-goon/oh-goon/blob/main/docs/AGENT_SKILLS.md#hashmarks-dogfood-acceptance)
owns cross-product scenario outcomes and required campaign evidence. Retained
query diagnostics from a rejected preparation do not replace evidence from the
exact admitted capture.

## Repository-work selection handoff

The active selected-work handoff is
`hashmarks.verification-selection-envelope.v2` plus
`hashmarks.downstream-verification-contract.v2`. Its exact flat
`hashmarks.verification-membership.v1` membership is repository evidence.
`execution_layout="external"` leaves physical grouping and isolation to Oh-Goon.
Hashmarks' own qualification `test-shards.v3` and repository-work-selection
formats are separate contracts; their layouts do not become consumer execution policy.

An execution system should:

1. resolve the loaded producer implementation identity once;
2. call `validate_native_consumer_bundle()` with that expected identity;
3. consume the detached validated projection and bind its repository/source to admitted work;
4. reject stale, unknown, mismatched or unsupported evidence under its admission policy;
5. project safe native executable selectors and execute the exact membership under its own policies.

The producer owns schema validation, member ordering, duplicate-member rules and
opaque producer/member/envelope/contract identities. The consumer preserves those
identities and checks its own executable-target constraints. It does not reconstruct
producer hashes or reparse raw envelopes after successful validation.

Oh-Goon may refine runtime grouping after a timeout only if completed, remaining
and unexecuted membership account for every admitted member exactly once.
Hashmarks does not choose timeout budgets, retries, concurrency, schedules,
machines, isolation or refinement strategy. A retained validator proves the
supplied packet's consistency; live source observation and admission are explicit
operations with their own scope and freshness.

## Verification handoff

Hashmarks can identify repository-derived verification relevance and mechanically describe verification surfaces. The presence of a verification description is **not** proof that verification ran or passed.

Oh-Goon/external runners own:

- whether a verification command is admitted;
- where and how it executes;
- actual exit code/output provenance;
- PASS/FAIL/result authority;
- recovery after failure.

## Freshness handoff

Consumers should treat Hashmarks freshness/provenance as a repository-evidence contract:

- `current` means the required repository evidence is positively current under the relevant observation authority;
- `stale` means a relevant change invalidated it;
- `unknown` means currentness cannot be proven.

A consumer must not convert `unknown` to fresh based on recency or convenience.
`source_equivalence: "proven"`, where present in a correspondence contract,
describes source correspondence. It is not an alternative spelling of the
canonical freshness state.

## Trust and producer policy

Repository-controlled declarations are claims unless the consumer's policy explicitly trusts the producer/source. Hashmarks can validate the structure and identity of evidence; the execution/certification layer decides which producers and evidence classes are trusted for admission or reuse.

Consumers that need exact loaded-producer binding should use the supported top-level `hashmarks.native_producer_implementation_identity()` API. Verification-selection consumers should use the supported top-level `hashmarks.validate_native_consumer_bundle()` validator. Do not bind integration code to `hashmarks.producer_identity`, `hashmarks.consumer_conformance`, or other implementation submodules merely because they are importable.

Consumers of broader repository-intelligence payloads should use the supported top-level `hashmarks.validate_repository_intelligence_evidence()` validator instead of maintaining a downstream schema allowlist or recreating Hashmarks identity/freshness/authority checks. A validated action map remains repository evidence only; it is not an execution membership contract. Verification plans may describe command intent, but the external execution system still decides whether and how to admit and execute that intent.

## Dependency strategy

Keep Hashmarks standalone. Oh-Goon should consume a pinned Hashmarks package/version through a thin adapter rather than copying Hashmarks internals into the Oh-Goon tree.

Record the resolved Hashmarks version and relevant evidence/contract identities in execution provenance so later certification can reproduce the exact decision inputs.

Embedding consumers install the selected wheel from
[GitHub Releases](https://github.com/Hugloss/Hashmarks/releases) into their own
Python environment using the environment's native package tool. A standalone
CLI/MCP executable is a separate distribution, not an importable Python library.
Hashmarks does not publish this release workflow to PyPI. Pin the selected release
or reviewed source commit; source changes documented as Unreleased require that
source build until a release includes them. See
[Public API and stability](../reference/API_STABILITY.md) for supported imports.

## CodeMap integration

Identity observations can be consumed independently of CodeMap. Consumers choose
whether derived CodeMap intelligence is required for a particular workflow. A
service failure or unknown freshness does not weaken that consumer's requirement;
reconciliation and any alternative evidence path remain explicit consumer choices.

Direct Python and service transport have distinct call shapes:

| Operation | Direct `CodeMap` | `CodeMapServiceClient` |
| --- | --- | --- |
| Synchronize | `codemap.index.sync()` | `client.sync()` |
| Task evidence | `codemap.tasks.evidence(task)` | `client.task_evidence(task)` |
| Selected-input inventory | `RepositoryIdentity.observe_inputs(...)` | No service-client method |
| Native membership observation | `codemap.verification.observe_membership(report)` | `client.verification_membership(report)` |
| ECMAScript source syntax | `codemap.source.ecmascript(...)` | `client.source_ecmascript(...)` |
| Exact byte receipt | `codemap.source.range_receipt(...)` | `client.source_range_receipt(...)` |

The documented service client import is
`from hashmarks.codemap import CodeMapServiceClient`. It connects to an
already managed CodeMap service. Do not assume a direct component method is
automatically available over CLI, MCP, or service transport.

The standalone observer capabilities and ownership boundaries are collected in
[Standalone consumer integration](STANDALONE_CONSUMERS.md). They let consumers
use Hashmarks identity, declarations, source, and membership semantics without a
dependency on Oh-Goon or a copy of its execution behavior.

## Normative references

- [`../reference/PRODUCT_BOUNDARY.md`](../reference/PRODUCT_BOUNDARY.md)
- [`../reference/ARCHITECTURE.md`](../reference/ARCHITECTURE.md)
- [`../reference/INVARIANTS.md`](../reference/INVARIANTS.md)
