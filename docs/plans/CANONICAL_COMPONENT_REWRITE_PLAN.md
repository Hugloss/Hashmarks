# Canonical component rewrite and return to backend 5/5 qualification

**Status: implementation in progress, explicitly authorized by the user.** Prepared against the modified
worktree on 2026-10-17, based on HEAD
`4dc2527f6a2391a01063617b593830b638a44550`. This is the current implementation
handoff and supersedes the bounded
[canonical-owner consolidation plan](CANONICAL_OWNER_CONSOLIDATION_PLAN.md).
The user authorizes breaking public Python APIs and removing compatibility
paths. Implementation resumed from the current dirty worktree; the plan's
acceptance requirements remain unchanged.

## Implementation checkpoint — 2026-10-17

- CR-00: exact starting dirty-tree ZIP and static operation/state/caller
  inventory are retained in `.hashmarks/canonical-component-rewrite/cr00/`.
  The baseline passed 87 tests. Its full inventories were 2,071 Ty diagnostics
  and 2,043 Pyright errors. Candidate receiver/dynamic-access inventories still
  require qualification during each owner migration.
- CR-01: Files canonicalizes workspace/policy paths and has a read-only root
  reference. The obsolete `_state_rel` Git-snapshot reader was repaired after six
  existing tests reproduced the failure. Its final ring passed 98 tests in the
  worktree and an independent extraction. See `cr01/manifest.json`.
- CR-02: Index, ObservationSource, DecisionScope and Source are independent
  components with migrated callers and removed root aliases. Task preflight is
  outside the lower read owner; paired domain memo values own their scope/cache
  lifetime. Index no longer invalidates the upper relationship cache. Store
  clearing advances the existing generation atomically, and public source
  outlines return detached symbols. Both defects have retained failing probes.
  Instruction seed nomination belongs to Context; Source observes selected paths.
- `cr02-integration-02.xml` records **684 PASS**. Modified foundational owners
  and direct component/type-contract tests pass scoped Ty and Pyright. Genuine
  metadata/sender public and freshly regenerated native workflows pass all their
  selected gates under observer
  `sha256:ca9fb9e8054019b0f66b31ea451e8d6d74383d791cfa2e411c743acf593d3b8e`.
  Reports are `cr02-public-02/summary.json` and `cr02-native-01/summary.json`;
  aggregate statuses remain INCOMPLETE because the full campaign was not run.

The foundation source ZIP is retained at `cr02-foundation/source.zip` with
SHA-256 `d3fefc4b2274655586105995c5c046041f641da4ec9b8273ebd067305562069f`.
Its independent extraction passed 683 tests; the one Git-index-membership check
passed against the real worktree in the 684-test ring. The current full configured
inventories are **2,054 Ty diagnostics / 2,031 Pyright errors**, still red.
Comparable bounded before/after locality observations for six owners are retained
under `locality/`; their external-or-unindexed calls require explicit qualification
before declaring complete locality.

CR-03 has started with `RepositoryImports`: its 17 resolver operations and
request-local walks now belong to that independent component, and old root
resolver methods are removed. The control-path preparation value in `engine.py`
keeps canonical path preparation with the composition root. The focused import
ring passed **148 tests**, with scoped Ty/Pyright clean; the complete preserved
integration ring plus import component tests passed **687 tests**.

Native publication and freshness qualification now belong to independently
constructed `RepositoryNativeEvidence`, exposed as `repo.native`. The engine
Vitest back-reference is removed; native producers have explicit injection at
their boundary. Source-bound SCIP/LSP adapters receive Source, read queries and
store directly instead of a CodeMap back-pointer. All retired root native
operations are removed, including migrated capture, CLI and identity consumers.
The native ring passed **250 tests**, including all native LSP change tests,
SCIP source correspondence and real CLI/MCP transport. Modified native owners
and the direct component tests pass scoped Ty/Pyright. See
`cr03-native-final.xml`, `cr03-native-ty.log` and `cr03-native-pyright.log`.
The preserved broader ring plus direct component tests passed **691 tests**.
Independent extraction of `cr03-native/source.zip` (SHA-256
`a9caf78b8ee76c3fab4006ec22c670e16f04da8f3ada8ee420bcc29b213dad7e`)
passed the same **250-test native ring**, with asserted import origin and observer
`sha256:4bc1b7ed17a1706c5eacfeb286ef1c8ebe5512e817664f4e467711b54c57fe9d`.
Source compileall and preflight passed.

CR-03's remaining production boundaries are now implemented. Independent
`RepositoryRelationships` owns dependency/reference/project/affected/test queries
and reverse-cache state; task adjacency remains explicitly task composition.
`RepositoryStructure` owns structural search, qualified direct-call/locality and
related test-path facts. Its filesystem lifecycle analyzer consumes Structure,
with no CodeMap back-pointer or higher verification dependency. Pure packet
comparison moved to `structural_locality_delta.py`; typed node values and the
unchanged serialization identity live in `structural_locality_model.py`.
This is DECOMPOSE MULTIPLE RESPONSIBILITIES for the original live/comparison
module, with the same schemas, identities, source bounds and exceptions.

- Relationship ring: **226 PASS**; independent extracted ring: **174 PASS**.
  The broader run exposed one structural assertion pointing to the retired
  query module; after moving its owner location, all **121 boundary tests** pass.
- Structural ring: **252 PASS**. The preserved integration membership plus all
  direct component tests passed **698 tests** (`cr03-integration.xml`). All
  migrated native/relationship/structural owners and their direct component
  tests pass scoped Ty/Pyright. Source compileall and preflight pass.
- Genuine metadata/sender public workflows pass all ten gates each, including
  initial size and evidence; freshly regenerated native workflows pass all ten
  gates each, including reopen/staleness. Both reports bind observer
  `sha256:c26cb051f6f2d9e0f585cb9543d8424b06647e917cb3d9ffd72edcc0caf112c5`.
  See `cr03-public/summary.json` and `cr03-native-workflows/summary.json`.
  Aggregate status is INCOMPLETE for the explicitly selected two-workflow scope.
- Current configured full typing is still red: **2,029 Ty diagnostics /
  1,992 Pyright errors and one warning**. See `cr03-full-ty.log` and
  `cr03-full-pyright.log`; scoped clean results do not replace this requirement.
- Exact candidate ZIP: `cr03/source.zip`, SHA-256
  `ff68995226a6c22481f96f48d6b60360bc2af047de399abffde3fb3222c93aa6`.
  Independent extracted integration passed **697 tests**, with one deselection.
  The Git-index membership test
  remains proved in the real-worktree ring, as with the foundation extraction.

CR-04's Search and Context production boundaries are implemented.
`RepositorySearch` owns find/task retrieval, query single-flight and the three
bounded retrieval/freshness memos. Tasks now submit observed contributing paths
through `remember_paths` rather than writing those caches. Find evidence carries
its normalized route into presentation. Replay/explanation lives in Search's
`retrieval_diagnostics.py`, because replay temporarily invalidates/restores that
same cache; the method mapping below reflects this ownership correction.
`RepositoryContext` owns disclosure assembly and single-flight, borrows the
existing ContextCache and composes lower Search/Source/Relationships. Stateless
action-anchor projection moved from Ownership to `WorkContextProjection`; its
tests no longer bypass a CodeMap constructor with `object.__new__`.

- Search ring: **274 PASS**. The preserved integration membership plus all
  eleven component files passed **706 tests** (`cr04-integration.xml`). Public
  find/context/overlay and retrieval tests passed **94 tests**. Migrated Search/
  Context owners and direct component tests pass scoped Ty/Pyright.
- Genuine metadata/sender public and freshly acquired native workflows again
  pass all ten selected gates each, under observer
  `sha256:f21a4c50235e5ee133523670760bc28dadcd0687bf71d4ce49767c97f757ab0c`.
  Reports are `cr04-public-workflows/summary.json` and
  `cr04-native-workflows/summary.json`. Full-campaign qualification remains
  INCOMPLETE, as required for this two-workflow scope.
- `cr04-final/source.zip`, SHA-256
  `98eef4d1de7678c6e10986a96454d487e924cb6a366784359855cf5b89d2fa3d`,
  passed **738 tests** in an independent extraction, with one Git-only test
  deselected after its real-worktree proof. Import origin and observer identity
  were asserted. Source compileall and preflight passed.
- The loop-efficiency guard was vacuous because it scanned retired methods in
  `engine.py`. It now names all current owners and requires each guarded method
  to exist. The strengthened guard and explicit Search/Context failure-cleanup
  tests pass in the worktree (**22 tests**). The refreshed artifact at
  `cr04-qualified/source.zip`, SHA-256
  `f6bab2b3520908e0d80264387abe89e3dfd27339ee2d6475954fcb9e57474994`,
  passed **72 tests** from independent extraction, including the stronger guards,
  cleanup/retry, actual CLI/MCP and overlay paths. Production observer identity
  remains the same `f21a4c…` candidate; see `cr04-qualified-extracted.xml`.
- A frozen real Python repository workload has identical returned evidence,
  parsed/reused artifact counts, instrumented store/primitive counts, traced SQL
  statement counts across all four borrowed SQLite connections, stable-byte
  reads and AST-cache observations in cold/warm/incremental phases. See
  `cr04-economics/summary.json`. This is one comparable corpus, not a timing or
  broad performance result.
- Current configured full typing remains red: **2,025 Ty diagnostics /
  1,986 Pyright errors and one warning** (`cr04-full-*.log`).

CR-05's core boundaries are implemented as `RepositoryOwnership`,
`RepositoryVerification` and `RepositoryTasks`. Ownership's nomination and final
proof now live in `ownership_nomination.py` and `ownership_candidate_*.py`;
Tasks orchestrates explicit values. Analyzers accept Source/Imports and exact
query capabilities rather than an owner/root bag. The filesystem lifecycle
analyzer receives four narrow inputs, including one typed direct-call resolver.
Verification's `for_owner` consumes a frozen request with normalized task data,
nominee status and exact active read-scope binding; it never calls Tasks.
Task convenience views and receipts share a scoped `TaskObservation`. Selected/
recent authority freshness is now task-owned, separately from Search's retrieval
freshness; Source owns the shared reconciliation mechanics. Retired core root
methods and state are removed.

- Core handoff/adversarial ring passed **130 tests**, independent new component
  ring **10 tests**, and preserved integration plus all fourteen component files
  **718 tests**. Actual public MCP/verification/direct-boundary ring passed
  **81 tests**. Scoped Ty/Pyright for the new owners and direct tests are clean.
- A wider verifier ring reproduced three defects on the frozen parent: late
  source-local disclosure replaced owner-bound reference facts. The generic
  merge repair preserves those existing facts and records direct/indirect
  observations within their own source basis. The repaired ring passed
  **91 tests**; `cr05-verifier-parent-probe.xml` retains the baseline failures.
  No oracle, expected relationship, size ceiling or authority gate was weakened.
- Both selected genuine metadata/sender public workflows and freshly acquired
  native workflows pass all ten gates each under observer
  `sha256:2cf349ad88cbc4eb33dd831d0fa0447c0bb464b6deec3df6c9320b0b30a2d733`.
  See `cr05-public-workflows/summary.json` and
  `cr05-native-workflows/summary.json`. Aggregate status remains INCOMPLETE for
  the explicitly selected two-workflow scope.
- `cr05/source.zip`, SHA-256
  `151f4d1226db06d4892a9a8da7e42bb1ff8b4deae43532e1297ff271dffb61a0`,
  passed **717 tests** from independent extraction, with the one Git-only
  assertion proved in the real worktree. Source compileall and preflight pass.
- Current configured full typing is still red: **1,989 Ty diagnostics /
  1,948 Pyright errors and one warning** (`cr05-full-*.log`).

CR-06's packet/brief implementation now belongs to `RepositoryTasks`, including
its inherited retrieval, scoped-source and configuration disclosure stages.
CodeMap no longer inherits those domain implementations, and all their typed
inputs/casts target Tasks. Tasks now borrows Context and obtains its Source from
the supplied Search owner, avoiding a second independently supplied Source.
Default/initial/decision/action views consume its existing scoped observation;
main packet assembly no longer retrieves the same canonical task result again.
Native relationship composition receives the actual Structure owner. Retired
root packet methods and implementation paths are removed without aliases.

- Packet/initial/brief/v5 ring: **86 PASS**. Actual public/default/operation/
  service/MCP ring: **136 PASS**. Extended brief/verification/transport ring:
  **125 PASS**. Independent task component covers default/initial owner authority,
  freshness, selected verifier, a brief receipt and observation reuse.
- Preserved integration plus all fourteen component files: **719 PASS**.
  `cr06/source.zip`, SHA-256
  `da94e2909e1422245724f35a23b8d42dc835ea0316c9b0a1f95db0775bfd66ff`,
  passed **718 tests** from independent extraction, with one Git-only deselection
  after real-worktree proof. Source compileall and preflight pass.
- Both metadata/sender public workflows and freshly acquired native workflows
  again pass all ten gates each, including the unchanged initial evidence/size
  targets. Reports bind observer
  `sha256:bc9544f3c909a8bffa63b6ffc707ddd662d48be300e489266ef7f34f37308fdf`:
  `cr06-public-workflows/summary.json` and `cr06-native-workflows/summary.json`.
  Aggregate status remains INCOMPLETE for the selected two-workflow scope.
- Additional class-level callers found by the full typing inventory now name
  Index/Source/Ownership/Verification/Tasks directly, including the benchmark-only
  surface classifier and public operation profiler. Their focused ring passed
  **65 tests**. The refreshed test/caller artifact at
  `cr06-qualified/source.zip`, SHA-256
  `e620eb9fc9a1a8fed3cbf0d18e241461ab73d32ac9fbda9e2787e6c3926f0a01`,
  passed **108 tests** from independent extraction. Product observer is unchanged.
  The final private-owner counter annotation was corrected subsequently.
- Packet-family scoped Ty/Pyright is clean. Full project typing remains red;
  the checkpoint inventories are **1,979 Ty diagnostics / 1,938 Pyright errors
  and one warning**, recorded in `cr06-full-ty-checkpoint.log` and
  `cr06-full-pyright-checkpoint.log`.

Continue with CR-07 Bindings/Correlation, CR-08 Declarations/Dependencies and the
remaining owner families. Complete structural-locality/read-binding/lifecycle
qualification and full project typing still remain mandatory before the final
twenty-capability corpus/oracle/witness campaign can claim 5/5.
Use `.hashmarks/canonical-component-rewrite/` for the retained evidence. Earlier
`cr02-index-v2` extraction failures remain historical; three test call sites and
one repository-Git-only proof requirement were corrected in later qualification.
Full architecture, configured project typing, structural-locality and the
independent twenty-capability 5/5 campaign are not complete.

## 1. Decision, scope and intended result

Rewrite CodeMap's shared-instance domain composition into independently
constructed components with explicit dependencies, operations and owned state.
Keep `CodeMap` as the workspace composition and resource-lifetime root. It will
have named component properties and context-manager support; it will no longer
inherit repository-domain mixins or expose their flat methods.

This is a full rewrite of **component boundaries and composition**, including
all first-party consumers. It is not permission to replace sound hashing,
storage, parsing or producer implementations. Retain coherent mechanisms behind
the new boundaries. The product gain must be observable: components can run and
be tested without constructing unrelated systems; state has one writer;
dependencies do not return through CodeMap; evidence and currentness survive
the migration; unnecessary repository work does not increase.

Two milestones have different completion criteria:

1. **Architecture complete:** CR-00 through CR-12 pass their declared checks,
   every old responsibility has a disposition, all obsolete production paths
   are removed, and the final candidate has current integration evidence.
2. **Backend evidence 5/5 complete:** the later Q-00 through Q-05 work closes
   the independently reviewed twenty-capability matrix. Architecture completion
   alone does not satisfy this milestone.

The rewrite is confined to Hashmarks. Other repositories may be deliberately
admitted, pinned qualification inputs; their code is not changed. Hashmarks
remains a repository observer. No planning engine, executor, execution ledger,
retry controller, certification motor, Git lifecycle manager, global semantic
graph, generic dependency container, or runtime ownership-policy engine is added.

Read these authorities before implementation:

- [Product boundary](../reference/PRODUCT_BOUNDARY.md).
- [State and semantic owners](../reference/STATE_AND_SEMANTIC_OWNERS.md), the
  single normative owner map.
- [Responsibility refactoring](../maintainers/RESPONSIBILITY_REFACTORING.md).
- [CodeMap navigation](../maintainers/CODEMAP.md).
- [API stability](../reference/API_STABILITY.md),
  [invariants](../reference/INVARIANTS.md), and
  [dependency evidence](../reference/DEPENDENCY_EVIDENCE.md).

This document schedules changes. Update the normative owner map as each owner
is actually migrated; do not describe planned classes there as implemented.

## 2. Starting point: preserve the work already done

The worktree contains substantial earlier work. Do not reset it, replay every
historical repair, or infer its content from HEAD alone. The older plan's TODO
labels are historical and must not drive duplicate implementation.

| Area | Observed starting state | Required action |
| --- | --- | --- |
| Stable ingestion | `_parse_or_reuse` uses `FileDigestStore.read_bytes_stable`; artifact-key namespace is v2 | Preserve the repair and its deterministic interleaving tests |
| Reverse graph reuse | Relationship code owns `_invalidate_file_graph_cache`; sync calls that owner operation | Preserve behavior; remove the upward dependency when independent components are wired |
| Source reads | Context slices and grep reuse qualified member observation | Move this authority into Source without reopening raw-read bypasses |
| Manifest admission | Startup and uv workspace discovery use admitted manifests | Preserve root and nested-project admission behavior |
| Metadata retrieval | Covered class-declaration supplements no longer consume an unnecessary promoted slot | Preserve exact facts, ordering, explicit-identifier precedence and omission accounting |
| File admission | `RepositoryFiles` exists in `repository_file_discovery.py`; its old mixin and aliases are removed | Finish and qualify this component; do not implement it twice |
| Component imports | `hashmarks.codemap.__init__` has explicit lazy module exports | Preserve independent component imports; this is not instance-level delegation |
| Remaining CodeMap | Domain mixins still share CodeMap state and private operations | Migrate the remaining owners and consumers |
| Qualification | The Files candidate has a 51-test focused pass | Run broader proof on the actual component candidate before carrying forward any claim |
| Typing | Last retained full runs: 2,069 Ty diagnostics and 2,041 Pyright errors | Treat as historical red measurements; obtain current inventories and repair by owner |

The independently extracted **repaired parent before the Files migration** is
retained at
`.hashmarks/canonical-owner-consolidation-20261017/checkpoint/`:

- Source ZIP SHA-256:
  `54fd803220f28f2b09b8bad13b10516a90355db80ce99206f5f8137dc7c66b60`.
- Observer identity:
  `sha256:b59ef4c6586859d508e255606389759291960a964a9d0d0dd0909ba5ea97422d`.
- Its bounded integration ring passed 642 tests; extracted smoke passed 182.
- Its selected metadata and sender public/native workflows passed their
  workflow gates, but their overall qualification remained INCOMPLETE.
- `repository_context.py` retained the same five Ty and seven Pyright findings
  as its independently checked baseline. Do not call every modified owner
  type-clean.

The parent is comparison and recovery evidence, **not proof of the current
Files candidate**. Inspect the manifest and import origin before using an
extraction; temporary paths may no longer exist. The Files log is
`.hashmarks/canonical-component-rewrite/files-tests.log` (51 passed).
If ignored artifacts are unavailable, regenerate the necessary baseline and
label historical claims unverified; do not invent a receipt.

## 3. Fixed architecture decisions

### 3.1 A component owns behavior and state

A component must meet all of these conditions:

- Its constructor accepts the specific lower capabilities or immutable inputs
  it uses, never a `CodeMap`, `Any` context, service dictionary or universal bag.
- It has no production import of `engine.CodeMap`, including type-only casts.
- Its owned state is initialized and changed by that component only.
- Its meaningful operations perform the responsibility; they do not merely
  forward through the old root implementation.
- It can be constructed with its actual narrow dependencies in a direct test.
  Such a test must not need an identity daemon or a full repository packet
  unless that behavior is the thing being tested.
- Its dependency direction is explicit and one-way. Receiving an immutable
  qualified fact from another domain does not transfer that fact's authority.

`CodeMap` owns construction, paths/configuration for construction, resource
cleanup, and read-only component properties. Domain caches and algorithmic
state leave `engine.py`. Use an `ExitStack` or equivalent explicit ownership to
close partially constructed resources and close each acquired resource once.
Components receiving a borrowed store or provider do not close it independently.

Do not introduce instance `__getattr__`, `__getattribute__`, root back-pointers,
automatic registration, root-bound callbacks, or component lookup by string.
The existing package-level lazy export map may remain: importing a named class
is different from redirecting a repository operation to an invisible owner.

### 3.2 Compatibility and contract changes

The new Python contract is deliberately breaking:

- Root calls such as `repo.sync()`, `repo.outline()` and `repo.task_evidence()`
  are removed when their consumers migrate. No deprecated wrappers or aliases.
- Keep the useful public `CodeMap` import and context-manager entry point.
  Renaming the composition root has no demonstrated benefit.
- Use the namespace/method map in section 6. Preserve current typed arguments,
  defaults, bounds and result semantics unless that map explicitly splits an
  operation. Do not spend the rewrite renaming every parameter.
- Remove root `store`, `file_store`, `artifacts`, provider and cache exposure
  from consumer use. Expose a domain observation instead when a caller needs a
  generation, revision, provider capability or index statistic.
- Python service-client methods also move under named families. They remain
  explicit typed requests through the existing IPC boundary, without a dynamic
  client proxy or access to server components.
- CLI/MCP/service operation names and serialized evidence schemas stay as they
  are by default. Their existing meanings are useful; moving Python ownership
  does not require changing wire bytes. Rewrite adapters to call the new owners.
- If a genuine semantic/wire change becomes necessary, version that particular
  contract in `operation_contract.py` and its domain validator, update every
  first-party producer/consumer together, and reject obsolete input explicitly.
  Do not dual-read or silently coerce old schemas for compatibility.
- Derived cache state is disposable. Reuse only when its existing revision,
  parser and qualification binding proves validity. If a storage format must
  change, reject/rebuild derived state with an explicit version; never migrate
  canonical repository bytes or introduce a second identity namespace casually.

Unmigrated domains may remain in the root during intermediate development
stages. A migrated operation has exactly one implementation and its old root
entry is deleted in that stage. This is temporary staged development, not a
supported dual API. Do not release a partly migrated public contract.

### 3.3 Existing authority remains distinct

Retain the existing owners for canonical content identity, file digests,
freshness vocabulary, completeness, producer claims, repository generations,
import identity, ownership proof and dependency semantic authority. Component
boundaries do not create stronger evidence or a universal confidence score.

Source completeness, semantic coverage, freshness, ambiguity and display bounds
stay independent. Missing or truncated results stay unknown/incomplete unless
the relevant owner proves absence for the required scope before projection.

## 4. Target component and dependency map

Class names below are target names; only `RepositoryFiles` is already
implemented as an independent component. Existing filenames are reused where
they describe the responsibility. **Proposed** marks a new file. Supporting
modules may become pure functions over typed values; there is no requirement to
make one class or one new file per old mixin.

| Component / exposure | Implementation home | Responsibility and allowed lower dependencies |
| --- | --- | --- |
| `RepositoryFiles` / `repo.files` | `repository_file_discovery.py` | Admission, format-neutral traversal, loaded context policy; paths and `ContextPolicy` only |
| `RepositoryObservationSource` / internal | **Proposed** `repository_observation.py` | Read existing identity-client observations and preserve unavailable/incompatible as unknown; identity client and workspace binding only |
| `RepositoryIndex` / `repo.index` | `indexing_lifecycle.py` | Discovery-to-parser ingestion, published import-root projection, reconciliation, index/build observations; Files, stable-byte/artifact/store mechanisms, parser/range provider, observation source |
| `DecisionScope` / `repo.reads` | `decision_session.py` | One generation-bound read scope, lower query reuse and diagnostics; Index/read queries and observation source, never task or presentation owners |
| `RepositorySource` / `repo.source` | **Proposed** `repository_source.py`; existing source primitives remain mechanisms | Qualified member/range/outline/symbol/grep/source observations and their visibility; Files, Index read/reconcile capability, stable bytes and DecisionScope |
| `RepositoryImports` / internal | `import_resolution.py` | Qualified import/alias/re-export identity; published index projection, read queries and Files/Source where already required |
| `RepositoryNativeEvidence` / `repo.native` | `native_evidence.py`, reusing internal `evidence_freshness.py` and producer adapters | Native import/enrichment, provenance/freshness qualification and capability observations; Files, Source, Index publication facts, store transaction mechanism and narrow producers |
| `RepositoryRelationships` / `repo.relationships` | `evidence_graph.py`, `relationships.py` | Existing imports/calls/references/project/affected relationships and reverse-cache validity; qualified Imports/Native evidence, indexed queries, DecisionScope |
| `RepositoryStructure` / `repo.structure` | `structural_locality.py` | Existing bounded structural search/locality/direct-call evidence; Source, Imports, qualified native inputs, read queries and structural search provider |
| `RepositorySearch` / `repo.search` | `find_engine.py`, `task_retrieval.py` | Candidate retrieval and its own caches/single-flight; normalized query primitives, Source, Relationships, read queries and DecisionScope |
| `RepositoryContext` / `repo.context` | `repository_context.py`, `work_context.py` | Context construction and progressive disclosure/economics over selected candidates; Search, Source, Relationships, ContextCache and DecisionScope |
| `RepositoryOwnership` / `repo.ownership` | `ownership_analysis.py`, `ownership_graph.py`, `ownership_nomination.py`, `ownership_candidate_*.py`, existing `ownership/` modules | Repository ownership/risk observations and task-candidate qualification; Imports, Source, Relationships, Structure and supplied candidate/evidence values |
| `RepositoryVerification` / `repo.verification` | `evidence_verification.py`, `verification_ownership.py`, `verification_plan.py`, `verification_explanation.py` | Relevance and declared test-plan facts for supplied owner/test evidence; Source, Imports, Relationships, indexed queries and value-level ownership facts; no task-component back-reference |
| `RepositoryTasks` / `repo.tasks` | `repository_tasks.py`, `task_action_projection.py`, `task_entry_points.py`, `task_freshness.py`, `task_verification.py`, `task_receipts.py`, `evidence_packet.py`, `evidence_decision_packet.py` | Task-local composition of retrieval, owner evidence, verification and bounded packets; explicit lower components and existing pure projections |
| `RepositoryBindings` / `repo.bindings` | `repository_evidence_bindings.py`, `repository_evidence_coverage.py`, `repository_evidence_binding_delta.py` | Consumer-declared evidence scope and factual binding/coverage/delta; Source, Relationships, existing endpoint-delta primitives |
| `RepositoryCorrelation` / `repo.correlation` | `evidence_correlation.py` | External claim-to-source correspondence; Source, Bindings and indexed queries; no causal or execution authority |
| `RepositoryDeclarations` / `repo.declarations` | `repository_declarations.py`, discovery/derivation modules | Provider-owned declaration claims, explicit correspondence, qualified values/absence and deltas; Files, Source, Bindings, domain validators and caller-selected providers |
| `RepositoryDependencies` / `repo.dependencies` | `dependency_resolution_evidence.py`, correlation/derivation/delta modules | Producer-neutral resolution/inventory/module-ownership evidence and comparisons; admitted project/import facts, Source/Bindings as required and existing adapters/contracts |
| `RepositoryChanges` / `repo.changes` | `repository_delta.py`, `change_impact.py`, `post_change.py`, `change_intelligence.py`, `freshness_map.py` | Caller-selected changed-path observations, snapshots and endpoint comparisons; Tasks, Source, Relationships, Index and existing delta/freshness primitives |
| `RepositoryCrossRepository` / `repo.cross_repository` | `cross_repository_evidence.py` | Existing caller-nominated cross-repository evidence; supplied endpoint identities/observations and Changes; no service discovery or inferred graph |
| `RepositoryEconomics` / `repo.economics` | `intelligence_economics.py` | Current repository-intelligence cost observations; immutable measured inputs/Changes and existing phase counters; no telemetry history or runtime control |
| `RepositoryViews` / `repo.views` | `repository_intelligence_query.py`, `evidence_profiles.py`; pure status composition may remain in `indexing_lifecycle.py` | Existing aggregate query/status/profile projections over exact named lower operations; no new authority, cache manager, universal dispatcher or domain redecision |

`RepositoryViews.status()` composes Index status, Native status and existing
provider capability facts. **Index must not depend upward on Native or Views to
build the old aggregate status packet.** A pure status composer consumes values;
Views obtains them through named capabilities. The index's own status reports
only index-owned facts. Until aggregate status is migrated, its old composition
is an explicitly unmigrated operation, not an Index compatibility wrapper.

Use existing store transaction/query implementations. Introduce a small
`Protocol` only where it restricts an actual consumed capability or permits
direct testing. Do not add a forwarding storage class for each SQL method.
Domain writers may publish their own derived rows through the **same existing
atomic generation transaction**; Index owns base sync/build semantics, not every
domain's producer logic. No component-local generation replaces store authority.

### State moves that must be explicit

| Current root state / mechanism | Final owner and validity rule |
| --- | --- |
| `files`, loaded policy/config/internal-state exclusions | Files; root exposes a read-only reference |
| `max_index_bytes`, `_python_import_roots`, sync/reprojection state | Index; import roots are published with the index projection and consumed read-only by Imports |
| `_identity_client` and `_daemon_observation` behavior | ObservationSource; expected transport failures remain unknown, not current |
| `_decision_session_*`, primitive row/symbol/ref/edge/lexical caches, read diagnostics | DecisionScope; exact active scope and existing generation, cleared on scope exit |
| `_decision_repository_identity_cache` | Lower observation identity primitive cached only in DecisionScope; no verifier-owned repository identity |
| `_reverse_file_graph_cache` | Relationships; bind to existing published generation and qualified native input validity before reuse |
| `_find_flight` | Search; preserve exception propagation and single-flight release |
| `_context_flight`, `ContextCache` use | Context; preserve content/policy/request binding and invalidation |
| `_task_result_cache` | Search; exact retrieval request, generation and admitted contributing evidence |
| `_task_authority_paths_cache`, `_task_recent_authority_paths` | Tasks; bounded freshness observations for selected authority, including delete/restore/ABA cases; no worker attempt history |
| `_decision_task_action_cache` | Tasks; exact request and active read-scope binding, defensive output copies |
| `_decision_snapshot_cache` | Changes; exact snapshot request and active read scope, defensive copies |
| `_decision_change_impact_owner_chain_cache` | Changes; exact existing ownership/revision/bounds inputs; never a second owner selector |
| `_decision_ownership_import_paths_cache` | Ownership, which derives exact ownership import paths in `ownership_graph.py`; use active-scope/generation binding and qualified Imports inputs |
| Range/search/native/project provider instances | Root owns lifetime; Index/Structure/Native borrow only the producer capabilities they use |
| WorkspaceMapStore, ArtifactStore, FileDigestStore | Existing mechanisms; root owns lifetime and grants narrow read/write capabilities, not public raw store access |

The import-path cache's semantic derivation is currently implemented by
`ownership_graph.py::_exact_ownership_import_paths` and
`_uncached_exact_ownership_import_paths`. Ownership owns the cache; Imports
supplies qualified identity facts. DecisionScope may record its reuse counters
without owning or clearing its contents.

## 5. Resolve the known dependency traps before moving methods

### 5.1 Ingestion and qualified reads must not call each other recursively

Index admits files, reads stable bytes, parses and publishes. It never calls
Source's qualified member observation to obtain ingestion bytes. Source may ask
Index to reconcile a stale path before a read scope; during a scope, it signals
`DecisionRefreshRequired` rather than mutating that generation.

DecisionScope establishes readiness through Index, binds the exact published
generation and identity observation, and supplies immutable query reuse. Move
`_ensure_map_ready` and `_reconcile_daemon_generation` out of the root into this
lower readiness composition without making Index depend on DecisionScope.
Split read-only readiness facts from index reconciliation if necessary inside
the existing lifecycle owner; do not invent another freshness classification.

Normal standalone operations retain the current bounded source-race handling:
leave the read scope, reconcile the named path through Index, and re-observe;
repeated drift fails explicitly. An explicitly caller-held scope cannot silently
advance its generation. BUILDING stays incomplete until explicit sync; safety
reporting keeps its currently admitted incomplete mode. This is repository
read consistency, not general execution retries.

### 5.2 Task preflight belongs to task/retrieval owners

Remove `_decision_preflight` dispatch by method-name strings from the lower
decorator. Search checks the freshness of retrieval-cache contributors. Tasks
checks selected/recent authority paths before opening a new read scope. A
task-specific probe is not a DecisionScope responsibility.

Preserve current full-discovery behavior for missing/moved owners and exact-path
reconciliation for byte or symlink changes. Cached authority paths survive a
temporary unsafe result within their existing bound so restoration cannot
resurrect stale proof. An operation already inside a read scope either uses the
same facts or reports drift; it must not bypass a required freshness check.

### 5.3 Native publication and relationship-cache validity are separate

Independent Index cannot call an upper relationship cache-reset method. Replace
this dependency with **Relationships validating its own cache against the
existing published generation plus the current qualification of contributing
native evidence**. Generation alone is insufficient when source/provenance
changes can make native rows stale without a new index publication.

Qualify native inputs before admitting a cache hit. Within a read scope reuse
one qualified input snapshot; outside one, revalidate as the existing authority
requires. Native enrichment publishes its rows and freshness binding atomically
under the existing generation, then returns that publication fact. Do not add
an event bus, subscriber callbacks, extra epoch, or global invalidation manager.

Test unchanged-generation manifest/source invalidation, actual publication,
no-change reuse, failed publication and same-state reopen. Rebuilding a graph
on every request to avoid reasoning about validity is not an accepted rewrite.

### 5.4 Ownership and verification exchange facts, not recursive services

Current public `verification_relevance(task)` calls `task_action_map(task)`;
task composition itself uses verification helpers. Moving both methods
unchanged would create a component cycle.

Use these explicit internal stages, keeping current algorithms and proof rules:

```text
normalize task/query once
  -> Search supplies candidate retrieval and bounds
  -> Ownership nominates candidate(s) and supplies repository proof facts
  -> Verification qualifies test/reference evidence for those candidate facts
  -> Ownership finishes its existing proof with any required identity facts
  -> Tasks composes qualified owner + verification + retrieval observations
  -> pure projections produce bounded/default/initial/text representations
```

The stages may exchange immutable `TypedDict`/dataclass values extending existing
contracts. They do not call back into Tasks. Verification consumes a nominated
or admitted owner fact with its explicit status; it never upgrades a nomination
to edit authority. Any verification-derived identity qualifier used by the
existing owner proof is an explicit value, not a request to select a new owner.
Once edit authority is admitted, verification relevance cannot replace or
rerank it. Candidate refinement before final proof remains valid where the
current algorithm actually requires it.

Task-taking convenience operations move to Tasks. Verification's direct API is
owner/test-bound. Shared task cue normalization moves to existing
`query_primitives.py`/`query_router.py` values or pure functions, not to a new
task workflow framework. Do not replace distinct authority domains with one
global score.

### 5.5 Member observations and endpoint comparisons have different owners

Move `_repository_member_observation` and its admission/read/range support from
`repository_delta.py` to Source. Bindings, Correlation, Declarations and source
projections use that operation. Endpoint comparison remains in existing typed
delta owners; it consumes observations rather than re-reading source ad hoc.

Move neutral repository/source packet-binding primitives out of Verification
to the lower observation/source layer. Preserve digest domains, byte encoding
and identities. A domain-specific digest remains with its domain; do not create
a universal identity manager.

Declaration `previous_observation` stays one-call comparison input. It never
hydrates current providers/subjects/correspondence, including after reopen in
the same durable state directory. Dependency producer syntax stays in adapters;
physical source kind never becomes core semantic authority.

### 5.6 Aggregate views cannot create downward dependencies

Changes composes Tasks, Source and Relationships. CrossRepository and Economics
consume Changes observations. Views consumes these and produces existing bounded
profiles/query/status projections. None of those lower owners may call Views.

Where two existing surfaces call each other for a reusable value, extract the
actual observation or pure value projection below both callers. Do not solve a
cycle by injecting a lazy root callback, optional component slot, service locator
or an untyped closure. Keep the existing bounded operation/mode registry as the
wire authority; do not add a second domain dispatcher.

## 6. New Python API and exhaustive migration families

Example of the intended public usage; these are target calls, not currently
available methods:

```python
from hashmarks import CodeMap

with CodeMap(workspace, state_dir=state_dir) as repo:
    repo.index.sync()
    outline = repo.source.outline("src/service.py")
    hits = repo.search.find_task(task)
    packet = repo.tasks.evidence(task)
    test_facts = repo.tasks.verification_relevance(task)
    status = repo.views.status()
```

Keep existing argument/default/result contracts under the following method
names. Names not explicitly shortened below stay unchanged inside the listed
namespace. Pure module functions and model types stay with their semantic owner.

| Old flat root operation(s) | New owner and method(s) |
| --- | --- |
| `sync`, `index_preflight`, `derived_graph`, `clean`, `watch_forever` | `index.sync`, `index.preflight`, `index.derived_graph`, `index.clean`, `index.watch_forever` |
| `status` | `views.status`; lower `index.status` is index facts only |
| `decision_session`, `decision_session_stats`, `decision_session_diagnostics` | `reads.session`, `reads.stats`, `reads.diagnostics`; session yields a read-scope value, not CodeMap |
| `outline`, `symbol`, `source`, `grep` | `source.outline`, `source.symbol`, `source.read`, `source.grep` |
| `repository_instruction_scope` | `context.instruction_scope` owns query-based seed nomination; lower `source.instruction_scope` observes caller-selected paths without depending on Search |
| `source_observation`, `scoped_source_occurrences`, `scoped_source_literals` | `source.observe`, `source.scoped_occurrences`, `source.scoped_literals` |
| Class-level aliases `diagnostic_source_revision_evidence`, `external_diagnostic_observation`, `diagnostic_observation_delta` | Remove the class aliases; import the existing functions directly from `diagnostic_source_revision.py` and `diagnostic_observation.py`, including MCP/test/doc callers |
| `import_scip`, `enrich_projects` | `native.import_scip`, `native.enrich_projects` |
| `projects`, `deps`, `refs`, `affected`, `tests` | `relationships.projects`, `relationships.deps`, `relationships.refs`, `relationships.affected`, `relationships.tests` |
| `task_graph_adjacency`, `task_relationships` | `tasks.graph_adjacency`, `tasks.relationships`; task-independent relation derivation stays in Relationships |
| `structural`, `structural_locality` | `structure.search`, `structure.locality` |
| `find`, `find_packet`, `query_route`, `find_task`, `formulate_task_query`, `task_query_views` | `search.find`, `search.packet`, `search.query_route`, `search.find_task`, `search.formulate_task_query`, `search.task_query_views` |
| `context`, `orient`, `task_context`, `task_context_plan` | `context.build`, `context.orient`, `context.task`, `context.task_plan` |
| `work_context`, `work_context_budget_sweep` | `context.work`, `context.budget_sweep` |
| `explain_task_retrieval`, `retrieval_stability` | `search.explain_retrieval`, `search.retrieval_stability`; replay owns temporary invalidation/restoration of the Search cache |
| `repository_findings`, `repository_ownership_graph`, `ownership_relation_graph` | `ownership.findings`, `ownership.repository_graph`, `ownership.relations` |
| `cache_ownership_findings`, `cache_invalidation_ownership_graph`, `concurrency_risk_findings`, `import_ownership_findings` | `ownership.cache_findings`, `ownership.cache_invalidation_graph`, `ownership.concurrency_findings`, `ownership.import_findings` |
| `task_entry_points`, `task_action_map`, `task_decision_packet` | `tasks.entry_points`, `tasks.action_map`, `tasks.decision_packet` |
| `task_evidence`, `task_action_brief`, `task_decision_brief`, `task_decision_brief_budget_sweep` | `tasks.evidence`, `tasks.action_brief`, `tasks.decision_brief`, `tasks.decision_brief_budget_sweep` |
| Task-taking `verification_relevance`, `verification_ownership_graph`, `explain_verification_selection` | `tasks.verification_relevance`, `tasks.verification_ownership_graph`, `tasks.explain_verification_selection`; these compose the same task observation once |
| `verification_plan`, `verification_relationship_evidence` | `verification.plan`, `verification.relationship_evidence`; direct `verification.for_owner` consumes qualified owner/candidate facts rather than task text |
| `repository_evidence_bindings`, `repository_evidence_coverage`, `repository_evidence_binding_delta` | `bindings.observe`, `bindings.coverage`, `bindings.delta` |
| `correlate_evidence`, `evidence_correlation_delta` | `correlation.observe`, `correlation.delta` |
| `repository_declarations`, `discover_repository_declarations`, `repository_declarations_operation` | `declarations.observe`, `declarations.discover`, `declarations.operation` |
| `repository_declaration_derivation_authority`, `repository_declaration_explain` | `declarations.derivation_authority`, `declarations.explain` |
| `dependency_codemap`, `dependency_resolution_evidence`, `dependency_resolution_queries` | `dependencies.codemap`, `dependencies.observe`, `dependencies.queries` |
| `dependency_evidence_correlation`, `dependency_import_correspondence`, `dependency_resolution_delta` | `dependencies.correlation`, `dependencies.import_correspondence`, `dependencies.delta` |
| `dependency_resolution_derivation_authority`, `dependency_resolution_explain` | `dependencies.derivation_authority`, `dependencies.explain` |
| `change_impact`, `task_change_impact`, `task_post_change_delta` | `changes.impact`, `changes.task_impact`, `changes.task_delta` |
| `refresh_after_change`, `refresh_after_change_brief`, `refresh_after_change_delta` | `changes.refresh`, `changes.refresh_brief`, `changes.refresh_delta` |
| `change_intelligence_brief`, `evidence_freshness_map` | `changes.brief`, `changes.freshness_map` |
| `repository_intelligence_snapshot`, `repository_intelligence_delta` | `changes.snapshot`, `changes.delta` |
| `external_observation_freshness` | `changes.external_observation_freshness`; it compares supplied repository/generation/change-scope facts without reading source or executing diagnostics |
| `cross_repository_evidence_packet` | `cross_repository.packet` |
| `intelligence_economics_receipt` | `economics.receipt` |
| `repository_intelligence_profile`, `repository_intelligence_query` | `views.profile`, `views.query` |

For each operation, CR-00 records all defining methods, including inherited
mixins and callable class assignments, and all production/test/script/example/
documented callers. Any uncovered
public operation is a blocking inventory gap: assign it to its existing semantic
family before deleting anything. This table is a migration checklist, not a
runtime registry or an instruction to promote internal methods to MCP.

## 7. Common procedure for every implementation package

1. Confirm predecessor acceptance on the actual candidate. Read the current
   diff and the package's relevant original assertions. Do not start by changing
   expected results to fit the new API.
2. Record classification, invariant, owner, callers, state writes, errors and
   direct tests in the package's existing change/qualification evidence. Reuse
   the established repository-evaluation reports; no new campaign controller.
3. Freeze the exact parent source membership, modes and content identity,
   including untracked first-party files. Preserve direct-test/oracle bytes.
   Classify intended Python API changes separately from evidence behavior.
4. Make the bounded change. Migrate direct first-party consumers and remove
   obsolete definitions in the same package. Update remaining unmigrated mixins
   to call the component directly; never add a root compatibility property to
   keep their old private field access working.
5. Run `make agent-finish`, focused behavior/authority tests, and both scoped
   type checkers with the unchanged project configuration. Use
   `hashmarks.python_ast_cache.read_python_ast` for file-backed AST tooling.
6. Preserve independent semantic assertions. Existing tests calling removed
   Python APIs need mechanical call-site/import migration; record those exact
   contract edits, preserve fixtures/expected facts/adversaries, and compare
   assertion bodies. Do not report these edited files as byte-identical replay.
   Replay unchanged applicable producer/CLI/MCP/semantic contract tests against
   the full changed source set. New component tests supplement that proof.
7. Record comparable pre/post dependency/locality, repeated reads/parse/query
   counters and relevant complexity measurements. Use the same repository,
   task, bounds and semantic inputs. Unresolved/truncated locality is incomplete
   measurement, not permission to lower bounds or certify success.
8. For a persistent source checkpoint: one configured source compile, one
   deterministic source ZIP, independent extraction, import-origin/identity
   verification and focused tests from the extraction. Follow the candidate
   tiers in AGENTS.md; repeated wheel/sdist builds are reserved for final
   promotion or packaging-transform changes.
9. Report PASS, FAIL or INCOMPLETE with the actual scope. Stop the package for a
   semantic failure; retain failed evidence, repair the owner, rerun affected
   checks and the package integration ring. A controller timeout invalidates
   only the in-flight batch and never becomes a product failure.

The explicit Python API revision is the exception to old signature preservation.
It is not an exception to source facts, freshness, authority, serialized
semantics, retained oracles, or complete behavioral proof. Do not create a
production or test compatibility facade that could hide a broken new boundary.

## 8. Ordered implementation packages

| Package | Deliverable | Prerequisites |
| --- | --- | --- |
| CR-00 | Exact starting checkpoint, exhaustive operation/state/caller inventory and current baseline | Planning approval / implementation instruction |
| CR-01 | Finish independent Files and its public boundary | CR-00 |
| CR-02 | Coordinated Index, ObservationSource, DecisionScope and Source migration | CR-01 |
| CR-03 | Qualified Imports, Native evidence, Relationships and Structure | CR-02 |
| CR-04 | Candidate Search and Context components | CR-03 |
| CR-05 | Ownership, Verification and Tasks with value-level handoffs | CR-04 |
| CR-06 | Default/initial/compact task evidence from the same facts | CR-05 |
| CR-07 | Bindings and Correlation over canonical Source | CR-02, CR-06 |
| CR-08 | Declarations and Dependencies with producer-neutral boundaries | CR-03, CR-07 |
| CR-09 | Changes, cross-repository, economics and aggregate Views | CR-06, CR-07, CR-08 |
| CR-10 | Complete public clients/adapters/docs and remove every legacy root path | CR-01 through CR-09; consumer migration happens throughout |
| CR-11 | Final architecture, lifecycle and no-new-debt proof | CR-10 |
| CR-12 | Current integrated/extracted candidate qualification | CR-11 |

Implement packages in the listed order. The prerequisites describe coupling,
not permission to delegate work or to leave a broken mainline between packages.
CR-02 and CR-05 are coordinated migrations with small internal steps; stop only
at a coherent tested checkpoint, not halfway through a circular dependency.

### CR-00 — Reconcile the current worktree and freeze a usable baseline

**Classification:** REFACTOR INTERNALLY for inventory/contract reconciliation;
no new product responsibility.

**Read/change:** `engine.py`, all CodeMap bases and their inherited bases,
`operation_contract.py`, `service.py`, `repository_cli.py`, `mcp_surface.py`,
`tests/typecheck/`, and the owner/API/navigation references. Qualification
inventory may live under `.hashmarks/canonical-component-rewrite/`.

1. Record `git status --short`, HEAD, exact dirty source membership and current
   Python/tool environment. Preserve the user work and existing ignored proof.
2. Derive a complete inventory using cached AST snapshots and repository search:
   root/public/private method definitions, inherited definitions, callable class
   aliases, own-state
   reads/writes, root-bound callbacks, monkeypatch points and actual callers.
   Inspect dynamic `getattr`/`hasattr` dispatch and decorator-bound methods too;
   text search alone does not prove their absence.
3. Reconcile the inventory with sections 4 and 6. Classify storage/parsers/native
   adapters as KEEP COHESIVE; classify shared-self multi-domain composition as
   DECOMPOSE MULTIPLE RESPONSIBILITIES; classify each extracted owner as EXTRACT
   RESPONSIBILITY. Record direct owning tests and semantic locality targets.
4. Freeze the current Files candidate separately from the repaired parent. Use
   current exact source identities; b59… must not label this candidate.
5. Run the Files focused ring in section 9, architecture/publication tests and
   current source compile. Run full Ty and Pyright once, separately, retaining
   both outputs even if the first fails. These inventories are the typing
   baseline, not a required 0-error result for every small stage.
6. Freeze semantic/transport assertions before migration. Mark expected Python
   import/call changes explicitly in API_STABILITY and the preservation scope.
   Keep backend corpus tasks, source oracles, review flags and witnesses fixed.

**Acceptance:** current baseline identity and tests exist; no old TODO is
mistaken for undone repairs; every public operation, state field and direct
caller has a target or a justified unchanged mechanism; typing debt is current.
An unassigned authority-bearing method blocks its owner stage.

Include `WorktreeOverlay` and the analyzer objects under `codemap/ownership/`
explicitly. They already receive/store CodeMap despite not being domain mixins;
removing the inheritance list alone would leave those back-pointers intact.

### CR-01 — Complete Files instead of recreating it

**Classification:** EXTRACT RESPONSIBILITY, completing the existing extraction.

**Owners/files:** `repository_file_discovery.py::RepositoryFiles`,
`engine.py`, `codemap/__init__.py`, existing admission consumers and
`tests/test_repository_files_component.py`.

1. Retain independent construction, loaded policy, admitted traversal, manifest
   discovery, exact internal-prefix handling and nested-repository/symlink rules.
2. Make the root reference read-only through a typed property; keep mutations
   such as policy refresh owned by Files. Do not expose `ContextPolicy` as a
   second mutable authority on CodeMap.
3. Audit the lexical/physical path precondition. CodeMap canonicalizes its root;
   standalone Files must either canonicalize with the existing path primitive
   or explicitly reject a non-canonical root. Choose **canonicalization using
   `canonical_host_path`**; preserve symlink-member confinement. Add a real
   standalone relative/root-symlink case, not a source-string assertion.
4. Confirm all old admission operations are gone and all consumers call Files.
   Keep private provider callbacks limited to `visible_manifests`, not CodeMap.
5. Run the focused Files ring plus source-read/revision regressions and
   scoped typing. Inspect parser-unsupported files as valid admitted files;
   admission and parse support remain separate.

**Acceptance:** no CodeMap/DB required for Files; semantic policy changes retire
denied rows and admit newly allowed paths through normal index reconciliation;
invalid policy does not return old evidence as current; old aliases are absent.

### CR-02 — Move the foundational consistency boundary together

**Classification:** EXTRACT RESPONSIBILITY for Index, ObservationSource and
DecisionScope; DECOMPOSE MULTIPLE RESPONSIBILITIES for source operations
currently spread across engine/query/context/delta modules.

**Files:** `engine.py`, `indexing_lifecycle.py`, `index_watch.py`,
`decision_session.py`, `query_surface.py`, `repository_context.py`,
`repository_delta.py`, proposed `repository_source.py` and
`repository_observation.py`, existing store/query/parser mechanisms.

Perform these substeps in order within one coordinated package:

1. Extract ObservationSource's actual IdentityClient use and expected-failure
   mapping. Keep it out of canonical identity's import graph. Test daemon
   unavailable/incompatible/protocol failure as unknown without broad catches.
2. Construct RepositoryIndex from Files, mechanisms, parser/range capability and
   ObservationSource. Move sync/build/reconcile/import-root projection state.
   Preserve atomic row+generation+COMPLETE publication, rollback, overlays,
   parser-error/unsupported behavior, artifact v2 and build-incomplete semantics.
3. Replace sync's relationship invalidation call with publication facts. Move
   relationship-cache ownership/validity work needed for this seam forward from
   CR-03; do not temporarily add an Index-to-root callback. Do not close the
   package before this seam's tests pass.
4. Move lower read scope and immutable store-query caches into DecisionScope.
   Rewrite decorators against a narrow scope capability; remove `cast(CodeMap,
   self)`, dynamic task preflight dispatch and yielding the full root. Preserve
   nested-scope generation checking and existing diagnostics/counter meanings.
   Before deleting the old preflight hook, put its required task freshness calls
   in the existing task action/decision entry points, even though their component
   extraction follows later. Otherwise the intermediate candidate would lose
   unsignaled-change and restoration protection.
5. Extract Source's member observation and range reads, outline/symbol/read/grep,
   scoped occurrences/literals and instruction-scope observations. Reuse stable
   bytes and current policy. Use Source for source packet identity/range binding;
   keep endpoint comparison functions in their existing domains.
6. Move readiness/reconciliation out of engine with the direction specified in
   section 5. Explicitly cover no-daemon, newly available daemon, dirty paths,
   unknown continuity, empty index, incomplete build and explicit read scopes.
7. Migrate **every remaining mixin** that reads `_decision_*`, root stores,
   `_ensure_*`, member observation, `_python_import_roots` or moved source
   operations to the new narrow capabilities. Root fields/aliases are not a
   shortcut. Leave domain-specific task/snapshot caches with their temporary
   owning domain until CR-05/09, without making DecisionScope clear their state.
   Preserve their old lifetime by adding the active read-scope binding to the
   owner's exact cache key or equivalent owner-local validity check. This token
   is disposable reuse scope, never a new repository generation. Prove an ended
   scope cannot supply a final cached packet to the next scope merely because
   the stored generation did not change.
8. Migrate applicable CLI/MCP/service/test/typecheck callers and remove the
   completed root operations and mixin bases. Preserve aggregate status as an
   explicitly unmigrated composition until Native/Views are available.

**Direct proof:** source revision binding, admission convergence, source-read
contract, publication/state/overlay generation, decision freshness/session and
watcher lifecycle tests. Add direct component tests for failed construction,
nested/read-drift behavior and Source working without Search/Tasks.

**Acceptance:** no Index→Source→Index recursion; lower components do not import
CodeMap; file changes between hash/read/parse never produce mixed revisions;
policy denial/symlink replacement never leaks bytes; no query silently promotes
BUILDING to a complete generation; atomic publication and watcher fencing hold.

### CR-03 — Separate import identity, native qualification and relationships

**Classification:** EXTRACT RESPONSIBILITY for Imports/Structure;
DECOMPOSE MULTIPLE RESPONSIBILITIES for `evidence_graph.py`'s producer publication
and relationship derivation.

**Files:** `import_resolution.py`, `evidence_graph.py`, `evidence_freshness.py`,
`relationships.py`, `structural_locality.py`, `semantic_relationship_source.py`,
SCIP/LSP adapters, project providers, proposed `native_evidence.py`.

1. Construct Imports from published index/root facts, Files/Source and narrow
   queries. Preserve relative/alias/re-export/star identity with the existing
   eight-hop bound; shadowing, cycles and ambiguity remain unresolved.
2. Move native import/enrichment and freshness/provenance operations into Native.
   Keep producer parsing in adapters and repository admission in Files/Source.
   Publish rows plus freshness binding atomically under the same store authority.
3. Move direct repository relationship derivation and reverse-cache state into
   Relationships. Complete section 5.3's cache binding and revalidation; include
   scope/policy changes in the existing index/qualification bindings.
4. Move structural search/locality into Structure using exact direct endpoints,
   direction and bounds. Retain qualified native/source evidence alternatives;
   do not add transitive declaration semantics or a semantic node/edge registry.
5. Replace engine-module provider monkeypatch hooks (including Vitest imports)
   with explicit provider injection at the producer boundary. Migrate tests to
   fake only that capability, preserving output assertions and failure behavior.
6. Remove retired mixin bases, root providers/cache references and duplicate
   low-level graph/identity implementations. Aggregate status can now compose
   index/native/provider facts through a pure value projection used by Views.

**Direct proof:** relationship-cache tests, qualified import bounds/re-exports,
native freshness/publication/transport, SCIP import roundtrip, structural
direct-call/import-call scopes and presentation collections. Run
`tests/test_native_lsp_changes.py` in full; do not retain its earlier failures as
accepted noise.

**Acceptance:** no false unique imports; stale native rows cannot enter a cache
hit; same-state reopen converges; native absent/incomplete remains unknown;
bounded path observations contain no invented segment or transitive edge;
unchanged qualified input reuses work without changing evidence.

### CR-04 — Give retrieval and context their own economics and state

**Classification:** EXTRACT RESPONSIBILITY for Search and Context; KEEP COHESIVE
for existing query/ranking, token estimation and ContextCache mechanisms.

**Files:** `find_engine.py`, `task_retrieval.py`, `repository_context.py`,
`work_context.py`, `query_router.py`, `query_primitives.py`, `context_cache.py`,
`task_evidence_retrieval.py`, `task_evidence_scoped_method.py`.

1. Construct Search with narrow lower evidence inputs. Move find single-flight,
   canonical task result reuse and retrieval freshness checks to Search.
2. Normalize the query once and pass the existing structured terms/route through
   retrieval and later owner/verification stages. Do not re-decide explicit
   targets from weaker raw text or change rank to make the corpus green.
3. Construct Context with Search, Source, Relationships and borrowed ContextCache.
   Move context single-flight/disclosure assembly and work-context operations.
   Cache/projection hits must preserve exact source/policy/request qualification.
4. Preserve the metadata supplement repair and bounded class-member disclosure.
   Keep explicit identifiers, out-of-class candidates, verifier test directories,
   ambiguous same names and exact omissions. Avoid re-reading/re-parsing a file
   for each consumer; pass the stable source/AST snapshot to analyzers.
5. Migrate consumers, defaults, fixtures and root access. A retrieval result
   remains a candidate; extraction must not give it ownership authority.

**Direct proof:** query router/canonical retrieval, context policy, task result
reuse, declared supplement order, source read visibility, explicit retrieval and
natural/same-name declaration tests. Measure cold/warm/incremental parse/read/SQL
counts using the same input as the frozen parent, including single-flight error
and cleanup paths.

**Acceptance:** rank and admitted semantic facts match the parent except for
separately reproduced generic defects; no extra full scan per packet; components
do not construct Tasks or Verification; metadata facts stay early and bounded.

### CR-05 — Establish value-level ownership and verification handoffs

**Classification:** DECOMPOSE MULTIPLE RESPONSIBILITIES in task composition;
KEEP COHESIVE for the current `hashmarks.ownership_decision` proof model and
neutral verification-plan derivation.

**Files:** `repository_tasks.py`, `task_action_projection.py`,
`ownership_candidates.py`, `ownership_nomination.py`,
`ownership_candidate_resolution.py`, `ownership_candidate_evidence.py`,
`task_action_types.py`, `ownership_analysis.py`, `ownership_graph.py`,
`ownership/`, `evidence_verification.py`, `verification_ownership.py`,
`verification_explanation.py`, `verification_plan.py`, `task_evidence_types.py`.

1. Extract Ownership's repository/risk/relationship operations and its derivation
   caches. Keep import/cache/concurrency diagnostics static observations, not
   runtime failure claims or proposed repairs that execute.
   Rewrite the actual analyzer inputs in `ownership/import_ownership.py`,
   `cache_ownership.py`, `cache_invalidation.py`, `concurrency_risk.py` and
   `filesystem_lifecycle.py`: pass Source, Imports and the exact query/fact
   capabilities each consumes, not the new Ownership object as a replacement
   universal bag. Preserve shared stable AST snapshots and failure/completeness
   accounting. Remove `FilesystemLifecycleAnalyzer.codemap` and equivalent
   stored root references.
2. Specify typed internal task inputs, candidate/owner facts and verification
   qualifiers by extending existing models. Preserve independent status,
   freshness, completeness, ambiguity, provenance and bounds. Do not add a
   generic universal evidence schema or runtime contract registry.
3. Implement the staged handoff in section 5.4 using existing algorithms. Split
   nomination from final proof only where needed to remove the actual cycle.
   Retain legitimate pre-proof candidate refinement and fail-closed identity.
4. Construct Verification without Tasks/CodeMap. Direct `for_owner` consumes
   supplied candidate/owner facts and their exact read binding. Test-plan
   derivation returns existing command/evidence descriptions and never runs them.
5. Construct Tasks from explicit lower owners. Move task entry-point/action-map
   assembly, task-taking verification shortcuts and task authority freshness
   caches into Tasks. Reuse one task observation for shortcuts; do not retrieve
   or prove the owner again in each public view.
6. Move neutral packet identity primitives to Source/observation owners. Migrate
   all non-verification consumers before removing the old methods.
7. Remove the old task/verification recursive call chain and corresponding
   root fields, decorators and aliases; update direct callers and type contracts.

**Direct proof:** exact explicit target, ambiguous close owners, production
`src/**/test_*.py`, identifier-shape normalization, star/re-export bounds,
verification locality/member identity, late declarations and reference fallback.
Include stale→unsafe→restore/ABA, delete/rename, unrelated same-name test and
candidate-limit changes that must not erase known ambiguity.

**Acceptance:** candidate retrieval, owner proof and verification selection have
one owner each; Verification never calls Tasks or selects edit authority; Tasks
never independently reimplements owner qualification; returned test relevance
is uncertainty-qualified and makes no sufficiency/execution claim.

### CR-06 — Compose task evidence once and preserve every projection

**Classification:** REFACTOR INTERNALLY within Tasks; EXTRACT RESPONSIBILITY only
for pure, named projections that bind an independent value.

**Files:** `evidence_packet.py`, `evidence_decision_packet.py`,
`task_evidence_initial.py`, `task_evidence_contract.py`, `task_evidence_types.py`,
`hashmarks/evidence_presentation*.py`, `hashmarks/evidence_declaration_text.py`.

1. Assemble one qualified task observation from CR-05. Default, decision/action
   briefs and initial packets consume that observation without rerunning rank,
   ownership or verification. Reuse exact generation/request-bound results.
2. Preserve initial codec behavior, opaque extension JSON and typed default vs
   initial distinction. Domain validation and codec roundtrip have different
   contracts; neither substitutes for the other.
3. Keep source references, missing edges, alternative owners, unknown branches,
   verification qualification and omissions through text/compact/JSON/initial.
   When a bound excludes admitted facts, account for that exclusion explicitly;
   do not turn projection omission into absence.
4. Run the genuine metadata/sender workflows at both revisions through Python,
   CLI and official MCP. Compare facts and omissions against the unchanged oracle
   and initial 4,000-token ceiling. Preserve earlier failing acquisitions.
5. If the component candidate regresses size or verifier retrieval, reproduce
   the generic defect in the relevant owner and repair it there. Do not raise
   the ceiling, delete facts, hard-code these repositories or alter oracle paths.

**Acceptance:** all supported forms preserve required semantic facts and
qualification; the selected genuine tasks meet their unchanged workflow gates
and initial bound on this candidate. The report remains scoped, not full 5/5.

### CR-07 — Move bindings and external correlation onto Source

**Classification:** EXTRACT RESPONSIBILITY; existing binding/correlation models
and endpoint delta rules remain KEEP COHESIVE.

**Files:** `repository_evidence_bindings.py`, `repository_evidence_coverage.py`,
`repository_evidence_binding_delta.py`, `evidence_correlation.py`,
`diagnostic_observation.py`, existing source/diagnostic correspondence modules.

1. Replace shared-self dependencies with Source observations and narrow indexed
   relationships. Definition identity remains separate from observed revision.
2. Construct Bindings and Correlation without Tasks, packet projection or engine.
   Keep untrusted claim validation at the existing boundary.
3. Compare explicit endpoint facts. Preserve unindexed/denied/unsupported/missing/
   stale/unknown states, complete-scope absence and non-comparable definitions.
4. Test wrong/stale/foreign paths, exact ranges, line movement, ambiguity,
   truncation, reused evidence content tampering and same-state reopen.
   External stack frames remain external observations; source correspondence
   does not become causation or execution-result authority.
5. Migrate CLI/MCP/service and qualification acquisition callers, then remove
   legacy root methods, diagnostic class aliases and duplicate member-read
   helpers. Keep pure diagnostic functions in their existing defining modules.

**Acceptance:** all domains observe the same member revision and visibility;
no bounded/no-match result produces an unqualified negative; external claims
cannot establish repository truth merely by naming a source.

### CR-08 — Preserve declaration and dependency producer boundaries

**Classification:** EXTRACT RESPONSIBILITY for the two domain compositions;
KEEP COHESIVE for declaration/dependency contracts and producer adapters.

**Files:** repository declaration discovery/derivation/delta/provider modules,
`repository_declarations.py`, dependency resolution/correlation/derivation/delta
modules, `project_graph.py`, `hashmarks/adapters/`, current validators.

1. Construct Declarations from Files/Source/Bindings and the providers selected
   for the current call. Provider names remain opaque provenance, not foreign
   keys. Remove no provider-independent evidence because another provider left.
2. Preserve exact source binding, literal/declared facts, unknown dynamic
   validation, duplicate-role ambiguity and qualified scope absence. No inferred
   A↔C, connected components, cycle winner or ontology alignment is introduced.
3. Prove `previous_observation` affects only the requested delta. Reopen the
   same state directory with different/no providers and no prior packet; old
   declarations/correspondence must not reappear.
4. Construct Dependencies from general semantic authorities and admitted
   project/import inputs. Maven/uv syntax, coordinates, scopes, module encodings
   and diagnostics terminate in adapters. Component/node identity excludes
   adapter/provenance names; one physical source may carry multiple authorities.
5. Preserve completeness vs coverage, ambiguity, physical source provenance,
   context and exact invalidation. No resolver launch or dependency implementation
   crawl is added.
6. Run genuine uv/Maven replay and native declaration/transport rings. Add
   cross-producer same-fact regression only for an actual changed boundary.
7. Migrate all callers and remove obsolete mixins/parallel producers. Publish
   actual component ownership in the normative reference.

**Acceptance:** declaration persistence/cycles/adversaries and dependency
cross-producer/coverage/scope/reopen tests pass unchanged in meaning; provider
syntax never leaks into core semantic qualification; no new global graph/state.

### CR-09 — Complete changed-path observation and bounded aggregate views

**Classification:** EXTRACT RESPONSIBILITY for Changes/CrossRepository/Economics;
REFACTOR INTERNALLY for existing stateless profile/query projections.

**Files:** `change_impact.py`, `post_change.py`, `change_intelligence.py`,
`freshness_map.py`, `repository_delta.py`, `cross_repository_evidence.py`,
`intelligence_economics.py`, `evidence_profiles.py`,
`repository_intelligence_query.py`, `worktree_overlay.py`, remaining status
composition.

1. Construct Changes from Tasks, Source, Relationships and Index. Move snapshot
   and impact reuse into its owner, keyed by exact read scope/request and current
   authority. Preserve defensive-copy behavior.
2. Keep refresh operations limited to caller-reported repository paths and
   re-observation. No patch decision, Git mutation, verification execution,
   retry/resume/progress ledger or certification behavior is added.
3. Observe/compare endpoint facts once; preserve renamed/deleted/unavailable and
   non-comparable scopes. Verification may corroborate already-admitted ownership
   through the existing relation, never replace or rerank it.
4. Construct CrossRepository from explicit identities/boundaries and endpoint
   observations. Construct Economics over current measured inputs. Keep them
   independent of consumer action/history and of any historical telemetry store.
5. Construct Views over exact named lower operations. Move aggregate status,
   profile and existing query-surface selection here without adding a universal
   registry/dispatcher. Profiles consume one snapshot and cannot recreate facts.
6. Migrate public operations and remove remaining domain caches from engine.
   Check that Changes does not call its higher Views/Economics/CrossRepository.
7. Rewrite `WorktreeOverlay` as a separate read-only composition consumer. Its
   constructor takes the base Index, Search and DecisionScope capabilities plus
   the caller-selected overlay workspace and worker identity, not a base
   CodeMap. If sharing artifact storage, pass its immutable location through
   explicit construction configuration; do not expose a mutable ArtifactStore.
   The overlay may construct/own a local CodeMap as a composition root, but it
   holds no borrowed base-root back-pointer. Capture base generation and
   fingerprint from Index under the base read scope; fused queries reject any
   base movement, including generation-only changes, before/during reading.
   Explicit overlay sync is the only way to adopt a new base. Preserve changed
   path masking, output bounds, independent local state and existing lifecycle;
   add no worktree creation, Git mutation or worker orchestration.

**Direct proof:** post-change generation/default/delta/refresh tests, snapshot
reuse/copy isolation, freshness map, cross-repository identity, economics and
profile parity; full status no-daemon/provider-unavailable/reopen behavior.
Run `tests/test_worktree_overlay.py` in full, preserving both pre-query and
mid-query drift adversaries while replacing raw store mutation hooks with a
test-owned publication mechanism.

**Acceptance:** composition is acyclic; one repository generation binds each
packet; invalid previous snapshots reject before side effects; changed paths
remain caller-owned inputs; economics report costs without controlling execution.

### CR-10 — Finish the breaking public migration and delete legacy paths

**Classification:** REFACTOR INTERNALLY at transport boundaries;
DECOMPOSE MULTIPLE RESPONSIBILITIES for the old root facade.

**Files:** `engine.py`, `codemap/__init__.py`, `hashmarks/__init__.py`,
`codemap/service.py`, `repository_cli.py`, `cli.py`, `mcp_surface.py`,
`mcp_server.py`, `operation_contract.py`, examples, benchmarks, evaluation
scripts, test fixtures/typecheck contracts and current API/getting-started docs.

1. Audit the section 6 inventory against actual definitions/callers. Migrate
   remaining public clients and tooling. Do not postpone all adapters until this
   package; each earlier owner stage already migrates its active consumers.
2. Keep `hashmarks.cli.main` the only current CLI entry and repository command
   families in `repository_cli`. No new root aliases or copied dispatch rules.
3. Keep semantic schemas/defaults in existing domain/operation owners; services
   validate hostile wire objects at ingress/egress, CLI/MCP translate errors once
   at their current boundaries. Domain methods do not raise SDK-specific errors.
4. Remove every domain mixin base from CodeMap. Delete retired root methods,
   alias imports, compatibility readers and forwarding-only modules. Retain
   useful pure domain modules rather than deleting by filename/LOC alone.
5. Give each public component property a precise type and read-only reference.
   Finish resource lifetime/failed construction/close-order behavior and package
   import laziness without a dynamic component proxy.
6. Update README, GETTING_STARTED, API_STABILITY, ARCHITECTURE, CODEMAP, semantic
   owner map, integration docs and active qualification commands/examples.
   Mark historical examples as historical instead of rewriting old receipts.

**Acceptance:** root provides construction/lifetime/components only; zero
first-party active flat API callers; zero production component imports/casts of
CodeMap; zero retired implementations; complete explicit adapter routing; real
CLI/IPC/official MCP behavior and hostile schema rejection remain correct.

### CR-11 — Prove ownership, lifecycle, locality and typing

**Classification:** validation of the completed architecture; no new runtime
governance machinery.

**Files/tests:** extend `tests/test_semantic_ownership_architecture.py` and
existing direct-owner/boundary tests. Keep guards narrow and behavior-driven.

1. Add a closed, test-only inventory of intended component import directions and
   owner state writes derived from the implemented map. Resolve concrete imports
   and injected constructor dependencies; inspect local imports/type-only paths
   and deliberate runtime delegation. Do not infer acyclicity from filenames.
   Composition roots and public adapters may import/construct CodeMap: engine,
   CLI/MCP/service and the separately owned overlay composition. That exception
   does not authorize a domain component or analyzer to receive/store the root.
2. Prove guard efficacy with positive controls: a fake root back-reference,
   wrong-owner cache write, dependency cycle, root callback and retired alias
   must be rejected by the same checks that accept real code. Source-string
   absence by itself is not sufficient.
3. Keep functional guards for stale native cache hits, read/parse interleaving,
   denied bytes, ambiguous owner/test identity and projection-bound changes.
   Architectural shape cannot substitute for those assertions.
   Exercise independently constructed components across two workspaces and
   read scopes with identical relative filenames. Qualify their input-binding
   contract: mismatched Source/store/native inputs must not blend repository
   authority. Check the supported shared-store/concurrent-reader case before
   choosing identity checks; do not introduce a global admission manager.
4. Confirm every introduced operation/stage has a direct owning test and complete
   structural locality for its declared measurement scope. Capture comparable
   pre/post complexity/dependency/query/parse observations, not a LOC-only win.
5. Run current full Ty and Pyright separately. Fix all newly exposed migration
   errors at producers, types and callers. Split unrelated remaining debt into
   exact owner-sized items; no Any blankets, unchecked casts, ignores, exclusion
   changes, severity changes or baseline relaxation.
6. Run `make agent-preflight` and `make lock-check`. Keep tool declarations and
   lock authority unchanged unless an independent defect requires authoring them.

**Acceptance:** no unassigned state writer or semantic redecision, no remaining
CodeMap domain inheritance/back-pointer/delegation, direct tests and locality
complete, no new typing debt, configured hygiene/lint/size gates pass. Full
typing must be reported honestly: an architecture candidate may have declared
unrelated debt, but it is not a clean project/release until both full gates pass.

### CR-12 — Qualify the actual rewritten candidate

**Prerequisite:** all implementation and formatting changes are complete.

1. Freeze one exact source candidate identity after normalization. Bind all
   reports to it, the evaluator identity, corpus/producer/tool identities,
   source revisions, operation inputs and observation bounds.
2. Run every deterministic product-test batch for this candidate; see section 9.
   Keep exact membership and complete outcomes. No partial batch is proof.
   Do not rerun passed batches solely because a later controller expired.
3. Run genuine dependency and semantic capture replay; acquire fresh native
   captures for the selected backend workflows and test required source changes,
   stale revisions, rebuilds, same-state reopen and official MCP transport.
4. Run the unchanged reviewed existing backend population where inputs are
   available, including metadata/sender before/after. Retain missing-input and
   unreviewed cases as INCOMPLETE. Pure regrade retained artifacts and confirm it
   does not invoke the observer; corrupt/missing artifacts must fail closed.
5. Compare parent/current/noise-control economics on identical source/tasks/
   bounds: cold, warm, incremental, rename, delete, incomplete-generation recovery,
   parser/query/read counts, packet bytes/tokens and persistence costs. Use the
   established two warmups/nine samples and same-version control. A speedup is
   optional; a material unexplained regression blocks closure until understood.
6. Build the deterministic source ZIP with all new files/modes and smoke/test
   the independently extracted artifact. Assert actual import origins and source
   identity; running repository imports under another cwd is not isolation.
7. For canonical/promotion closure, perform the independent byte-identical
   rebuild and existing isolated wheel/sdist checks. Do not invoke unrelated
   release publication, branch mutation or another repository's lifecycle.
8. Publish one bounded architecture result: what changed, tests and artifact
   identities, measured maintenance/economics gain, typing status and remaining
   broad capability gaps. Do not promote any capability from architecture alone.

**Acceptance:** complete deterministic membership passes; current selected
genuine public/native and extracted checks pass with exact authority binding;
facts/uncertainty/omissions preserved; no unresolved architecture blocker or
unexplained material regression. A scoped pass is not full twenty-capability
5/5 and must not be labeled as one.

## 9. Executable validation and recovery instructions

Commands here exist today. Run them only when implementation resumes, from the
repository root. Normal tool setup consumes the committed lock:

```bash
make init
make agent-finish
```

The starting Files ring is bounded and already has direct tests:

```bash
uv run --frozen --offline --no-sync --group test python -m pytest -q \
  tests/test_repository_files_component.py \
  tests/test_python_import_root_admission.py \
  tests/test_repository_file_admission_convergence.py \
  tests/test_context_policy.py \
  tests/test_dependency_scope_explicit_queries.py \
  tests/test_dependency_scope_persisted_convergence.py \
  tests/test_index_economics.py \
  tests/test_semantic_ownership_architecture.py
```

The foundational authority ring supplements the relevant package's direct tests:

```bash
uv run --frozen --offline --no-sync --group test python -m pytest -q \
  tests/test_codemap_source_revision_binding.py \
  tests/test_source_read_owner_contract.py \
  tests/test_codemap_relationship_cache.py \
  tests/test_codemap_publication_authority.py \
  tests/test_codemap_enrichment_publication_authority.py \
  tests/test_codemap_state_binding.py \
  tests/test_decision_freshness_scope.py \
  tests/test_decision_freshness_convergence.py \
  tests/test_decision_session_diagnostics.py \
  tests/test_index_watch_lifecycle.py
```

Use the existing owning tests named in each package plus actual callers from
CR-00; these two rings are not the complete final suite. Add new component tests
beside the relevant direct tests, with independent construction and adversaries.
Run real local-socket/official MCP tests on an environment that supports those
capabilities; constrained-host diagnostics cannot stand in for those checks.

Run both full type checkers separately so failure of the first does not prevent
the second inventory:

```bash
make ty-check
make pyright-check
```

For final deterministic coverage, defaults are 64 selected shards and four
shards per batch. Freeze membership before running; if defaults change, derive
the batch count from the actual plan rather than assuming sixteen:

```bash
make test-shard-plan
make dev-check-batch DEV_BATCH=0
```

Run batches 1 through 15 for the default selection, recording each complete
batch. Reproduce a single failed shard and resume after a proven batch:

```bash
make test-shard TEST_SHARD=7
make dev-check-tests DEV_BATCH_START=2
```

The numbers above illustrate resume/reproduction only; use the recorded failing
shard and next unproven batch. Statically process-sensitive/expensive nodes keep
their singleton `isolated_process` membership. The external execution layer
chooses process scheduling, further subdivision, timeouts and retries. Do not
add a Hashmarks resume runner or execution ledger to perform this plan.

```bash
make dependency-dogfood
make semantic-evidence-dogfood
make semantic-evidence-live
make compile
make agent-preflight
make lock-check
```

Fresh native runs require installed native producers/prerequisites. The current
backend acquisition commands are documented in
[the backend remaining plan](../qualification/BACKEND_E2E_REMAINING_PLAN.md#commands-and-handoff).
Use their current `--help` and exact manifest source maps; do not invent source
locations or launch enormous acquisition runs while implementing one component.

Recovery rules:

- Stop a failing package at its last coherent checkpoint. Preserve the failure,
  candidate identity and exact input; repair within that owner. Do not restart
  the whole architecture or erase previously frozen receipts.
- If a patch must be abandoned, restore only that package's known files from
  its frozen parent after preserving the current diff. Never reset the user's
  whole worktree. Git mutation is an external developer action, not product code.
- An interrupted validation is INCOMPLETE for that batch. Resume the next
  unproven work on the same candidate. After source changes, use dependency/scope
  evidence to decide what earlier proof remains applicable; never relabel an old
  report with a new producer identity.
- Missing tools, corpus sources or transport support block only the proof that
  needs them. Finish independent work and list missing evidence precisely.
- Keep failed oracle expectations. An oracle correction requires independent
  source evidence and preserved old/new identities, never the candidate's chosen
  answer as justification.

## 10. Resume the actual 5/5 work after architecture acceptance

The authoritative development evaluator remains
`scripts/repository_evaluation/backend_matrix.py` and the active campaign
manifest. They are development measurement, never production policy. The
existing research detail remains in
[BACKEND_E2E_REMAINING_PLAN.md](../qualification/BACKEND_E2E_REMAINING_PLAN.md).

The retained population is 89 entries / 59 distinct genuine problems / eight
suites. Independent capability review remains outstanding; no capability is
established at 5/5. Recompute these facts at Q-00 rather than treating the counts
as permanent constants.

### Q-00 — Rebind campaign and evaluators to the rewritten observer

Freeze the architecture candidate, evaluator, manifests and exact source maps.
Update evaluator **API calls** to components while preserving task inputs,
source oracles, required witness identities, gates, review flags, thresholds and
distinct-problem accounting. Pure regrading and negative controls must prove
the evaluator still detects wrong, missing, stale and truncated evidence.

### Q-01 — Complete genuine corpus membership

Seven whole catalogs remain: **8 handlers, 9 producer/consumer data, 11 DI/config,
15 dependency/build, 16 cross-service, 18 additional native evidence, and
20 economics**. Debugging has four problems from one repository and still needs
eight genuine problems across two additional repositories. Existing catalogs
also need their remaining qualification, not just source intake.

Use the admitted repository pools in the research plan. Pin actual before/after
revisions and archives, preserve problem identity and write answer-blind tasks.
Each capability needs at least twelve distinct genuine problems across at least
three repositories under the current matrix. Reused problems/formats/variants
add no distinct breadth. A new tag needs its own supported semantic oracle.
Reserve unseen heldouts before product tuning; do not inspect reserved sources
while developing the generic repair.

### Q-02 — Review independent oracles and close witnesses

Independently review exact owner/symbol/range/revision facts, existing relevant
tests, metric eligibility, missing-edge/unknown expectations, display facts and
capability-specific adversaries. Freeze their identities before acquisition.
Do not set `reviewed: true` because the candidate passes its evaluator.

Close required witness membership with artifact-bound source facts and exact
capture/revision identities. Required missing, excluded, malformed or truncated
members remain explicit. A zero-error average cannot compensate for any hard
authority or freshness violation.

### Q-03 — Run the full genuine public/native population and repair generic defects

Acquire both revisions through Python/CLI/official MCP/default/initial/required
formats, plus actual fresh native producers where required. Include edit,
stale/rebuild/reopen, tampering and wrong-source adversaries. Retain all failures.
Run the existing pure graders over retained artifacts independently of observer
execution. Missing actual native captures cannot be replaced by replay claims.

Repair only reproduced observer defects at the canonical owner and preserve a
minimal neutral regression. Do not chase imported dependency implementations,
hard-code repository names, leak oracle hints, remove rare/ambiguous cases or
weaken a bound. Qualified absence and missing links must stay visible.

### Q-04 — Close typing, economics, heldouts and exact artifacts

Finish both unchanged full type gates, all deterministic test membership,
comparable cold/warm/incremental/rename/delete/recovery economics with same-version
noise controls, exact four-repository owner heldouts and reserved unseen backend
heldouts. Exposed-and-repaired heldouts need unseen replacements before claiming
independence. Produce current exact-source and independent wheel/sdist proof.
Do not compare artifacts across different observer/evaluator/source/bounds without
an explicit comparability basis.

### Q-05 — Admit the twenty-capability result honestly

Every capability must meet its own reviewed population and required gates on
the same qualified candidate. Preserve current targets: owner top-three recall
at least 95%, debugging correspondence and initial-evidence recall at least 90%
on eligible reviewed populations, no false exact/unique authority, complete
adversarial freshness detection, required presentation parity and the 4,000-token
initial ceiling. Required native/language/economics gates must have actual proof.

The evaluator must report twenty qualified rows with no required failure or
incomplete member. Full configured project checks and exact-artifact proof must
also be clean before the overall clean-pass claim. If any requirement remains,
publish the exact remaining gap and keep the overall result INCOMPLETE or FAIL.
No architecture result, test count or selected workflow pass substitutes for it.

## 11. Handoff and definition of done

The initial entry point was **CR-00, then CR-01**. On resumption, use the
implementation checkpoint above and continue the first unfinished package.
Preserve the existing components and repaired parent. Do not resume by rewriting
engine.py wholesale, installing new tools, editing the campaign grader or adding
more backend syntax.

An implementation handoff must state:

- the last coherent completed package and exact source identity;
- actual component/API/state moves and obsolete paths removed;
- focused, integrated, transport, typing and extracted-artifact results with
  their scope and remaining uncertainty;
- the next unfinished package, prerequisites and exact known blocker;
- whether architecture completion, clean project validation, and twenty-capability
  5/5 completion have each been established separately.

Architecture completion requires real independent owners, explicit one-way
dependencies, complete caller migration and removal, preserved evidence behavior,
qualified cache/read semantics and current measured proof. Backend 5/5 still
requires the genuine corpora, independent oracles, witnesses and final broad
qualification. These remain two observable finish lines.
