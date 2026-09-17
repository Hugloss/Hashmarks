# Hashmarks agent instructions

## Product admission comes before implementation

The normative product/feature-admission contract is [`docs/reference/PRODUCT_BOUNDARY.md`](docs/reference/PRODUCT_BOUNDARY.md).

**Every proposed new capability must be checked against the Hashmarks product profile before design or coding starts.** This applies even when the proposal comes from the user, a benchmark, a failing experiment, an integration request, or existing code.

Do not assume that making an agent more capable means the capability belongs in Hashmarks. Hashmarks is repository intelligence for consumers; it is not the consumer's reasoning, workflow, memory, execution, or orchestration layer.

For every new product proposal, classify it first:

- **ADMIT** — repository intelligence is the primary purpose and source of authority;
- **SPLIT** — keep only the neutral repository-evidence primitive in Hashmarks and route workflow/runtime behavior outward;
- **REJECT** — the proposal primarily belongs to the consumer or execution layer.

A finding is not automatically a requirement. For **every** result or proposed improvement, first decide whether it is:

- an in-profile defect to repair;
- an in-profile optimization;
- a missing repository primitive that needs admission review;
- consumer/runtime behavior that must be routed outward;
- existing boundary debt to simplify/remove; or
- measurement-only infrastructure that must stay outside production semantics.

The agent must apply this test to **its own ideas**. Do not implement a proposal merely because it sounds useful, improves an end-to-end agent benchmark, or was explicitly suggested. Product ownership is decided by the Hashmarks profile.

Use the mandatory admission gate and proposal record in `PRODUCT_BOUNDARY.md`. If ownership is unclear, prefer the smaller Hashmarks and gather evidence before expanding its responsibility.

Existing APIs, experiments, compatibility surfaces, and historical benchmarks are not architectural precedent. Boundary debt must not be used to justify more boundary debt.

## Evidence authority is non-strengthening

A derived, cached, summarized, ranked, or presentation-layer result must never silently become stronger than the repository evidence and freshness/provenance authority that supports it. Do not turn stale into fresh, unknown into proven, ambiguous into unique, or a consumer/model interpretation into repository truth.

Hashmarks does **not** use one global confidence/precedence score. Content identity, freshness, provider qualification, repository relationships, selection, and projections are distinct authority domains. Apply the existing kind-specific rule; if no rule proves a unique resolution, preserve ambiguity/unknown. A new projection or provider must compose existing authority rather than creating a second truth owner.

## External-library scope is closed by default

**Do not chase remaining findings in external libraries.** Hashmarks analyzes the admitted repository, not every library that repository imports. An import/reference/dependency declaration is repository evidence; it is not permission to recursively inspect the dependency implementation.

Coding agents working on Hashmarks must therefore:

- not descend into `.venv`, `site-packages`, `node_modules`, package-manager caches, SDK/runtime trees, or unrelated dependency checkouts merely because the target repository uses them;
- not create package-specific suppressions or special cases for Starlette, Pydantic, pytest, or other named libraries just to reduce finding counts;
- treat external libraries as bounded development/qualification corpora only when they help expose a **generic** repository-analysis defect;
- convert any admitted defect into neutral semantics plus a minimal regression fixture, then stop investigating the library;
- treat named external-library findings preserved in historical evidence as history, **not active roadmap items**;
- return **NO_CHANGE** when a remaining external-library finding does not demonstrate a generic Hashmarks correctness, freshness, ambiguity, or repository-scope defect.

If a third-party project is itself the explicitly admitted target repository, analyze it as that repository. The prohibition is on dependency-driven recursive ecosystem archaeology, not on analyzing a repository the caller deliberately selected.

When asked to "improve Hashmarks", prefer repository-intelligence correctness, freshness, authority safety, evidence quality, evidence economics, simplification, and removal of misplaced responsibilities over adding features.

## Non-negotiable product boundary

**Hashmarks must never be turned into either the coding agent's solution loop or Oh-Goon's execution/certification motor.** Those are separate responsibility planes. Interoperability may transfer repository evidence across those boundaries; it must never transfer reasoning, execution, orchestration, lifecycle, result, or certification authority into Hashmarks.

**Hashmarks is not an agentic orchestrator and must not become another ChatGPT/Codex/OpenCode clone.** It should make those agents materially better at repository work by supplying repository intelligence only.

Hashmarks owns **repository intelligence**. External coding agents and their harnesses own the **solution loop**.

### Hashmarks owns

Hashmarks may build and expose compact, mechanically derived repository evidence such as:

- canonical identity and maintained repository indexes;
- symbols, paths, imports, calls, ownership and impact relationships;
- bounded task-local retrieval and progressive source disclosure;
- provenance, freshness, invalidation and repository-native negative-evidence facts;
- compact post-change evidence deltas over caller-reported changed paths;
- changed-code impact and relevant verification/test authority;
- bounded verification-relevance evidence from indexed reverse references around an already-selected edit owner;
- declared cross-repository relationships;
- stable CLI/JSON/service/tool surfaces that let external agents consume this intelligence.

### External agents/harnesses own

Hashmarks must not take ownership of:

- solution reasoning or autonomous planning;
- editing source code or deciding the patch;
- arbitrary shell/tool execution for the coding task;
- verification execution on behalf of the coding agent;
- recovery strategy after a failed attempt;
- task scheduling or multi-agent orchestration;
- model routing, conversation memory, or context-window management;
- worktree/git lifecycle or final solution behavior.
- process launching or command supervision for certification/QA execution;
- process timeouts, retries, resume orchestration, or concurrency control;
- CI/job scheduling, machine allocation, or execution-environment recovery.

Existing standalone commands such as Impact execution helpers do not transfer coding-agent solution-loop authority to Hashmarks. Agent-facing repository-intelligence APIs may return typed verification commands/evidence, but the external agent or harness decides whether and how to execute them.

### Execution-layer boundary

Hashmarks may describe deterministic, replayable execution/certification **selection contracts** (for example immutable test-shard membership, process-isolation requirements, expected evidence, and plan identity). It must not become the executor for those contracts. **The execution layer belongs somewhere else, not inside Hashmarks.** External harnesses/CI systems own launching processes, enforcing deadlines, retrying or resuming incomplete shards, choosing concurrency, scheduling jobs, allocating environments, and recovering broken execution environments.

Generation-bound handoff follows the same rule. Hashmarks may emit `hashmarks.repository-work-selection.v1` to bind immutable `test-shards.v3` membership and process-isolation requirements to repository-content/selection-input identity and producer provenance. The envelope must not contain execution policy: no argv, timeout/deadline, retry count/delay, worker/concurrency choice, scheduling, machine placement, process state, or environment-recovery instruction. Consumers such as Oh-Goon verify/admit the envelope and remain the sole execution/certification authority.

Consumer conformance does not change that boundary. Hashmarks may validate its own envelope/shard schema, re-prove repository binding, and derive a grouping-independent identity for exact selected test-node membership. An external execution layer may use that identity to prove conservation while refining execution grouping, but Hashmarks must not choose the refinement, timeout, retry, worker count, or schedule. Unknown v1 handoff fields and attempts to expand Hashmarks authority fail closed.

Verification relevance follows the same boundary. Hashmarks may use bounded indexed reverse references, namespace locality, and task-local evidence to identify a more relevant test surface around an already-selected edit owner. It must not run that test, claim the test is sufficient, alter edit authority, or turn verification selection into an autonomous solution step.

Negative evidence follows the same boundary. Hashmarks may persist or transport **repository-derived** negative evidence such as a symbol being absent, an import being unresolved, a path being stale, or an ownership result being ambiguous. A failed/disproven edit supplied by a worker is **agent attempt history, not repository truth**; it must remain owned by the external worker/harness and must not become durable Hashmarks repository authority. Historical failed-target receipts are compatibility/boundary debt and must not be expanded.

## Hashmarks ↔ Oh-Goon execution boundary

Hashmarks and Oh-Goon are deliberately separate planes. **Hashmarks defines immutable repository evidence and selection authority; Oh-Goon owns execution and certification authority.** A request to make long-running qualification easier to resume does not move checkpointing or execution control into Hashmarks.

### Hashmarks may provide to Oh-Goon

Hashmarks may produce or validate deterministic, replayable evidence needed by an execution layer, including:

- `hashmarks.repository-work-selection.v1` envelopes bound to repository-content and selection-input identity;
- `hashmarks.test-shards.v3` immutable selected test membership and `isolated_process` requirements;
- `hashmarks.test-shard-membership.v1` grouping-independent membership identity;
- plan identity, producer provenance, repository freshness, and strict consumer-conformance validation;
- pure membership-conservation checks such as proving that completed plus remaining members exactly equal the admitted original membership;
- compact decision-authority receipts that let bounded worker projections refer back to the exact repository/task/edit/verification authority without embedding all evidence.

These are **evidence contracts only**. They may describe what work is selected and what membership must be conserved, but they do not decide how or when that work runs.

### Oh-Goon or another execution layer must own

The following are execution/certification concerns and must not be implemented in Hashmarks:

- dividing selected shards into runtime chunks or choosing chunk size;
- durable execution-progress ledgers, completed/running/remaining state, or checkpoint-after-result behavior;
- deciding which chunk/shard runs next or resuming only unfinished work;
- process launch, process-tree supervision, cancellation, deadlines, hard timeouts, concurrency, worker placement, or machine allocation;
- retry policy, timeout-driven splitting/bisection, resume policy, and append-only execution attempts;
- runtime `HOME`/cache/temp/socket-path isolation and execution-environment repair;
- classification of product failure versus controller interruption versus environment failure;
- verification-result authority, membership-closure certification, certificate issuance, or execution Game Tape authority.

Hashmarks may validate that any externally refined execution grouping conserves the exact admitted membership, but **must never choose the refinement**.

For Hashmarks' own deterministic pytest selection, statically known process-sensitive or expensive benchmark/reproducibility nodes must be emitted as singleton `isolated_process` shards and must never be mixed with ordinary product-test nodes. This is a repository selection invariant, not runtime chunking policy. External execution still owns deadlines, further subdivision, retries, scheduling, resume, and result authority. If a controller stops after only part of the admitted membership ran, Hashmarks' responsibility is still only to make the original immutable membership and identities re-provable. The execution layer owns completed/running/remaining progress, environment recovery, and resume behavior.

### Boundary litmus test

Use this rule when implementing future phases:

- If the question is **“what does this repository mean, what code/test is relevant, or what immutable membership was selected?”** → Hashmarks.
- If the question is **“may this run, how is it chunked/launched/retried/resumed, what happened, or can the result be certified?”** → Oh-Goon/execution layer.
- If the question is **“what source change should be made?”** → coding agent/harness.

A useful feature that crosses these boundaries must be split: keep the deterministic repository-evidence primitive in Hashmarks and move execution/runtime behavior to the execution layer.

### Batch-resumable development qualification

Development/refactor work must be qualified in named, bounded batches. A host/runtime timeout is not a test failure and must invalidate only the in-flight batch. Never rerun already-proven batches merely because a later controller window expired. For the deterministic pytest boundary, use `make dev-check-batch DEV_BATCH=N` (four selection shards by default), reproduce a single failing shard with `make test-shard TEST_SHARD=N`, and resume later batches with `make dev-check-tests DEV_BATCH_START=N`. Partial batches are never counted as proof.

### Qualification runner supply boundary

Hashmarks owns the repository qualification contract: deterministic test membership, supported runner compatibility, repository selection identity, and evidence describing what should be verified. Hashmarks does **not** own the package distribution or execution environment that supplies pytest/Ruff for certification. The external execution/certification layer owns exact runner bytes, interpreter/environment identity, preparation, and execution receipts.

Hashmarks uses minimum-only qualification-tool admission: pytest `>=8.4`, Ruff `>=0.12`, and uv `>=0.10.0`. Newer releases are accepted by default; add an upper bound or exact-version requirement only after a concrete incompatibility is reproduced. The exact tool versions used in a qualification run must be captured by external execution receipts as provenance, not admission policy. Hashmarks must not acquire pytest/Ruff implicitly or encode external tool bytes into repository evidence authority. `make test*` may consume an already-prepared environment but must fail clearly when the required runner is absent or below the supported minimum. Ruff is diagnostic structural-quality tooling only and is never a canonical-promotion prerequisite. Chosen CI/artifact-host versions are qualification environments, not extra contributor version pins.

Python tooling that repeatedly parses repository files must use `hashmarks.python_ast_cache.read_python_ast` rather than coupling `ast.parse` directly to `Path.read_text`. The cache is process-local acceleration only and is keyed by device/inode/size/mtime/ctime with a stable-read check. It must never become repository identity, freshness, or execution authority. Source-only analyzer APIs may retain `ast.parse(source)` as a fallback, but file-backed callers should pass the cached tree so one stable file snapshot can serve multiple analyzers.

## Feature filter

Before adding an agent-facing feature, ask:

1. **Does this make repository evidence more accurate, compact, fresh, explainable, or cheaper to retrieve?** If yes, it may belong in Hashmarks.
2. **Does this make Hashmarks decide, execute, edit, recover, schedule, delegate, or manage the coding solution itself?** If yes, it belongs in the external agent/harness, not Hashmarks.
3. Prefer exposing a small typed evidence primitive over adding another autonomous workflow.
4. Reuse existing repository authorities (`CodeMap`, Impact, identity, native evidence) instead of creating parallel agent-specific truth.
5. Post-change impact may reconstruct an existing ownership relation from the selected verification surface only to corroborate the already-admitted edit owner; it must never use that reconstruction to replace or rerank the owner.
6. Performance work must optimize repository indexes/graph mechanics rather than hide evidence or add planning, delegation, scheduling, model routing, or other agent-orchestration behavior.

When a proposed feature crosses this boundary, preserve the useful repository-intelligence primitive and reject the agent-runtime portion.

### Qualified import identity

Repository evidence must qualify Python import identity before treating a same-named reverse reference as authority when resolution is available. Relative imports, `as` aliases, package re-exports, and symbol-scoped star re-exports may be followed through at most eight import hops. Ambiguous/cyclic/over-bound identity remains unresolved and requires scout/discrimination; never replace that uncertainty with short-name or archive/legacy fallback authority. This remains repository understanding only—do not add execution, timeout, retry, resume, or certification behavior here.

Authority & Ownership Graph v2 composes exact cache-invalidation ownership evidence into the repository graph. `invalidates-cache` edges require local or qualified import/alias proof from the cache-invalidation resolver; shadowed names and same-name lexical coincidence remain unresolved. This is static repository evidence only and never grants runtime mutation or execution authority.

### Import / module-cache ownership diagnostics

Cross-repository interoperability baselines are qualification evidence, not permanent product constants. Use the exact external versions and artifact identities recorded by the current qualification/release evidence; do not encode a stale Oh-Goon release into Hashmarks product semantics. Version references in historical benchmark notes remain historical only.


Hashmarks may statically report repository-owned Python loader patterns that bypass normal `sys.modules` identity (for example `spec_from_file_location` → `module_from_spec` → `exec_module`), resolve the target back to a unique repository path/package identity, and explain the cache/module-ownership risk. Lexical evidence may nominate candidate files, but AST structure must prove the finding. Intentional test/plugin loaders and explicit `sys.modules` registration remain advisory/custom-loader evidence rather than automatic defects. Hashmarks must not rewrite imports, execute the loader, infer runtime failure from the pattern alone, or certify the repair; those actions remain with the coding agent and external execution layer.

Real-world ownership rule: do not classify production `src/**/test_*.py` modules as tests from basename alone; admit test files as edit surfaces only for explicit test-maintenance requests; normalize identifier shape (for example `CandidateCheckpoint` ↔ `candidate_checkpoint`) before concluding that two repository symbols are unrelated; and preserve unresolved close owners as scout/discrimination evidence instead of letting generic `contract`, `policy`, or `authority` wording manufacture certainty. Build-file projection is repository evidence only and must never become execution-policy ownership.

## Repository-understanding measurement boundary

Hashmarks owns measurement semantics intrinsic to repository intelligence: index preflight shape, build completeness, cold/warm/incremental cache state, phase/index economics, lexical evidence volume, persistence amplification, per-surface evidence cost, and the edit/verification surface selected in a worker packet. These facts may be consumed by an external observability system.

Hashmarks does **not** own historical telemetry retention, dashboards, heatmaps, alerts, fleet/run comparisons, timeout decisions, retries, restart/resume orchestration, scheduling, process management, or certification policy. Do not add those features here. Expensive evidence surfaces must be measured against correctness before changing indexing authority.

### Real-world evidence-value calibration

Before changing persistent lexical representation because a surface is expensive, run a frozen-corpus comparison with the benchmark-only `benchmarks/codemap_surface_calibration.py`. The benchmark may clone and destructively transform a *copy* of a completed CodeMap to measure alternative representations, but those transforms have no runtime indexing authority. An indexing representation may be considered for product code only after retained real-repository corpora show zero new false-safe edit/verification decisions. Underspecified tasks must be graded for expected scout/discrimination rather than assigned an arbitrary hidden owner.

Repository churn measurements (warm full recheck, explicit changed paths, rename, delete, and incomplete-generation recovery) are Hashmarks repository-intelligence QA. Their timings are evidence; Hashmarks must not convert them into deadlines, retries, restart/resume policy, scheduling, historical telemetry, dashboards, or alerts.

### Calibration durability / hot-loop boundary

Hashmarks benchmark tooling may atomically persist identity-bound per-task calibration receipts so completed repository-understanding measurements survive an outer host/process limit. This is evidence durability only: do not add runtime retry/resume, timeout ownership, scheduling, process restart, or certification semantics. On repository-understanding hot paths, prefer stable IDs/keys, set-based or bulk SQLite reads, and bounded pure/generation-bound caches over N+1 lookups or nested scans when exact decision semantics are preserved.

### Candidate validation cost boundary

Do not spend promotion-grade packaging proof on every source-only iteration. Use three validation tiers:

- **iteration:** focused correctness/architecture tests only;
- **persistent candidate:** bounded source test rings, one source `compileall`, one deterministic source ZIP, and focused tests/smoke from an independent extraction;
- **canonical/promotion or packaging-transform change:** escalate to independent rebuild byte-identity, broader exact-artifact requalification, and isolated wheel/sdist installation.

Exact-ZIP `compileall` and a second deterministic ZIP rebuild are not mandatory for an ordinary source-only candidate when the packaging transform itself is unchanged and the extracted artifact passes the focused import/test smoke. This avoids paying repeatedly for duplicate proof while keeping packaging-integrity checks at the boundary where they add information.


## Ownership-intelligence boundary
Hashmarks ownership/cache/import/verification/concurrency diagnostics are repository evidence only. They may nominate risks, owners, repair surfaces, and verification surfaces, but must never execute repairs, manage runtime concurrency/processes, admit execution, retry, recover, or certify results. Those external execution responsibilities remain Oh-Goon-owned.

### Warm-service parity / invalidation ownership

Repository-intelligence methods exposed by `CodeMapServiceClient` require a matching validated service operation; client-only API surfaces are defects, not deferred features. Cache invalidation ownership is static repository evidence: resolve only local/simple aliases or qualified import identity to a known cache owner, fail closed on same-name ambiguity, and never execute `.clear()`, `.cache_clear()`, `.invalidate()`, or `.invalidate_all()`. Runtime cache lifecycle and mutation authority remain outside Hashmarks.


### Verification ownership v2 authority links

Hashmarks may bind verification candidates to edit authorities only when structural repository evidence proves that relation. It must fail closed on wording-only or namespace-only matches. This remains repository intelligence; Oh-Goon owns execution, process lifecycle, recovery, and certification.

## Hashmarks / Oh-Goon authority boundary

Hashmarks owns repository-intelligence and verification-selection semantics. Oh-Goon owns admission and physical execution semantics. Hashmarks may identify, classify, associate, rank, and recommend repository evidence, but must not schedule, launch, retry, bisect, resume, or certify it. Oh-Goon may admit, freeze, regroup, execute, retry, bisect, resume, and certify admitted evidence, but must not infer, reconstruct, repair, or reinterpret Hashmarks repository intelligence. Producer-defined identities and semantics are verified by consumers and are never independently recreated by consumers. Schema evolution must not transfer authority: execution-policy-looking producer fields are non-authoritative unless an explicit Oh-Goon-owned schema/policy admits them.

## Current-contract boundary

Before the first public release, Hashmarks keeps one current public spelling/schema per supported surface. Historical local database shapes, evaluation schemas, and unpublished aliases are disposable development state, not compatibility obligations. Remove obsolete readers/aliases instead of adding migration or normalization layers. Runtime protocol validation may still reject an incompatible daemon because that is a current safety fence, not backward-compatibility support.

### G50 — Oversized-source decomposition preserves authority
Structural decomposition may move cohesive repository-intelligence implementation behind internal mixins/modules, but it must not change public CodeMap contracts, ranking/selection semantics, deterministic identities, or transfer execution/certification authority into Hashmarks. File-size reduction is a maintainability outcome, not an authority or schema change.

## Responsibility-first naming and decomposition gate

Large LOC is a signal to investigate, not proof that a file should be split. Before reducing a large source file, classify it as **KEEP COHESIVE**, **REFACTOR INTERNALLY**, **EXTRACT RESPONSIBILITY**, or **DECOMPOSE MULTIPLE RESPONSIBILITIES** after reviewing domain ownership, public contracts, function/control-flow complexity, mutable state, dependency direction, testing difficulty, and discoverability.

Names must reveal responsibility and product ownership without relying on historical filename prefixes. Avoid generic cross-module names such as `Receipt`, `Identity`, `Context`, `State`, `Result`, `Verifier`, `Manager`, `Runtime`, `Manifest`, `ResumeState`, and `Provenance` unless a genuinely local scope makes ownership obvious. Avoid mechanical `*_helpers`, `*_utils`, `*_core`, `*_impl`, `*_partN`, and source-filename-prefix decomposition.

Hashmarks vocabulary should prefer `evidence`, `repository`, `CodeMap`, `impact`, `repository qualification`, `qualified repository identity`, `evidence packet`, `evidence receipt`, `evidence freshness`, `repository projection`, and `consumer conformance`. `authority`, `admission`, `execution`, `certification`, `sandbox`, `supply`, `execution generation`, `authority receipt`, `release promotion`, and `Game Tape` are Oh-Goon vocabulary and must not name new Hashmarks-owned permission/runtime concepts.

At interoperability boundaries, product names are intentionally explicit: a consumer-side contract should say `Hashmarks` or unmistakably say `Evidence`. Hashmarks observes repository state; Oh-Goon admits source. If a symbol could plausibly exist unchanged in both products, add a domain noun.

Before the first public release, historical development names are not compatibility promises. If an unpublished name crosses the product boundary, remove it or move it to development-only evaluation infrastructure rather than preserving a shim. After publication, compatibility changes require an explicit versioned API decision.

### G52 — One current pre-public contract

Before the first public release, obsolete aliases/readers are removed rather than preserved. Generated local databases are rebuilt when their current shape is not satisfied. Historical vocabulary does not justify expanding ambiguous `authority`, `admission`, `execution`, or `certification` concepts inside Hashmarks. Current client/daemon protocol validation remains a fail-closed safety boundary.

### G53 — Historical execution surfaces stay out of the first public contract

The historical standalone execution/result-cache/work-session surfaces modeled authority that belongs to an external execution system or consumer workflow. The current `IdentityEngine` is explicitly **not** in that category: it owns canonical repository-content identity and freshness observation only. HM255 removes those unpublished surfaces from the installed public API instead of preserving compatibility shims. Content-addressed repository-artifact reuse remains valid; execution-result reuse, process authority, retry/resume, and certification remain external. These historical names must not re-enter Hashmarks merely because archived patches or benchmarks still mention them.

## Responsibility-first refactoring gate

Before file-size, naming, or complexity cleanup, apply `docs/development/reviews/RESPONSIBILITY_COMPLEXITY_REFACTORING.md`. Large LOC and Ruff debt are investigation signals, not extraction requirements. Every candidate must be classified KEEP COHESIVE, REFACTOR INTERNALLY, EXTRACT RESPONSIBILITY, or DECOMPOSE MULTIPLE RESPONSIBILITIES before code movement. Interoperability transfers information, never authority.

## CLI responsibility ownership

The top-level `hashmarks.cli` module owns process entry, global argument normalization, identity/daemon protocol commands, and current impact/benchmark command registration. Repository-intelligence command families are owned by `hashmarks.repository_cli`. New repository commands belong with repository CLI ownership; do not grow the top-level facade merely because it is the executable entry point. `hashmarks.cli.main` is the single current CLI entry surface; obsolete command aliases are not preserved pre-publication.

### G55 — Post-RCR work is product-value driven

After RCR-08, structural cleanup is not an open-ended queue. New refactoring phases require a fresh measured reason tied to correctness risk, repository-intelligence economics, contract clarity, or demonstrated maintenance cost. Ruff/LOC alone do not authorize a phase. Retrieval refactors must preserve ranking/selection authority and may only remove redundant repository work when output evidence is unchanged.

### G56 — Local developer entrypoints are simple and dependency intent is source authority
A new local developer must not need to know Hashmarks' internal qualification topology to start or test it. `pyproject.toml` owns dependency intent; local `uv.lock` is generated, gitignored workspace state. `make init` resolves/syncs the project-owned `test` group and may create or refresh that local lock; `make lock` is an explicit convenience for refreshing it; `make setup` composes preparation with the runtime doctor; `make test` consumes the prepared local environment; and `make check` owns the concise local compile/CodeMap/test path. Frozen/offline commands may consume an existing local lock for repeatability, but the lockfile is not release source, package content, or promotion identity.

### G57 — Architecture guards resolve relative imports

Product-boundary checks must inspect both absolute and package-relative imports. A relative import is not a valid way to reintroduce removed execution/agent-loop responsibilities into modern CodeMap/repository-intelligence code. Architecture tests must resolve imports to fully-qualified module ownership before classifying the dependency; textual spelling alone is not authority.

### G58 — Consumer conformance is runtime-neutral

Hashmarks consumer conformance and versioned evidence contracts must remain independently consumable. Oh-Goon is a consumer, not a required runtime dependency or semantic owner. Modern CodeMap, repository CLI, contract-surface, and consumer-conformance code must not import Oh-Goon/goon runtime packages. Contract metadata may describe external execution/certification authority, but it transfers no execution authority and must remain usable by other consumers.

### G59 — Removed boundary debt must stay removed

`docs/development/PREPUBLIC_BOUNDARY_DEBT.md` records historical execution and agent-loop surfaces removed before the first public release. Modern CodeMap/repository-intelligence code, CLI, service contracts, examples, and top-level exports must not reintroduce those responsibilities. Development-only evaluation harnesses may model external agents, but they must remain outside the installed product contract.

### G60 — Release-correctness proofs must be scope-bounded
A release-correctness test must not rebuild the full real Hashmarks repository when the asserted invariant is independent of repository scale or exact repository bytes. Use a representative repository that still traverses the real public product surface. Real-repository and scale proofs remain appropriate only when repository scale, repository bytes, integration topology, or measured economics are themselves part of the contract. Do not add production caching merely to hide test-fixture reconstruction cost.

### G61 — Qualification planning reuses one repository snapshot
A single qualification-plan construction must enumerate test membership once and derive its units from the same classification artifact. It must not rescan repository identity or reclassify the same membership merely to construct downstream views. Reuse is operation-local and identity-bound; this rule does not authorize persistent caches or execution authority in Hashmarks.

### G62 — Read-only qualification contract tests share one immutable repository proof
Tests that only validate projections, tamper rejection, authority fields, or consumer interpretation of the same qualification state must reuse one session-scoped immutable qualification plan/handoff. Determinism of a projection is proven by deriving it twice from the same bound input, not by rescanning identical repository bytes twice. Keep a bounded number of explicit fresh-construction tests for repository-plan determinism and snapshot correctness. Test reuse must never become production-global caching or weaken repository identity binding.

### G63 — Test runtime visibility is diagnostic, not correctness authority

The full-suite runtime profile is owned by `make test-profile` and reports the slowest 25 pytest phases taking at least one second. Duration alone never changes PASS/FAIL semantics, and slow-test optimization must preserve the proof scope required by the tested contract. Do not duplicate duration flags across qualification entrypoints or introduce production caches solely to improve test timing.

### G64 — Ruff is minimum-version diagnostic evidence, never canonical-promotion authority

Hashmarks declares a minimum supported Ruff version plus an explicit rule contract so tool defaults cannot silently change lint semantics. Newer Ruff releases are accepted by default; each external diagnostic receipt records the exact version that produced it. Add an upper bound only when concrete incompatibility is proven. Ruff remains diagnostic-only: missing/failing Ruff debt does not create or transfer canonical promotion authority, and the Python dependency supply remains independently locked.

### G65 — Exception translation has one owner per boundary

Expected caller-visible failures are translated exactly once at the public boundary that owns the transport. Repository/domain methods raise their own errors; leaf CLI handlers must not wrap every call in local `try/except`, and MCP repository methods must not import or raise SDK transport exceptions. The repository CLI adapter owns repository-request translation, the top-level CLI dispatcher owns process-exit translation, the MCP server owns `McpSurfaceError -> ToolError`, and local daemon/CodeMap IPC handlers share one JSON request/error serialization boundary.

Local exception handling remains appropriate only when the current scope owns a resource or fallback invariant that must be repaired there: transaction rollback, lock/single-flight propagation, watcher/process cleanup, optional-provider isolation, or bounded retry of explicitly classified transient repository races. Do not add broad defensive catches, and never add a catch-and-immediate-reraise block. Architecture tests freeze the current broad-exception allowlist so new `Exception`/`BaseException` catches require an explicit boundary decision.
