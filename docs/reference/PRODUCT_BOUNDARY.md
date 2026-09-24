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

## Two permanent non-goals

Hashmarks must never be turned into either of the adjacent systems it serves.

1. **Not the agent.** Hashmarks must not absorb the consumer's reasoning, planning, attempt history, memory, edits, delegation, model or tool choices, workflow sequencing, recovery decisions, or final-solution authority. An agent may consume Hashmarks evidence, but Hashmarks must not become the agent's solution loop.
2. **Not the execution/certification motor.** Hashmarks must not absorb Oh-Goon-style admission, sandboxing, process launch or supervision, cancellation, timeout/retry/resume, worker placement, runtime-environment control, execution-result authority, certification, release promotion, or Game Tape/execution-history ownership. Oh-Goon or another execution layer may consume Hashmarks evidence, but Hashmarks must not become its execution engine.

These are ownership rules, not wording rules. Renaming orchestration as "intelligence", execution policy as "evidence", or agent memory as "context" does not make it Hashmarks functionality. Interoperability transfers evidence, never authority.

Every proposal must therefore answer two negative questions before admission: **does this make Hashmarks more like the agent, or more like the execution/certification system?** If yes, reject it or split out only the repository-derived primitive.

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

A new production responsibility must fit the observer model before implementation. This is a direct ownership check, not a requirement to invent policy about policy.

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

### Dependency-adapter translation boundary

Package-manager and resolver syntax is an edge concern. Maven, uv, Gradle, npm, SBOM, and future producer formats may be parsed by dedicated adapters, but shared dependency qualification must reason only about producer-neutral facts and semantic evidence authorities. A source-format `kind` is provenance, not authority; one physical source may support several semantic authorities, and a complete physical artifact does not by itself establish complete semantic coverage. New adapters must translate into the general dependency evidence contract rather than teach core Hashmarks the producer's native shape.

### Evidence authority precedence and non-strengthening

Hashmarks has several authority domains rather than one universal truth score. Content identity, freshness, repository relationships, qualified provider evidence, selection, and consumer projections answer different questions. Do not collapse them into one numeric confidence or a single total ordering.

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

This is a non-strengthening contract, not permission to invent a new global precedence engine. Existing evidence-kind authorities remain distinct.

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
- final solution correctness or completion authority.

This is a category rule, not a blacklist. New terminology or implementation techniques do not change ownership.

## Neutral inputs are allowed only when they remain neutral

A caller may need to supply explicit query parameters, visibility constraints, policies, changed paths, repository scopes, or other neutral inputs. Such inputs are acceptable when they constrain **how repository intelligence is projected**, not when they smuggle consumer workflow state into repository authority.

A request-local projection must not become hidden persistent state, and removing the request-local constraint must restore the same underlying repository truth.

## Repository evidence versus consumer conclusions

Hashmarks may expose strong evidence and a uniquely supported repository-derived owner/candidate when repository evidence proves uniqueness. That does not transfer final reasoning authority.

For example, Hashmarks may say that one file is the uniquely supported owner under current repository evidence, that several candidates remain ambiguous, or that a set of tests is structurally relevant. It must not reinterpret consumer outcomes as new repository truth unless a corresponding repository change or repository-derived observation supports that conclusion.

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
3. **Or does it merely move more of the consumer/execution workflow into Hashmarks?**

Prefer correctness, simplification, narrower ownership boundaries, better evidence, better economics, and clearer contracts over feature accumulation.

A useful proposal outside the Hashmarks profile should be explicitly routed to the consumer or execution layer rather than implemented here.
