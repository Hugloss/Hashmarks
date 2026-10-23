# Hashmarks observer constitution

**Status: normative.** This document defines what Hashmarks is: a repository observer. It is a product constitution, not a second policy engine that must itself be interpreted by another policy layer.

The shortest governing rule is:

> **Observe repository state and evidence. Preserve identity, provenance, completeness, freshness, uncertainty, and change. Never decide the consumer's next action or the execution system's policy.**

New work is checked directly against that rule and the ownership boundaries below. Defect repairs and refactors that do not change product responsibility do not require ceremonial policy records.

Implementation presence is evidence about the codebase, not authority to expand the product boundary. A feature does not belong in Hashmarks merely because it is useful to an agent, improves an agent benchmark, already has partial implementation, or can technically be added.

## Product profile

Hashmarks is a **repository observer that exposes repository intelligence for agents, tools, and humans**.

Its job is to turn repository state into compact, freshness-bound, provenance-bearing evidence that helps a consumer understand the repository: identity, topology, symbols, references, ownership, impact, ambiguity, candidate repository surfaces, verification relationships, change consequences, and related repository-derived structure.

Hashmarks should be excellent at answering observer questions of the form:

> **What is observable about this repository, how do we know it, how complete/current is that observation, and what changed?**

This includes structural-locality facts useful to external refactoring agents: exact symbol spans, bounded call/caller relationships, forwarding-only syntax, file/symbol navigation closure, related verification paths, ambiguity, and before/after deltas. Hashmarks may expose those facts and their completeness, but it must not decide whether a decomposition is desirable, whether a helper has semantic value, or whether an edit should be made.

Hashmarks must not evolve into the system that decides or performs the consumer's work.

The permanent ownership split is:

- **Hashmarks:** repository intelligence and the infrastructure required to derive, validate, cache, invalidate, serialize, and economically expose that intelligence.
- **Consumer / coding agent / IDE / human:** reasoning, planning, choices, memory of its own work, edits, hypotheses, interaction strategy, and final solution behavior.
- **Execution / certification system:** process execution, admission, isolation, scheduling, timeouts, retries, resume, environment recovery, result authority, and certification.

### Narrow product-distribution lifecycle exception

Hashmarks also has one deliberately narrow responsibility that is **not repository intelligence**: maintaining awareness of its own published product release and handing an explicitly approved self-update to the installation mechanism that already owns the installed bytes.

> **Hashmarks may discover update availability. It never owns updating itself.**

This exception is bounded to product self-maintenance:

- an eligible interactive CLI may periodically read public GitHub latest-release metadata;
- the request carries no repository-derived data or ambient GitHub credentials and its disposable cache stays outside repository state;
- MCP, daemon, CI, and non-interactive invocations perform no automatic check, and `HASHMARKS_NO_UPDATE_CHECK=1` disables automatic checks;
- `hashmarks upgrade` may perform an explicit fresh release check;
- installation mutation is offered only for the canonical standalone distribution and requires an explicit interactive **Upgrade now** choice;
- that standalone handoff replaces the running Hashmarks process with the existing checksum-verifying standalone installer;
- Python-package/source installations are reported as externally managed and are handed back to the native mechanism chosen by the user or surrounding workflow;
- Hashmarks does not detect/certify uv, pip, pipx, or other package-manager ownership, parse their receipts, reproduce their filesystem layouts, or preflight their update semantics.

This exception does not transfer general process-execution authority into Hashmarks. It does not admit repository/task command execution, a Hashmarks-owned package resolver or package-resolution layer, package-manager detection/certification, installer backend registries, workflow orchestration, release promotion, retries/supervision, or execution-result authority. The standalone handoff exists only to stop the old Hashmarks process and let the existing standalone installer replace its own product bytes.

## Four permanent non-goals

Hashmarks must never be turned into any of the adjacent systems or authorities it serves.

1. **Not the agent.** Hashmarks must not absorb the consumer's reasoning, planning, attempt history, memory, edits, delegation, model or tool choices, workflow sequencing, recovery decisions, or final-solution authority. An agent may consume Hashmarks evidence, but Hashmarks must not become the agent's solution loop.
2. **Not the execution/certification motor.** Hashmarks must not absorb Oh-Goon-style admission, sandboxing, repository/task process launch or supervision, cancellation, timeout/retry/resume, worker placement, runtime-environment control, execution-result authority, certification, release promotion, or Game Tape/execution-history ownership. The bounded standalone self-update handoff above does not grant any of those authorities: it can only replace the running standalone Hashmarks CLI with its existing standalone installer after explicit consent. Oh-Goon or another execution layer may consume Hashmarks evidence, but Hashmarks must not become its execution engine.
3. **Not a repository version-control, mutation, or historical-archive engine.** Hashmarks may observe caller-selected repository authorities, preserve immutable observations needed by the active consumer work window, and compare or diff repository meaning and evidence across those authorities. It must not create or manage branches, implement merge/rebase/cherry-pick or conflict-resolution semantics, roll back/revert/reset/checkout repository state, mutate refs or worktrees, crawl or pre-index Git history, retain an unbounded timeline of repository observations, or otherwise become an alternative Git/repository-lifecycle/history owner. Git and the external consumer/harness own those operations. Historical observation and semantic diff are bounded, read-only repository intelligence; they never grant repository-mutation authority or require permanent retention.
4. **Not a semantic knowledge graph.** Hashmarks may expose bounded repository-derived graphs already owned by CodeMap and explicit producer-owned correspondence inside repository declarations. It must not turn semantic subjects, roles, or correspondence into a global node/edge registry, infer transitive/symmetric/inverse/reachability relationships, compute semantic graph closure or paths, unify provider vocabularies into a global ontology, persist semantic edges independently of the producer claim that created them, hydrate semantic/relationship state from caller-supplied previous observations, or derive graph confidence/centrality/ranking/precedence. Explicit A↔B and B↔C claims never manufacture A↔C. Cycles such as A↔B, B↔C, C↔A never manufacture a connected component, equivalence class, consensus, majority authority, or component-level winner. Reopening CodeMap does not restore prior semantic relationships merely because the durable state directory still exists. A general semantic graph or graph query layer is outside the Hashmarks product boundary.

Historical support is a **bounded working-set capability**, not time travel over the repository's lifetime. Hashmarks may retain the small set of explicit authorities useful to an active agent/session or similarly bounded task window, subject to bounded count/time/bytes retention and ordinary eviction. Eviction changes availability/cost, never repository meaning. If an older authority is needed after eviction, the caller or Git must supply/reconstruct that authority again; Hashmarks must not scan backwards through repository history to recover it.

### Semantic identity without repository-history ownership

Hashmarks may borrow identity and semantic-comparison primitives from versioned-data systems when those primitives remain read-only repository intelligence. In particular, Hashmarks may expose separate identities for a provider-declared semantic subject, an exact declaration/evidence definition, and an immutable observed result; it may preserve provenance and compare those observations factually.

Those identities do not create a Hashmarks-owned commit graph. A semantic subject identity is not a branch or ref; a declaration identity is not a commit; an observation identity is not a checkout target. No identity primitive grants branch, merge, rebase, cherry-pick, rollback, reset, checkout, push/pull, conflict-resolution, worktree/ref mutation, or permanent history-retention authority.

The preferred implementation rule is:

> **Identity without ownership; compare without mutation; bounded evidence without repository-lifetime history.**

If a proposed identity/history feature requires Hashmarks to manage an evolving line of history rather than compare explicit observations, it crosses this boundary and must be reduced to the read-only semantic primitive or remain with Git/the caller.

These are ownership rules, not wording rules. Renaming orchestration as "intelligence", execution policy as "evidence", agent memory as "context", or Git lifecycle as "history management" does not make it Hashmarks functionality. Interoperability transfers evidence, never authority.

Every proposal must therefore answer four negative questions before admission: **does this make Hashmarks more like the agent, more like the execution/certification system, more like a repository version-control/mutation engine, or more like a general semantic knowledge graph?** If yes, reject it or split out only the repository-derived primitive.

## Repository scope boundary: do not chase external libraries

> **Do not chase remaining findings in external libraries.**

Hashmarks analyzes the **admitted repository-owned material**, not the repository's dependency ecosystem. An import, reference, lockfile entry, package declaration, or dependency edge may be valid repository evidence, but it does **not** transfer analysis ownership to the dependency implementation.

The default rule is:

> **An import is an evidence edge, not permission to recursively investigate the imported library.**

Therefore Hashmarks must not expand ordinary repository analysis merely because repository code imports or calls a dependency. By default, analysis does not descend into dependency implementations such as virtual environments, `site-packages`, `node_modules`, package-manager caches, SDK/runtime installations, or sibling dependency source checkouts outside the admitted repository. Vendored/generated dependency trees are analyzed only when they are explicitly admitted as repository-owned input. If a third-party project is itself the explicitly admitted target repository, it is analyzed as that repository—not because another repository happened to depend on it.

Third-party libraries may be used during **Hashmarks development or qualification** as bounded real-code corpora to expose generic analyzer defects. That use is evidence gathering, not a standing product roadmap. Once a generic defect is characterized, reduce it to neutral repository semantics and regression coverage. Do not keep investigating Starlette, Pydantic, pytest, or any other named dependency merely to lower a finding count. Do not add package-name suppression tables or library-specific analyzer behavior unless the package identity itself is authoritative repository evidence for a deliberately admitted contract.

Named external-library findings retained in historical evidence are **characterization history, not backlog**. A remaining external-library finding becomes actionable only if it proves a generic repository-intelligence correctness/freshness/ambiguity defect or the same generic defect is reproduced in repository-owned material. Otherwise the correct decision is **NO_CHANGE**.

This rule protects both product scope and economics: dependency fan-out must not turn one repository query into recursive ecosystem archaeology.

## Direct observer admission test

A new **repository-intelligence** production responsibility must fit the observer model before implementation. This is a direct ownership check, not a requirement to invent policy about policy. The narrowly bounded product-distribution lifecycle above is governed by its own explicit limits and must not be used as precedent for repository/task execution.

A change is in profile when its semantic output is an observation or projection of repository state/evidence: identity, structure, relationship, provenance, completeness, freshness, uncertainty, capability, or delta. If its semantic output is a recommendation, sufficiency decision, workflow choice, retry/recovery decision, execution control, or certification decision, that responsibility belongs outside Hashmarks.

The detailed tests below are review aids for ambiguous cases, not independent authorities. The observer constitution above remains the authority.

A proposed capability belongs in Hashmarks only if the answer to the following questions is clear and favorable.

### 1. Product-purpose test

Does the proposal improve Hashmarks' ability to understand, represent, validate, or efficiently expose **repository intelligence**?

If its primary purpose is to make decisions or perform work on behalf of a consumer, it belongs outside Hashmarks.

### 2. Source-of-authority test

What makes the result true?

Preferred Hashmarks authority sources are repository bytes, repository topology, maintained indexes, repository/dependency/build/test metadata, declared cross-repository relationships, and freshness/provenance over those sources.

If the result is made true primarily by consumer workflow history, model reasoning, runtime outcomes, task execution state, orchestration state, or a previous decision made by an agent, it is not repository authority.

### Cross-artifact declaration boundary

Repositories may contain several declarations of the same conceptual fact across files, formats, generated metadata, and repository areas. Hashmarks may bind explicitly scoped/provider-normalized declarations to exact repository evidence and report canonical equality/difference, ambiguity, qualified absence, provenance, freshness, identity, and factual deltas.

Hashmarks core must not invent a universal metadata ontology, infer semantic correspondence from similar names or values, rank sources of truth, choose a winning declaration, or turn majority agreement into authority. Producer-specific extraction and normalization terminate at a provider/adapter boundary; context that makes declarations non-comparable must remain in semantic scope rather than being flattened into a false conflict.

Explicit cross-provider correspondence also does not admit a semantic graph. Each correspondence remains a local producer-owned declaration claim. Hashmarks must not persist or compose those claims into inferred edges, transitive closure, reachability, graph paths, ontology equivalence, or graph-derived ranking. If A↔C matters, an explicit producer must own and evidence A↔C rather than relying on A↔B plus B↔C.

The normative contract is [Repository declarations](REPOSITORY_DECLARATIONS.md).

Producer discovery is an explicit trusted-extension boundary: caller-selected Python providers may detect and translate producer-native repository syntax into the neutral declaration contract, but repository bytes supporting semantic claims must pass through the Hashmarks-owned revision-binding provider context and remain equivalent through qualification. Dynamic file discovery uses bounded admitted repository-file enumeration through that same context, sharing CodeMap's repository discovery admission/pruning owner without requiring parser support for the producer format; the public API does not expose a raw repository filesystem path. Provider repository reads and enumerations are bounded and revalidated. Provider code is in-process and not sandboxed; its contract is read-only, and callers own provider trust. Hashmarks must not ambiently load provider entry points, execute repository-supplied provider code, or run arbitrary provider implementations through MCP. This does not grant Hashmarks process supervision, timeout/retry, sandbox, or execution-result authority. A provider detection miss is observability about that provider only, never semantic absence. Detected provider failure, provider-input drift, or provider-enumeration drift fails closed rather than yielding partial or stale evidence.

### Dependency-adapter translation boundary

Package-manager and resolver syntax is an edge concern. Maven, uv, Gradle, npm, SBOM, and future producer formats may be parsed by dedicated adapters, but shared dependency qualification must reason only about producer-neutral facts and semantic evidence authorities. A source-format `kind` is provenance, not authority; one physical source may support several semantic authorities, and a complete physical artifact does not by itself establish complete semantic coverage. New adapters must translate into the general dependency evidence contract rather than teach core Hashmarks the producer's native shape.

### Evidence authority precedence and non-strengthening

Hashmarks has several authority domains rather than one universal truth score. Content identity, freshness, repository relationships, qualified provider evidence, selection, and consumer projections answer different questions. Do not collapse them into one numeric confidence or a single total ordering.

Repository-file admission is shared across those authority domains. A producer may discover or interpret project/build/package metadata using producer-native semantics, but CodeMap-derived evidence cannot persist or qualify repository files through a producer-local pruning, visibility, or symlink policy. Project graphs, packaging-derived import roots, manifest freshness, and declaration-provider discovery reuse the canonical repository-file admission owner; producer semantics begin only after that boundary.

The safe precedence rule is directional:

> A weaker, derived, cached, summarized, or presentation layer may not silently strengthen, repair, override, or redefine the stronger authority it depends on.

In practice:

- repository bytes and explicit repository-owned metadata remain authoritative for the facts they directly define;
- freshness/provenance gates whether derived evidence may participate as current evidence, but cannot rewrite the underlying repository bytes;
- maintained indexes, parsers, provider evidence, reconstructed relationships, findings, rankings, and selections remain derived and must obey their existing kind-specific qualification rules;
- a compact packet, overview, finding, classification, or cached projection cannot make stale/unknown/ambiguous evidence fresh, proven, or uniquely resolved;
- native/provider evidence may strengthen a claim only under its explicit qualified provenance/freshness contract;
- when existing authority rules do not establish a unique resolution, Hashmarks preserves ambiguity or unknown rather than choosing by ordering convenience;
- human/model-generated interpretation and consumer outcomes are outside repository authority and cannot become repository facts merely because a projection repeats them.

Negative evidence is subject to the same rule. Hashmarks may own repository-native absence only when the relevant semantic owner can state the required observation scope and prove it complete and non-truncated for that claim. Empty or bounded results, provider detection misses, incomplete change sets, limited traversal, or compact projections do not themselves prove absence. Projection happens after semantic qualification; when the required universe is not closed, the result remains unknown/incomplete/not-admissible rather than being strengthened into `false`, `none`, `no match`, or another authoritative negative.

This is a non-strengthening contract, not permission to invent a new global precedence engine or negative-evidence manager. Existing evidence-kind authorities remain distinct.

### 3. Consumer-independence test

Would the capability still make sense for more than one kind of consumer—for example an agent, IDE, human reviewer, static analysis tool, or CI analysis component?

A Hashmarks primitive may be optimized for agent consumption, but its meaning must not depend on one particular agent loop or orchestration strategy.

### 4. Description-versus-control test

Does the capability **describe repository evidence**, or does it **control what the consumer should do next**?

Hashmarks may rank, nominate, qualify, or explain repository-derived evidence candidates. Those labels describe evidence strength or relationship, never a recommended consumer action. The consumer remains responsible for turning that evidence into an action.

### 5. State-ownership test

Is any new state required? If so, is that state about the repository and the evidence Hashmarks has observed, or about what a consumer has done?

Persistent Hashmarks state must exist to preserve repository intelligence, provenance, freshness, indexes, identities, or economics. It must not become hidden workflow memory for a consumer.

### 6. Determinism and replay test

Can the semantic result be reproduced from repository state plus explicit, neutral query/policy inputs?

Cache history may alter cost and latency, but must not secretly alter semantic authority. Incremental authority must never exceed fresh reconciled/cold truth.

### 7. Layering test

Is Hashmarks the narrowest correct owner of this capability?

If a consumer can implement the behavior by using existing Hashmarks evidence without weakening repository-intelligence quality, the behavior generally belongs to the consumer. If an execution layer can own it without losing repository meaning, it belongs to the execution layer.

### 8. Primitive-before-workflow test

If a proposal combines a useful repository primitive with consumer workflow, split it.

Keep the neutral repository-evidence primitive in Hashmarks. Keep reasoning, execution, orchestration, and lifecycle behavior outside.

### 9. Existing-surface test

Is the proposal being justified only because a similar API, field, benchmark, or implementation surface already exists?

Implementation presence is not architectural precedent. A production surface that violates this profile is a defect to narrow or remove, not an example to copy or harden.

### 10. Measurement test

Does a benchmark or experiment show that the proposal improves repository-intelligence correctness, evidence quality, freshness, latency, or evidence economics—or only that moving more of the agent workflow inside Hashmarks makes an end-to-end benchmark easier?

Only the first category is evidence for product admission. Measurement never overrides the product boundary.

## Proposal-handling workflow

A result from analysis, testing, benchmarking, profiling, integration work, or an agent recommendation is a **finding**, not automatically a product requirement. Before implementation, classify the finding into one of these paths:

1. **In-profile defect** — existing admitted repository-intelligence behavior is incorrect or unsafe. Fix it without expanding product responsibility.
2. **In-profile optimization** — existing admitted behavior is too slow, costly, large, or stale. Optimize it while preserving semantics and authority.
3. **Missing repository primitive** — the finding suggests repository intelligence Hashmarks does not yet expose. Run the full admission gate, then ADMIT or SPLIT.
4. **Consumer/runtime behavior** — the finding is useful, but its authority belongs to reasoning, workflow, execution, orchestration, or certification. Route it outward; do not implement it in Hashmarks.
5. **Boundary violation** — a proposal or production surface assigns responsibility outside the profile. Reject or split new proposals; narrow or remove an existing violating surface rather than harden or expand it.
6. **Measurement-only idea** — useful for evaluating Hashmarks but not for production semantics. Keep it in tests/benchmarks/experimental harnesses.

The key discipline is:

> **Observe first, classify second, implement third. Never let the existence of a finding decide product ownership.**

A coding agent must apply this classification to its **own proposals** as well as proposals supplied by others. If its best technical idea does not fit the Hashmarks profile, it must say so and route the idea to the correct layer instead of implementing it here.

## Default decision when uncertain

When ownership is ambiguous, prefer the **smaller Hashmarks**:

1. retain or expose the repository-derived primitive;
2. keep the consumer-specific behavior outside;
3. gather evidence that a stronger Hashmarks abstraction is actually needed;
4. expand the product boundary only when the repository-intelligence case is explicit and independently defensible.

The burden of proof is on adding product responsibility, not on keeping it out.

### External-evidence admission corollary

External evidence may enrich Hashmarks' understanding of repository correspondence; Hashmarks does not acquire ownership of the system that produced the evidence. An admitted external-evidence capability must terminate in repository evidence, qualified correspondence, provenance, completeness, freshness, uncertainty, identity, or delta. If making the result true requires reasoning, diagnosis, execution, workflow history, remote discovery, runtime control, recommendation, or deciding what should happen next, that responsibility remains outside Hashmarks.

## What Hashmarks may own

The following categories fit the product profile when they remain repository-derived and evidence-oriented:

- repository, file, symbol, import, reference, call, package, and project identity;
- repository discovery and topology;
- ownership, qualified identity, re-export/alias relationships, and structural provenance;
- impact and dependency relationships;
- producer-neutral cross-artifact declaration correspondence, exact evidence, ambiguity, coverage-qualified absence, and factual declaration deltas;
- task-local repository retrieval and bounded progressive disclosure;
- ambiguity, competing repository candidates, and discriminating repository evidence;
- candidate repository-surface nomination derived from repository evidence;
- verification relevance, test-surface relationships, and mechanically derived repository-bound verification descriptions;
- freshness, invalidation, observation identity, negative repository evidence, and reconciliation;
- deterministic repository-derived membership/selection contracts;
- serialization, interchange validation, consumer conformance, and provenance for Hashmarks evidence;
- repository-intelligence caches/indexes and their correctness/economics;
- metrics and experiments that evaluate repository-intelligence quality and cost.

These categories are not automatic approval. Each new proposal still passes the admission gate above.

## What Hashmarks must not own

Hashmarks must not take responsibility for behavior whose primary authority belongs to the consumer's solution loop or an execution/runtime layer, including:

- autonomous solution reasoning or planning;
- consumer workflow/history as product authority;
- editing or patch application;
- choosing actions because of previous consumer outcomes;
- delegation, agent lifecycle, model routing, or conversation/context management;
- arbitrary task/tool/process execution;
- execution scheduling, process supervision, timeout/retry/resume policy, or environment recovery;
- runtime result authority or certification;
- git/worktree lifecycle as part of solving the task;
- global semantic graph/ontology ownership, persistent semantic edge registries, inferred semantic relationships, transitive closure, semantic reachability/path queries, or graph-derived ranking/precedence;
- final solution correctness or completion authority.

This is a category rule, not a blacklist. New terminology or implementation techniques do not change ownership.

## Neutral inputs are allowed only when they remain neutral

A caller may need to supply explicit query parameters, visibility constraints, policies, changed paths, repository scopes, or other neutral inputs. Such inputs are acceptable when they constrain **how repository intelligence is projected**, not when they smuggle consumer workflow state into repository authority.

A request-local projection must not become hidden persistent state, and removing the request-local constraint must restore the same underlying repository truth.

## Repository evidence versus consumer conclusions

Hashmarks may expose strong evidence and a uniquely supported repository-derived owner/candidate when repository evidence proves uniqueness. That does not transfer final reasoning authority.

For example, Hashmarks may say that one file is the uniquely supported owner under current repository evidence, that several candidates remain ambiguous, or that a set of tests is structurally relevant. It must not reinterpret consumer outcomes as new repository truth unless a corresponding repository change or repository-derived observation supports that conclusion.

Verification relevance follows the same evidence-admissibility rule. A bounded reverse-reference/symbol search may return useful candidate tests, but it may not prove that no verifier exists or that one verifier is unique when any relevant verification-search bound was exhausted or import identity remains unresolved. In that case Hashmarks preserves the candidate evidence and reports incomplete/bounded authority rather than strengthening the observed subset into absence or uniqueness.

Ownership relation graphs follow the same rule. Bounded positive reachability/corroboration remains useful evidence, but an exhausted edge or symbol-candidate bound may not establish that no structural owner exists or that one observed delegation continuation is unique. The graph must expose incomplete/truncated observation and keep uniqueness inadmissible until the configured graph scope is fully observed.

Exact-symbol ownership is subject to the same rule independently of canonical task retrieval. A bounded exact-symbol index lookup may preserve observed exact candidates, but if its candidate bound is exhausted it may not mint `qualified-symbol`, `unique-exact-symbol`, `exact-symbol`, or weaker structural fallback as repository-global ownership proof. Literal repository-path identity remains an independent authority when the task explicitly names that path.

Task-entry ambiguity uses completeness proved by the canonical retrieval composition itself. A second `find_task(N+1)` call cannot prove that internal source windows were exhaustive and must not supply absence or uniqueness authority. Query-term and omitted-identifier input limits count as incomplete retrieval even when the returned hit count is below the requested limit. The task-entry v4 packet reports the retrieval bound reasons and keeps ambiguity unknown when its canonical candidate scope is incomplete. Within a complete canonical scope, role and distinctive-anchor ambiguity is derived before the `per_role` display bound; a hidden competing anchor cannot create a unique role resolution. A task-action exact-identifier search that was skipped for an independent owner surface is `not-evaluated`; it cannot claim negative or uniqueness evidence, and the independent owner retains its own proof.

Generic plain-name ambiguity admission is part of the same ownership proof. If an ordinary method token such as `resolve` or `close` is promoted only when the maintained exact index proves multiple repository definitions, an exhausted symbol window cannot establish that no duplicate exists. That generic-name evidence remains incomplete unless a stronger explicit path, qualified identifier, or shaped exact identifier independently supplies ownership proof.

Structural Locality call binding follows the same rule. A bounded same-name symbol lookup may not turn one retained symbol into an exact call target, nor may a bounded qualified-root lookup prove that no indexed class namespace exists. When the relevant candidate window is exhausted, call-target evidence remains unresolved and the packet must carry incomplete/truncated candidate-search authority instead of counting an exact edge or exact caller.

The general rule is:

> **Consumer experience may trigger a new repository query; it must not silently become repository evidence.**

## Evidence correlation boundary

Hashmarks may accept bounded, structured external or derived observations and correlate them to canonical repository evidence when that strengthens repository understanding without acquiring consumer or runtime authority.

The governing rule is:

> **Hashmarks establishes repository truth and correlates evidence to it. The consuming agent decides what the evidence means and what action to take.**

External observations remain claims. Repository-native material such as source, tests, manifests, and admitted lockfiles remains governed by existing repository authorities. Derived/runtime material such as resolver output, dependency trees, CI failures, tracebacks, logs, profiler samples, compiler diagnostics, or scanner findings may point into that truth but may not overwrite it.

Correlation may preserve path/symbol/location correspondence, provenance, ambiguity, completeness, qualified source equivalence, and before/after repository deltas. It must not infer causation, root cause, sufficiency, repair choice, retry policy, execution policy, or certification.

Producer-specific ingestion, monitoring, storage, and search remain outside Hashmarks. External observations are request-local inputs unless a separate admitted repository-intelligence contract proves persistence is necessary.

## Execution-layer boundary

Hashmarks may describe deterministic, replayable repository-derived selection contracts and the evidence necessary to validate them. It must not become the executor for those contracts.

External execution/certification systems own launching processes, enforcing deadlines, retrying/resuming work, choosing concurrency, scheduling jobs, allocating environments, recovering runtime state, deciding result authority, and issuing certification.

Hashmarks may prove the repository-side identity, provenance, conservation, or relevance of selected work. It must not choose runtime execution policy simply because it produced the selection.

## Benchmarks and experiments

Experiments may use real or simulated agents, retries, model calls, execution, or orchestration to **measure Hashmarks**. That is evaluation infrastructure, not product admission.

Hashmarks may expose a neutral diagnostic that describes whether its own repository-intelligence transport is locally ready—for example the read-only MCP contract identity and launch projection. Such a diagnostic must remain descriptive and consumer-independent. It may not decide benchmark admission, select a harness, configure a host, certify a run, or replace the evaluator's independent proof of executable identity and workspace binding.

Production code must not absorb experimental workflow merely because a benchmark uses it. When an experiment discovers a useful capability, re-run the admission gate and extract only the repository-intelligence primitive that belongs in Hashmarks.

## Change record

Only a change that introduces a **new production responsibility** needs a short ownership note. Keep it factual:

```text
Observed repository fact/evidence:
Authority source:
Completeness/freshness behavior:
Existing Hashmarks owner extended:
Consumer/execution responsibility explicitly not acquired:
Decision: OBSERVER / SPLIT / OUTSIDE
```

Do not create an admission record for ordinary defect repair, refactoring, tests, documentation, or optimization that preserves existing semantics. The record exists to prevent responsibility drift, not to create a governance workflow.

## Review rule for coding agents

When asked to "improve Hashmarks", do not equate improvement with adding capabilities.

Before proposing implementation work, coding agents must first ask:

1. **Does this strengthen Hashmarks' repository-intelligence profile?**
2. **Does it reduce correctness risk, stale authority, ambiguity, cost, or evidence size within that profile?**
3. **Does it merely move more of the consumer/execution workflow into Hashmarks?**
4. **Does it turn bounded semantic identity/correspondence into a general knowledge graph, ontology, edge registry, or transitive relationship engine?**

Prefer correctness, simplification, narrower ownership boundaries, better evidence, better economics, and clearer contracts over feature accumulation.

A useful proposal outside the Hashmarks profile should be explicitly routed to the consumer or execution layer rather than implemented here.

## Verification and developer qualification owner map

The new `CodeMap.verification.nomination(...)` method offers a command-free,
operation-registry-bound observation of a repository's verification surface.
Its `verification_target`, `runner_evidence`, `scope`, `source_evidence`
and `confidence` describe repository observations only. It returns no
executable or working directory and never calls the legacy `plan(...)`
method or probes installed native executables. Every available nomination
also carries the `source_member_revision` issued by the existing Hashmarks
source-member observer and a `supporting_source_members` ledger of exact
qualified test/manifest revisions (including native `known-absent` observations).
All supporting inputs use the same read generation and native revision owner;
denied, unstable or invalid supporting material fails closed without silently
switching to an alternate native tool. Vitest evidence comes from
authored package metadata, not `node_modules` materialization. Unsupported
or insufficient source evidence remains an unavailable nomination, **not**
proof that the repository has no verifier. The historical `plan(...)` API
retains its independent *advisory command-availability* semantics for old
consumers until separately migrated; it does not publish admission truth.


Hashmarks owns repository-derived verification **targets**, member/provenance
identity, ambiguity and freshness, not a consumer's executable selection.
`CodeMap.verification.plan(...)` exposes `verification_target` as the
repository nomination. Existing `runner`, `argv` and `working_directory`
fields are **advisory compatibility fields**; they are not admissible
native-tool, process-launch, sandbox or certification authority. Consumers
resolve executable bytes and construct commands themselves. Keep old fields
until their consumers explicitly migrate; do not silently reinterpret them.

`task_decision_brief.safe` and `task_action_brief.status` are historical
evidence-budget/readability labels. Their `status_scope` is always
`evidence-role-coverage`: even `safe-fresh` does **not** say that an edit,
verification suite or execution is safe/admitted. The coding agent reasons
about changes; the execution system admits and verifies effects. New
consumers should use explicit evidence role coverage and freshness separately
instead of using these legacy strings as permission signals.

Hashmarks' own deterministic developer test sharding and associated legacy v2
source fingerprint belong to `hashmarks._development.test_shards`. The old
`hashmarks.test_shards` module is an import-identity alias for existing
scripts/tests and must never be treated as the product CodeMap verification
membership engine. `developer_selection_source_identity` is an alias of that
legacy hash algorithm, not a new native repository-content authority. Its
scope/exclusions are deliberately distinct from `RepositoryIdentity`
observations, and must not be substituted into external source admission.
No OH-Goon execution behavior is controlled by these developer shards.

### Stable nomination projection identity

Each available or unavailable `verification_nomination` response carries a
`nomination_identity` computed through Hashmarks' existing
`repository_observation.evidence_identity` function. The domain is the
operation-registered schema and the payload includes all other response
fields, including source/supporting-member revisions and unknown reasons.
Consumers may recompute this content identity to detect representation drift.
This digest is **not a signature, trust proof, freshness lease, execution
authorization or new repository-source identity**; only the source observer
qualifies member revisions and the consumer remains responsible for policy.

### Verification nomination transport validation

The pure `hashmarks.verification_nomination_validation.validate_verification_nomination`
consumer utility replays the **canonical operation schema** and the original
`nomination_identity` using the existing `evidence_identity` function.
It checks exact available/unavailable fields, canonical target and member
paths, present/absent member states, nonduplicate supporting members, test
revision correspondence, and absence of hidden executable-command fields.
Malformed or changed packets return `valid: false` with concrete reasons.

A valid packet only proves **structural consistency and content integrity**.
The structural validator deliberately does not duplicate the producer's
runner/scope semantic decisions; unknown nonblank labels remain opaque values.
Rehashing a modified packet can establish self-consistency, not authenticity.
The validator does not read current repository files, establish producer
authenticity, issue freshness guarantees, grant test membership, or admit
execution. It explicitly reports `repository_binding: not-checked`,
`producer_authenticity: not-checked`, and `execution_authority: external`.
Consumers requiring live source qualification must obtain it separately from
the source observer; they must not infer it from the digest.

### Current-source correlation for nomination evidence

`CodeMap.verification.observe_nomination_source_binding(packet)` is a
**separate observation**, never an extension of the pure nomination transport
validator. It first consumes
`validate_verification_nomination(packet)`, then asks Hashmarks' existing
source-member observer for the current state and revision of each *claimed*
input. It also checks the observed inputs again before returning so an
intervening source change cannot silently be reported as a match. It does
not select tests or rederive whether the producer's runner is appropriate.

The result distinguishes `matched`, `mismatch`, `unknown`,
`not-applicable` (unavailable nomination), and `invalid-packet`. A matched
state proves only revision correspondence at observation time; it does **not**
authenticate the caller's nomination, attest provenance, issue a freshness
lease, select a native command, authorize execution, or certify results.
Unknown/unreadable/denied source observations never become negative evidence
or proof that a claimed member is absent. Current repository intelligence is
provided solely by the existing source observer, not by another hashing,
filesystem traversal, or validation authority.

### Nomination source-binding observation receipts

Each `checked_source_members` row in the current-source correlation contains
the original **source-observer member record**, not merely a derived match
label. Its `observed_member` is transported unchanged from the canonical
Hashmarks source observer (including the member revision or the observer's
unknown/unsupported reason). `recheck` is `stable` when the second
observation equals the first; if it differs, the row becomes `unknown`
with `recheck: changed` and `reobserved_member` containing the exact
second native observation. Reasons are projected **after** that recheck
and describe the final state, never a superseded first-read mismatch.

These are observation-time, bounded facts. The receipt neither asserts an
atomic filesystem snapshot nor proves that bytes remained unchanged after
the final read. No new hashing, source-selection or verification-execution
authority is introduced. Consumers can inspect the retained native facts
rather than reconstructing semantic decisions from status strings.

### Pytest manifest evidence qualification

The Hashmarks verification-nomination owner now interprets already source-
qualified `pyproject.toml` bytes with Python's standard `tomllib` parser.
Only a real TOML `[tool.pytest.ini_options]` table supports the
`pyproject-pytest-config` / high-confidence label. Comments, quoted strings
and unrelated `[tool.pytest]` tables do **not** establish pytest declaration.
Malformed TOML does not silently fall back to a medium-confidence claim:
it remains `source-evidence-unqualified`. This is repository **syntax**
evidence only, not installed pytest capability, collected test membership,
command selection, process launch or a guarantee that tests will pass.
The historical advisory `plan(...)` compatibility API is unchanged.

### Vitest package-declaration qualification

The JavaScript/TypeScript verification-nomination owner interprets only
**qualified** authored `package.json` source bytes, using Python's standard
JSON decoder with duplicate-key rejection. A Vitest dependency is declared
only when a relevant dependency section is an object and its `vitest`
specifier is a nonblank string. Absent sections or ordinary package scripts
do not create a Vitest declaration; a malformed section, invalid specifier,
or duplicate JSON key produces `source-evidence-unqualified`, not a
high-confidence runner nomination or an invented negative claim.

This is repository **declaration syntax** only. The observation does not
resolve package versions, prove installed Vitest, choose native executables,
authorize test execution, or report test outcomes. The established
source-member revision ledger and nomination identity remain authoritative
for the exact observed inputs. The legacy advisory `plan(...)` surface is
not changed.

### Python test-node source qualification

A requested `test-node` projection for Python is admitted as repository
evidence only if the already source-revision-qualified Python member bytes
contain **exactly one top-level** function or async function with that name,
as checked by Python's standard `ast` parser. Comments, nested functions,
class methods requiring a qualified class target, duplicate declarations,
missing definitions and malformed Python do not establish the precise
`file::test_function` claim. They produce an unavailable nomination rather
than a fabricated node. A file-level nomination without a node claim remains
available under its original repository test-file scope. No test code is
imported or executed, and the legacy advisory `plan(...)` is not changed.
This parser qualifies syntax, not collected pytest membership or results.

### Flat Python test-node selection precision

For command-free Python verification nominations, `symbol` and `qualname`
are explicit source-selection claims. Hashmarks' existing nomination owner
preserves precise identity: a dotted selector is not silently flattened into
a top-level `file::test_function` target, and inconsistent simultaneous
`symbol`/`qualname` values cannot pick an arbitrary winner. Such requests
return `source-evidence-unqualified`, not a narrower or broader invented
test-node result. A matching flat name is still checked against the already
qualified Python source AST, while a request with no node claim remains
file-level. This neither implements pytest collection semantics nor determines
which tests an execution system should run. The independent historical
advisory `plan(...)` compatibility behavior is unchanged.

### Explicit Python nomination selectors never widen silently

A non-`None` `symbol` or `qualname` is an explicit Python node-selection
claim, not a suggestion to fall back to a broader file-level nomination.
Only a nonblank, flat Python identifier beginning with `test_` can qualify
a requested `test-node` candidate; it must still match exactly one
top-level declaration in the already source-revision-qualified AST. Empty,
non-test, nonidentifier, wrong-typed, dotted, or contradictory explicit
selectors remain `source-evidence-unqualified`, **not** `test-file`.
Only a request with both selectors absent yields an unqualified file-level
nomination. This is repository syntax precision, not pytest test discovery
or authorization to run tests. The historical advisory `plan(...)` continues
its separate compatibility behavior.
