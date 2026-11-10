# Hashmarks evidence-quality requirements

**Status:** Proposed delivery requirements; implementation and qualification are not implied.  
**Scope:** Strengthen the existing headless repository observer through better evidence and evidence economics.  
**Prepared:** 2026-11-10.  
**Paired delivery document:** `oh-goon/oh-goon:docs/development/EVIDENCE_DRIVEN_ORCHESTRATION_REQUIREMENTS.md`.

## 1. Goal and governing owners

> **Make Hashmarks more useful by establishing repository facts more precisely, preserving their basis and limits, and retrieving them more efficiently. Do not add presentation or execution responsibility.**

The [observer constitution](../reference/PRODUCT_BOUNDARY.md), [invariants](../reference/INVARIANTS.md), and [state and semantic owners](../reference/STATE_AND_SEMANTIC_OWNERS.md) remain normative. This document supplies a bounded improvement and acceptance plan under those owners. It does not create another feature-admission authority, runtime registry, universal evidence schema, or mandatory merge gate. Resolve any conflict in the existing owning contract rather than maintaining two meanings.

Hashmarks owns repository observation, qualified relationships, source correspondence, provenance, freshness, completeness, uncertainty and factual change. Coding agents own reasoning and edits. Oh-Goon or another authorized executor owns admission, native operations, execution custody and outcomes. Native tools retain their own resolution and operational semantics.

Hashmarks must remain independently usable through its existing Python, CLI and MCP interfaces. No requirement may make Oh-Goon, a browser, a renderer, a hosted service or a model provider necessary to obtain repository evidence.

### Explicit exclusions

This initiative introduces **no Pierre integration, GUI, viewer, dashboard, HTML report, syntax highlighter, diff renderer, readability product, narrative generator, presentation dependency or UI-specific API** in either repository. It does not remove supported CLI help, errors, existing transports or structured evidence explanations.

Also excluded: repository/task command execution inside Hashmarks; Git history crawling or mutation; package resolution or installation; test execution; workflow decisions; a global semantic knowledge graph; a new evidence database, history store, cache family, broker or scheduler. Existing narrow distribution/installation exceptions are unchanged and cannot justify analysis-time execution.

## 2. Existing capabilities are the starting point

The [MCP contract](../integration/MCP.md) documents `task_evidence`, `change_impact`, `structural_locality`, `correlate_evidence`, `repository_evidence`, `dependency_codemap`, `repository_declarations`, `post_change` and `evidence_comparison`. They are investigation entry points, not a proposed second tool catalog.

The [derived-authority and bounded-comparison plan](../maintainers/DERIVED_AUTHORITY_AND_BOUNDED_COMPARISON_PLAN.md) records an implemented baseline and completed saturation within its declared scope. Do not reopen that work, rebuild provenance/explanation, or add retention merely because this document mentions related outcomes. Historical qualification remains scoped to its recorded revision.

Before changing a capability, inspect its current public contract, producer owner, supported consumers and decisive tests. Classify the selected scenario as **SUPPORTED**, **PARTIAL**, **DEMONSTRATED GAP** or **UNKNOWN**. These are planning dispositions, not new runtime states. A documented feature is not proof of runtime qualification; a partial search is not proof of absence.

Defect repairs require a violated contract and reachable consequence. Capability improvements require a concrete consumer need or measured cost and a bounded acceptance scenario; they need not pretend that correct existing behavior is a bug. Already-satisfied obligations require no implementation.

## 3. Evidence improvement requirements

| ID | Required outcome | Acceptance obligation |
| --- | --- | --- |
| HE-01 | Exact source correspondence | Bind evidence to the admitted repository/member, relevant revision and coordinate convention; distinguish identical bytes at different locations and current from historical endpoints. |
| HE-02 | Inspectable basis | Preserve existing typed evidence references and structured derivation reasons sufficient to inspect or validate a claim, without inventing missing provenance. |
| HE-03 | Honest qualifications | Keep freshness, semantic coverage, observation bounds, ambiguity, visibility and unsupported cases distinct where their meaning differs. |
| HE-04 | Useful repository relationships | Improve supported source, dependency, declaration, diagnostic or verifier relationships through their existing semantic owners, with bounded counterexamples and uncertainty controls. |
| HE-05 | Sound change comparison | Distinguish repository changes, source relocation, producer/capability changes and unavailable endpoints; do not infer causation or semantic equivalence from visual/textual similarity. |
| HE-06 | Lower evidence cost | Reduce unnecessary reads, parsing, latency or payload cost without weakening qualification, source admission or authority. |
| HE-07 | Consumer-independent contracts | Preserve declared meaning through Python, CLI and MCP and supported consumer handoffs; no UI-specific fields, protocol family or required orchestration host. |
| HE-08 | Privacy and scope preservation | Denied evidence must not influence exposed selection, counts, identifiers or diagnostics beyond the existing disclosure contract; no dependency-driven expansion outside admitted input. |

### 3.1 Source identity and ranges

Reuse the existing [source-range receipt](../reference/SOURCE_RANGE_RECEIPTS.md), [source-binding](../reference/SOURCE_BINDINGS.md) and [repository-binding](../reference/REPOSITORY_EVIDENCE_BINDINGS.md) authorities. Do not prescribe a new identity format.

A commit identifier plus a dirty flag is insufficient to identify changing working-tree content. A matching digest is not physical source identity. Range coordinates must retain their endpoint and declared unit; byte offsets, decoded characters and physical lines cannot be silently interchanged.

The current changed-line contract describes correspondence with current admitted source. It does not prove an edit occurred, a behavior changed, a call ran or a verifier covers that behavior. Old or deleted source must use an explicitly supported historical endpoint, supplied through the existing caller-owned authority path. Otherwise retain unresolved/unavailable evidence. Never substitute the current occupant of a line or symbol name. Historical support does not authorize a history crawler, permanent archive or new retention cache.

### 3.2 Evidence basis, not presentation

Structured reasons and typed supporting references are evidence. Visual layout, prose summaries and reviewer interaction are not part of this work.

Preserve each existing evidence family's authority-bearing dimensions: semantic scope, physical source, member revision, relevant producer semantics/capability, configuration/visibility inputs and observation bounds. Bind only dimensions that materially affect interpretation or reuse. Do not impose one giant envelope or global confidence score on different evidence families.

Claims must remain connected to their qualified basis after transport or permitted compaction. A supported detail reference may avoid embedding all source bytes, but unavailable details must stay unavailable rather than being reconstructed from a newer source. Stored packets are comparison inputs under their contract, not permission to hydrate current semantic state.

### 3.3 Uncertainty, absence and relationship strength

Empty, truncated, unsupported, denied, stale and ambiguous results do not mean the same thing. Preserve existing typed distinctions and machine-readable reasons. Qualified absence requires the appropriate semantic owner to establish a complete, current, non-truncated observation scope for that exact claim.

Use existing CodeMap and evidence-family relationships. Do not introduce a universal ontology, infer declaration equivalence transitively, or promote a candidate into a proven relationship. Static correspondence is not runtime causation. Verifier relevance or qualified membership is not proof of coverage, test success, sufficiency or permission to execute.

### 3.4 Native observations and adapters

Consume supported passive repository metadata and caller-supplied native observations. Keep producer-specific syntax at existing adapter boundaries; native tools still own package resolution, installation, environment interpretation, Git operations and test execution.

Keep authored intent, resolved inventory, installed state, test collection and execution outcome distinct. A lockfile cannot establish installed state; a diagnostic cannot establish a passing test. An input called an observation is not automatically trusted or current: preserve its supplied provenance, qualification and limits.

No new process runner or automatic tool invocation is authorized in Hashmarks. No native command is required when supported passive evidence already suffices.

### 3.5 Evidence economics

Measure an existing query path on a fixed workload before changing it. Compare cold, warm and post-edit behavior where relevant; record source reads/bytes, parse work, returned bytes, latency and memory. Use existing measurement owners and independently checked expected facts.

For a semantics-preserving optimization, compare qualified results under equivalent inputs. For an intentional capability improvement, document the expected semantic difference and demonstrate it against an independent source/fixture oracle. Identical old/new outputs are not required when better evidence is the intended outcome.

Limits may bound delivery but cannot strengthen authority. Cache hits, misses, eviction and restart must not change factual meaning. Reuse existing invalidation/state owners; do not add a new cache or historical store without a separately evidenced need and applicable product approval. Do not claim a numerical speedup from one incomparable run.

## 4. Headless acceptance scenarios

Map each scenario to an existing test first. Add a focused regression or capability test only for missing proof. Scenario labels below are test obligations, not new APIs or runtime statuses.

| ID | Controlled scenario | Required observation |
| --- | --- | --- |
| HC-01 | Change a source member twice while HEAD and the dirty flag remain unchanged. | Evidence from the first content revision cannot qualify the second as current. |
| HC-02 | Identical bytes at two paths; then a move with unchanged bytes. | Content equality does not collapse physical identity; semantic and locator change remain distinguishable. |
| HC-03 | Delete a symbol or request an older endpoint; include multibyte text and alternate line endings under supported coordinate contracts. | Exact endpoint/range binding or explicit unresolved state; no current-line substitution. |
| HC-04 | Bound a result, deny a relevant member, or use unsupported dynamic syntax. | No fabricated absence, completeness, unique ownership or leaked denied evidence. |
| HC-05 | Change observer semantics/capability without changing repository bytes. | Interpretation changes are not mislabeled as repository edits; invalid reuse is rejected. |
| HC-06 | Supply a diagnostic overlapping changed code and a nearby unrelated diagnostic. | Supported source correlation is preserved; neither overlap nor proximity proves causation. |
| HC-07 | Compare authored dependencies, a native lock and a supplied installed-state observation. | Authority domains remain distinct; disagreement and missing qualifications are retained. |
| HC-08 | Query through supported Python/CLI/MCP projections; repeat after cache eviction or restart. | Equivalent qualified facts and traceable omissions; no browser, renderer or new subprocess dependency. |
| HC-09 | Refine an owner result within its supported contract and exercise a real consumer plus unknown/ambiguous controls. | No independent consumer obligation disappears because an incidental classification changed. |
| HC-10 | Use existing declaration correspondences A-B and B-C without an A-C producer claim. | No invented A-C equivalence, global graph authority or winner selection. |
| HC-11 | Headless query before/after a proposed cost reduction. | Expected evidence remains correct; measured reads/bytes/latency/memory describe comparable conditions. |
| HC-12 | Mutate an admitted input during a multi-read observation. | Return a coherent observation under the existing snapshot contract or explicit unresolved/failure; never combine incompatible generations or add an unbounded retry. |

Start with one Python and one JavaScript/TypeScript or mixed-language fixture where the selected contract supports them. Unsupported languages remain explicitly outside the scenario's claimed coverage; do not force universal support. Include a bounded real admitted repository workload before making general usefulness or performance claims.

## 5. Cross-repository handoff

The [Oh-Goon integration boundary](../integration/OH_GOON_INTEGRATION.md), [verification membership handoff](../reference/VERIFICATION_MEMBERSHIP_HANDOFF.md) and [changed-set verification](../reference/CHANGED_SET_VERIFICATION.md) remain the owners of the producer contract.

Hashmarks establishes qualified repository evidence and supported exact verification membership. Oh-Goon validates through supported producer contracts, binds its own admission/custody and executes native work. Oh-Goon must not parse producer internals or re-create missing relevance. Hashmarks must not prescribe worker count, commands, retries, admission policy or result certification.

A cross-project change is needed only when the producer contract or a real consumer obligation changes. Improvements confined to Hashmarks may ship independently. Public breaking changes require an explicit supported-version migration; do not add a legacy fallback, second schema family or dual intelligence implementation merely to retain obsolete internal behavior.

## 6. Ordered delivery and ownership

| Work package | Responsible owner | Deliverable and exit condition |
| --- | --- | --- |
| H0: qualify one useful question | Existing Hashmarks evidence owner | Pin source and selected consumer; map requirements to current contracts/tests; record SUPPORTED/PARTIAL/GAP/UNKNOWN and the decisive next probe. No blanket repository-audit prerequisite. |
| H1: improve the existing producer | Same evidence-family owner | Smallest evidence correction or enhancement, paired positive/uncertain controls, and no new state/transport/presentation owner. Exit on a demonstrated user-relevant fact or reduced evidence cost. |
| H2: qualify affected consumers | Hashmarks plus affected consumer owner | Exercise allowed semantic refinements, foreign/stale evidence and supported uncertainty; migrate only affected consumers through their current public boundary. |
| H3: measure and close | Existing qualification owner; EvalShot for comparative agent scoring | Comparable evidence-quality/economics receipt, actual commands/outcomes, residual limits and updated owning docs. No ranking or general improvement claim without its evidence. |

Do not wait for unrelated workstreams to finish. Block only unresolved dependencies material to the selected change. Do not invent findings or implementation work to fill a roadmap.

## 7. Review, validation and recovery

Use existing [AgentsCookbook skills](https://github.com/Hugloss/agentsCookbook/tree/4e083f49daf3bfe4e53d7528a82dea04d93914ef/skills): `native-tool-authority-review`, `evidence-provenance-binding-review`, `canonical-consumer-contract-review`, `fact-grounding-auditor` and `plan-contract-guard`. Use `single-source-of-truth-review` only when two reachable producers can establish accepted truth for the same fact, scope and generation. Select narrower negative-evidence or snapshot reviews only for implicated paths. Do not add a new skill catalog or mandatory review service.

A PR identifies its current owner, benefit, exact source/consumer boundary, applicable HE/HC obligations and actual proof. A defect repair provides a before-failing regression; a new capability provides a bounded requirement and independent oracle. Ordinary maintenance need not benchmark every PR. Performance claims require comparable measurement. Reuse the existing [CI verification policy](../maintainers/CI_VERIFICATION.md); do not weaken existing full-suite/release obligations or add an unrelated global gate.

For implementation failures, revert through ordinary native version control and restore the supported dependency/API combination. Rebuild disposable derived state through its existing owner when required; never relabel stale state to preserve availability. A schema/data migration must use the existing owner's migration and recovery policy and prove it before release. No runtime rollback mechanism is required for this documentation-only change.

## 8. Completion and evidence boundary

A delivered improvement must show: a useful grounded fact or evidenced cost reduction; exact source/provenance and uncertainty preservation; supported headless consumer behavior; no new GUI/presentation/native-engine replacement; and focused tests plus the repository-required checks for its actual scope. Keep unrelated unknowns explicit rather than declaring repository-wide compliance.

Planning references were inspected at Hashmarks `dfcebc228e7edec0f55185ec5da333969d36012a`, Oh-Goon `288d93806f96d196c87b6aa1e30c4a8674b64bb5`, and AgentsCookbook `4e083f49daf3bfe4e53d7528a82dea04d93914ef`. They establish the documented ownership and available contracts, not complete implementation coverage. Refresh affected source and tests before implementation. No runtime tests, benchmarks or whole-codebase audit are claimed by this document.
