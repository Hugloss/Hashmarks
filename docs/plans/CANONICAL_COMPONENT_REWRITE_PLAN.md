# Canonical component rewrite: stabilization delivery and later 5/5 research

**Active completion target: architecture stabilization and a trustworthy backend
baseline, approved by the user on 2026-10-18.** Follow
[`STABILIZATION_PLAN.md`](STABILIZATION_PLAN.md), S1–S6, for the finite remaining
delivery checklist. Exhaustive corpora, per-private-stage proof, broad economics,
unseen heldouts and all twenty capability rows reaching 5/5 are a separate,
nonblocking research backlog. Their evaluator requirements and incomplete
ratings remain unchanged; this milestone does not claim backend 5/5.

The stabilization plan supersedes the older completion/acceptance language and
"next work" lists below. Retain those as implementation/design history and the
future qualification specification. Do not start new corpora, syntax or another
architecture rewrite to finish stabilization.

**Latest budget clarification:** the user explicitly made 6,000 tokens an
advisory optimization target. Stabilization must report actual complete reply
sizes, but a size-only failure does not block completion or trigger another
compression cycle. Correctness, provenance, freshness and evidence preservation
remain hard requirements. Retained backend evaluator results keep their original
budget policy and identity; do not manufacture a 5/5 pass from this scope change.

This implementation was prepared against the modified
worktree on 2026-10-17, based on HEAD
`4dc2527f6a2391a01063617b593830b638a44550`. This is the current implementation
handoff and supersedes the bounded
[canonical-owner consolidation plan](CANONICAL_OWNER_CONSOLIDATION_PLAN.md).
The user authorizes breaking public Python APIs and removing compatibility
paths. Implementation resumed from the current dirty worktree. Observer,
authority, freshness and provenance boundaries remain mandatory.

**User-authorized acceptance update — 2026-10-18:** the final initial-response
ceiling is now **6,000 tokens**. The user explicitly accepted this budget while
requiring all other issues and qualification requirements to be fixed. This
supersedes the earlier temporary 5,000-token working budget and 4,000-token final
ceiling. `backend_matrix.INITIAL_TOKEN_CEILING` remains the single executable
qualification owner. Existing 4,000-token measurements and failures retain their
original observer/evaluator identities; they are historical results, not passes
under the new policy. The later twenty-capability qualification retains its
population/oracle/metric requirements. The subsequently approved stabilization
scope above changes which deliverables block the current milestone.

## Implementation checkpoint — 2026-10-17

Current position, updated 2026-10-18: all **23 canonical component owners**
are implemented. `CodeMap` composes them and owns resource lifetime; domain
operations and caches belong to named components. Current full configured Ty
and Pyright checks pass. The latest independently extracted verification,
retrieval and presentation ring passes **296 tests**; all **287 unchanged
predecessor tests** also pass against the complete CR-43 production tree, with
zero skips or exclusions. Its five genuine configuration workflows pass their
admitted common gates, with **540/540** required witnesses and maximum initial
reply **5,748 tokens**. The original metadata/sender workflows also pass all
admitted gates, including initial evidence and size, on this same CR-43 candidate.
The earlier path-role candidate
passed 193 affected tests and all 182 unchanged original affected tests. The full CR-25
membership passed 4,856 pytest cases over 64 shards, with zero skips; that full
result remains bound to CR-25 rather than the later repairs.
All **twelve configuration workflows** over three repositories pass every
admitted common API/CLI/official MCP gate on CR-41, with **1,698/1,698** required
source witnesses and **468/468** selected initial facts, max **5,333 tokens**.
That evidence remains bound to CR-41; later test disclosure requires CR-43 proof.
The handler
suite pins twelve source-reviewed genuine workflows over three repositories.
Retained selected API/CLI/official MCP replays close AsyncAPI and registration
verification disclosure. Current Iterable acquisition now retains the nominated
test on both revisions, preserves source facts through native transports, and
passes the 4,000-token compact/text bound. Matched current economics reduce warm
full-plus-initial observation cost by about 23% against CR-30 while preserving
every admitted fact; broad cold/churn economics remain open. The late-keyword source disclosure repair remains qualified
on its earlier candidate. Direct public-operation review now covers all 95
listed behaviors, with extracted execution for their 143 named test functions
on the retained CR-17 candidate. Internal-stage and baseline correspondence
remain open. The configuration suite now admits twelve source-authored workflows;
broader semantic/capability review remains pending. Earlier
reports retain their original identities. Architecture
acceptance remains open for complete operation/direct-
test/baseline correspondence and locality qualification (CR-11), followed by
current full membership, comparable economics and final artifacts (CR-12).
The twenty-capability backend 5/5 result is not established. Earlier checkpoint
numbers below are historical evidence, not the current typing status.

Project checkpoint: CR-46 fixes duplicate package-name publication while retaining
ambiguity; its exact extraction passes **234** affected tests and all **230**
unchanged predecessor tests, zero skips/exclusions. Full typing and hygiene pass.
CR-44 separately preserves distinct explicit project-provenance links; CR-45
strengthens the benchmark so perfect project/depth scores cannot hide wrong
relationships. The **complete CR-43 twelve-workflow** configuration acquisition
now passes all admitted common gates, **1,698/1,698** source witnesses and all
**540/540** selected task/test witnesses, maximum **5,748 tokens**. Those public
results remain bound to CR-43 and are not relabeled as CR-46 qualification.

Latest checkpoint: CR-48 repairs read-scope diagnostic failure cleanup and binds
fourteen lifecycle/freshness stages to reviewed owning-test evidence; 158
extracted and 155 unchanged predecessor tests pass, with full typing/hygiene
clean. CR-49 adds the missing data-boundary source intake: twelve genuine
nominations over three repositories and twenty-four trees, with 53 exact
declarations/809 source sites checked. Its 59 extracted grader/gate tests pass;
pair semantics, executable workflows and capability review remain INCOMPLETE
on that checkpoint. CR-50 now admits all twelve data source workflows with
143 exact physical-line facts and 24 direct call/argument observations, authored
before capture. All twenty-four source trees and actual changed-file transitions
pass admission; 1,289 oracle mutations are rejected. CR-51 independently proves
fourteen primitive read/cache stages with a 52-test ring. CR-52 repairs a genuine
6,285-token MCP compact overflow by losslessly factoring repeated source
qualifiers: 297 extracted affected tests pass, and the reproduced Iterable
workflow passes all admitted public gates and 324 required witnesses at a
5,923-token maximum. All twelve data source workflows now pass admitted common
gates and all 3,873 required source/call witnesses on CR-52. CR-53 additionally closes a reproduced test-declaration
disclosure omission with 204 extracted/203 unchanged predecessor tests and
fresh keyed-null public proof: all 354 source/call and 18 new after-test
witnesses pass, max 5,173 tokens. These are separately identified candidates.
Pair semantics, broader relevant-test review,
metric eligibility and capability review remain unqualified; the campaign is
unchanged.

Current stabilization completion work:

| Work | What still needs proof |
| --- | --- |
| S1 ownership | Current existing component/input-binding/lifecycle/architecture contract tests pass; canonical owners and retired APIs remain correct. Exhaustive private-stage/native-locality audit is deferred. |
| S2 quality | Full configured typing, preflight, lock convergence and source compilation pass on the final source. |
| S3 regression | Complete every named deterministic batch on the final extraction, retaining exact membership and no unresolved selected-test failure. |
| S4 representative public proof | Exactly the Iterable, renamed DTOData and keyed-null workflows pass required fact/authority/freshness/public-surface gates and witness accounting on the final extraction. Actual reply sizes are reported; 6,000 tokens is advisory. |
| S5 artifact | One deterministic source ZIP and independent extraction with correct import/producer identity and zero qualified-input drift. |
| S6 handoff | Current stabilization report identifies proof and limitations; broad twenty-capability qualification remains INCOMPLETE and nonblocking. |

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

CR-07's production boundaries are implemented and qualified on the retained
candidate:

- `RepositoryBindings` owns observation, endpoint comparison and coverage over
  Source; `RepositoryCorrelation` borrows Source and Bindings. Neither constructs
  Tasks or calls CodeMap. Flat root methods are removed and current consumers,
  transports and public documentation use the named components.
- Pure retained-binding validation lives in
  `repository_evidence_binding_validation.py`; pure correlation values and packet
  integrity live in `evidence_correlation_model.py` and
  `evidence_correlation_replay.py`. Diagnostics reuse those checks without
  inheriting a live observing service. No repository or external-claim authority
  changed.
- The focused binding/correlation/adversarial/operation ring passed **306 tests**.
  The unchanged integration membership plus independent component tests passed
  **726 tests**. Independent source extraction passed **258 tests**, including
  CLI/MCP, tampering, generation, coverage, topology and multiplicity cases.
  New direct-component cases prove unindexed revision sharing, unchanged span
  identity across another-line edits, stale source-equivalence rejection,
  same-name ambiguity and import independence from Tasks/CodeMap.
- Source compileall, preflight and scoped F401/F821 pass. Changed owner and new
  component-test scoped Ty/Pyright checks pass. Full project checkpoints remain
  red: **1,968 Ty diagnostics / 1,925 Pyright errors and one warning**.
- Candidate `cr07-qualified/source.zip`, SHA-256
  `f3a37b7c0bd2cc704b07de675e6d9899f66f81d239e2c8a72534db24bb866735`,
  binds observer
  `sha256:d42f07f04fa55fbc9fb65c85c56a9f7f57d48ea9cf23a62fa51a74404ab3643e`.
  `cr07-public-workflows/summary.json` and
  `cr07-native-workflows/summary.json` bind that same observer. Metadata/sender
  pass all ten gates each in each ring, including unchanged initial-size and
  evidence gates; native captures were regenerated in this invocation. Aggregate
  qualification remains INCOMPLETE because these are two selected workflows.

CR-08's production boundaries are implemented and qualified:

- `RepositoryDeclarations` borrows Bindings and derives its Source, Files and
  read scope from the same owner. Existing discovery/derivation implementations
  belong to it. `RepositoryDependencies` composes the existing internal
  observation/correlation/derivation/comparison implementations over explicit
  Source, Imports and repository Correlation. It lives in
  `repository_dependencies.py` to keep their existing import dependencies
  acyclic. Neither component calls CodeMap or Tasks. Flat root methods are
  removed; production, transport, qualification and documented callers migrated.
- **370 existing contract tests**, **8 direct-component tests**, **734 integration
  tests**, **15 genuine uv/Maven replay tests**, and the **96-test semantic
  evidence dogfood ring** pass. Existing provider-removal, same-state reopen,
  correspondence cycles and cross-producer endpoint tests retain their meaning.
  Direct cases additionally prove source-revision sharing, comparison-only
  previous input, format-neutral semantic identity and import independence.
- `cr08-qualified/source.zip`, SHA-256
  `41591fdd311d1dccbbede2793b4f4dc8bb07565875670ad2fb52ee4d5f23bad4`,
  passed **545 tests** from independent extraction. The one Git-index-only node
  was excluded only there after passing in the real-worktree integration ring.
  The initial Gitless run remains retained as a failed environmental probe.
  Source compileall, preflight, scoped F401/F821 and owner/new-test Ty/Pyright
  checks pass. Full typing remains red: **1,966 Ty diagnostics / 1,923 Pyright
  errors and one warning**.
- Public workflows and fresh native acquisition ran from that independent
  extraction, binding observer
  `sha256:b67c45ea16120b3caf321a6d85204154d53558f267319e13db54253b3ea03319`.
  Metadata/sender pass all ten gates each in each ring, including the unchanged
  initial-size/evidence checks. Reports are
  `cr08-public-workflows/summary.json` and `cr08-native-workflows/summary.json`;
  aggregate status is INCOMPLETE for the selected two-workflow scope.

CR-09's production boundaries are implemented and qualified:

- `RepositoryChanges` owns the existing change, refresh, snapshot, delta and
  freshness implementations, including scope-bound snapshot/impact reuse.
  `RepositoryCrossRepository`, `RepositoryEconomics` and `RepositoryViews`
  borrow explicit lower owners. The shared `EvidenceProfileProjection` consumes
  supplied values without live repository services. `CodeMap` now inherits no
  domain implementation; the obsolete `query_surface.py` is removed.
- Index owns `derived_graph`, index-only `status`, publication binding and the
  immutable artifact database location. Views composes full status through those
  lower facts and the existing native/watch qualifiers. `WorktreeOverlay` takes
  base Index/Search/DecisionScope plus explicit artifact-location configuration;
  it stores no borrowed base CodeMap and rejects sync/read generation or
  fingerprint drift. Existing generation adversaries remain, with test-owned
  publication and new independent-base/fingerprint adversaries.
- Five new deterministic reproductions exposed mixed-generation composition in
  brief, freshness, snapshot, cross-repository and comparison-economics packets.
  They failed before repair and now pass: composition binds the first qualified
  input generation. Cached snapshot return rechecks that binding. A separate
  failing measurement showed two current snapshot captures in one economics
  comparison; endpoint comparison now consumes the already-observed value, with
  one capture proven after repair. Invalid prior economics input is checked
  before current observation. No retry, executor or alternative generation owner
  was introduced.
- Pure diagnostic class aliases were removed; callers import defining functions.
  The planned verification name exposed two distinct contracts: elementary
  `verification.relationship_evidence` and graph composition
  `verification.ownership_relationships`. Both remain under Verification; no
  graph result replaced the elementary signature.
- **752 integration tests** and **423 focused change/diagnostic/aggregate/overlay
  tests** pass. Independent extraction passed **1,148 tests**, including genuine
  dependency and semantic replay. One Git-index-only node was deselected only
  in the Gitless extraction after passing in the real-worktree ring. Scoped
  owner/new-test Ty and Pyright, F401/F821, source compileall and preflight pass.
  Full typing remains red: **1,966 Ty diagnostics / 1,922 Pyright errors and one
  warning**.
- `cr09-qualified/source.zip`, SHA-256
  `1fa744e12af65b319374694b2b07a7a9e799aa15bf0fd13b16864842037f84a8`,
  binds observer
  `sha256:1a0df149f3a9df3b29507299b2048e7ecd38173bc84a0bc3cbc92d3baa322963`.
  Public and freshly regenerated native metadata/sender workflows ran from this
  extraction and pass all ten gates each in each ring, with unchanged initial
  evidence/size targets. Reports `cr09-public-workflows/summary.json` and
  `cr09-native-workflows/summary.json` remain INCOMPLETE for selected scope.

CR-10 progress — 2026-10-18:

- Four additional lifecycle reproductions failed before repair: leaked open
  resources after component-constructor failure or workspace-binding rejection,
  repeated cleanup on repeated close, and cleanup stopping when one resource
  raised. The construction root now registers resources immediately in an
  `ExitStack` and transfers it only after successful component composition.
  All four cases pass, including cleanup after a close error. Component wiring
  and resource acquisition are separate private construction stages; no domain
  method or root back-pointer was added.
- Root/state/concurrent-publication/service/native/diagnostic qualification
  passed **126 tests** in the worktree and **126 tests** from independent source
  extraction. Scoped Root/lifecycle-test Ty and Pyright and preflight pass.
  Candidate `cr10-resource-qualified/source.zip`, SHA-256
  `e01ca151b48fad727770ee2dc546a99b8520af1e4958ee79dfc749ce36a27e09`,
  binds observer
  `sha256:a610339536e70fdfdfb22179b7d933944738bc7f551792d4ba631bc19fcb7b40`.
  CR-09's genuine reports remain evidence for their earlier exact observer;
  they are not reattributed to this subsequent lifecycle candidate.
- A read-only audit covering the **98** original public operations/class values
  reports zero retired root callers for its constructor/type-derived receiver
  scope. One class-level diagnostic freshness caller found by the full typing
  inventory was migrated to Changes. The audit is not proof that arbitrary
  dynamic or unindexed receivers are resolved. Effective guard positive controls,
  full caller/adapter closure, mixed-input qualification and locality still need
  CR-11 work. Current architecture/navigation/API docs describe the named owners.

CR-11 progress — 2026-10-18:

- A closed, test-only inventory now checks **23 component constructor graphs**,
  resolved component import directions, reserved cache writers, root properties
  and root construction callbacks. Positive controls use the same checks to
  reject an aliased/type-only root back-reference, direct/container foreign cache
  writes, a dependency cycle, whole-root/bound/lambda callbacks and retired root
  aliases. These checks are scoped architectural evidence, not an arbitrary
  Python security proof. No production registry or governance state was added.
- Eleven previously accepted mixed-owner constructions failed the new expected
  rejection tests. Redundant Index/store/Source arguments were removed from
  DecisionScope, Source, Imports, Native, Search, Verification, Correlation and
  Relationships. Remaining multi-owner compositions reject different read scopes.
  Store binding still belongs to the existing store owner. Two different
  workspaces with identical relative filenames remain distinct; independent
  readers of the same durable store still work. The binding/architecture ring
  passes **28 tests**.
- All **147 production Ty diagnostics** from the prior checkpoint were repaired.
  Both `ty check hashmarks` and `pyright hashmarks` now report **zero errors and
  warnings**. Repairs narrow checked codec/adapter values, type existing domain
  validation results, preserve completed nullable cache values, describe native
  SDK metadata without unchecked casts, and pass exact lower owners into import
  identity/diagnostic helpers. Optional SDK construction remains lazy. The stale
  watcher test copying the entire dependency extras declaration was removed under
  the explicit AGENTS.md prohibition on duplicate configuration/version-policy
  assertions; executable watcher/SDK behavior tests remain.
- Production clean typing is **not full-project clean typing**. Current full
  commands remain red: **1,795 Ty diagnostics / 1,731 Pyright errors, zero
  warnings**, in `cr11-full-ty-current.log` and
  `cr11-full-pyright-current.log`. Test/evaluation-script debt must be repaired
  without blanket Any, ignores, exclusions or severity changes.
- **786 integration tests**, **275 native/protocol tests**, **138 selection and
  conformance tests**, and **155 identity/metadata/relationship/watcher tests**
  pass in their bounded rings. The exact candidate passed **1,177 tests** from
  independent extraction; the one Git-index-only node was excluded only in the
  Gitless artifact after real-worktree proof. Preflight, source compileall and
  committed-lock convergence pass.
- Candidate `cr11-typed-production/source.zip`, SHA-256
  `034eb85811ffd1dda2607cde68dd713c76393f9fec34a7b254fc47379e8b7a9f`,
  binds observer
  `sha256:8377db1c3c0951d13f45b8535740bc8caa08ce2cd89846a2d202c4b66cfc6d66`.
  Public and freshly acquired native metadata/sender workflows ran from that
  extraction and pass all ten gates each in each ring. Reports
  `cr11-public-workflows/summary.json` and `cr11-native-workflows/summary.json`
  remain INCOMPLETE for selected scope. The broader twenty-capability corpus,
  independent oracle review, witnesses, heldouts and final qualification remain.

CR-11 test/evaluation typing follow-up — 2026-10-18:

- Corpus timing retains the callable's actual result type. Corpus task metrics
  and suite/protocol results now describe their existing fields with precise
  TypedDicts; numeric summaries retain numeric value types. The suite imports its
  sibling through the canonical `scripts` module path rather than an unresolved
  direct-execution fallback. No benchmark scores, task membership, expected
  owners or acceptance thresholds changed.
- Diagnostic member-evidence assertions now check open JSON object/array/scalar
  shapes before access or intentional tampering. The fixture exposes typed
  source options and keeps deliberately malformed booleans at the JSON ingress.
  Original provenance, stale/foreign evidence, completeness and tampering
  assertions remain. No unchecked casts or checker suppressions were added.
- The two evaluation owners and diagnostic member-evidence test pass both
  scoped typecheckers. **117 behavioral tests** pass across the metrics suite,
  member-evidence and source-revision tests. Production bytes are unchanged from
  observer `8377db1c...`; that candidate's earlier production and genuine-workflow
  proof is not a claim about the full later test/evaluation tree.
- Full commands remain red at **1,698 Ty diagnostics / 1,645 Pyright errors,
  zero warnings**, recorded in `cr11-full-ty-owner-checkpoint.log` and
  `cr11-full-pyright-owner-checkpoint.log`. Continue owner-sized repairs; the
  larger test/script and final qualification scopes are still incomplete.

CR-11 checked assertions and embedded caller repair — 2026-10-18:

- Fifteen test owners now retain checked JSON object, array and scalar shapes
  through assertions and deliberate tampering. The concurrent-publication
  fixtures forward the actual Index/store parameter and result types rather
  than erasing them to `object`. Existing source, ambiguity, negative-evidence,
  declaration-identity, dependency-coverage and projection assertions remain.
  The MCP tests share one fake SDK module installation while retaining their
  tool catalog, error translation, lazy construction and native SDK checks.
- Interchange validators now accept `object` at their public untrusted-input
  boundary and immediately use the existing checked mapping admission. This
  corrects the annotations to match their already tested fail-closed behavior;
  it does not relax a schema, field check, authority rule or failure condition.
  No unchecked casts, Any blankets, checker suppressions or tool-policy changes
  were added. The production observer is now
  `sha256:6b4e99d22cb962e91f5494a92bf10e0ef5596d095a8c4289604d407887aae965`;
  earlier observer `8377db1c...` workflow proof remains bound to that earlier code.
- Real subprocess runs reproduced two missed migration callers in
  `full_edit_verify_benchmark.py` and `internal_agent_ledger.py`: both raised
  `AttributeError` at the removed `CodeMap.sync`. They now use `index.sync` and
  `tasks.decision_packet`/`tasks.decision_brief`. Three new real subprocess
  smoke cases cover those paths; the existing controlled execution remains
  evaluation-only. Ten tests pass across these two callers.
- The caller audit now also inspects literal Python payloads. Its current
  five parsed payloads contain no retired root calls. All 24 non-Python strings
  were inspected as docstrings, and all 14 interpolated candidates are diagnostic
  messages, not executable code. This extends the declared audit scope; it is
  not proof of arbitrary dynamic execution or a replacement for transport tests.
- Current worktree proof: 79 diagnostic/comparison tests, 33 MCP tests,
  108 adapter/changed-line/qualification/malformed-root tests, 19 authority and
  concurrent-publication tests, 33 ordinary metric tests and six metric tests
  each run in its own process pass. The validator/conformance ring also passes
  103 tests, with overlap in the preceding rings. Each repaired owner passes
  both scoped checkers; full production typing remains clean. Source compile,
  preflight, lock convergence and diff hygiene pass.
- Full configured project gates are still red: **1,275 Ty diagnostics /
  1,244 Pyright errors, zero warnings**, in `cr11-full-ty-followup.log` and
  `cr11-full-pyright-followup.log`. These improve the preceding 1,698/1,645
  inventories but do not establish a clean project or 5/5. Complete locality,
  current full deterministic membership, broader corpora, independent oracle
  reviews, witnesses and final qualification remain required.
- The frozen source checkpoint is `cr11-typing-followup/source.zip`, SHA-256
  `3acf00f8f2fc18887d2f87585a91f5e5a893fcc1ce02243689b03abfe45d0734`,
  source identity
  `sha256:25cfab90e00de433bf6ef62d7f738ca7438f5252cd8b8075602d3ddb8d4ad86e`.
  Independent extraction `/tmp/hashmarks-cr11-typing-followup-uafdf7jb` verifies
  its import origin and current `6b4e99d2...` observer. **316 tests pass** from
  that extraction; six marked metric cases are excluded from the combined
  process and have separate passing worktree process reports. The source
  archive predates this artifact-result prose only.
- Public and freshly regenerated native metadata/sender workflows ran from
  that extraction. All ten gates pass for each selected workflow in each ring,
  bound to the same `6b4e99d2...` observer. Reports
  `cr11-followup-public/summary.json` and `cr11-followup-native/summary.json`
  remain **INCOMPLETE** for their deliberately selected population. These
  current results do not establish broader corpus, review, witness or 5/5 closure.

CR-11 typed evaluation follow-up — 2026-10-18:

- Trace, retrieval-regret and regret-suite owners now expose the validated input
  and report shapes with typed dictionaries. Existing raising validators also
  narrow their accepted values; no unchecked cast or checker suppression is
  needed. Unknown metadata remains opaque, missing discovery costs remain
  `None`, and incomplete required evidence still prevents comparison. Imports
  use the canonical module path. Suite helpers receive report values rather
  than an untyped module dependency.
- All six modified script/test owners pass both scoped type checkers. Their
  **22 behavioral tests** pass in the worktree and independent extraction.
  The actual three module CLI commands also pass and match their API results.
  On controlled complete/incomplete inputs, independently imported pre/post
  artifacts produce byte-identical loaded evidence, traces, comparisons and
  suite reports, including unknown metadata. Retained proof is
  `cr11-evaluation-preservation/comparison.json`; this is preservation evidence,
  not genuine-corpus breadth or independent oracle review.
- Exact checkpoint `cr11-typed-evaluation/source.zip` has SHA-256
  `79e65ace900b457693bab9e839e0d9768d0c15aaf36abacfc24d9b97f879fc7f`,
  source identity
  `sha256:97289937550eab1ecba55b64bec75bf0158937aaaff957cd6c3441819e66e961`,
  extraction `/tmp/hashmarks-cr11-typed-evaluation-tl5woh7p`. The archive
  predates this result prose only. Production and the backend evaluator remain
  unchanged from the preceding `6b4e99d2...` observer qualification.
- Current full gates remain red at **1,196 Ty diagnostics / 1,192 Pyright
  errors, zero warnings**, recorded in `cr11-full-ty-evaluation.log` and
  `cr11-full-pyright-evaluation.log`. Continue the remaining script/test owners,
  locality closure and full deterministic qualification. No whole-project or
  twenty-capability 5/5 claim is established by this checkpoint.

CR-11 component diagnostics and owner typing follow-up — 2026-10-18:

- Experiment manifests/reports and experiment-set aggregation now retain their
  validated types through direct imports of the existing defining functions.
  Extra metadata stays opaque, and the existing digest, subject, pairing,
  repeated-run and breadth checks remain. A malformed replication-policy root
  now fails explicitly, and a report missing its claimed eligible reduction
  cannot increment the aggregate. Six new malformed/unknown cases pass.
- Ownership, cache, provenance, configuration, native presentation, SCIP,
  persistence and acceptance tests now retain known producer types or check open
  JSON fields before access. Existing ambiguity, stale-evidence, source denial,
  missing-edge, capture-identity and previous-packet non-replay assertions remain.
  Native capture replay passed 96 tests before the later diagnostic owner fix;
  current-candidate native qualification is still required below.
- A reproduced fixture defect affected five worktree-cache setups: annotations
  in place of `setenv` calls meant they did not isolate their shared cache.
  Real calls now bind both supported platform cache variables. The snapshot
  test proves the persisted artifact lies inside the declared test cache. The
  empty parser fixture implements the actual structural producer protocol.
- A reproduced observer defect merged Source and Bindings `observe` diagnostics
  into one producer. ReadScope now qualifies operation labels with the concrete
  component's module/class identity. Same-owner repeated requests still count
  as duplicates. A separate reproduced defect marked an exactly full span
  buffer truncated; the flag now compares actual observed and retained counts.
  Boundary controls cover below, at and above the advertised limit.
  These changes concern runtime diagnostics only and add no repository,
  execution, certification or telemetry-retention authority.
- The affected diagnostics/read-scope/input-binding/worktree ring passes
  **37 tests**. Whole production typing and all nineteen affected owners pass
  scoped Ty/Pyright. Full project validation remains red at
  **901 Ty diagnostics / 902 Pyright errors, zero warnings**, recorded in
  `cr11-full-ty-owner-diagnostics.log` and
  `cr11-full-pyright-owner-diagnostics.log`. The previous `6b4e99d2...` observer
  qualification is historical after this diagnostic production change.
- Frozen checkpoint `cr11-owner-diagnostics/source.zip` has SHA-256
  `4c43e2913392b55f1516ac87d630ca981dd31d382e353821b7541b40ffaa5d68`,
  source identity
  `sha256:13b555170bbb63061a6461412416b7c5641df90904c417df14ed2eef7d2d6716`.
  Independent extraction `/tmp/hashmarks-cr11-owner-diagnostics-lw_fvp0n`
  verifies its import origin and observer
  `sha256:dd1291363cccf5e034e8619f685c5c2c5c839912ab7227ee94e7b160c80da342`.
  **314 tests pass** from this extraction, including the affected owners,
  architecture/lifecycle controls and the complete native capture replay ring.
- The independently imported previous/current artifacts produce byte-identical
  experiment and aggregate reports on the retained ordinary/replicated valid
  inputs, including strict raw-evidence binding and opaque metadata. Proof is
  `cr11-experiment-preservation/comparison.json`. This establishes controlled
  preservation, not independent real-world oracle review or corpus breadth.
- Public and freshly regenerated native metadata/sender workflows ran from
  that exact extraction. All ten gates pass for each selected workflow in each
  ring. Reports `cr11-owner-diagnostics-public/summary.json` and
  `cr11-owner-diagnostics-native/summary.json` remain **INCOMPLETE** for selected
  scope. The archive predates this artifact-result prose only. Full-project
  typing, complete locality, deterministic membership and Q-00–Q-05
  corpus/oracle/witness work remain. This is not architecture or 5/5 completion.

CR-11 output collectors and checked boundary assertions — 2026-10-18:

- Twenty affected owners now pass scoped Ty/Pyright without unchecked casts,
  new ignores, Any blankets or relaxed tooling. Source-boundary tests check
  actual returned objects/arrays. MCP tests check native result/text variants
  and use the existing SDK resource owner to close servers. Known producer
  defaults, read-only annotations, response parity and negative controls remain.
- Existing evaluator runners had a reproduced timeout defect: partial stdout
  and stderr could be bytes and then fail during concatenation or persistence.
  Both existing runner paths now translate partial output to UTF-8 text and
  persist exactly the bytes covered by their reported identities. Six cases
  cover byte, text and missing output. Boolean/malformed usage counters remain
  unknown; valid zero and known counters remain distinct from unavailable totals.
  Seven counter cases pass. These repairs stay in evaluation infrastructure and
  add no execution responsibility to the Hashmarks product.
- File-cost, observation and collector results now retain their numeric and
  structured fields. The existing benchmark selection, fusion, role resolution,
  score calculations and corpus/oracle inputs remain. Four dependency/derived
  evidence owners retain their adversarial identity and generation assertions.
  The affected worktree rings pass: 31 boundary/MCP tests, 47 ordinary runner and
  metrics tests, 34 ownership/concurrency/diagnostic tests and 17 dependency tests.
  Overlapping metric rings are not additional independent population breadth.
- Exact checkpoint `cr11-output-collectors/source.zip` has SHA-256
  `ae6494df27729971b7c8de4c3ad300e48c3f2dfab4dea24f0007d014c91844f5`,
  source identity
  `sha256:d2befed88ad67c5dd7f508f6a90e1f243b3122563cb06eefb86ce65f1736bdb9`,
  extraction `/tmp/hashmarks-cr11-output-collectors-mi0wke7r`. Actual import
  origins and the unchanged `dd129136...` observer are verified. **129 tests
  pass** from that extraction, with six marked metric cases excluded from the
  combined process. The affected selective-scout metric case also passes in its
  own extracted process. Five other excluded cases are not credited to this run.
- Controlled valid inputs produce byte-identical file-cost, main/scout scoring,
  public-prompt and usage reports across independently imported previous/current
  artifacts; proof is `cr11-output-preservation/comparison.json`. Timeout and
  invalid-counter behavior is separately qualified by its regressions. This is
  controlled preservation evidence, not new genuine-source or oracle breadth.
- Source compile, preflight, scoped import/name checks and diff hygiene pass.
  Production and the backend evaluator are unchanged from the preceding frozen
  observer qualification. Current full gates remain red: **654 Ty diagnostics /
  686 Pyright errors, zero warnings**, in `cr11-full-ty-output-collectors.log`
  and `cr11-full-pyright-output-collectors.log`. The archive predates this result
  prose only. Remaining typing, complete locality, deterministic membership,
  broader corpora, independent oracles, witnesses and final qualification still
  prevent an architecture-complete or twenty-capability 5/5 claim.

CR-11 bounded evidence and identity assertions — 2026-10-18:

- Exact-owner, cache, change-brief, cross-repository, freshness, bounded-symbol,
  backend ablation and gate assertions now retain known types or check open
  JSON shapes. Qualified-identity and same-version drift controls still reject
  ambiguous, stale, wrong-symbol and mismatched implementation evidence.
  `combine_required` accepts untrusted iterable values at its type boundary;
  its existing strict bool/None validation and failure-preserving body are
  unchanged. No acceptance threshold, oracle, case membership or review flag
  changed.
- Generic timing retains the callable's actual result. The source-size audit
  uses `read_python_ast` and typed definition/file/threshold results. A new CRLF
  control reproduced an undercount of physical bytes. `PythonAstSnapshot`
  exposes its captured stable-read byte length for this diagnostic; the audit
  reports that length without a second file observation. Cache metadata remains
  process-local acceleration and never becomes content identity, freshness or
  execution authority. The thresholds remain review nominations only.
- Worktree proof: 38 owner/cache/brief/service tests, 46 hard-gate/ablation/
  negative-evidence/freshness tests and 17 qualified/same-version identity tests
  pass. The AST-cache/audit/metrics/diagnostics ring passes 23 tests, with overlap
  accounted for by its selected membership. All fifteen affected owners and
  whole production typing pass both scoped checkers. Full configured checks
  remain red: **539 Ty diagnostics / 562 Pyright errors, zero warnings**, in
  `cr11-full-ty-bounds-identity.log` and
  `cr11-full-pyright-bounds-identity.log`.
- Exact checkpoint `cr11-bounds-identity/source.zip` has SHA-256
  `95219ee78ab15e15a0a3f9330503700b0fb90b9b0cd89e3df62cc7603299033b`,
  source identity
  `sha256:01841c88025e7039699143b9f64e177e5557da9839c0907dffad8f4b56012d67`,
  extraction `/tmp/hashmarks-cr11-bounds-identity-a5exoky_`. Import origin and
  observer `66b138197c64b768f4e2f0112dfee2489dea3aa9735a81b6bc5a464a86ca8574`
  are verified. **156 tests pass** from the independent extraction, including
  affected contracts and constructor/lifecycle controls. The archive predates
  this result prose only. Previous `dd129136...` qualification remains historical.
- Public and fresh native metadata/sender acquisition on this extraction pass
  all ten gates for each selected workflow in each ring, bound to observer
  `66b13819...` and evaluator `ba14c7c5...`. Reports
  `cr11-bounds-identity-public/summary.json` and
  `cr11-bounds-identity-native/summary.json` remain **INCOMPLETE** for selected
  population. Remaining full
  typing, complete locality, deterministic membership, broader corpora,
  independent oracles, witnesses and final qualification still prevent 5/5.

CR-11 canonical tooling and component-family inventory — 2026-10-18:

- The journal now imports its canonical trace normalizer directly. Release
  tooling retains validated standalone rows instead of erasing them back into
  an untyped receipt; manifest row admission is shared by asset naming,
  checksum generation and materialization. The argparse protocol exposes the
  actual operation used by its callers. Source/tag/checksum/bundle-membership
  checks remain enforced, and no release or repository mutation was performed.
- Profile/shard measurements check JSON shapes at ingress. Worker measurement
  owners retain typed decision, verification, read-cost and score values;
  their existing task selection, cue scoring, summaries and isolation behavior
  are preserved. Host qualification uses the canonical common-module import
  and `sys.stderr`. Repository tests use actual pytest fixture types, a narrow
  watcher-process protocol and checked JSON shapes. Adversarial mutations still
  reach the original evidence objects rather than detached array copies.
- `external_observation_freshness` accepts untrusted completeness input and
  retains its existing strict boolean admission. `require_nonblank_string`
  exposes its existing non-optional return contract through an overload. These
  are type-boundary repairs; neither changes an authority or freshness rule.
  No new ignore, unchecked cast, Any blanket, exclusion, severity relaxation,
  acceptance threshold, oracle flag or corpus membership was introduced.
- Worktree rings pass 31 release, 30 comparison/membership, 59 freshness/
  admission/watcher/handoff, 89 measurement, 84 authority/projection/recovery
  and 62 tooling/evidence tests. The subsequently changed inspection and
  multistep benchmark nodes each pass in a separate process. These rings
  overlap and are not distinct corpus breadth. Full configured inventories
  are now **269 Ty diagnostics / 288 Pyright errors, zero warnings**, recorded
  in `cr11-full-ty-owner-typing.log`,
  `cr11-full-pyright-owner-typing.log` and
  `cr11-owner-typing-remaining.json`. Whole production passes both checkers.
- Exact checkpoint `cr11-owner-typing/source.zip` has SHA-256
  `fce17ae6baf9341a0eb5e8686cc363d3de5dd24a41fe9c58e63eb6510d11e79a`,
  source identity
  `sha256:8b4292c7a4f5a99c972f0227028ab6bbf92cb285db4194c6e336b1c4829a8d3f`,
  extraction `/tmp/hashmarks-cr11-owner-typing-tu_3iyiw`. Exact import origin
  and observer `2b4edd3822feed69f5ff6c56375b4cfe76533bcffeb979575a0b5934f2520be3`
  are verified. **270 tests pass** from this extraction, plus the two modified
  benchmark nodes in separate extracted processes. Preflight, compileall,
  lock convergence, scoped undefined-name checks and diff hygiene pass.
- Public and freshly regenerated native metadata/sender runs from this
  extraction pass every selected gate under evaluator
  `306de9746756ecd4649a34027c7be44fb707628a2346b9f8910c269ea1d07c3e`.
  Reports are `cr11-owner-typing-public/summary.json` and
  `cr11-owner-typing-native-02/summary.json`; both remain **INCOMPLETE** for
  their selected population. The first native launch failed because its PATH
  omitted Node; that environment failure is retained separately and is not
  counted as qualification.
- Expanded locality acquisition covers **1,087 nominated definitions across
  the 23 components and composition root**, including family implementations.
  Its exact inputs and per-definition observations are retained in
  `cr11-owner-typing-locality/`. This does not establish complete locality:
  inherited `self` calls and other repository calls remain unresolved, and
  external-or-unindexed calls still require classification. Before/after
  semantic target correspondence and direct owning-test correspondence also
  remain open. Do not waive these findings or reduce the measurement depth.
  Acquisition completed for all 1,087 definitions with zero observation errors.
  `review-index.json` deduplicates **67 unresolved call sites** and **8,160
  external-or-unindexed sites**. Overlapping neighborhoods contain 41 nodes
  with incomplete caller bounds and 227 truncated candidate-search records;
  these occurrence counts are not independent problems or a success score.
  Call/reference bounds are already 1,024, the currently supported maximum.
  The next locality repair should reproduce `_resolve_call_target` allowing a
  truncated global short-name lookup to prevent qualification of a locally or
  import-bound target. Keep real ambiguity, shadowing and unavailable evidence
  unresolved; do not manufacture exact inheritance/runtime relationships.
- Acquisition exposed two nonexistent family-module nominations,
  `retrieval_stability` and `explain_retrieval`. Their operations are methods
  of existing owners, not standalone modules. A new catalog check reproduced
  both stale nominations; they are removed and a nonexistent-module control
  attacks that same check. The architecture/input/lifecycle ring passes
  **34 tests**, and the changed guard passes both scoped type checks. This
  test-only repair and this result prose postdate the source ZIP above;
  observer/evaluator implementation bytes remain unchanged.
- Final catalog checkpoint `cr11-family-catalog/source.zip` has SHA-256
  `dbe9f85c4ed62c4a9188ba7052dd4dc8b13dfb4db34c902336eea8b23361d2e5`,
  source identity
  `sha256:344de3120365eeaf93257b12e82452c9ca0b66550f702ae70638ef972350e4c7`,
  extraction `/tmp/hashmarks-cr11-family-catalog-jcuicr9o`. All 34 architecture,
  input-binding and lifecycle tests pass from that extraction. Its imports and
  observer/evaluator identities are verified. `measurement-reuse.json` proves
  that only the catalog test and plan differ from the 270-test checkpoint;
  production, evaluator, source manifests and oracles are byte-identical.
  This final receipt prose postdates that archive. Overall status remains
  **INCOMPLETE**, with CR-11, CR-12 and Q-00–Q-05 still open.

CR-11 source-bound call qualification — 2026-10-18:

- **Classification: REFACTOR INTERNALLY / OBSERVER defect repair.** Structure
  remains the direct-call semantic owner; Imports owns import identity and
  Source owns current admitted file observations. No new public API, graph,
  cache, policy or execution responsibility was added. Shared Python syntax
  helpers expose the existing ordered class-member binding rule and distinguish
  body writes from formal receiver arguments.
- The global sixty-four-name pool previously vetoed exact local/imported class
  members, receiver methods and imported function aliases when unrelated
  declarations crowded that pool. Positive qualification now uses complete
  admitted file observations, exact import leaves and the selected AST
  declaration range. Unqualified fallbacks retain their bounds. Conditional
  members, shadowed/rebound receivers, unproven imports and inapplicable indexed
  source ranges cannot become exact targets. Imported data retains its existing
  external-or-unindexed category; runtime dispatch remains unestablished.
- Import/export binding reads now reject source drift inside an active read
  scope. A reproduced re-export edit had allowed current AST facts to be
  combined with the old indexed repository binding. The repaired workflow
  requires refresh, preserves the old generation until sync, and then exposes
  the current defining source.
- Twenty identical behavioral controls were run against the unchanged prior
  observer `2b4edd38...`: **10 failed / 10 passed**. Failures include four
  incorrect exact associations, the stale re-export binding and the crowded
  positive bindings. The repaired controls all pass. Their exact common source
  and probe identity are retained in `cr11-locality-before-probe.json` and
  `cr11-locality-before-source-controls.xml`.
- An additional range control checks that a symbol name with coordinates for
  another declaration stays unresolved. Its first version assumed the index
  retained the last duplicate declaration; inspection showed that assumption
  was unsupported. The retained failed probe is not qualification. The final
  control explicitly supplies an inapplicable indexed range and asserts no
  exact target, without introducing a second symbol/index owner.
- The existing qualified-root negative control now includes a genuinely
  conditional source binding. Its unknown/truncation/negative-authority
  assertions remain intact. Independent positive controls separately prove
  that a complete direct binding survives unrelated global name bounds. No
  corpus oracle, review flag, threshold or global candidate limit changed.
- Worktree qualification: 53 locality/import-scope/bound tests pass, the final
  direct control file passes 21 tests, the broader source/import/component/
  freshness ring passes 198, genuine LSP/SCIP change and CLI/MCP replay passes
  53, and export/exact-bound controls pass seven. Rings overlap and are not
  independent corpus breadth. Scoped checks and whole production pass both
  type checkers. Full configured checks remain **269 Ty diagnostics / 288
  Pyright errors, zero warnings** (`cr11-locality-full-ty.log` and
  `cr11-locality-full-pyright.log`). Preflight, source compileall, lock
  convergence, scoped undefined-name checks and diff hygiene pass.
- Current-source locality and a controlled re-observation of the prior exact
  1,087-target source remain required before claiming a measured improvement.
  Inherited receiver context, unresolved/external classification, truncation,
  direct owning tests and baseline correspondence still need closure. CR-11,
  CR-12 and the full twenty-capability campaign remain open.

CR-11 qualification accounting and canonical measurement hook — 2026-10-18:

- The controlled remeasurement retained all **10,114 observed call sites** on
  the unchanged prior source and bounds. It also exposed an important limit:
  268 prior exact resolutions became uncertain, mostly around receiver writes
  in typing-cast blocks. A falling unresolved count was partly a movement into
  the external/unindexed category, not a qualified improvement. The final
  resolver keeps known formal-receiver candidates in unresolved repository
  evidence. No typing-library exception or runtime branch evaluation was added.
  Receiver-write/native qualification remains an open proof obligation.
- The 1,087 prior definition requests represent **1,084 distinct qualified
  targets**: four overload declarations share `TaskEvidencePacketMixin.evidence`.
  Repeated requests returned the same artifact identity and add no distinct
  coverage. Current frozen-source acquisition includes the new source/syntax
  helpers (1,091 requests / 1,088 distinct targets). Physical overload
  declaration coverage versus operation membership still needs qualification.
- A broader economics test exposed a remaining retired root attribute in the
  benchmark's observation counter. The counter now patches canonical
  `Source.member`; a positive control intentionally observes a member and
  verifies that the benchmark rejects it. The original AttributeError remains
  in `cr11-locality-qa-typing.log`. The repaired measurement/reacquisition/
  dependency-scope/exception ring passes **28 tests**, including genuine uv/Maven
  capture-derived economics. AST scans in exception-boundary tests use the
  process-local Python AST cache. No benchmark acceptance target changed.
- These four additional test owners pass both scoped checkers. The configured
  project inventory is now **244 Ty diagnostics / 263 Pyright errors, zero
  warnings** (`cr11-locality-qa-remaining.json` and
  `cr11-locality-qa-full-pyright.log`). Production remains clean under both
  checkers. Full project typing is still red.
- Final frozen source `cr11-locality-qualified/source.zip` has SHA-256
  `357b5442eaa1b4812d9080df0c0deb0b6c7657d4437d3bcd475e45196a2ba96b`,
  source identity
  `sha256:1adb682104dfdcad2ddb742af1010fa24ad25ab2c3191df3e64e059508295831`,
  extraction `/tmp/hashmarks-cr11-locality-qualified-4ne6s5lm`, observer
  `8649b349cc1c4afc8b9b24e392e70ce556f73ff73d708ad36c8cba4ea55cecae`.
  Import origin and unchanged evaluator `306de974...` are verified. The
  extraction passes **287 tests**; the latest locality ring passes 54, and
  the direct-consumer/native replay ring passes 121. Its JUnit export emitted
  a property-format warning; the affected native node passes cleanly with a
  property-compatible xunit1 export, preserving its witness metadata. These
  counts overlap and do not qualify new corpus breadth.
- The earlier `cr11-locality-scope` candidate (`3e46b284...`) and its comparison
  are intermediate evidence only. The final same-source/current-source
  observations and selected public workflow reports are retained under
  `cr11-locality-qualified-*`. Their completed results must be inspected before
  updating the measured qualification claim. This result prose postdates the
  final source ZIP; production, evaluator, tests and benchmark bytes are frozen.

Final source-bound qualification results — 2026-10-18:

- `cr11-locality-qualified-comparison.json` verifies identical repository,
  target-source and measurement-configuration identities for the controlled
  same-source comparison. All **10,114 call sites remain**, with no new or
  retargeted site. **268 former exact resolutions are now unknown**, and no
  previously unknown site gained a resolution in this real-source population.
  The synthetic source contracts prove supported positive binding behavior;
  they do not establish a real-repository recall improvement.
- The final same-source result contains **407 unresolved sites**, 8,088
  external-or-unindexed sites, **11 distinct symbols with incomplete caller
  bounds**, and 231 truncated candidate records across distinct target
  neighborhoods. The current frozen source has 1,091 requests / 1,088 distinct
  targets, no missing module nominations, 407 unresolved sites and the same
  outstanding bound counts. Both acquisitions completed with zero observation
  errors. Counts must not be presented as architecture success.
- Next locality work must independently qualify receiver-write contexts,
  especially type-only cast blocks, and retain the original declaration facts
  and uncertainty. Prefer existing source/native claim machinery; do not add
  library-name suppressions, infer runtime branch values, weaken source/range
  checks, waive unknowns or shrink the measured scope. Overload declaration
  accounting, direct owning-test correspondence and the remaining bound scopes
  remain required before CR-11 closes.
- The final observer's public metadata/sender report
  `cr11-locality-qualified-public/summary.json` passes all ten selected gates
  per workflow under observer `8649b349...` and evaluator `306de974...`.
  Aggregate status remains **INCOMPLETE**. The 287-test independent extraction,
  121-test direct-consumer/native replay ring, final production/scoped type
  checks, preflight, compileall, lock convergence and diff hygiene pass with
  their recorded scopes. Fresh native acquisition for this observer and the
  complete campaign still remain part of final qualification.

CR-11 genuine native receiver witness and lexical context — 2026-10-18:

- **OBSERVER:** extend existing native call-site source correspondence with an
  independent indexed lexical context. This observes repository ranges and
  revision agreement; it neither repairs a producer's claim nor infers runtime
  dispatch. Source/Reads retain repository authority, the relationship model
  owns pure position/range validation, and the existing LSP adapter transports
  the same producer evidence. No new graph, global resolver or executor exists.
- A finite capture from the installed Pyright language server on the frozen
  Hashmarks owner-chain method returned 15 outgoing claims, including the
  three selected demoted owner-chain methods. The raw caller item covers only
  its name token, so the old `outside-caller-item` result remains visible.
  `declaration_context` separately checks current index/member revision,
  unique declaration identity, source coordinates and lexical containment.
  None of these facts certifies a runtime edge or full execution path.
- `cr11-receiver-native-probe/` retains exact source-archive identity, actual
  requests/responses/transcript, raw normalized capture and before/after
  qualification. All 15 claim identities, captured locations and original
  range states remain unchanged. The new lexical context matches all 15 ranges;
  five targets map to repository declarations, including the three selected
  owner-chain methods. This is one genuine native witness, not closure of all
  268 demotions or extra independent corpus breadth. No external dependency
  implementation was inspected by the agent.
- The pure model rejects stronger authority, negative evidence, mismatched
  member identities, invalid coordinates and contradictory containment even
  after packet digests are recomputed. Existing stale, out-of-bounds and
  outside-caller controls remain. Position/range codecs moved from the live
  resolver to the pure relationship model; all defining imports migrated and
  no old aliases remain. Source, producer scope and lexical context stay
  separate axes. The source-integrity file passes 18 tests; the broader
  source/native/hover/SCIP/transport ring passes 164.
- Ruff diagnostics now retain typed finding/file/summary values while reading
  unchanged limits from `pyproject.toml`. The trace emitter imports its actual
  canonical guard/public-input owner and retains direct CLI execution from an
  unrelated directory. CSV economics checks numeric measurements rather than
  coercing booleans into numeric evidence. Nine metric/trace tests pass,
  including direct CLI and boolean adversaries; missing usage remains missing.
- Full configured typing is now **221 Ty diagnostics / 235 Pyright errors,
  zero warnings**, in `cr11-native-context-remaining.json` and
  `cr11-native-context-full-pyright.log`. Production and all changed owners pass
  both scoped checkers. Preflight, compileall, lock convergence and diff hygiene
  pass. Native evidence and qualification remain incomplete until the full
  declared source/claim population, transports and witnesses are qualified.
- Exact source `cr11-native-context/source.zip` has SHA-256
  `130e07845e9a2bd29ba180bb08d3ea43f74d215789bc2b49b86ef7ee81fe6d9b`,
  source identity
  `sha256:b751aa41c300c1fabb43fbbbc25737651d7eb7f735a6ecd37773d61e4a8afe2d`,
  extraction `/tmp/hashmarks-cr11-native-context-hme37gb9`, observer
  `8e3fc400fc694b93c93940d28ad7c0b38b4dd297765792f434c8e73fd9585035`.
  Import origin and unchanged evaluator `306de974...` are verified.
  **207 tests pass** from the extraction; the genuine native probe also
  re-qualifies through that extracted observer with all original claim
  identities/warnings retained. The selected public metadata/sender report
  `cr11-native-context-public/summary.json` passes every selected gate and
  remains **INCOMPLETE** for campaign scope. This final result prose postdates
  the archive; source and test bytes remain frozen. No full 5/5 claim is made.

CR-11 configured full typing closure and profile integrity — 2026-10-18:

- **Both unchanged configured type gates now pass across the full project.**
  `cr11-full-ty-configured.log` records zero Ty diagnostics and
  `cr11-full-pyright-final-attempt.log` records zero Pyright errors/warnings.
  No exclusion, severity, baseline or tool-requirement changes were made.
  Ruff/preflight also passes after the repaired owner types and actual imports.
- The remaining test owners now check nullable/JSON/typed-union evidence at
  their actual boundaries. Digest, snapshot, import-resolution tuple and
  source-row counter mocks preserve the real producer types. Tamper controls
  still mutate original evidence objects; dataclass configuration replacement
  exercises invalid runtime admission without type ignores. A stale
  `ContextPlanningMixin` import now inspects canonical `RepositoryContext.build`.
- Script collectors retain typed results and exact counters instead of object
  erasure. Canonical package imports replace duplicate bare-module/dynamic-loader
  paths. Optional Windows PTY loading remains inside its existing Windows QA
  operation, with a narrow native-factory/process port; no new dependency,
  installation path or product execution responsibility was introduced. Valid
  selection/scoring behavior and missing-value handling remain unchanged.
- Profile-comparison controls reproduced seven failures: duplicate IDs in any
  input, missing/extra/empty repeat membership, and absent noise controls being
  treated as known zero noise. The repair preserves exact membership, rejects
  malformed/empty/semantically ungrounded/nonpositive or nonfinite measurements,
  and returns `UNCALIBRATED` with unknown noise when no repeat was supplied.
  Valid paired thresholds and per-case noise logic are unchanged. The profile/
  repository-evaluation/measurement ring passes 45 tests. No backend grader
  target, corpus oracle or review flag changed; evaluator implementation identity
  changes because its package contains the repaired measurement code.
- Focused evidence includes 49 ownership/negative/MCP guards, 59 concurrency/
  snapshot/authority/calibration tests, 54 CSV evidence tests, and isolated
  collector/reproducibility nodes. These overlap and do not establish complete
  deterministic membership. The full deterministic ring has started: batch 0
  (shards 0–3) passes in `cr11-dev-batch-00-02.log`. Its first launch rejected a
  duplicate `--no-sync` flag before tests; no work from that launch is credited.
  Remaining batches must complete before declaring full project tests clean.
- Full typing closure does not close CR-11 locality/native-witness obligations,
  CR-12 exact-artifact/integrated qualification, or Q-00–Q-05 genuine corpora,
  independent oracles, witnesses, heldouts, economics and final twenty rows.

CR-11 integrated qualification and source-drift boundary — 2026-10-18:

- The typing-clean checkpoint is `cr11-typing-clean/source.zip`, SHA-256
  `23f5d6997d91591db36e31761129c9363993b014a0414a75dd645d3f327cfb84`,
  source identity
  `sha256:0af11c556e315aa051eaab5a9352f5516526923c67a6542652d467308dbe5833`.
  Its independent extraction passes 199 focused tests. Observer identity remains
  `sha256:8e3fc400fc694b93c93940d28ad7c0b38b4dd297765792f434c8e73fd9585035`;
  evaluator identity is
  `sha256:770456057c6ea2fb0fc043855228e50589256c7e10859eef30eb073d62732041`.
- Integrated batches 0–11 passed after correcting a test's read-counter scope:
  index ingestion now reads bytes to bind content/digest, while binding
  observation still performs one shared read for its sixteen consumer bindings.
  The test now measures that observation phase separately; the thirteen-test
  regression ring and complete batch 2 pass. Exact prior membership conservation
  is retained in `cr11-test-selection-repair-comparison.json`.
- Batch 12 reproduced a genuine concurrent source-drift defect. A bounded
  twelve-round discovery run retained an escaping `DecisionRefreshRequired`
  (`cr11-multiprocess-discovery.json`). Deterministic controls then reproduced
  both task-evidence and change-impact failures without sleeps or scheduler luck.
- The canonical read owner now exposes its existing reconciliation boundary as
  `reconcile_decision`. Both staged operations restart their complete observation
  after the read scope closes and the changed member is reconciled. Ordinary
  scoped operations use the same implementation. Nested reads preserve the
  existing outer owner; repeated drift of the same member fails closed. No new
  retry window, executor, freshness authority or stale-result fallback was added.
- The focused generation/freshness/impact/MCP ring passes 60 tests, and fresh
  twelve-round mutation dogfood passes all 768 calls with zero errors, BUILDING
  leaks or generation regressions. Scoped Ty/Pyright and preflight pass.
  Shared read behavior changed, so the old integrated results are historical;
  `cr11-refreshed-dev-all.log` contains the new full-membership run. Its complete
  outcome and current source identity must be recorded before claiming success.

CR-11 native population, independent packaging and import-order repair — 2026-10-18:

- The read-boundary candidate is `cr11-refresh-boundary/source.zip`, SHA-256
  `84536104c34779390632a33a41700a4069ef1863846d140281969d3854a65158`,
  source identity
  `sha256:8c6e600472c36444327e83f2ae44d6d1cd503172db511c769c807cc3c940c3b4`,
  observer
  `sha256:0d7e1b8716a30d067f9a42495f49e9483f8d65c9d1cc2f2907070454ec3dd60d`.
  Its independent extraction passes 91 focused tests; both full configured type
  gates pass. These results precede the import-order repair below.
- Fresh installed Pyright acquisition covers all 110 callers / 26 source files
  behind the retained 268 exact-to-unknown call-site demotions. All 268 sites have
  exact native endpoint correspondence and current lexical call-site containment,
  checked against unchanged call syntax and occurrence membership across the
  shifted source lines. `cr11-receiver-native-population/site-correspondence.json`
  retains the per-site source hashes, raw claim identities and comparison basis.
  This closes that specific witness gap without promoting static unknowns or
  lexical containment into runtime dispatch/reachability.
- The 1,569 raw claims remain intact: 636 unique repository endpoints and 933
  outside-repository endpoints, with zero omitted locations. All retain the
  producer's `outside-caller-item` qualification. Independent lexical context
  is within-declaration for 1,558 claims and outside for eleven; none of those
  eleven is promoted. Broader locality still remains INCOMPLETE: all 1,092
  declaration requests / 1,089 targets were observed, with 407 unresolved sites,
  8,096 external-or-unindexed sites, eleven incomplete caller scopes and 231
  candidate-truncation occurrences (`cr11-refreshed-locality-accounting.json`).
- Genuine replay passes 96 semantic and fifteen dependency tests. Actual fresh
  SCIP/native qualification passes all twelve core workflows / 24 revisions,
  including CLI/MCP/stale/reopen checks, in `cr11-refreshed-live-native/summary.json`.
  This is explicit-target native proof; it does not substitute for answer-blind
  retrieval, independent capability review or the full campaign matrix.
- Independent source ZIP, wheel and sdist rebuilds are byte-identical; the wheel
  rebuilt from the sdist is identical too. Both isolated installations pass the
  actual CLI smoke, and the wheel passes official installed MCP transport.
  `cr11-refreshed-packaging/build-comparison.json` binds these artifacts to the
  read-boundary candidate. Declared optional extras were installed in its isolated
  environment after the offline cache lacked them. No project dependency intent
  or committed lock changed. Cold/warm/incremental parent/current/same-version
  observations preserve exact evidence and read/query/parse counts; these are
  deterministic counters, not the required full timing/churn campaign.
- The refreshed deterministic run passes batches 0–11, then batch 12 finds an
  import-order defect in a different test: package-level lazy delta exports can
  become module objects when the corresponding submodule was imported first.
  Fresh-process controls reproduce both import orders. The repair removes the
  ambiguous callable aliases and migrates the CLI/tests to the defining pure
  delta modules. No compatibility shim or module interception is retained.
  The import/presentation/structure ring passes 38 tests, and both full type
  gates still pass. Current observer after that repair is
  `sha256:6524cfd92113cd8e3dc918586d6cd157c050c4ea0059cdc0f6b1af1ff9532ac6`;
  the preceding candidate's reports retain their original identities.
- Broader core public acquisition preserves new failures rather than claiming
  twelve retrieval successes. Stable-offset misses its changed method, and two
  completed FastStream workflows also miss required disclosure facts. A parent
  API run reproduces stable-offset before the read-boundary repair. Removing the
  diagnostic-word restriction from bounded lexical lookup fixes stable-offset
  but regresses metadata; a same-line-term restriction still regresses metadata.
  Both experiments remain disposable source copies and are **not implemented**.
  Their retained failures and independently isolated neutral fixture identify the
  next evidence-ordering investigation; existing tasks/oracles remain unchanged.

CR-11 composed post-change reads and preserved before authority — 2026-10-18:

- The import repair was frozen as `cr11-import-surface/source.zip`, SHA-256
  `a2c9208196e81fd827353931dd69ace9ee86a5bc8e27a1e632716a04446c9b42`.
  Its independent extraction passes 140 focused tests and its native replay
  passes. The subsequent full test run was deliberately stopped during batch 5
  when genuine workflows proved another source defect; completed batches 0–4
  remain recorded, and the interrupted batch is INCOMPLETE, not a test failure.
  `cr11-import-surface-controller-interruption.json` records the exact scope.
- Genuine partial-pull and failed-BEGIN workflows both reached an escaping
  `DecisionRefreshRequired` while `task_delta` observed a changed imported file
  outside the caller's reported path list. Four deterministic regressions
  reproduced the same defect across delta, refresh, brief and compact refresh.
  A further controlled competing publisher proved a mixed before-revision
  snapshot could be accepted. Both failures retain their pre-repair evidence.
- `DecisionScope.observe` now owns read-stage recomputation, while Changes retains
  the original before values and sync result. Index member reconciliation checks
  its expected generation inside the existing publication transaction and
  returns that exact generation. Another publisher fails closed; nested readers
  propagate to their outer owner. The before snapshot and previous index binding
  are captured together in a qualified read scope. No prior packet is hydrated
  into durable state and no new generation/cache/execution authority is added.
- Reported-path normalization is shared by the five Changes operations that
  previously repeated it. The type-checked current task packet supplies its
  freshness directly. The focused read/index/post-change/authority ring passes
  67 tests, and unchanged full Ty/Pyright plus preflight pass at this checkpoint.
- Re-running the two genuine problems through API before/after and post-change
  acquisition now completes both delta checks with PASS under observer
  `sha256:38a37cc161c95daa5679198c4f412cafd92072eaea8bb263eb709a7eb5b46793`.
  SQLAlchemy's task facts pass; FastStream retains a separate disclosure failure.
  Empty transport selections remain INCOMPLETE and do not establish CLI/MCP proof.
- Fresh multi-process stress then captured actual repeated source changes. A
  typed `RepeatedSourceChangeError` now preserves the direct read's one-refresh
  bound while the existing CLI/MCP bounded recomputation recognizes that signal.
  A matching untyped message remains unrelated; no deadline or retry budget was
  increased. The final focused ring passes 104 tests; fresh twelve-round stress
  passes all 768 calls with zero errors, BUILDING leaks or generation regressions.
  Both unchanged full type gates pass again in
  `cr11-composed-read-full-typing-final.log`. Deterministic membership and exact
  artifacts must now be requalified for these repaired source bytes.
- The campaign census was recomputed without observer execution. Frozen suite/
  grader identities and all 89 entries / 59 problems / eight suites still agree.
  The seven missing catalogs and debugging shortage remain. Executable grader
  capability proofs are absent throughout the retained population; workflow
  declaration metadata alone does not fill them. The twenty-row unacquired
  matrix remains INCOMPLETE in `cr11-current-campaign-census.json`.

CR-11 complete deterministic membership checkpoint — 2026-10-18:

- **All selected deterministic product-test membership now passes.**
  `cr11-deterministic-membership-closure.json` reconciles all 3,445 selected
  test-node selectors across sixteen complete batches / 64 shards, yielding
  **4,748 passing pytest cases, zero skips, zero missing or duplicate members**.
  Parameterized selectors explain the difference between the two counts. Failed
  and partial earlier batches are retained and excluded from this proof.
- The final two fixture repairs preserve their original assertions: the
  conformance spy targets Index, and structural-start fixtures supply Search's
  bounded observation instead of replacing its convenience hit projection.
  Nine conformance and both structural fixture tests pass. No production,
  evaluator, tool configuration, corpus or oracle changed for these repairs.
- Test-source weights changed grouping while exact membership stayed
  `sha256:2103b0bb29f66ed500539cb62432b49d4dd86c68d3b54eb46cca5f3432b5451f`.
  Unchanged singleton batches 0–1, complete reweighted batches 2–14, and the final
  batch's saved immutable membership provide exact closure. The external agent
  executed that final complete batch through pytest; no runner, progress store,
  execution policy or certification machinery was added to Hashmarks.
- Current observer is
  `sha256:f0c80ad1fb4f0fb818a2e0efba44dad1af63a2a329350bc0115fa07cc04ec19a`;
  evaluator remains
  `sha256:770456057c6ea2fb0fc043855228e50589256c7e10859eef30eb073d62732041`.
  Both current metadata/sender workflows pass all ten public gates. Actual fresh
  native qualification passes all twelve core workflows / 24 revisions. Native
  replay passes 96 semantic and fifteen dependency tests; independent extraction
  passes 178 focused tests, plus nine after the conformance-spy correction.
- Fresh current Pyright capture observes all 110 retained callers and all 268
  expected targets. Strict unchanged-call comparison passes 266 sites; two
  intentional changes from sync/decision generation to `scope.generation` remain
  explicitly different. `changed-site-witnesses.json` separately proves their
  current callee ranges and native endpoints, without claiming historical
  argument equivalence or runtime dispatch. Broader locality/direct-test
  correspondence still needs its declared closure.
- Seven further profile-comparability failures are reproduced in
  `cr11-profile-provenance-reproductions.json`: mismatched repeat producer,
  repository, cases, evaluator, sample protocol, semantic fingerprint or semantic
  stability can still produce WIN. They are controlled QA reproductions, not
  genuine corpus additions, and remain **unrepaired**. The earlier duplicate/
  membership/readiness repair does not close this provenance gap.
- Full architecture, final exact-artifact qualification and Q-00–Q-05 remain
  open. Clean deterministic tests and typing do not establish twenty-capability
  5/5; the missing catalogs, independent executable oracles, witnesses, heldouts,
  source-disclosure failures and complete economics campaign still apply.

Profile comparison provenance closure — 2026-10-18:

- The seven false-WIN controls above are now repaired and revalidated in
  `cr11-profile-provenance-revalidated.json`. Comparisons require matching source,
  case-set, evaluator and measurement protocol. A noise repeat also requires the
  same observer and stable matching semantic fingerprints. A candidate observer
  may differ. Missing provenance, invalid integer/shard bounds and an omitted
  shard identity cannot masquerade as a comparable or completely merged profile.
- Existing positive numeric/semantic expectations and per-case thresholds remain
  unchanged. No-repeat observations remain UNCALIBRATED with unknown noise.
  Comparable complete merged profiles still work. The focused comparator and
  repository-evaluation ring passes 62 tests; the original seven reproductions
  all reject rather than yield WIN. No corpus, oracle, review flag, performance
  threshold or product execution responsibility changed.
- Production observer remains `f0c80ad…`. The evaluator changes to
  `sha256:ae8085bcdab106f0bd6b75406b69d230b049ffc429d32e920ed86a5f908593b9`.
  Earlier backend reports retain evaluator `770456…`; they are not relabeled as
  fresh results from the new evaluator. The full 4,748-case deterministic proof
  belongs to the preceding clean source checkpoint; this QA-only follow-up adds
  its focused proof and requires current source/evaluator qualification.

Qualification/Ruff responsibility consolidation — 2026-10-18:

- **Classification: DECOMPOSE MULTIPLE RESPONSIBILITIES; observer decision SPLIT.**
  The old promotion module combined repository handoff binding with hardcoded
  Ruff versions/rules and execution-result receipt validation. Repository
  content/membership/provenance binding is OBSERVER; environment compatibility,
  tool-result receipts and release/certification policy are OUTSIDE. The explicit
  AGENTS.md single-configuration-owner rule and product constitution require
  removing that policy rather than adding another pyproject parser or matrix.
- The repository-binding check now belongs to the existing `qualification_units`
  owner. `validate_native_qualification_repository_binding` first validates the
  retained handoff, then compares its current content, membership, classification,
  plan, handoff and producer identities. Invalid input returns before repository
  measurement. No new registry, state, cache, producer/schema or execution owner
  was added. Dependency direction is the existing handoff CLI to its canonical
  qualification owner; the promotion wrapper is removed.
- `hashmarks/promotion_receipt.py` and `scripts/promotion_gate.py` are deleted.
  The existing `scripts.qualification_handoff` gains `--validate FILE`, exposing
  only the existing validation result. Removed APIs have no compatibility shim.
  Ruff version/rule constants and environment receipt semantics are gone from
  production. Historical exact-symbol corpus cases/grader bytes are untouched;
  they remain observations of their original source revisions.
- The parent receipt/CLI/fuzz ring passed 33 tests before removal. Current direct
  binding, native handoff, qualification and malformed-root tests pass 43 tests.
  Neutral controls preserve current binding, actual source drift with unchanged
  membership, rehashed foreign/self-consistent identity drift, input immutability
  and hostile execution fields. CLI checks retain stale rejection and ensure
  no result/promotion fields or obsolete tool receipt option. Fuzz coverage now
  targets the supported repository-binding validator. Removed compatibility and
  execution-receipt tests are not counted as current product obligations.
- This intentionally changes public API and observer implementation identity.
  Both current full type gates and preflight now pass with zero diagnostics/debt.
  Observer is
  `sha256:945d23159de8e22f4ecf2acc604a61c4cc6e009a1c5258d62be25a5a942cc3c1`;
  evaluator remains `ae8085b…`. Independent candidate checks must complete;
  earlier `f0c80ad…` observer reports retain their original identities. Canonical
  architecture/locality closure and the full twenty-capability campaign remain
  open. This removal does not promote any capability to 5/5.

  Independent extraction now passes 105 focused qualification/profile/fuzz
  tests. Actual subprocess handoff rendering/current validation returns 0;
  source drift returns 3 with validation-only authority. Before/after locality
  uses the same observer, depth two and 1,024 call/reference bounds. The preserved
  repository-binding path has zero unresolved repository calls and zero candidate
  truncation on both sides, with three files before and two after. External or
  unindexed calls remain explicit. The CLI `main` neighborhoods retain candidate
  truncation, so the broader locality report stays INCOMPLETE; no bound/depth was
  lowered to produce a pass. Evidence: `cr11-qualification-binding-locality/`.

Genuine disclosure diagnosis after boundary consolidation — 2026-10-18:

- Unchanged FastStream shutdown and queue-lifetime tasks were observed using the
  existing public packet and bounded source readers. The broker method's file
  is ranked 43 within the existing 64-file pool; repeated singular/plural query
  families and signature-only context matches crowd declaration disclosure.
  The concurrent queue constructor is outside that pool and matches only one
  declared context term, so it is a distinct unresolved case. Expected source
  labels were used for comparison only, never injected into the task query.
- A disposable ordered-qualified-name/unique-family experiment recovers the
  broker method without regressing metadata/sender source facts. A neutral
  40-constructor fixture exposes an additional duplicate-hint defect: removing
  the repeated locator also erased its context qualification and promotion.
  Preserving qualification on the existing locator passes that fixture and 23
  existing declaration/context/lexical tests. These changes remain **unshipped**;
  clean implementation, typing and public transport/size checks are still needed.
- The refined experiment still misses the existing before-revision broker test.
  The source-only review confirms `tests/brokers/base/connection.py` contains
  `test_stop_before_start` and `test_connect`, both awaiting a broker stop. Its
  `Any` receiver does not prove exact runtime wiring. Expanding mechanical task
  variants and qualifying the test namespace before the lexical bound still
  did not surface it. Those experiments are also unshipped; candidate ordering
  before the eight-row projection remains to be inspected. Edit ownership stays
  ambiguous and the selected verifier is unchanged.
- The first diagnostic context pool omitted production's test-path filter; its
  raw 32-row absence is not used as a production completeness claim. The corrected
  filter probe and all rejected/partial experiments are retained under
  `cr11-disclosure-source-probe/`, `cr11-qualified-name-*` and
  `cr11-verification-subject-experiment.*`. No bound, oracle, review flag or corpus
  membership was changed to improve the result. Neither source-fact improvement
  nor this research closes a capability at 5/5.

Declaration ordering and independent verification subjects — 2026-10-18:

- **OBSERVER defect repairs; REFACTOR INTERNALLY in the existing Tasks/Search
  evidence owners.** The neutral 40-constructor regression fails on the frozen
  parent. Repeated normalized task families no longer manufacture additional
  declaration matches. Context preselection retains callable-name matches before
  signature-only matches; qualified-name order and name coverage distinguish an
  operation from parameter-heavy constructors. A duplicate locator retains its
  existing facts and context qualification. No edit-owner or verifier selection
  policy, source oracle, corpus input or bound was changed for this repair.
- The declaration/context/lexical/initial ring passes 44 tests. Current public
  metadata/sender workflows pass all ten gates, including initial size and format
  parity. The first broker shutdown public run now exposes its exact method but
  still fails verifier disclosure; that failure remains retained in
  `cr11-declaration-order-public/` rather than being reclassified as success.
- Read-only candidate traces identify a distinct identity regression: verification
  replaced an observed method with its parent class, dropping the method anchor.
  On the genuine shutdown source the relevant existing test ranked 166 in that
  broad class pool. Keeping the exact method, normalized lexical forms and test
  namespace improves its rank; coherent qualified declaration overlap must also
  precede filename-only similarity. These are advisory disclosure observations,
  with exact references and namespace evidence retaining earlier precedence.
- Parent-class references remain independent context observations instead of
  being erased or relabeled as method references. The same three source locators
  may therefore produce at most two distinct subjects each; metadata reports
  `source_locator_bound: 3` and `subject_bound: 6`. The returned verification
  bound stays eight, and the existing lexical/source windows are unchanged.
  Each subject keeps its own source basis and reference qualification. Selected
  edit/test authority is untouched; no runtime call, sufficiency or execution
  claim follows from class or lexical similarity.
- A new direct regression requires separate method and class bases. All 30
  unchanged verification prototype regressions pass, and the current focused
  ring passes 34 tests. The extended reference, ambiguity, stale identity and
  presentation ring passes 109 tests. Both full type gates and preflight pass.
  The combined genuine CLI/MCP run is now terminal: broker shutdown, metadata
  and sender each pass all ten gates, including before/after source/test facts,
  initial evidence/size, freshness, authority and presentation parity. Aggregate
  status remains INCOMPLETE for this three-workflow scope. Independent extraction
  passes 153 tests. Reports: `cr11-verifier-subject-public/summary.json` and
  `cr11-source-verification-subjects-extracted.xml`. No overall 5/5 claim is
  established; the separate queue constructor and stable-offset cases remain.

Additional genuine qualification — 2026-10-18:

- Observer `44af3024…` and evaluator `ae8085bc…` have three further
  complete public acquisitions: FastAPI dictionary defaults, Litestar
  NotRequired field schema, and SQLModel field discriminators. Each passes the
  eight available common gates across both revisions, CLI and official MCP,
  including the unchanged initial-size ceiling and presentation parity. These
  tasks explicitly nominate source paths; owner recall and initial sufficiency
  remain unqualified. Reports are `cr12-model-public-<workflow>/summary.json`.
- The existing model source oracle has been independently checked against six
  pinned repository identities and eight class/field source units. The retained
  review is `benchmarks/repository_evaluation/manifests/backend-model-v1/`
  `source-oracles.review.json`. It records source-span hashes and references the
  unchanged oracle; `capability_reviewed` remains false. This is source review,
  not capability or witness closure.
- The expanded source-only review now covers all twelve admitted model problems
  across three repositories: 24 exact repository identities, 39 model-stage
  units, direct field annotations/default syntax, declared base expressions,
  nested class identities and exact source spans. See
  `source-oracles-expanded.review.json` beside the original review. All three
  input oracle files remain unchanged. Capability review, required semantic
  adversaries and complete witness membership remain open.
- The remaining eight model API acquisitions pass their independently expected
  source/test and declaration facts before and after the genuine changes
  (`cr12-model-remaining-api/summary.json`). Missing transports in these API-only
  observations retain INCOMPLETE status. Subsequent full public acquisition
  completes all twelve model problems: eleven pass the available fact/transport/
  size checks, while Iterable still misses its test and exceeds the initial
  ceiling. One datetime authority check remains unqualified. Fresh native
  production passes all twelve workflows (`cr12-model-native-public-02/`).
  Pure aggregation admits all seven model report parts without constructing
  CodeMap or launching a process (`cr12-model-campaign-regrade/`). Its model row
  remains FAIL: native binding cannot compensate for failed retrieval/size,
  missing authority or unreviewed capability witnesses.
- The four-repository heldout evaluation completed all 24 cases against the
  exact required source identities. Nineteen pass, including both expected
  ambiguities. Five historical Hashmarks cases fail: paths-under, stale-path
  removal and directory pruning select the wrong ambiguous candidate; MCP task
  evidence and repository-content identity remain over-ambiguous. No false-safe
  or false-unique result was observed. The unchanged failing results are retained
  at `cr12-heldout-current/summary.json`; this gate is not closed.
- An isolated queue declaration-component experiment is not admitted to product
  code. It reveals the genuine constructor but still misses its existing test,
  and a neutral crowded-class control fails on both parent and experiment.
  Retained results include `cr12-component-hint-api/` and
  `cr12-class-component-experiment.log`. Increasing source visibility in one
  repository is not sufficient evidence for the proposed generic repair.
- The model API-only baseline additionally fails to disclose the existing
  Iterable response-options test on both revisions. Its absent CLI/MCP outcomes
  remain INCOMPLETE, not passes (`cr12-model-baseline-api-selected/`).

Lossless initial-wire repair — observer `b91988e9…`, 2026-10-18:

- **REFACTOR INTERNALLY** in the existing initial codec. Choose between the
  existing JSON/zlib/Base64 payload and JSON/LZMA/Base85, preserving every
  decoded value, semantic identity and presentation fact. Encoder history is
  bounded by payload size; decoding retains the unchanged 1 MiB output limit
  and adds a 16 MiB LZMA dictionary-memory limit. No retrieval bound, source
  oracle, qualification threshold, review flag or test-selection policy changes.
- The neutral varied-source regression fails on the frozen parent and passes
  after repair. New decoder controls cover corrupt/truncated/concatenated
  streams, size lies, dictionary-memory inflation, duplicate keys, header
  shadowing, false/null/zero/Unicode and future fields. The focused ring passes
  **184 tests**. A broader run also reproduces an outdated provenance-label
  expectation on the frozen parent: the fixture's `prefix` parameter now yields
  the already-admitted declaration-context route. Its expected route labels
  are updated, while canonical order, source facts, authority, omission counts
  and unchanged edit/verification assertions remain; exact symbol/ranges are
  additionally asserted.
- Fresh genuine Iterable CLI/MCP acquisition passes initial size at both
  revisions, with a maximum compact/text response of **3,972 tokens** instead
  of 4,207. The independent existing-verifier expectation still fails; overall
  workflow status remains FAIL (`cr12-lossless-initial-public-iterable/`).
- Fresh native metadata/sender/subscriber workflows pass every selected gate
  (`cr12-lossless-initial-native/`). Their aggregate remains INCOMPLETE for the
  selected three-workflow scope. The corresponding public acquisition passes
  all ten selected gates for each of the same three workflows, including the
  original source/test facts, size and format parity
  (`cr12-lossless-initial-public-core/`); its aggregate also remains INCOMPLETE.
- Full configured Ty and Pyright pass with zero diagnostics/errors/warnings
  (`cr12-lossless-initial-full-typing-02.log`); preflight passes without policy
  relaxation. Public-encoder measurements use the identical genuine packet,
  two warmups and nine samples, plus an independently extracted parent repeat.
  Wire bytes fall from 9,673 to 8,720; median encoder time rises from about
  5.8 ms to 14.1 ms, with traced peak memory rising from about 0.51 MB to
  2.27 MB. This measured space/CPU tradeoff is not a repository-wide speedup
  or completion of the required economics campaign (`cr12-initial-encoder-*`).
- The preceding exact extraction has fresh complete acquisition membership for
  1,099 locality requests / 1,096 distinct targets, with zero observation errors.
  It still has 400 unresolved repository call sites, 8,061 external/unindexed
  sites and eleven incomplete caller counts. A fresh Pyright capture covers
  all 160 unresolved callers. Exact source-expression/range checks corroborate
  374 of 400 sites as explicit producer claims; 26 remain unknown. Static
  authority is not strengthened and runtime dispatch remains unestablished.
  These observations bind the preceding `44af3024…` extraction, not the later
  codec candidate (`cr12-extracted-component-locality/` and
  `cr12-locality-native-current/site-correspondence.json`).
- Source archive and independent-extraction evidence for this codec checkpoint
  use the `cr12-lossless-initial-source` names. Independent extraction passes
  **373 tests**, including direct components, input binding/lifecycle, codec,
  backend grading, native LSP and official transport, with actual import origin
  and observer identity asserted. The four changed/new codec operations have
  zero unresolved repository calls and no incomplete caller counts at the same
  depth-two / 1,024-call/reference bounds; external/unindexed calls remain
  explicitly unclassified. This paragraph records results after the ZIP was
  frozen; production, tests and source-review bytes are unchanged. Complete
  deterministic membership,
  architecture/locality closure, missing catalogs, semantic adversaries,
  independent capability review and final twenty-row qualification remain open.

Reference-window repair — observer `65352b1a…`, 2026-10-18:

- A neutral direct-component fixture reproduces production-reference fanout
  hiding a test's qualified import through a package re-export. The repair stays
  with the existing owners: Store orders a caller-nominated preference inside
  the same bounded global read; DecisionScope binds that preference into its
  generation/short-target memo key; Verification nominates canonically classified
  test paths. Owner/import qualification and edit authority remain separate.
- The returned evidence window remains 1,024 rows, with one physical lookahead
  row. Preferred references are followed by unpreferred references within the
  same capacity. Saturation remains incomplete and cannot establish absence or
  uniqueness. Controls cover shadowed aliases, detached cached rows, different
  preference orders, unpreferred fallback and the 1,025th-row sentinel. Three
  existing fake query ports accept the added keyword while retaining all original
  assertions; no corpus oracle, threshold or authority assertion is weakened.
- The focused read/verification/economics ring passes **43 tests** and the wider
  ownership/import/freshness/disclosure ring passes **223 tests**. Full Ty,
  Pyright and scoped Ruff pass. The adopted production, evaluator and tool-config
  bytes match the isolated candidate across 356 files. Its real public
  metadata/sender/subscriber workflows pass all ten gates each, including source/
  test facts and initial size. Reports use `cr13-refpriority-public-core/`.
- The genuine Iterable workflow still misses its independently nominated test;
  its compact/text maximum remains under the ceiling at **3,961 tokens**
  (`cr13-refpriority-public-iterable/`). The partial-pull before verifier also
  remains missing (`cr13-refpriority-partial-batch/`). These are unresolved
  retrieval defects, not passes or claims that the candidate search is complete.
- The complete twelve-workflow API-only baseline at the preceding `b91988e9…`
  observer is retained in `cr13-core-api-baseline/`. Eight workflows pass their
  before/after expected facts. Stable-offset symbol disclosure, SQLAlchemy pickle
  source/symbol disclosure, the concurrent queue owner/symbol/test, and the
  partial-pull before verifier fail. Missing transports stay INCOMPLETE.
  Current broader corpus qualification, complete structural locality, exact
  direct-test/baseline correspondence and the final twenty-capability result
  remain open.

Canonical Source helper cleanup — observer `5383cbdb…`, 2026-10-18:

- Alternate-path review found one private `RepositorySource._source_shape`
  static-method alias forwarding to the already canonical pure
  `source_line_correspondence.source_shape` owner. Its sole caller now invokes
  the defining helper directly; the alias is deleted. No other consumer or
  override was found. Classification: REFACTOR INTERNALLY. This removes a
  concrete ownership/localization obstacle without adding resolver heuristics,
  compatibility wrappers, caches or semantic authority.
- Unchanged Source/direct/official-transport tests pass before and after:
  **74 PASS** on each side (`cr13-source-shape-parent.xml` and
  `cr13-source-shape-after.xml`). Paired locality for the exact
  `_source_observation_from_bytes` target, using the same observer,
  configuration and depth-two / 1,024-call/reference bounds, changes unresolved
  repository calls from **1 to 0** and exposes the canonical helper. Three files
  remain observed; symbol count increases from 9 to 10 and context from 287 to
  304 lines because the helper is now followed. External/unindexed calls increase
  from 58 to 70. This is one-target correctness evidence, not a speedup or
  complete component-locality claim. See `cr13-source-shape-locality/summary.json`.
- A fresh Pyright language-server capture against the independent extraction
  also binds that exact call-expression range to the unique repository
  `source_line_correspondence.py::source_shape` endpoint. One nominated caller
  is captured and qualified without errors; the pure range/source match passes
  for its one nominated call site. See
  `cr13-source-shape-native/site-correspondence-normalized.json`. This is an
  explicit producer/source correspondence witness; runtime dispatch and global
  call completeness remain unestablished.
- Full configured Ty and Pyright pass, as does source compileall. The exact
  source ZIP is `cr13-canonical-source-shape/source.zip`, SHA-256
  `9b76c1ffff1074e0c19cccae34f47896828583c9b9558cfa3e6ce400ddd51fd0`.
  Its source identity is
  `sha256:c1aa612c6d4f18804c79d645f3dcd064d32134f2baa9d49a760605116db309e3`.
  The independent extraction passes **478 tests**, including component,
  lifecycle, binding, verification, native and public-transport coverage, with
  actual import origin and observer identity asserted
  (`cr13-source-shape-extracted.xml`).
- Fresh native metadata, sender and subscriber-stop workflows pass all ten
  gates each at this observer, including before/after CLI/MCP, source binding,
  source token correspondence and stale reopen. The report is
  `cr13-canonical-source-native/summary.json`. Its aggregate status remains
  INCOMPLETE because nine other suite workflows were not selected. This native
  source/transport scope cannot establish the full backend capability result.
- The same three genuine public workflows pass all ten gates each at the
  current observer, including independently expected source/test facts,
  before/after CLI/MCP parity, authority and initial evidence/size. Maximum
  initial compact/text sizes are **3,548 tokens** for sender, **3,436** for
  metadata and **3,107** for subscriber-stop. See
  `cr13-canonical-source-public-core/summary.json`. This selected three-workflow
  report remains INCOMPLETE for full-suite/capability qualification.
- The current public Iterable run still fails the independently expected
  `tests/test_skip_defaults.py` verification retrieval on both revisions
  (`cr13-canonical-source-public-iterable/summary.json`). Initial compact/text
  size passes with a maximum of **3,961 tokens**, and freshness, revision and
  authority gates pass. Failed facts/CLI/MCP/presentation gates remain failed;
  source-only/native passes do not compensate for missing verification evidence.
- These proof paragraphs follow the frozen ZIP. Production, evaluator,
  tool configuration and source-review bytes remain identical to that snapshot;
  the later two-test Changes addition is separately bound below. All 23
  component owners are implemented; CR-11's complete
  operation/direct-test/baseline correspondence and locality disposition,
  CR-12's current complete membership/economics/artifacts, and Q-00 through Q-05
  remain open. Architecture implementation is not architecture acceptance or
  twenty-capability 5/5 qualification.

Public-operation correspondence at the same observer is retained in
`cr13-operation-correspondence/summary.json`: all **95** public operations in
the frozen CR-00 baseline map to callable current component operations, and
**zero** retired root callables remain. The authored migration table supplies
the mapping; actual runtime definitions identify the owner and defining module.
This closes the public-name migration inventory only. Static test-call leads
are explicitly unreviewed: Context's `work`/`budget_sweep` are exercised through
`WorkContextProjection`, external freshness has class-level direct calls, and
the operation-contract suite covers dynamically dispatched surfaces. Those
facts must be reviewed against assertions and receiver identity; they are not
automatic direct-test coverage. Introduced/internal stages, behavioral baseline
correspondence and full locality remain INCOMPLETE.

The public-operation review identified a missing direct behavioral test for
`Changes.refresh_brief`: existing operation-contract coverage checked its schema
boundary but did not prove changed-path isolation or generation consistency.
Two new tests independently construct Changes and prove that an unreported
changed file is not refreshed, the task brief reflects the current published
observation, and publication during task composition rejects the packet and
releases the read scope. The unchanged production implementation passes both.
The Changes/refresh/delta/diagnostic/projection/architecture ring passes
**100 tests** (`cr13-refresh-brief-ring-02.xml`); both new tests also pass from
an independent copy of the frozen production extraction with an explicitly
hashed test-only overlay (`cr13-refresh-brief-test-overlay.json`). Full Ty,
Pyright and agent preflight pass. Initial probe failures from using an unsupported
brief field/index-counter comparison and from a sandbox-denied service socket
are retained; the successful ring uses the actual decision-identity contract and
an environment permitting local sockets. No production or oracle change was
needed. The frozen source ZIP and its 478-test proof predate these two tests;
the overlay is iteration evidence, not a replacement exact-artifact claim.

The final two-test replay strengthens the brief check with the public evidence
receipt's exact `codemap_generation`, independently of its hashed decision
identity (`cr13-refresh-brief-direct-final.xml` and
`cr13-refresh-brief-extracted-final.xml`). Four existing external-freshness
controls also pass (`cr13-external-freshness-direct.xml`). The operation report
now records **39** manually reviewed public-operation test correspondences and
leaves **56** unreviewed. Each reviewed row names the concrete independent
receiver, assertions, test bytes and execution evidence; its scope is only those
listed behaviors, not complete operation/internal-stage coverage. Static names
do not prove coverage.

The root lifetime review specifically proves partial-construction cleanup,
workspace-binding failure cleanup, idempotent close, and attempting every close
when one fails. All listed reviewed tests have matching executed test nodes in
the retained XML receipts; no static call lead is counted as execution proof.

A supplemental current-source locality scope covers 25 operations: both retained
Python binding helpers, all top-level initial codec operations, canonical
`source_shape`, and the two changed reference-query methods. All 25 observe
without error or incomplete caller counts. The first 23 have zero unresolved
repository calls. Three unresolved query-mixin call sites are corroborated by
fresh Pyright claims and exact source-expression/range matching, including the
two `_count_read` calls and `refs_many_for_paths`. Reports are
`cr13-extracted-component-locality-supplement/summary.json` and
`cr13-reference-query-native/site-correspondence-normalized.json`. External/
unindexed calls remain undisposed; this explicit source/native correspondence
does not establish runtime dispatch or complete architecture locality.

The complete current census and supplement now contain **1,122 requests /
1,119 distinct targets**, with zero observation errors, zero missing nominated
modules and zero missing targets from the preceding census. This adds 23 explicit
codec/source/query targets to the previous scope; its totals must not be compared
as a same-scope performance or regression score. Pure artifact accounting retains
**404 unresolved repository call sites**, **8,298 external/unindexed sites**, and
**35 incomplete caller observations over 11 distinct symbols**. The report names
each affected symbol; none gains completeness from the census.
The report remains INCOMPLETE:
`cr13-current-locality-accounting/summary.json`. The explicit native witnesses
above corroborate their nominated sites only; the full unresolved population
still needs current source/native correspondence and qualified disposition.

Fresh native capture now covers all **162** callers in that current unresolved
population, with **162 qualified / zero errors**. Pure exact call-expression,
source-binding and range matching corroborates **379 of 404 sites** as unique
repository endpoints; **25 remain unknown**. The latter include `super` exception
initialization and external regex/dictionary/metadata calls. No SDK or dependency
implementation was inspected and no unknown was promoted to a repository
negative or runtime fact. See `cr13-locality-native-current/summary.json` and
`site-correspondence-normalized.json`. These are current observer-bound producer
claims; caller bounds, external/unindexed disposition, internal stages and
behavior/economics baseline correspondence still prevent CR-11 closure.

Local-source review accounts for all 25 remaining uncorroborated sites without
examining external implementations: 20 receivers are assigned imported
`re.compile` results, two are calls through imported `importlib.metadata`, one
uses a repository dictionary alias, and two invoke `super().__init__` from
classes explicitly inheriting `RuntimeError`. Exact local declaration/call spans
are retained in `cr13-locality-native-current/unknown-site-disposition.json`.
Every row remains **unknown** for runtime dispatch with negative evidence
inadmissible; this source-syntax disposition does not clear the whole external/
unindexed population or the remaining architecture gates.

The same canonical caller search was also replayed for all 11 distinct symbols
with incomplete caller bounds, using observational instrumentation against the
frozen extraction (`cr13-caller-bound-review/summary.json`). Exact reasons are
retained per symbol: reference-window saturation and/or incomplete reverse-import
alias qualification. The search and its limits were not rewritten. Returned
callers remain candidates under those incomplete scopes; neither a wider display
nor the forward native witnesses proves a complete reverse-caller universe.

Handler-corpus intake has started from three inspected genuine changes over
FastAPI, Litestar and FastStream, with six exact local Git archives and recomputed
repository-content identities (`cr13-handler-source-intake/intake.json`). Cached
AST/source review prepared 35 decorated handler units over twelve selected
owner/test-file observations before any observer output
(`source-oracles.json`). The FastAPI wrapping regression test is created only
after its change, so it is explicitly absent before and cannot serve as a
before-existing verifier. FastStream's actual fix adds a curried
`docs_router.post(...)(handler)` registration; decorator-only observation cannot
claim that registration is absent. This is INCOMPLETE intake, not a new admitted
campaign suite or a replacement for twelve genuine problems, independent
capability review, semantic adversaries and public/native witnesses.

Retrieval diagnostic freshness repair — 2026-10-18:

- Direct Search review reproduced missing preparation and missing shared read
  scope in `retrieval_stability` and `explain_retrieval`. A cached unsignaled
  source edit was not reconciled, and publication between replay/selected/lane
  stages could produce a mixed-publication diagnostic. Four neutral controls
  fail against the independently extracted `5383cbdb…` parent with asserted
  import origin (`cr14-retrieval-diagnostic-frozen-parent.xml`).
- Classification: REFACTOR INTERNALLY. Search remains the sole retrieval/cache
  owner. Both public diagnostics now prepare contributing paths through the
  existing Search owner, then compose inside the existing generation-bound
  DecisionScope. Two named observation stages retain the existing replay/cache
  restoration, route/fusion algorithms, bounds and wire schemas. The existing
  static `ReadScopeOwner` port types that dependency; no state manager, graph,
  dispatcher or extra cache is introduced.
- Direct controls prove reconciled generation, rejection of interleaved
  publication, released scope and canonical-result preservation after a replay
  failure. The focused retrieval/task/freshness/architecture/codec ring passes
  144 tests before the final static port declaration; final extracted/ring and
  full typing evidence must follow below. All prior observer-bound public/native
  and locality reports remain historical after this production repair and must
  not be relabeled as current proof. The full CR-11/CR-12 and twenty-capability
  requirements remain open.

- The final typed candidate passes full Ty/Pyright and agent preflight, source
  compileall, and **152 tests** from its independent extraction with import
  origin and observer asserted (`cr14-diagnostics-extracted.xml`). It binds
  observer
  `sha256:3f7e72e6a755abbc50d8ef5cd63b7d617ed200acdd5ea3f9b93c044bf81ea194`.
  Exact archive: `cr14-retrieval-diagnostics/source.zip`, SHA-256
  `f41bfaaa54a7fbcac9e3706e29b8eb19097fd89fc4376c270a70353e2ec2814e`;
  source identity
  `sha256:218ac80a80ee4a9f9925b5d50b8f11dba380daeb8ba9fd255228b900452ca741`.
- A bounded parent/current/parent-repeat economics observation uses the same
  pinned genuine metadata source, task and limits, two warmups and nine timed
  samples per diagnostic (`cr14-diagnostic-economics/summary.json`). Warm packet
  bytes and hashes are identical on all three sides (573 stability / 2,661
  explanation bytes). Stability medians are 59.1 / 43.2 / 56.6 ms; explanation
  medians are 15.0 / 15.9 / 13.4 ms. Current explanation performs eight contributor
  file-row reads and one document-frequency read for explicit freshness
  preparation; the same-generation cache previously avoided that qualification.
  This scoped evidence neither proves a general speedup nor replaces the full
  cold/incremental/rename/delete/recovery economics requirement. These result
  paragraphs postdate the exact ZIP; production/test/evaluator bytes remain
  unchanged.

- `cr14-diagnostic-preservation.json` confirms the only changed production file
  since the frozen parent is `retrieval_diagnostics.py`; the preserved query/
  task/freshness/architecture/codec ring bytes are identical. Both prior direct
  Search tests and new controls have parent/current execution evidence. Current
  operation review is `cr14-operation-correspondence/summary.json`: **46** listed
  public-operation behaviors reviewed / **49** still unreviewed. Inherited review
  bytes are compared explicitly and historical execution is not rebound to the
  new observer. Paired public-target and new-stage locality is retained in
  `cr14-diagnostic-locality/summary.json`; unresolved cast/mixin call targets
  have current native/source qualification: all four callers captured and
  qualified without errors, and **12/12** nominated repository call sites match
  exact source ranges and unique producer-claimed endpoints
  (`cr14-diagnostic-native/site-correspondence-normalized.json`). Caller bounds
  are complete in this scope. External/unindexed calls remain explicit and
  runtime dispatch is not inferred; the full architecture census is separate.

Handler intake now pins **12 distinct genuine changes / three repositories /
24 exact source trees** (`cr14-handler-source-intake/intake.json`), without
changing campaign membership or capability review flags. Independent cached
AST/source intake retains **268** HTTP/websocket/subscriber-like decorated
units over 48 selected file observations, including unsupported syntax rather
than calling it absent (`source-oracles-expanded.json`). Exact diff/source
correspondence additionally retains 40 changed production definition spans and
449 test declarations (`change-source-review.json`). These counts describe
acquired source, not reviewed semantic breadth. Three nominated test files exist
only after their change, and before-existing verifiers still need independent
selection. Actual causal owners, input/return branches, supported registrations,
semantic adversaries, independent review and public/native witnesses remain
INCOMPLETE; reaching the source-count minimum does not close the handler catalog.
Three creation-only before-test gaps now have independently inspected existing
surfaces in `existing-before-tests.review.json`: included-router response tests,
existing streaming response tests, and the existing AsyncAPI response test.
Each record binds its exact pinned file/span and explains its limited relevance;
none is claimed to cover the new defect or provide sufficient regression proof.
The other test/oracle/capability requirements remain open.

Curried route-call source primitive — 2026-10-18:

- The genuine selected-provider baseline independently freezes three curried
  route-call expressions before and four after the AsyncAPI try-route change,
  while the previous provider returns zero groups on both sides. No route
  absence or runtime-registration claim is admissible from that result. See
  `cr14-handler-registration-baseline/independent-source-oracle.json` and its
  before/after API artifacts.
- The existing selected `StaticPythonInterfaceDeclarations` provider now also
  reports explicit expression statements of the form
  `receiver.method(route)(handler)`. The claim binds the exact call span, method,
  literal/dynamic route syntax, simple handler-argument spelling and argument
  expansion. Handler resolution and runtime registration remain unestablished;
  no declaration linkage, framework identity, reachability or new graph exists.
  Existing provider path/source/group bounds apply. Classification: REFACTOR
  INTERNALLY; the observer ownership note is in `STATIC_INTERFACE_EVIDENCE.md`.
- Neutral parent probes fail for the missing syntax. Controls cover conditional/
  nested statements, dynamic routes/handlers, absent/rebound names, foreign
  receivers, argument expansion, decorator-position exclusion and 129-group
  failure before publication. An initial intermediate control found decorator
  expressions were being counted; limiting this claim to expression statements
  fixes that overreach. The first provider/source/architecture ring passes
  **122 tests**; final frozen proof follows separately.
- `cr14-handler-registration-after/` retains a useful intermediate 3/4-fact
  observation but is explicitly disqualified for implementation binding: source
  changed while that Python process was alive. Its recorded final file hash
  cannot attest the already imported module. Rerun from an immutable extraction
  with start/end observer checks; never relabel this run as a current pass.

- The stable candidate binds observer
  `sha256:912eda24c7238bdbc6432373a239f06f3d4a42fe5f93ffa093f9f08dc715b966`.
  `cr14-curried-route-source/source.zip` has SHA-256
  `9e6cf5c43e863feddef1c5f8932e6e4eccd82a3ddf345270cc3eb1e531422244`
  and source identity
  `sha256:b976e1d9a179602111379654205bd9789ebb097db27dd5acdff5b4a79faedcf4`.
  Its independent extraction passes **136 tests**, including provider syntax,
  source/authority adversaries, correspondence persistence, architecture and
  initial presentation (`cr14-curried-route-extracted.xml`). Full Ty/Pyright,
  compileall and preflight pass for the frozen source. Nine later curried syntax/
  presentation controls pass in the worktree; their separately hashed test-only
  overlay does not alter the frozen production artifact claim.
- The identical genuine before/after source problem was rerun from that immutable
  extraction with start/end observer checks. Its independent oracle and source
  fact grader pass all **seven** exact call expressions (three before / four
  after), including method, handler spelling, source line and retained runtime/
  handler/absence/coverage unknowns (`cr14-handler-registration-frozen/summary.json`).
  The aggregate remains INCOMPLETE for public transport, broader representative
  semantic cases and capability qualification.
- The preceding diagnostic observer's public core report passes all ten gates
  each for metadata/sender/subscriber-stop; maxima are 3,434 / 3,549 / 3,107
  initial tokens (`cr14-diagnostics-public-core/`). Its genuine Iterable workflow
  still fails expected verification retrieval on both revisions, with initial
  maximum 3,958 tokens (`cr14-diagnostics-public-iterable/`). These retain their
  `3f7e72e6…` observer binding and are historical after the provider extension.
- Paired locality for the source composer and both new pure stages uses the same
  depth-two / 1,024-call/reference configuration on exact parent/current source.
  All four observations have zero unresolved repository calls and complete
  caller bounds (`cr14-curried-route-locality/summary.json`). External/unindexed
  calls remain explicit. The nine final syntax/presentation controls also pass
  from their independent hashed test overlay
  (`cr14-curried-presentation-extracted.xml`); these are additional tests after
  the frozen 136-test candidate, not a rebuilt exact artifact.
- A tracked source-only catalog now preserves the twelve handler problems and
  24 exact trees at
  `benchmarks/repository_evaluation/manifests/backend-handler-v1/source-catalog.json`.
  Candidate owners/tests, selected-file hashes, source identities, creation-only
  before-test gaps and pending proof are explicit. Every semantic/capability
  review flag remains false; the active campaign is unchanged. Source identity
  validation is separate from semantic/oracle/witness qualification.
- All 24 tracked source identities and selected present/absent file hashes pass
  against the exact admitted trees (`cr14-handler-catalog-validation.log`). The
  catalog SHA-256 is
  `370d66f3708ebe4532ea50364e1b36ca65e5b02b28054e58d4f8603cd4722b78`.
  Projection-only grading over the seven genuine call claims passes all eight
  stage/format combinations (`cr14-genuine-route-presentation.json`), retaining
  each complete declaration and uncertainty. This is retained-result formatting
  proof, not newly acquired CLI/official MCP source-provider transport.
- A final source-edit control proves that changed curried call syntax is rejected
  before refresh, updates after explicit index refresh, and cannot be restored by
  a previous packet after reopen with no selected provider. The final hashed
  test overlay replays **ten** curried syntax/presentation/freshness cases from
  independent production bytes (`cr14-curried-freshness-extracted-final.xml`).
  A checked object read fixes the new test's typing diagnostic without changing
  its assertions; final full typing and preflight must remain clean.
- Final full Ty/Pyright and preflight pass
  (`cr14-final-freshness-full-typing-02.log`,
  `cr14-final-freshness-preflight.log`). The bounded provider economics comparison
  uses the identical genuine source/path/receiver with two warmups, nine timed
  samples and parent repeat. Medians are 5.60 / 10.47 / 5.75 ms; packet bytes
  are 3,394 / 18,293 / 3,394, with 0 / 4 / 0 source claims returned. This is the
  measured cost of four newly exposed facts and their bindings, not a speedup
  or equivalent-evidence comparison (`cr14-curried-route-economics/summary.json`).
  Full economics and bounded initial-response qualification remain open.

Public interface selection — 2026-10-18:

- The existing selected interface provider is now reachable through the same
  public declaration operation as backend syntax. Classification: EXTRACT
  RESPONSIBILITY for the former MCP-only provider factory and duplicated CLI
  construction. `repository_declaration_selection.source_declaration_providers`
  is the single pure request-to-provider translator; existing producers still
  own all syntax/bounds, and Declarations/Bindings/Source retain authority.
  No provider registry, new cache, source interpreter or discovery state exists.
- MCP uses one `source_selection` object containing `python_backend_paths`,
  `include_class_fields` and/or `python_interface`; the former flat source
  arguments are removed. The CLI retains backend-path flags and adds
  `--python-interface-json FILE`. Interface paths, receiver names and the existing
  body/input-syntax booleans are explicit; unknown selection fields fail before
  discovery. Wire response schemas and all observer semantics are unchanged.
- Five request probes failed before implementation because the prior API cannot accept the
  selection; the new boundary accepts valid selections and rejects malformed
  paths/names/booleans/unknown fields. The current CLI/official MCP/evaluator
  ring passes **145 tests** (`cr15-interface-ring.xml`); final source artifact,
  broader ownership/source rings and genuine seven-expression transport proof
  follow separately. Existing task inputs/oracles/gates remain unchanged;
  the QA capture adapter translates their source-selection shape explicitly.
- Controls additionally cover discovery-only use, no mixing supplied groups,
  no previous-packet hydration, source drift rejection before refresh, changed
  facts after explicit refresh, and combined backend/interface provider values
  equal to their direct Python observation. The owner map and public docs name
  the new construction boundary; no syntax semantics move into CLI/MCP.
- The final selected-source request passes full configured Ty/Pyright, compileall
  and preflight. The additional actual transport/architecture ring passes
  **49 tests**, including the combined-provider control
  (`cr15-interface-architecture.xml`). The frozen candidate is
  `cr15-interface-transport-source/source.zip`, SHA-256
  `0dc1d11cd03a83fb4d4d88ae833814183a6728c1b55716d6580a7811c56d75a4`,
  source identity
  `sha256:aae97a4b2e0438d953f998b133cd1c1302ce61e6a205ee9a853ee96e9408b0ec`,
  observer
  `sha256:3d02ecd4884a94012755c86460c81c6c31babff77cc67194816602bc98159181`.
  Final extracted and genuine workflow reports follow this exact binding; prior
  public/native reports retain their original observer identity.
- The independent extracted candidate passes **217 tests**, including actual
  interface/backend CLI/MCP, authority, source freshness, provider selection,
  architecture, evaluator and initial presentation
  (`cr15-interface-extracted.xml`). Import origin and observer identity are
  asserted in the extracted process. The genuine fixed before/after oracle
  passes all **18** API/CLI/official MCP stage/format checks for its exact seven
  call expressions (`cr15-genuine-interface-transport/summary.json`), including
  unchanged source identities/revisions, native equality and uncertainty/
  presentation parity. This is one selected-provider source workflow; broader
  handler semantics, genuine lifecycle/adversarial witnesses and final capability
  qualification remain open. These result paragraphs follow the frozen ZIP;
  executable/evaluator/test/source-catalog bytes must remain unchanged.
- Comparable locality retains the same CLI/MCP adapter targets before/after and
  the four new pure selection stages (`cr15-selection-locality/summary.json`).
  All new stages and the CLI adapter have zero unresolved repository calls and
  complete caller bounds. The MCP composition retains one pre-existing
  unresolved retry-predicate call on both sides; it remains explicit. External/
  unindexed calls and whole-architecture locality are not waived.

Handler workflow integration — 2026-10-18:

- The existing backend runner's selected-declaration path previously admitted
  and constructed only the model provider. Interface workflow probes reproduce
  that gap. Source admission now accepts exact backend/interface request shapes
  and retains the same required independent source labels/check IDs. Acquisition
  reuses the canonical source-selection translator; one pure caller-path
  projection supplies acquisition, artifact regrading and source-bound witness
  membership. Production source/evidence semantics are unchanged.
- New controls prove interface facts and source bindings survive pure artifact
  regrading with observer construction forbidden, and an incorrect declaration
  fact fails even while task facts pass. Wrong source/stage, unlabeled paths and
  attempts to introduce runtime authority reject. The first focused ring passes
  seven tests; the complete current QA ring and exact artifact proof follow
  separately. No existing corpus oracle, threshold, review or witness requirement
  is weakened.
- The tracked handler suite now has three independently source-reviewed genuine
  before/after workflows over FastAPI, Litestar and FastStream, using six exact
  source trees. The existing declaration and changed-line boundary surfaces test
  route-call syntax, literal routes/stream annotations, and handler decorators/
  parameters/body unknowns. Relevant existing tests are nominated from inspected
  pinned assertions; runtime coverage and sufficiency remain unestablished.
  All capability review flags stay false and nine catalog problems remain
  explicitly pending. The active eight-suite campaign is unchanged.

Continue the complete handler workflow population and its independent semantic/
adversarial witnesses without adding a provider registry or executing handlers.

- The existing backend QA ring passes **149 tests** in the worktree and its
  independent extraction (`cr16-interface-runner-ring-02.xml`,
  `cr16-handler-extracted.xml`). Full configured Ty/Pyright and preflight pass.
  Exact first-three-workflow candidate: `cr16-handler-runner-source/source.zip`,
  SHA-256 `c8cdc9ff1891038aad3fe201f0fe7e0c791559320b1c3decc4e3f93fe978a07c`,
  source identity
  `sha256:7ddcf749a6c763d0bfe4c2af0c6ee55b5668163888c129b0d7791929d5ab4474`.
  Observer stays `3d02ecd4…`; evaluator is
  `sha256:e2e2d332d3702f68245ad22ff3267733d1436cb6a4e24ad8b61170ae98422f14`.
- The three genuine public before/after workflows completed through API/CLI/
  official MCP. All six selected declaration/boundary stages pass source facts,
  revision, authority and transport parity. Stream-type and Annotated-input
  workflows pass all admitted common gates; AsyncAPI fails its independently
  nominated **before-existing verifier**, while its after verifier passes. The
  aggregate stays FAIL (`cr16-handler-public/summary.json`). All three initial
  size gates pass. These facts do not establish complete handler semantics or
  capability review.
- Source review now extends the root handler suite to all **12 distinct genuine
  problems / three repositories / 24 exact source trees**, using existing
  direct call/argument/boundary observations for the other nine changes.
  Required keyword facts bind their exact call site; over-bound or missing facts
  must fail rather than disappear. The nested-router case records the actual
  source change—explicitly rejecting unsupported nesting—not propagation
  inferred from its commit title. Full handler semantic/branch coverage and
  adversarial capability review remain open; no capability flag is promoted.
  The frozen three-workflow report retains its original suite/grader identity;
  it must not be relabeled as proof of the expanded twelve-workflow corpus.

- The frozen three-workflow report also passes pure artifact regrading with
  both observer construction and subprocess launch forbidden, while preserving
  its failed before verifier (`cr16-handler-pure-regrade.log`). The expanded
  twelve-source workflow baseline uses the separate immutable
  `cr16-handler-expanded-source/source.zip`, SHA-256
  `e9103f9a98a63d04dc8510ccde7cf953d41c7c4f8be4d27e2e14326231b34785`,
  source identity
  `sha256:6d6be2ce973f597c0b88c623dbe4fe35b3df57ac12caae32422a3585da4fd5e2`.
  It retains observer `3d02ecd4…` and its original evaluator; missing transports
  and required facts cannot be upgraded by API-only acquisition.
- One genuine boundary probe independently confirms a missing answer-bearing
  source fact: the caller explicitly nominates a late configuration keyword,
  but the fixed first-eight argument prefix hides it on both pinned revisions.
  Source/authority binding passes while the required keyword fact fails
  (`cr16-schema-boundary-probe/`). The missing fact is not waived as a successful
  observation merely because omission counts are honest.
- Classification: REFACTOR INTERNALLY. The existing pure function-boundary
  observer now prioritizes arguments intersecting caller-reported lines inside
  the same eight-positional/eight-keyword limits, emits retained arguments in
  original source order and preserves original positional indices. Counts,
  truncation, expansion visibility and all runtime/negative uncertainty remain
  unchanged. A neutral public component test fails on the parent
  (`cr16-argument-lines-parent.xml`) and passes with the repair; the first
  boundary/source/transport ring passes 63 tests. A bounded heap avoids sorting
  the complete argument list, and under-bound calls keep the existing direct
  path. Full configured typing and preflight pass; final frozen/extracted and
  genuine post-change qualification follow separately. The old twelve-workflow
  baseline continues against its immutable extraction and must keep its original
  observer identity.
- The complete twelve-workflow API baseline finishes with eight workflows
  passing every independently expected API fact and four failing workflows:
  AsyncAPI's before verifier, Iterable's before/after verifier, registration-once's
  before verifier, and the late schema keyword on both revisions
  (`cr16-handler-expanded-api/summary.json`). Missing CLI/MCP remain incomplete.
  The preserved report binds the unchanged `3d02ecd4…` observer and must not be
  relabeled after the argument repair.
- The repaired argument candidate's independent extraction passes **212 tests**,
  including the previously deselected MCP boundary case
  (`cr16-reported-arguments-extracted.xml`). Full typing, compileall and preflight
  pass. Exact candidate: `cr16-reported-arguments-source/source.zip`, SHA-256
  `0802c36223ee9c67f1d11a541e110994637c4aa163bcb6bcaeddf1fb4486335e`,
  source identity
  `sha256:5af0294b6c05a5de67f649c28397d87f9996a8e1cb1a356245ffd9a6c0419696`,
  observer
  `sha256:943fe4cecbed6336eb1bb7d02ad65c4db7b34626dd31e554a8b4d00a01074066`.
  The worktree's earlier combined ring was 137 PASS / one deselection and is
  scoped accordingly; the extracted ring executes its full named membership.
- Replaying the same genuine late-keyword workflow through API/CLI/official MCP
  now passes every admitted common gate and both boundary stages, including
  exact required keyword facts, unknowns, revision and presentation parity
  (`cr16-schema-after-public/summary.json`). It retains eight keyword rows with
  the original nine/eight omitted counts on the two revisions. Aggregate status
  remains INCOMPLETE for the unselected eleven workflows and independent handler
  capability proof. The three remaining verifier failures are not repaired or
  compensated by this selected source-fact pass.
- The neutral reported-line test also fails against the exact frozen parent
  with import origin and parent observer asserted
  (`cr16-argument-frozen-parent.xml`). All nine original direct test/helper ASTs
  are unchanged; only the new neutral test is added. The only changed production
  owner between those artifacts is `function_boundary_syntax.py`
  (`cr16-argument-preservation.json`).
- Same-source/span/task/bounds economics use two warmups, nine observations and
  a parent repeat (`cr16-argument-economics/summary.json`). Median times are
  184.01 / 187.41 / 181.15 ms; packet bytes 5,624 / 5,634 / 5,624. All sides retain
  eight keyword rows and eight omissions; only the repaired side includes the
  independently required keyword. Query counters are retained. This measures a
  bounded correctness repair, not a general speedup or full economics closure.
- Paired locality covers the argument projector, body visitor/composer and new
  selection stage (`cr16-argument-locality/summary.json`). All new/argument/body
  stages have zero unresolved repository calls and complete caller bounds. The
  visitor retains the pre-existing `self.generic_visit` unresolved site on both
  sides; external/unindexed disposition and complete architecture qualification
  remain open. No external implementation was inspected to reduce the count.
- Read-only candidate comparison for the three retained verifier failures is in
  `cr16-verifier-locality-probe/`. Source-specific ranks expose different failure
  modes; a row captured across contexts is explicitly not canonical-owner proof.
  The probe makes no ranking/authority change. Continue by tracing the selected
  owner and disclosure handoff, with a neutral reproduction, rather than adding
  project names, oracle hints, synonym tables or arbitrary score tuning.

CR-17 verification disclosure follow-up — 2026-10-18:

- A genuine registration replay still omits the independently nominated before
  test (`cr17-registration-public/summary.json`). Source-specific observation
  proves its qualified `Litestar` reference is recovered but ranks 23rd in the
  main pool. The primary file-only source locator previously contributed no
  source-scoped disclosure; secondary declaration scopes consumed that bounded
  projection. The after revision passes. Authority, freshness, revision and
  initial-size gates pass; required fact/transport/presentation gates remain red.
- Classification: REFACTOR INTERNALLY. Verification now probes at most 64
  visible module-named test paths using the existing bulk reference query and
  qualified import/source rules. Shadowed and different-owner controls remain
  unresolved; denied/outline paths cannot consume source-observation slots.
  The independently extracted nine-file ring passes 94 tests at observer
  `05cc2507…`; full configured typing and preflight pass at that snapshot.
- A neutral public task reproduces the file-only disclosure loss with 30
  competing reference-backed tests (`cr17-file-subject-parent-03.xml`). The two
  preceding fixture attempts failed before the intended assertion and are not
  defect proof. Tasks now composes the existing bounded file-symbol observer
  for an exact current file locator, preserving null declaration/range facts,
  source/test revisions, search-bound reasons, unknown ownership and unchanged
  selected verification. The focused source/reference/negative-evidence ring
  passes 21 tests (`cr17-file-subject-focused-02.xml`). The same corrected test
  fails at the missing-test assertion against the independently extracted frozen
  parent (`cr17-file-source-frozen-parent.xml`); the overlay changes test bytes
  only and asserts the parent import origin/observer identity.
- Exact candidate: `cr17-file-source-disclosure/source.zip`, SHA-256
  `21da356daba6752c14bc01a6c206ca5564d5ba53095e0169d2b54d3f795c920c`,
  source identity
  `sha256:59443d91b40eab062c1a02233614caef70beaedd42a874d4b6629594897594b7`,
  observer
  `sha256:5d0dc9e7d5123a47e9e48dfa139627e16e6df464ee38e7929ac9c69298053e74`.
  Independent import/observer checks and all 95 tests in the named nine-file
  verification ring pass (`cr17-file-source-extracted.xml`). Full configured
  Ty/Pyright, preflight, lock convergence and source compileall pass.
- The genuine selected three-workflow public report now closes every admitted
  common gate for AsyncAPI and registration on both revisions
  (`cr17-file-source-public/summary.json`). Maximum required compact/text initial
  sizes are 2,990 and 2,635 estimated tokens respectively. Iterable remains FAIL:
  `tests/test_skip_defaults.py` is missing on both revisions, despite passing
  authority/freshness/revision and size gates (maximum 3,968). Its source-specific
  diagnostic (`cr17-iterable-reference-probe/`) retains the exact reference-backed
  candidate at rank 29 in one source scope and indirect candidate at rank 56 in
  the main pool. It is a different projection problem, not missing import proof.
  Aggregate status remains FAIL; unselected workflows and capability review stay
  incomplete. No oracle, test identity or threshold changed.
- Paired locality covers four existing owners and both new stages at matching
  depth/two 1,024 bounds (`cr17-file-source-locality-02/summary.json`). All caller
  observations are complete. Fresh Pyright outgoing captures cover all six
  nominated callers with no errors; all six unresolved repository sites match
  exact source ranges and unique producer-claimed endpoints
  (`cr17-file-source-native/site-correspondence-normalized.json`). This qualifies
  those sites only; external/unindexed scope and full architecture locality
  remain open. The first locality attempt used unqualified method names and is
  retained as a failed QA invocation, not proof.
- Direct public-operation assertion/receiver review advances from 46 to all 95
  listed behaviors (`cr17-operation-current-correspondence/summary.json`). Seven
  incremental current extracted rings pass 12, 14, 16, 15, 11, 11 and 12 cases.
  The 56 named tests without current execution are then run separately and all
  pass (`cr17-operation-current-requalification.xml`); completed rings are not
  rerun. Every one of the 143 named reviewed test functions has an explicit
  current receipt, frozen source/test byte binding and observed parameter
  membership. Original review provenance remains historical. This is a closed
  listed-function inventory, not full deterministic pytest membership or proof
  of every possible parameter/branch. Negative/schema-only controls are labeled
  with their limited scope; these counts do not establish all positive
  semantics, every internal stage or before/after baseline equivalence.
- Same genuine registration source/task/default bounds, two warmups/nine warm
  samples and a parent repeat expose an explicit cost
  (`cr17-file-source-economics/summary.json`): medians 844.8 / 1,968.4 / 852.0 ms,
  packet bytes 20,626 / 26,306 / 20,626. Only the repaired side exposes the required
  existing test. File-row and suffix-query counters also increase. This is not a
  speedup or economics closure; repeated import/reference work is being measured
  before choosing a semantics-preserving optimization.
- A read-only genuine-source probe confirms 1,842 import-owner lookups over 664
  distinct path/target inputs, including 1,178 repeated lookups in the same task
  (`cr17-import-repetition-probe/summary.json`). No new cache is introduced by
  this measurement. Any follow-up reuse must preserve exact source/read-scope
  binding, uncertainty side effects and returned evidence.
- Both existing replay targets pass against the independent extraction:
  `make dependency-dogfood` passes 15 cases and
  `make semantic-evidence-dogfood` passes 96, including native LSP changes and
  actual CLI/MCP transports (`cr17-dependency-dogfood.xml` and
  `cr17-semantic-evidence-dogfood.xml`). Exact pure regrade of all three genuine
  public outcomes also passes with observer construction and subprocess launch
  forbidden (`cr17-file-source-pure-regrade.json`). The retained Iterable failure
  is reproduced; regrading does not upgrade it or missing capability proof.
- The pinned four-repository evaluation is rerun against the same extracted
  observer (`cr17-heldout-current/summary.json`). All 24 cases are observed:
  17 PASS, two AMBIGUOUS_EXPECTED, and the same five retained Hashmarks
  ambiguity failures (three WRONG_AMBIGUOUS, two OVER_AMBIGUOUS). Each repository
  run records observer `5d0dc9e7…`; source identities match the retained corpus.
  There are zero FALSE_SAFE_EDIT, FALSE_UNIQUE, WRONG_VERIFIER or consumer-action
  leak classifications. This is a complete measurement with a failing
  qualification result, not a clean heldout gate or unseen replacement proof.

CR-18 import-observation reuse — 2026-10-18:

- Classification: REFACTOR INTERNALLY. The measured repeated import-owner work
  now reuses immutable path/uncertainty observations inside the existing
  request-local verification state. Exact source-path/target inputs are keys;
  endpoint projections share that observation but independently replay unknown
  import identity into their state. There is no persistent/global cache, new
  freshness generation or changed ranking/proof rule.
- A direct public Verification control proves that changing an intermediate
  re-export from one source owner to another cannot retain an old exact test
  relationship across read scopes. It passes against the parent
  (`cr18-import-scope-parent.xml`); this is semantics preservation, not a new
  defect oracle. The focused source/reference/freshness ring passes 33 tests and
  the independently extracted nine-file ring passes 96
  (`cr18-import-scope-focused.xml`, `cr18-import-extracted.xml`). Import origin
  and observer identity are asserted; full configured Ty/Pyright, preflight and
  source compileall pass.
- Exact candidate: `cr18-import-observation-reuse/source.zip`, SHA-256
  `3f41c46484edd9496c2d79ed163a111ba617c80230228876faa21064174944de`,
  source identity
  `sha256:1db814218d00d6bd7377c06aa947f34eb1339f38be471e8537d5b7346c3d7f60`,
  observer
  `sha256:81aa456175aa1ba9035feeae530194b1cdb6d459fb328f573dbaa2073ef8575b`.
- Comparable warm registration observations retain two warmups, nine samples
  and a parent repeat (`cr18-import-economics/conservation-summary.json`):
  medians 2,060.7 / 1,770.6 / 2,168.0 ms, with 5,154 / 4,497 / 5,154 file-row
  reads and identical 26,306-byte full responses. The required existing test is
  retained throughout. Default and decoded-initial facts, unknowns, omissions,
  ordering and selection are identical after validating each actual authority
  and recomputing only canonical implementation-bound context/derived packet
  identities under one explicit comparison producer. Original observations
  retain their own authority. Raw identity hashes appropriately differ; the
  original raw-equality QA assertion is retained as a failed assumption, not an
  observed evidence regression. This is a scoped improvement, not full economics
  closure or recovery of all cost from the newly admitted file evidence.
- The same read-only import probe observes 1,532 lookups over the same 664
  distinct path/target inputs, reducing repeats from 1,178 to 868
  (`cr18-import-repetition-probe/summary.json`). Remaining repeats across distinct
  source/endpoint observations are not silently given global cache authority.
- Paired locality retains one unresolved repository call on both sides and
  complete caller bounds (`cr18-import-locality/summary.json`). One fresh
  Pyright caller capture qualifies that exact source range and producer-claimed
  endpoint (`cr18-import-native/site-correspondence-normalized.json`). No new
  helper/call-selection or semantic owner is introduced. Full locality and
  before/after architecture acceptance remain open.
- The three genuine public workflows are requalified against this exact
  extraction (`cr18-import-public/summary.json`). AsyncAPI and registration pass
  all admitted common before/after API/CLI/official MCP gates, with required
  compact/text maxima still 2,990 and 2,635 tokens. Iterable retains its missing
  before/after verifier and 3,968-token bound; aggregate status remains FAIL.
  Exact artifact-only regrade with observer construction/process launch forbidden
  passes (`cr18-import-pure-regrade-02.json`). The first regrade invocation used
  an unavailable relative interpreter in the extraction and executed no grading;
  its failed invocation log is retained separately. Prior reports retain their
  original observer bindings.

CR-19 configuration source intake — 2026-10-18:

- `backend-configuration-v1/source-catalog.json` pins twelve genuine changes,
  four each from the already admitted FastAPI/Litestar/FastStream pools, with
  twenty-four exact Git archive/content identities, nominated source/test byte
  hashes and provisional answer-blind tasks. No observer output was used to
  construct its source facts. Its catalog SHA-256 is
  `665698fc34da18c8472c3c459b340784eaf2d0a771254ca88c68150a7b211052`.
  Archive trees, raw tar bytes and exact source map are retained under
  `cr19-configuration-source-intake/`.
- A separate verification pass recomputes all content/archive identities and
  compares every nominated file with the corresponding Git object
  (`cr19-configuration-source-intake/source-admission.json`). All twenty-four
  sources pass integrity admission. Three nominated test files and one nominated
  owner file do not exist before their changes; semantic absence is not claimed.
  Before-test relevance and causal source ownership still require independent
  review. Performance changes are genuine source changes, not asserted runtime
  failures.
- Every semantic/capability review flag and distinct-problem review remains
  false. The active campaign is unchanged, with no additional qualified row.
  Three future holdout candidates are metadata nominations only: no reserved
  tree is extracted, independence is not established, and contamination/oracle
  review or replacements are still required. This source intake does not close
  capability 11 or the Q-01/Q-02 qualification requirements.
- Persistent source snapshot: `cr19-configuration-intake-source/source.zip`,
  SHA-256
  `4f8e2e28a133d6930fdaad05703e94ab101947d2b5f32c5a615040180bd9bf35`,
  source identity
  `sha256:706a50dc6bc885978089ef25f6ab39828c7d5d109f39123f5e6efc2d90636762`.
  The observer remains `81aa4561…`. Against CR-18, only the new catalog/README
  and plan bytes change; production, tests, evaluator, handler oracles and tool
  configuration are identical. Independent extraction asserts import origin,
  observer/catalog identity and all unreviewed flags, then passes the two
  file-scope/import-lifetime regressions (`cr19-configuration-extracted.xml`).
  Preflight and diff hygiene pass. This bounded data-only extraction smoke does
  not replace the earlier 96-test ring or eventual full candidate qualification.

CR-20 configuration initializer evidence — 2026-10-18:

- The retained Iterable verifier is not repaired. A read-only lexical probe
  places it at rank 108–125 among approximately 500 matching tests, outside the
  existing lexical window. Stronger matching generic files remain ahead; raw
  word counts do not justify moving one oracle-nominated filename. The original
  source/test oracle and its failed report are preserved
  (`cr20-iterable-lexical-probe/summary.json`).
- Configuration intake now has one executable, independently source-frozen
  before/after workflow for the default-provider change. Its exact initializer
  identifier expectations precede observer acquisition; eleven catalog entries
  remain pending and capability review is false. The original observer fails
  both initializer-reference facts while source binding and runtime-unknown
  checks pass (`cr20-configuration-parent-api/summary.json`). No relevant-test
  oracle is invented for the unreviewed nomination.
- Two neutral public declaration controls reproduce the same omission
  (`cr20-keyword-reference-parent.xml`). Classification: REFACTOR INTERNALLY.
  The existing shared default-syntax owner now retains direct keyword value
  names/member expressions within its unchanged eight-keyword prefix. Unknown
  dynamic values, expansion, truncation, hidden literal defaults and runtime
  binding stay explicit. The initial focused declaration/interface/handler ring
  passes 72 tests; final extracted, typing and genuine transport proof follow.
  This is OBSERVER source syntax, not runtime provider resolution or a second
  configuration authority.
- The frozen initializer candidate passes 154 independently extracted tests
  (`cr20-keyword-extracted.xml`), full configured typing and preflight. Exact
  source ZIP: `cr20-initializer-keyword-source/source.zip`, SHA-256
  `44d285f3fac0a4f49d28f1d0e231562082d766a9722ec7f36784a7ca80cfebac`,
  source identity
  `sha256:78f82b2a5a112101073daae424ba471fd9935dca5bd513ac8711d304e91dfd52`,
  observer
  `sha256:9de7534fb2b5770d79c30c39059abc8f1d3190974cc8903894b580db26fc23e1`.
  The configuration workflow passes every admitted before/after API/CLI/official
  MCP gate with a 3,257-token maximum required compact/text initial reply
  (`cr20-configuration-public/summary.json`). Aggregate status stays INCOMPLETE
  for eleven pending workflows and unreviewed semantic/capability proof.
- A direct syntax-owner test separately proves the shared signature primitive
  preserves a keyword member reference without provider/request-validation or
  negative authority (`cr20-keyword-direct-owner.xml`). Paired locality for
  default/reference owners and the new keyword stage has zero unresolved
  repository calls and complete caller bounds at matching depth-three/1,024
  bounds (`cr20-keyword-locality/summary.json`). External/unindexed and complete
  architecture/baseline disposition remain open.
- Existing genuine model regression acquisition exposes a contract extension:
  four exact nested initializer records in three cases require additional
  direct-reference fields. The previous nine-field facts remain identical;
  whole-object comparison rejects the added fields. Original parent/oracle
  acquisitions pass (`cr20-model-parent-api/summary.json`,
  `cr20-computed-parent-declarations/summary.json`); current failures under the
  unchanged original oracle remain retained in `cr20-model-regression-api/` and
  `cr20-computed-regression-api/`.
- `backend-model-v1/initializer-reference-source-oracles.json` records the
  independently source-derived extension. Removing exactly its two added fields
  from the candidate grader reconstructs every original expectation. Tasks,
  labels, expected tests, membership, unknowns, review flags and thresholds do
  not change. Pure regrade of all three captured model workflows passes under
  the stronger oracle, and eight mutations reject both old runtime-claim and
  new referenced-name corruption (`cr20-model-oracle-extension/controls.json`).
  The first control attempt failed to disambiguate same-named nested classes;
  the corrected control binds path/class/line and is the actual eight-control
  proof. This is not independent capability review or qualification closure.
  Fresh current model CLI/MCP acquisition under the stronger oracle remains
  pending; older reports retain their original oracle identity.
- Configuration source membership now appends three source-reviewed call slices
  without changing the first workflow: FastAPI parameter traversal, Litestar
  bound-method classification, and Litestar stateful-callable arguments. Each
  pins the original declaration, exact call/argument source ranges, before/after
  source hashes and unknown callee/runtime authority. Existing Litestar DI tests
  contain direct `Provide` calls and are required as relevance candidates, with
  no sufficiency claim. Four selected workflows span three repositories; eight
  intakes and every capability/semantic/adversarial review remain pending.
  Source admission validates all four. The first admission attempt hashed an
  entire multiline call where the existing contract requires the first source
  line; the corrected first-line and full-span hashes are retained separately.
- Fresh acquisition with the stronger model oracle passes every admitted common
  before/after API/CLI/official MCP gate for all three affected workflows, with
  maximum compact/text initial sizes 2,684 (field schema), 3,126 (computed field)
  and 2,526 (SQL field type) tokens (`cr21-model-extended-public/summary.json`).
  Aggregate qualification remains INCOMPLETE. The exact frozen original
  declaration/interface/handler test bytes also pass all 70 cases against the
  complete changed production tree (`cr21-keyword-frozen-tests.xml`), while the
  three new controls fail on the independently extracted frozen parent
  (`cr21-keyword-frozen-parent.xml`). Overlays and source origins are explicit.
- A same-source/request/bounds economics comparison retains two warmups/nine
  samples and a parent repeat (`cr21-keyword-economics/summary.json`). Medians
  are 14.62 / 14.37 / 15.68 ms; payload bytes 19,327 / 19,662 / 19,327. Source
  field count, keyword names/omissions, runtime uncertainty and store counters
  are identical; only the repaired side exposes the required provider name.
  This is a bounded new-fact cost measurement, not full product economics.
- Full current nominated locality acquisition covers 1,160 requests / 1,157
  distinct targets, with zero observation errors or missing prior targets
  (`cr21-current-locality-accounting/summary.json`). It includes all shared
  initializer/function syntax and source-selection stages as explicit additional
  measurement scope. Fresh Pyright capture qualifies 173 callers without
  errors; 391 of 421 unresolved repository sites have exact source/range/unique
  producer-endpoint correspondence (`cr21-locality-native-current/`). The
  remaining 30 include regex/metadata/dictionary/super calls and five inherited
  AST visitor calls. Unknowns remain unknown. There are still 35 incomplete
  caller observations over eleven symbols and 8,469 external/unindexed sites;
  the caller bound is already the supported 1,024 maximum. This is current
  measured incompleteness, not architecture closure or permission to inspect
  dependency implementations. Earlier locality numbers remain historical.

CR-22 explicit file disclosure — 2026-10-18:

- The four-case configuration acquisition retains one new genuine failure:
  stateful-provider cleanup after the change drops the explicitly resolved
  `litestar/di.py` path from retrieval results. All required boundary, verifier,
  freshness, authority and size checks pass. The first three workflows pass
  their admitted common gates; aggregate status remains FAIL
  (`cr21-configuration-public/summary.json`).
- Three neutral saturation cases reproduce the missing file at limits 1, 3 and
  20 (`cr22-literal-file-parent.xml`). Classification: REFACTOR INTERNALLY. Tasks
  now retains a current, visible file locator when the caller resolved a literal
  path but no named declaration is admitted for disclosure. This composes the
  existing target/visibility/freshness owners and never invents a declaration or
  changes edit/verification authority. The source identity remains file-scoped.
- The focused retrieval/ambiguity/privacy ring passes 68 cases, with two
  official-MCP cases explicitly pending (`cr22-literal-file-controls.xml`).
  Denied paths stay hidden, outline-only paths reveal no body, and full/initial
  responses preserve the existing ownership proof and selected verifier. One
  optional TypedDict test access was corrected after full typing identified it;
  fresh full typing/extracted/official transport qualification follows.
- The exact candidate `cr22-resolved-file-source/source.zip`, SHA-256
  `77c649ceda755899b984fe1b5d2fcd22603457635c058e29808a39f6a3303cc5`,
  source identity
  `sha256:17bf0dbbbd0f45ef0da886e988bbeeb7db4df5511901026f43a7ab6e481a0ab5`,
  observer
  `sha256:02ff7e5080dea31f72b715288a02904541708e4cebd1c28fe53950a46fa68fa5`,
  passes all 109 named extracted tests, including both official MCP cases
  (`cr22-file-extracted.xml`). The three neutral cases fail on the exact frozen
  parent with import origin and producer asserted
  (`cr22-literal-file-frozen-parent.xml`). Full configured Ty/Pyright,
  preflight, lock convergence and compileall pass.
- All four genuine configuration workflows now pass every admitted common
  before/after API/CLI/official MCP gate (`cr22-configuration-public/summary.json`).
  Maximum required compact/text sizes are 3,257, 2,526, 2,902 and 3,154 tokens.
  The stateful-provider source path is visible without establishing an edit
  owner. Aggregate status remains INCOMPLETE for the eight pending workflows,
  semantic/adversarial/native/witness review and capability admission. The
  retained Iterable failure and five heldout ambiguity failures are not closed.
- Exact retained-artifact regrading of all four outcomes passes with observer
  construction and subprocess launch forbidden
  (`cr22-configuration-pure-regrade.json`). Production, tests, evaluator, oracles
  and tool configuration are byte-identical to the CR-22 source snapshot after
  these proof paragraphs; they do not rebind older source or oracle reports.
- Paired requested-identifier/supplement locality retains complete caller bounds.
  Fresh Pyright captures for both callers qualify all twenty nominated unresolved
  repository sites at exact source ranges and unique producer-claimed endpoints
  (`cr22-file-native/site-correspondence-normalized.json`). No new helper or
  selection owner is introduced; this does not rebind the broader CR-21 census.
- The same genuine stateful-provider source/task/bounds with two warmups/nine
  samples and parent repeat exposes a real cost
  (`cr22-file-economics/summary.json`): medians 948.4 / 2,315.7 / 954.0 ms,
  full-response bytes 25,622 / 24,576 / 25,622. Only the repaired side retains the
  requested file in retrieval. Owner remains unknown and selected verifier is
  unchanged. Additional file-scoped reference disclosure increases repository
  work. The measurement is explicit and does not establish an economics win;
  output-preserving reuse remains a follow-up, without suppressing source facts.

CR-23 internal-stage inventory leads — 2026-10-18:

- A source-only CR-00/current census retains 2,342 original and 2,456 current
  CodeMap function definitions (`cr23-introduced-stage-inventory/summary.json`).
  There are 173 new short-name and 692 changed-location leads, including public
  renames, moved code, properties, overloads and real new stages. These are
  source investigation leads, not counts of new responsibilities or migration
  defects. The explicit public-operation table accounts for 89 of those leads;
  one is type-only and three are overload declarations. Original public review
  provenance/execution stays historical rather than being rebound.
- Remaining runtime leads require actual semantic migration/stage classification,
  exact owning tests and pre/post baseline correspondence. Name coincidence,
  source movement, full typing or the 95-operation public review cannot close
  that work. This inventory makes the still-open CR-11 population inspectable;
  it does not weaken the architecture acceptance gate.

CR-24 stable AST binding artifacts — 2026-10-18:

- Read-only profiling of the genuine stateful-provider task records about 26.2
  million Python calls. Repeated export-binding analysis dominates: 3,927
  module-binding scans invoke approximately 1.06 million recursive write checks
  (`cr24-profile/profile.pstats`). A separate input probe confirms one exact
  source/symbol request is observed twice in the same read scope, but indirect
  source scopes differ; their results cannot be merged indiscriminately
  (`cr24-verification-repetition/summary.json`).
- Classification: REFACTOR INTERNALLY. The existing Python export-syntax owner
  now supplies a read-only per-snapshot binding artifact. Ordered bindings and
  declaration identity share the same canonical qualification rules; one module
  statement-write analysis serves multiple queried names. Imports consumes the
  binding/declaration value once instead of rescanning the same tree twice.
  A 256-entry disposable projection cache binds absolute path, full stable AST
  metadata identity and the actual tree. Existing Source freshness/visibility
  qualification still runs; the artifact is acceleration, not identity or new
  repository authority. Source-only AST APIs remain uncached.
- The first preserved import/authority/verification ring passes 85 tests.
  Extended binding/order/scope/workspace controls pass 118, including definition
  headers, lambda/comprehension scopes, match/exception captures, conditional
  imports, star imports, annotation ordering and changed AST inputs
  (`cr24-binding-controls-02.xml`). Two additional direct controls preserve stub
  uncertainty and reject a changed re-export during an active read scope
  (`cr24-binding-freshness.xml`). Full typing passes after correcting the new
  test to construct the canonical Imports owner rather than assume a public root
  attribute. No source oracle, task, threshold, bound or ranking rule changes.
  Exact-artifact, preservation, genuine transport and comparable economics
  qualification remain pending for this new candidate.
- Frozen candidate `cr24-binding-artifact-source/source.zip`, SHA-256
  `236e7d38f0a1f01d13278e5a859db26578644756c7f68b7c0a97ffc0ba3f783c`,
  source identity
  `sha256:da7153fef098049f18cab45025e5a3892201673467eed5009da863150669d830`,
  observer
  `sha256:2dcb0b1aa90f1132ed68b641115742fcb624eb8ea4b9249ba8b0d9da1694b325`,
  passes 148 independently extracted import/binding/verification/locality tests
  (`cr24-binding-extracted.xml`). Exact frozen parent test bytes pass all 94
  preserved cases against the complete new production tree
  (`cr24-frozen-tests.xml`). A read-only differential compares all 70 actual
  module/name binding queries from the genuine task with the frozen original
  syntax rule; kind, targets and declaration identity agree
  (`cr24-binding-differential/summary.json`).
- Same-source/task/bounds economics retain two warmups/nine samples and parent
  repeat: 2,720.5 / 1,087.8 / 2,582.8 ms, with identical 24,576-byte full replies
  and file-row reads 4,172 / 2,893 / 4,172
  (`cr24-binding-economics/conservation-summary.json`). Original full/context/
  initial identities are validated against each actual producer. Recomputing
  only implementation-bound context and derived identities under a common
  comparison producer makes full and decoded-initial bytes identical. File
  disclosure, source facts, ordering, unknowns and authority remain unchanged.
  This closes the measured regression substantially for one workload, not the
  full cold/warm/incremental/economics population.
- Paired locality covers all five changed existing binding stages and four
  introduced artifact stages at matching depth-three/1,024 bounds. Every scope
  has zero unresolved repository calls and complete caller bounds
  (`cr24-binding-locality/summary.json`). Fresh producer captures are retained as
  supplemental observations, not a vacuous zero-site qualification substitute.
  Full configured typing and preflight pass; genuine transport requalification
  is still running against this exact artifact.

CR-25 declaration CLI error boundary — 2026-10-18:

- Broader deterministic validation passes batches 0 and 1 at the CR-24 source,
  then stops in batch 2/shard 8: 73 cases pass and the existing centralized CLI
  exception-owner guard fails. The earlier declaration-selection migration left
  a leaf `try/except ValueError` in `_repository_declarations_code`
  (`cr24-dev-tests-remaining.log`). This failure is retained and no guard is
  weakened. The frozen 64-shard selection has 3,494 test nodes.
- Classification: REFACTOR INTERNALLY. Provider construction now occurs inside
  the existing `_call_codemap` request/error boundary; JSON reading stays with
  its original input adapter and the redundant leaf translation is removed.
  Focused exception/declaration CLI controls pass 23 cases, with six MCP cases
  explicitly outside that initial scope (`cr25-cli-declaration-controls.xml`).
  A direct invalid-source CLI request proves caller-visible validation errors
  still reach the shared boundary. Current typing, exact-artifact and named
  deterministic batch requalification follow; completed old-source batches
  remain proof for their original source, not silently rebound after this fix.
- Candidate `cr25-cli-boundary-source/source.zip`, SHA-256
  `f177a673114767d064b93ec6c17f9049b77a2d3ef84975c8d79aa00b016f7966`,
  source identity
  `sha256:9f5f339658ac40b8f0141c9610fc234ffe0e54729fc4c2d410bc6e7d86b55ef0`,
  observer
  `sha256:a69d706b4b872d9f148e7a4a0afed376be6b4070af49b07b75c38811c2f08574`,
  passes all sixteen named batches / 64 shards: 4,856 pytest cases over 3,495
  deterministic selected test nodes, zero skips, with every source byte held
  fixed through completion (`cr25-full-test-membership.json`). The declared
  plan identity and complete terminal logs are retained. Full configured typing
  and all 29 independently extracted CLI/declaration tests pass, including the
  six MCP cases omitted from the first focused ring.
- The genuine sender/metadata workflows pass every admitted common, owner-recall
  and initial-evidence gate through API/CLI/official MCP at this exact observer
  (`cr25-core-public/summary.json`); aggregate status remains INCOMPLETE for
  unselected cases and capability proof. The current four-repository evaluation
  repeats all 24 cases and retains the same five ambiguity failures, with no
  new false-safe/false-unique outcome (`cr25-heldout-current/summary.json`).
  These are current measurements, not complete twenty-capability acceptance.

CR-26 active source-oracle propagation — 2026-10-18:

- The active campaign is `backend-campaign-v2`, not its historical v1 baseline.
  Its copied model grader still held the original nested initializer records.
  The already validated source-derived extension is now applied there: exactly
  four records add direct references, and the campaign changes only that grader
  digest. Every original assertion, task, source label, expected test, threshold,
  witness, membership and review flag is preserved. This proposal stayed
  unapplied until all CR-25 test batches completed.
- Four captured source cases and eight old/new corruption controls pass under
  the active copied oracle, with observer/process construction forbidden
  (`cr26-active-oracle-proposal/controls.json`). Source admission validates all
  twelve model workflows; all eight suite/grader digests and 89-entry / 59-problem
  membership identities revalidate. The existing grader/gate/workflow regression
  ring passes 130 tests (`cr26-active-oracle-regressions.xml`). The README's
  stale seven-suite count is corrected. No historical report or full test result
  is rebound after these data changes; full active-campaign qualification remains
  incomplete.

CR-27 canonical test-path role — 2026-10-18:

- A neutral indexed workflow proves a production `src/service/test_adapter.py`
  caller is incorrectly listed as a test by impact and structural locality
  (`cr27-role-workflow-probe/summary.json`). The shared boolean classifier,
  repository domain classifier and import-loader classifier independently
  interpret the same path. Seven new semantic controls fail on the parent
  (`cr27-role-parent.xml`), including the actual verification-path contamination.
- Classification: REFACTOR INTERNALLY. The existing repository-domain owner now
  supplies the single test-path role predicate to ranking, context, impact,
  locality and import-loader diagnostics. Production-root Python test-shaped
  names stay source; explicit test/testing directories and supported test suffixes
  remain candidates. This is path-role evidence, never test execution or coverage
  authority. Both independent alternate predicates are removed rather than
  allowed to disagree with the canonical role.
- The first domain/relationship/import/authority ring passes 93 cases, and a
  direct production-loader control preserves its source warning rather than
  incorrectly downgrading it to a test advisory (`cr27-role-controls.xml`,
  `cr27-loader-role.xml`). Affected production callers remain implementation
  evidence while verification lists contain only test-role paths. Current
  typing, exact artifact and broader affected-source qualification are now
  recorded below. The completed CR-25 membership remains bound to that earlier
  source.
- Exact candidate `cr27-canonical-test-role-source/source.zip`, SHA-256
  `6d2be5fc041a4c19bfd9b0e779b15a432fb5780967f845f0fba06302356abbdd`,
  source identity
  `sha256:75d5d4fdefc6ac0de90df87389b96224f6be8c33302d8b8c409231b8c80e5989`,
  observer
  `sha256:16257d502d3cbe9d09f02f1e482e892816f191d63571a6546724ad8712cdcc18`,
  passes 193 independently extracted affected-source tests with zero skips,
  including official MCP transport (`cr27-role-extracted.xml`). Both full
  configured type gates pass (`cr27-role-typing.log`). An explicit old-test
  overlay additionally replays all 182 original affected tests from CR-25
  against the complete changed production tree; all pass with zero skips
  (`cr27-frozen-tests.xml`, `cr27-frozen-tests-receipt.json`). This is behavior
  preservation proof, not an unchanged extraction or full test-membership run.
- The latest four-repository evaluation completes all 24 cases and retains
  exactly the same three WRONG_AMBIGUOUS and two OVER_AMBIGUOUS failures,
  with zero false-safe/false-unique outcomes
  (`cr27-heldout-current/summary.json`). These failures remain open; neither
  the role repair nor passing affected tests closes architecture or 5/5.
- Paired locality observes the same four canonical role stages before/after
  at depth three and both 1,024 reference/call bounds. All eight observations
  have zero unresolved repository calls and complete caller bounds
  (`cr27-role-locality/summary.json`). The removed import-local predicate is
  accounted as removed, not queried as a surviving owner. External/unindexed
  observations retain their classification; this scoped proof does not replace
  the larger architecture census.

CR-28 configuration call-source oracles — 2026-10-18:

- Four previously pending catalog problems now have exact before/after
  call/argument oracles authored from pinned source ASTs before observer
  acquisition: body-field construction, repeat bookkeeping, callable cache
  wrapping and generator-provider classification. The existing four workflows,
  their assertions and all twenty-four source identities are unchanged.
  `backend-configuration-v1/call-source-oracles.json` retains exact declaration
  and call hashes, selected occurrence and expected argument syntax.
- These are bounded syntax slices, not runtime wiring, guard semantics,
  performance or causal-test proof. All capability review flags remain false.
  The executable configuration suite now has eight workflows; four catalog
  problems remain pending. Active campaign membership remains unchanged.
  Source admission revalidates all eight workflows and twenty-four trees. Eight
  minimal source-authored cases pass and 56 mutations fail closed, including
  borrowing the correct argument from a different call. Observer construction
  and process launch are forbidden during these pure grader controls
  (`cr28-configuration-call-oracles/controls.json`). They validate the oracle,
  not product behavior.
- Frozen candidate `cr28-configuration-call-source/source.zip`, SHA-256
  `4828a677838d8cdf3690372ec65c7041992853f357982c9384c60615564ea88e`,
  source identity
  `sha256:762e36996accca10525b400b5683dfc07aa4142425df384d329a252400aef1e6`,
  retains observer `16257d50…`. Its independent extraction passes all 121
  existing grader/workflow tests and 91 export/import binding tests, zero skips
  (`cr28-corpus-extracted.xml`, `cr28-internal-binding-tests.xml`). The unchanged
  binding owners and their direct test bytes match CR-24 exactly; that byte
  correspondence does not rebind the earlier full-candidate measurements.
  A redundant in-sandbox workflow-test replay was stopped while waiting on MCP;
  it is not counted as proof. The complete extracted run includes its transport
  checks with the necessary local-socket permission.
- All four new genuine workflows pass every admitted common and boundary gate
  on both revisions through API/CLI/official MCP
  (`cr28-configuration-public/summary.json`). Maximum compact/text initial
  costs are 2,783 / 2,518 / 2,647 / 2,809 tokens. The aggregate is INCOMPLETE for
  unselected workflows and independent capability review. Source/call hashes
  revalidate independently against the frozen data candidate
  (`cr28-configuration-call-oracles/source-recheck.json`). No review flag,
  original oracle, threshold, witness requirement or active membership changed.
- Pure regrading reproduces all four outcomes with observer construction and
  process launch forbidden (`cr28-configuration-pure-regrade.json`). The exact
  artifact hashes are checked before replay. This remains four newly observed
  slices, not eight current workflow observations or a capability rating.

CR-29 task-matched call-keyword evidence — 2026-10-18:

- A source-only probe finds the retained Iterable verifier uniquely declares
  four task-matched keyword variants in both revisions
  (`cr28-keyword-source-probe.json`). A neutral public task with thirty competing
  test filenames reproduces the omitted test in full and initial replies:
  both new cases fail at the missing-path assertion on the parent
  (`cr29-keyword-parent.xml`). There is no project-name or expected-test lookup.
- Classification: KEEP COHESIVE. The existing immutable reference-syntax
  artifact records named call keywords and source lines during its existing
  AST traversal. RepositoryVerification qualifies visibility, current source
  and revision; Tasks retains these facts while ordering source-candidate
  disclosure. Existing direct-reference and namespace precedence remain ahead
  of this additional syntax discriminator. Edit ownership and selected
  verification remain independently owned.
- Observer ownership note: observed evidence is named call-keyword spelling,
  exact source lines and normalized task-term overlap. Authority is the admitted
  indexed file and its cached stable AST snapshot. At most sixteen distinct
  matching names are returned, with explicit observed/omitted counts and the
  128-character identifier scope; statically dead/type-only branches are outside
  this observation. Freshness stays with Source. Existing reference-syntax,
  RepositoryVerification and Tasks owners are extended; runtime argument binding,
  causal test sufficiency, source-edit choice and verification execution remain
  unestablished/outside. Decision: OBSERVER.
- The first focused authority/disclosure ring passes 27 cases, including hidden
  and outline paths, stale keyword removal, wrong-owner references, exact source
  lines, explicit omissions and full/decoded-initial preservation. Every original
  test/helper AST in the modified test file is unchanged. A temporary misplaced
  original assertion caused one test NameError during authoring; its original
  function body is restored and the passing ring includes it. Current extracted,
  genuine workflow, typing, locality and economics qualification follow below.
- Candidate `cr29-task-keyword-source/source.zip`, SHA-256
  `f85b5cf61cdf3ebea263462df6d5f12a89d025b772af3ce597f58ea9fc7561bf`,
  source identity
  `sha256:2041f46d6dcd5df40d151fc67b6b3540a7b474c15ff681346b4124d4a7dabd17`,
  observer
  `sha256:6cdac79680a9b8d9ac9c0f0783093a903fea71ca2978c75e3789ed0067c88f60`,
  passes 146 independently extracted verification/initial/MCP tests, zero skips.
  Full configured typing passes. Exact frozen overlays reproduce both missing
  candidate assertions against CR-28 and pass all 126 original affected tests
  against the complete CR-29 production tree (`cr29-keyword-preservation.json`).
- The unchanged genuine Iterable workflow now passes source/verifier, authority,
  freshness, revision, transport and presentation gates on both revisions, but
  FAILS initial size: MCP compact costs 4,060 / 4,053 tokens; required text and
  CLI formats stay below 4,000 (`cr29-iterable-public/summary.json`). This failed
  candidate is retained. The new source facts are not removed to reduce size.
- Paired locality covers three existing stages and both introduced stages at
  depth three / 1,024 bounds (`cr29-keyword-locality/summary.json`). Caller bounds
  are complete, but two repository-call sites remain unresolved; this remains
  scoped INCOMPLETE architecture evidence rather than a locality waiver.

CR-30 compact verification qualifier combinations — 2026-10-18:

- Classification: REFACTOR INTERNALLY in the existing task-presentation owner.
  Mixed verifier qualifiers previously repeated three field names and their
  values per finding. Compact groups now use an explicit column/set table when
  its actual compact UTF-8 size is smaller. Each finding retains its path and
  absolute source reference; its qualifier index recovers the exact original
  tuple. Uniform groups retain the existing common-qualifier encoding. No native
  fact, bound, identity or selection authority changes.
- A pure reconstruction of the exact retained MCP replies conserves every
  qualifier and reduces compact cost from 4,060 / 4,053 to 3,962 / 3,946 tokens.
  This is a proposal measurement against retained replies, not fresh current
  transport proof. Lossless LZMA/table probes did not give a useful alternative
  and no codec change was introduced. The focused initial/authority/presentation
  ring passes 51 tests. The new mixed-state test restores all eight findings and
  qualifier tuples, preserves input bytes semantically and checks a real byte
  reduction. Fresh artifact, typing, transport and economics qualification follow.
- Exact candidate `cr30-verification-qualifier-source/source.zip`, SHA-256
  `4cb676e88e38318181e783fadd786cf2e7e06783ecd11973a7704411a07b2a17`,
  source identity
  `sha256:12dad3ecb92ae92fb878a61ae28d60ce4d1be51e70b378323fb766afb70a12e5`,
  observer
  `sha256:a32f264cb3a6e96f2a1dfa1b5d63f4283b3dd798b65acc0b9c4cfc9120d7cfbd`,
  passes 147 independent extracted tests and all 146 exact original affected
  tests over the complete changed source, zero skips
  (`cr30-qualifier-preservation.json`). Both full type gates pass. The pure
  projection conservation receipt reconstructs every prior presentation field
  while preserving the original native wires and identities
  (`cr30-projection-conservation.json`). Five paired presentation/locality
  observations have zero unresolved repository calls and complete caller bounds
  (`cr30-qualifier-locality/summary.json`); this does not waive CR-29's two sites.
- Fresh genuine Iterable acquisition passes every admitted common gate on both
  revisions through API/CLI/official MCP. Maximum required initial compact/text
  costs are 3,962 / 3,945 tokens (`cr30-iterable-public/summary.json`). Its aggregate
  remains INCOMPLETE for eleven unselected workflows and capability review.
  Pure regrading, with observer construction/process launch forbidden, reproduces
  the outcome and independently checks the four exact keyword names, lines,
  source revisions and unknown authority in all 36 acquired native observations
  (`cr30-iterable-pure-regrade.json`). The original oracle and every threshold,
  review flag and campaign membership remain unchanged.
- Warm economics compare the same genuine source/task/bounds with two warmups,
  nine samples and a parent repeat (`cr30-keyword-economics/summary.json`). Each
  sample observes full plus initial plus compact presentation. Median costs are
  3,211 / 3,892 / 3,365 ms, with unchanged admitted owner and selected verifier;
  the independently nominated verifier appears only on the repaired observer. Last-observation
  file-row read counters increase from 2,663 to 4,148. This 16–21% warm cost
  increase remains open work; it is not a performance win or broad economics
  qualification. Complete cold/churn measurements remain mandatory at Q-04.

CR-31 request-local keyword observation reuse — 2026-10-18:

- A fresh genuine-task profile measures 755 keyword-observer calls across five
  source-candidate groups; this stage accounts for 0.773 profiled seconds and
  repeats source qualification as groups revisit the same test paths
  (`cr31-keyword-profile/`). Classification: REFACTOR INTERNALLY. Tasks now
  explicitly passes one operation-local observation map through its source-local
  groups. RepositoryVerification owns its key and evidence: exact ReadScope
  identity, path and complete task-term tuple. No state survives the composition.
- Every reuse still checks current visibility and Source freshness first. Empty
  observations do not authorize negative evidence and must also reject a changed
  file. Outside an active read scope, there is no reuse. New direct-owner controls
  cover query/read-scope separation, consumer mutation after scope expiry,
  matching/nonmatching source edits within a scope, changed source revisions and
  deny/outline transitions. Original test/helper ASTs are unchanged. The focused
  ring passes 42 tests; both full type gates and preflight pass. Exact-output,
  economics, extracted and genuine transport qualification follow.
- The first matched economics comparison keeps every full and decoded-initial
  field byte-identical after validating each actual producer binding and
  recomputing only canonical producer-dependent identities under one comparison
  producer (`cr31-keyword-economics/conservation-summary.json`). Packet bytes
  remain 59,559. Last-observation file-row reads fall 4,148 → 3,673; medians are
  4,142 / 3,975 / 4,308 ms for parent/current/parent-repeat. This one-scope
  result does not close full cold/churn economics.

CR-32 pure word-normalization reuse — 2026-10-18:

- The same profile finds almost 490,000 calls to the canonical pure word
  normalizer. Classification: REFACTOR INTERNALLY. The existing static owner
  now uses a bounded 4,096-entry cache keyed by exact word and derivation mode,
  returning its existing immutable tuple. It reads no repository state and
  caches no freshness, source, ranking or selection authority.
- A frozen-predecessor differential checks 967 unique declaration/parameter
  word parts from 592 genuine test-source files, alternating both modes twice:
  all 3,868 exact comparisons pass (`cr32-normalization-differential.json`).
  A direct regression prevents derivation-mode contamination. Full configured
  typing passes. The complete affected ring and exact candidate/economics
  qualification follow; an interrupted in-sandbox MCP replay is not proof.
- Frozen candidate `cr32-normalization-source/source.zip`, SHA-256
  `1103896596644278d64463484c499ca03384c580efd562f8918c3684b42bf8f9`,
  source identity
  `sha256:26e0ade086015d8ea067cc3770d3eed2bd84f366697d1cdc2dde1280eb87c386`,
  observer
  `sha256:2e0e338690c5947d5721081a36509af67e70d67847197e787f2bfb542344be92`,
  passes 180 independently extracted affected tests and all 174 exact original
  CR-30 affected tests against the full changed production tree, zero skips
  (`cr32-extracted.xml`, `cr32-preservation.json`). Nine paired locality
  observations cover four existing stages and the new source-group composition,
  at depth three / 1,024 bounds, with complete caller bounds. One unresolved
  repository call remains in the keyword observer on each side; the new group
  stage has zero (`cr32-locality/summary.json`). Broader locality remains open.
- Current matched medians are 4,211 / 3,254 / 4,227 ms for parent/current/parent
  repeat, using two warmups and nine full-plus-initial-plus-compact samples per
  side. Read counts are 4,148 / 3,673 / 4,148. All full and decoded-initial fields
  are byte-identical after validating actual producer bindings and recomputing
  only the canonical producer-dependent context/packet identities under one
  explicit comparison producer (`cr32-keyword-economics/conservation-summary.json`).
  Original packets retain their actual identities. This roughly 23% improvement
  is one warm workload, not full economics or capability-20 acceptance.
- Fresh genuine Iterable acquisition passes every admitted common API/CLI/official
  MCP gate on both revisions (`cr32-iterable-public/summary.json`); maximum
  required initial costs remain 3,962 / 3,947 tokens. The aggregate is INCOMPLETE
  for unselected cases and review. Pure regrade reproduces all outcomes with
  observer construction/process launch forbidden and checks all 36 native
  keyword/source observations (`cr32-iterable-pure-regrade.json`).

CR-33 configuration composition and constructor slices — 2026-10-18:

- Two additional source-authored workflows observe context getter composition
  and dependency-constructor adaptation. The former binds the existing repository
  getter before the composition file is added and the nominated composition
  getter after it. Physical source addition does not establish semantic absence.
  Exact declarations, call/argument facts and their byte hashes were frozen
  before observer acquisition. All eight prior workflows/oracles and all earlier
  source-oracle records remain unchanged, including scalar types. Source
  admission revalidates ten workflows over twenty-four trees; the twelve
  source-authored positive controls and 84 mutations reject wrong calls, ranges,
  arguments, split-call borrowing and stronger runtime claims.
- Data candidate `cr33-configuration-wiring-source/source.zip`, SHA-256
  `ee8985352f28fb901c5f40b614c27afd381dd850fb205ab503d1c8e06ca060e2`,
  source identity
  `sha256:0409fb6eb293ccca33964eb1235bde06a41d9db6a4983b3dcb56ba4bcd613575`,
  retains observer `2e0e3386…`. Both new workflows pass all admitted common and
  boundary gates on both revisions through API/CLI/official MCP, with maximum
  compact/text initial costs 2,815 / 2,662 tokens
  (`cr33-configuration-public/summary.json`). Pure regrade preserves both results
  with observer construction/process launch forbidden
  (`cr33-configuration-pure-regrade.json`). Aggregate remains INCOMPLETE for
  unselected workflows and independent capability review. The remaining two
  catalog slices are named dependency markers and non-init constructor-field
  filtering. Active campaign membership, review flags, thresholds and original
  expected facts remain unchanged.
- The independent data extraction passes all 121 existing grader/workflow tests,
  zero skips (`cr33-corpus-extracted.xml`). All original functions/helpers in
  both modified owner-test files are unchanged at the AST level; new controls
  are additive (`cr32-original-test-ast-preservation.json`).
- Source-only next-step proposals are frozen separately in
  `cr33-pending-source-oracles.json`: the named-marker assignment at
  `litestar/di.py:42` and constructor-comprehension guard at
  `faststream/_internal/fastapi/get_dependant.py:35`, with exact before/after
  source/file/line hashes. These are not admitted suite members. The existing
  `Source.observe(..., lines=(line,), anchor_context_lines=1)` and CLI/MCP
  `source_observation` member context already own this observation primitive.
  The remaining work is to bind it into the existing development workflow and
  pure-regrade/witness paths, rather than adding a production-specific parser.
  Preserve unknown runtime marker binding and constructor compatibility.
- The API feasibility probe observes all four before/after source contexts and
  exact bytes (`cr33-pending-source-probe/`). Its first QA comparison wrongly
  equated raw source-range SHA-256 with the source owner's domain-separated
  physical-line digest. The inspected owner uses the `hashmarks.source-line.v1`
  NUL prefix and excludes LF. The corrected proposal retains both distinct hashes
  and the original raw-hash-only proposal; all four canonical digest/text checks
  now pass. No product behavior, admitted oracle or threshold changed. These
  pending cases still lack workflow, transport, witness and capability proof.

CR-34 exact source-line workflow family — 2026-10-18:

- Classification: EXTRACT RESPONSIBILITY for development QA only. The new
  `backend_source.py` owns bounded source-line request validation, acquisition
  and pure fact/revision grading over the existing public Source observer.
  Existing source admission, before/after workflow composition, pure replay
  and artifact-bound witness owners compose that family. No production parser,
  source responsibility, execution controller or second harness is introduced;
  the production observer identity remains `2e0e3386…`.
- Source acquisition precedes the existing whole-snapshot recheck and witness
  collection. Requests bind one admitted path and one to eight distinct positive
  lines; native and all display checks are mandatory. Replay rereads the exact
  source bytes, checks member revision and domain-separated line digests, and
  rejects wrong membership, stale/unavailable members and altered artifacts.
  Exact revision correspondence can be established with repository freshness
  still unknown; that native state is explicitly preserved, never made current.
- The two previously frozen pending cases now use actual marker-assignment and
  comprehension-filter lines through Source.observe, not unrelated call proxies.
  All ten original workflows/oracles remain unchanged. The suite has twelve
  source-authored slices over the same twenty-four trees and three repositories;
  no active-campaign membership, threshold or review flag changes. Full semantic,
  adversarial, relevant-test and capability qualification remain incomplete.
  Current integration, exact artifact, typing and genuine transport proof follow.
- The first frozen source-line family ring passes 18 tests, including actual
  API/CLI/official MCP, pure replay, missing/tampered captures, denied/outline
  and stale sources, and strict scope admission. A concurrent worktree broad
  run correctly invalidated its observations when evaluator files changed;
  those errors are retained, not product-test or qualification passes. Broader
  proof is rerun against an immutable extraction.
- Final source-line candidate `cr34-source-line-final/source.zip`, SHA-256
  `8613aa46a08b71ca2201aa8108e0bdca258705141f3557ff2b2aa2c824f0216a`,
  source identity
  `sha256:aa2f7f98253153081fb879ca1613a7517b26d0e56d18ba07166d9d04627da9a0`,
  retains production observer `2e0e3386…` and binds evaluator
  `sha256:4a7aedfaa1955aad7f34460f55fbb09321096e1df9153f0d2ba55c1a41e3e57e`.
  The independent extraction passes all 139 source/structural/runtime/workflow/
  grader tests with zero skips (`cr34-final-extracted.xml`); both full configured
  type gates pass. Four positive oracle controls reject all 36 wrong-text/digest/
  path/line/role/truncation/authority/execution/coverage mutations
  (`cr34-line-oracle-controls.json`), without independent capability-review claims.
  Exact replay of the two earlier call-source workflows remains unchanged under
  the new evaluator (`cr34-prior-corpus-regrade.json`).
- Both genuine marker/filter workflows pass every admitted common and source
  family gate before/after through API/CLI/official MCP
  (`cr34-configuration-public/summary.json`). Their maximum required initial
  compact/text costs are 3,037 / 2,672 tokens. Each contributes 84 passing,
  artifact-bound source-fact/presentation witnesses across all three surfaces.
  Aggregate remains INCOMPLETE for ten unselected workflows and independent
  capability review. All 121 exact frozen original workflow/grader tests also
  pass over the complete new evaluator, with zero skips
  (`cr34-frozen-tests-receipt.json`). This is an explicit test overlay, not an
  unchanged extraction or full product-test membership result.
- Exact pure regrading verifies all artifact hashes and reproduces both current
  outcomes plus their complete witness membership, with observer construction
  and process launch forbidden (`cr34-source-pure-regrade.json`). No historical
  observation is relabeled with the new evaluator identity. Current preflight,
  lock convergence, source compileall and diff hygiene pass; only this plan's
  result prose postdates the frozen source candidate.

CR-35 configuration guard/wiring source review — 2026-10-18:

- Source review identifies real oracle gaps: cached-generator classification
  calls alone omit the `use_cache` rejection guard; repeat-bookkeeping calls
  omit the new guard; context getter calls omit declared context ordering.
  The reviewed source now contributes 66 exact guard/wiring/metadata lines over
  all twelve problems, before acquisition, using the existing source-line
  family. No product parser or execution behavior changes.
- `backend-configuration-v1/source-review.json` binds the selected facts to
  exact source bytes and primary upstream commit subjects, and records distinct
  trigger conditions. Commit identity alone is not the distinctness criterion.
  All prior task/source/metric/threshold/check/review fields are preserved;
  existing line requirements are additive. Four FastAPI changes have separate
  upstream PRs/operations; the two constructor changes have separate triggers
  (slotted metadata attributes versus non-init constructor fields).
- All 24 source stages pass source-authored oracle sanity checks, and all
  330 wrong-text/digest/missing-anchor/context-only/truncation mutations fail
  (`cr35-oracle-controls.json`). This establishes oracle efficacy, not runtime,
  test sufficiency, independent capability review or final qualification.
  Nominated test paths remain unqualified until their actual source relations
  are reviewed; three named test files do not exist before their changes.
  A complete same-candidate twelve-workflow acquisition follows.
- An independent source-shape pass binds every one of the 66 selected lines to
  its actual statement AST and containing declarations
  (`backend-configuration-v1/source-ast-review.json`). Four are module-level
  imports/alias/export facts and remain unscoped to a function. This checks
  source context without inferring control-flow execution, runtime provider
  identity or capability readiness from textual coincidence.
- Test-source review records 17 exact test declarations across the twelve
  problems, with file/range hashes, imports, calls and assertion syntax
  (`backend-configuration-v1/test-source-review.json`). It distinguishes direct
  after-change regression declarations from unresolved before counterparts.
  The original request-parameter cache-test nomination has no OpenAPI request;
  `get_flat_params` is directly called by `fastapi/openapi/utils.py`. A separate
  existing OpenAPI test is recorded as source-related, without claiming complete
  runtime reachability. The unchanged non-init-field test has no `init=False`
  declaration and is not established as defect-sensitive. Default-provider
  identity sensitivity also remains unproven. Original nominations/assertions
  remain untouched; execution and sufficiency are not claimed.
- Required source-fact/presentation witness membership is derived from the
  frozen oracle before scoring: 1,698 exact stage/surface/format/check units
  (`cr35-required-source-witnesses.json`). Missing units remain explicit and
  cannot be hidden by passing averages. Partial accounting revalidates completed
  receipt identities, artifact bytes and exact oracle pointers without starting
  observation (`cr35-source-witness-accounting.json`). It is QA evidence
  accounting, not an execution ledger or capability admission.
- A neutral locality probe reproduces a generic remaining classification gap:
  same-file literal/call-assigned data receivers are labeled unresolved
  repository calls, while imported data receivers already have an external/
  unindexed classification (`cr35-local-data-probe/`). Conditional bindings
  correctly remain unresolved. The retained current-site example is
  `_WORD_RE.findall` in `query_primitives.py`, reached from keyword observation.
  Do not inspect regex/library implementation to close it. A later repair must
  reuse canonical export/declaration binding proof for local data, preserve
  conditional/ambiguous bindings and avoid claiming runtime dispatch. No product
  change is mixed into the in-flight twelve-workflow qualification candidate.
- Metadata-only holdout review checks each reserved commit against every admitted
  same-repository revision without extracting or inspecting reserved source
  (`backend-configuration-v1/holdout-metadata-review.json`). None is an ancestor
  of this catalog's source revisions. Non-ancestry does not establish semantic
  or task/oracle independence; all reservations remain unqualified. No hidden
  holdout is inspected or promoted during product tuning.
- Real captured source packets are independently attacked with wrong-before
  revision, missing anchor, truncation, unknown line coverage, forged member/
  line digest and wrong member path (`cr35-genuine-source-adversaries.json`).
  Controls require the actual current packet to pass first; originals remain
  untouched and every mutation must fail revision binding. This proves source
  provenance/completeness rejection only, not runtime configuration semantics.
  Missing workflow artifacts remain explicitly unobserved until acquisition
  finishes; no partial adversarial population is counted complete.
- Initial task-evidence audit exposes a separate product gap
  (`cr35-task-sufficiency-audit.json`): actual default-provider task packets omit
  the provider initializer/reference spelling, and the cached-yield task packet
  omits the generator/cache guard. Caller-nominated extra source reads expose
  these facts but do not prove their initial retrieval/composition. Do not turn
  source-line acquisition success into 5/5 or flip initial-evidence eligibility.
  A later generic observer repair must compose existing source/declaration facts
  around admitted literal source locators, with exact provenance and bounded
  omissions, preserving ownership/verification selection and the 4,000-token
  bound. Prove the gap with a neutral public regression before implementing it.
- The neutral public reduction now reproduces that gap with ordinary
  `settings.py` / `providers.py` / `declarations.py`, without framework or oracle
  filenames (`cr35-neutral-sufficiency/`). The literal source path is visible
  and ownership is resolved, but the declared `default_factory` spelling is
  absent from both full and decoded-initial task packets. The next production
  repair can turn this exact reduction into an owning regression and compose
  the existing backend-declaration observation around literal source locators.
  Keep runtime binding unknown and keep selection authority with its existing
  owner. The complete current-candidate workflow run remains unmodified.
- Inspected composition explains the omission: Tasks' class-declaration stage
  skips file-only locators and emits direct methods only. Generic annotated
  class/default syntax already belongs to StaticPythonBackendDeclarations and
  RepositoryDeclarations. Engine currently constructs Tasks before Declarations;
  any composition change must preserve the documented one-way dependency map
  and Source revision binding rather than instantiate a second analyzer/cache
  or independently reinterpret the default initializer.

CR-36 preserve caller-selected source anchors — 2026-10-18:

- The complete source review finds a genuine hard failure: constructor metadata
  requests six exact source anchors, but ordinary compact/text source-family
  caps expose only five. Native and structured observations retain line 75;
  compact/text CLI/MCP omit it. Four required source-presentation witnesses fail
  (`cr35-source-witness-accounting.json`). The failed candidate and unchanged
  source oracle remain retained; no required fact or check is removed.
- Twelve neutral public regressions fail on the parent at requested-anchor
  retention for 6/8/32 lines, both formats and competing literal matches
  (`cr36-anchor-parent.xml`). Classification: REFACTOR INTERNALLY in the existing
  evidence-presentation owner. Explicit source-member line requests use its
  existing 48-row bound and retain requested anchors before separately bounded
  literal matches. Source's own supported request bounds stay unchanged; all
  supported 32 anchors fit. Non-explicit source ordering/caps and native source
  facts, identities, freshness and uncertainty remain unchanged.
- The first focused source/context ring passes 49 cases. This is a projection
  repair, not a new source analyzer, general limit increase, repository-negative
  claim or semantic-runtime interpretation. Fresh exact-artifact, type,
  frozen-original test, transport and genuine-oracle requalification follow.
- Exact projection candidate `cr36-source-anchor-projection/source.zip`, SHA-256
  `67557fe8c2697cadb3e551a30c1126c46a7404bec09a414d59083bb50a30fe37`,
  source identity
  `sha256:48071785d7361338f4155e895fde3c01ea87874b09e1d778abc132df7dd74c7e`,
  observer
  `sha256:60afc9f52d69a54c6268ca7fa2a56123a362cd8be495b06771be535c520d0f18`,
  passes 116 independent extracted source/presentation/initial/workflow tests
  with zero skips (`cr36-anchor-extracted.xml`), plus current full Ty/Pyright.
  The complete twelve-workflow CR-35 run is terminal FAIL: 1,698/1,698 required
  source units observed, 1,694 PASS and four constructor line-75 compact/text
  presentation witnesses FAIL. All twelve genuine source-binding adversary
  sets reject their 84 mutations (`cr35-genuine-source-adversaries.json`).
  The same unchanged reviewed corpus is reacquired on CR-36; old evidence is not
  rebound and no failed check is removed.
- All 104 exact frozen original source/presentation/initial tests pass over the
  complete changed production tree, zero skips
  (`cr36-original-source-tests-receipt.json`). Pure reprojection of the exact
  retained CR-35 native packets passes all 210 required source display checks
  across 72 stage/format observations (`cr36-retained-projection-recheck.json`),
  preserving the original native packet identities. This is not substituted for
  fresh transport acquisition; the same-candidate full corpus is running, with
  a focused rerun of the previously failing constructor case also retained.
- The fresh focused constructor rerun passes every admitted common and source
  family gate on both revisions through API/CLI/official MCP
  (`cr36-constructor-focused/summary.json`): all 159 required source witnesses
  PASS, including the previously omitted line 75 in compact/text. Maximum
  required task initial cost is 2,662 tokens. Aggregate remains INCOMPLETE for
  the other eleven workflows and independent capability review. The complete
  CR-36 twelve-workflow population continues separately; its observed receipts
  are evidence only for completed units, never proof for the unfinished set.
- The full twelve-workflow run is now terminal: every admitted common gate
  passes, and all 1,698/1,698 required source witnesses PASS with zero missing
  members (`cr36-source-witness-accounting.json`). Observer-free pure regrading
  reproduces every outcome (`cr36-full-pure-regrade.json`). Aggregate remains
  INCOMPLETE because independent semantic/capability reviews and initial-evidence
  eligibility are still unresolved. These results remain bound to CR-36.

CR-37 initial declared-field disclosure — 2026-10-18:

- The retained genuine configuration audit and a neutral selected-file reduction
  reproduce a missing initial source fact: a file-only locator is visible while
  its annotated field's `default_factory`/provider reference is absent. Seven
  public cases fail on the parent; denied/outline controls pass
  (`cr37-field-parent-corrected.xml`). The parent source/test bytes are retained
  in `cr37-field-parent/source.zip`; no corpus oracle or review flag is changed.
- Classification: EXTRACT RESPONSIBILITY for task-local field disclosure,
  composed from the existing declaration owner rather than another parser or
  semantic graph. Tasks receives the canonical RepositoryDeclarations component
  through an explicit same-read-scope constructor dependency. Its bounded
  projection retains the existing static producer's values, exact field lines,
  source revision, provider/repository qualification and unknown runtime
  semantics. It changes no owner or selected verifier. Source-order class bounds
  count omissions; unavailable or empty observations cannot establish absence.
- A first affected run exposes a text projection omission; the native and
  compact/structured packets contain the field facts but initial text does not.
  The text owner now projects the same qualified context with its absolute
  native pointer. Focused parity, privacy, reopen, provider bounds, exact-artifact
  and genuine before/after qualification follow. This checkpoint does not claim
  architecture acceptance, initial sufficiency or any capability at 5/5.
- The frozen CR-37 artifact passes 192 independently extracted affected cases
  and 142 exact unchanged predecessor tests, zero skips, with full configured
  Ty/Pyright clean. Its genuine provider workflow is nevertheless FAIL:
  source facts, authority, revisions and transports pass, but newly exposed
  fields make required initial compact/text replies exceed 4,000 tokens
  (`cr37-provider-genuine/summary.json`). This failure is retained. Architecture
  locality observations also preserve unresolved orchestration/mixin call sites;
  no locality completeness waiver is claimed.

CR-38 bound initial field disclosure and preserve metadata — 2026-10-18:

- Full packets keep all admitted declaration values. Tasks supplies a bounded
  lexical field-name selection for the initial profile (three matching fields,
  or source order when there is no match). The pure initial projector consumes
  those indexes and records every excluded field plus original source indexes;
  it changes no owner, verifier or source coverage. Empty observations add no
  field supplement and do not establish absence.
- Compact/text scopes retain the selected exact field records and readable
  unknown/non-authority qualifiers. Explicit native metadata references preserve
  the rest of each supplied mapping, including future fields, false, zero and
  null. Independent consumer reconstruction and real CLI/MCP tests cover this
  contract; no opaque presentation codec or repository-specific rank rule is
  introduced. Source packet facts and qualification flags are not weakened.
- The first focused run finds an unchanged-test regression: adding empty field
  metadata unnecessarily changed an admitted owner row. Empty supplements are
  now omitted, and unchanged initial rows are preserved when no field is
  excluded. Current exact-artifact, full typing and genuine size qualification
  follow; no initial-sufficiency or 5/5 claim is made at this checkpoint.
- Exact candidate `cr38-field-initial/source.zip`, SHA-256
  `4212a13d3a956db2b5556e0146dba9bb550a85a6f7141641016f56cf5028607d`,
  source identity
  `sha256:1fe61c595d5f8543412dc82778a443cc61d31d3da55ebfcd788378bf30af8224`,
  observer
  `sha256:7fc74c6b4401d94cbd451ca267350b70357fed472ce9ad59281025526483fe91`,
  passes 195 independent extracted affected tests and all 142 unchanged
  predecessor tests over the complete new production tree, with zero skips.
  The three deliberately changed constructor/dependency-contract test owners are
  named in `cr38-original-field-tests-receipt.json`; no compatibility shim is
  used. Full configured Ty/Pyright, preflight, lock convergence and compileall
  pass. This result prose postdates the archive; the observed production and
  test bytes remain frozen.
- The fresh genuine provider workflow passes every admitted before/after
  API/CLI/official MCP gate (`cr38-provider-genuine/summary.json`). All 114
  source witnesses pass; maximum required initial cost is 4,000 tokens,
  including MCP's complete text/structured reply. Pure artifact regrading passes
  with observer construction and process launch forbidden
  (`cr38-provider-pure-regrade.json`). The aggregate remains INCOMPLETE for the
  eleven unselected workflows and independent capability/eligibility review.
- A separate source-authored correspondence check starts from the exact earlier
  CR-35 reviewed line-33 declarations and file hashes, without using observer
  outputs to construct expected values. Both revisions, full/initial API,
  CLI/MCP and their readable views pass all 60 observations, with exact native
  metadata recovery. All 32 wrong-revision/keyword/reference/line/path,
  missing-field, strengthened-runtime and strengthened-coverage mutations reject
  (`cr38-field-correspondence.json`). The before `default_factory=Provider` and
  after `default=dependency_provider` facts now appear in initial replies. This
  does not establish shared runtime provider identity, causal relevant-test
  coverage, the other initial-sufficiency gaps, or any complete 5/5 row.
- Comparable depth-three/1,024-bound locality observations cover the two
  constructor/orchestration stages before and after, plus four field-disclosure
  stages (`cr38-field-locality/summary.json`). All eight observations finish
  without incomplete caller bounds. Constructor and group projection resolve
  their repository calls, but the orchestration still has 16 unresolved calls,
  selector/composition scopes each retain the known regex-data call, and the
  attach stage retains two mixin calls. This is INCOMPLETE architecture evidence;
  these counts are per scope, overlap, and are not distinct-defect totals.

CR-39 admit the source-authored initial provider oracle — 2026-10-18:

- The existing before/after declaration oracle already pins the exact provider
  field, class scope, line 33, initializer keyword/reference and runtime unknowns.
  The corpus now checks those same source-authored values in initial task replies,
  with exact revision, incomplete coverage, unresolved correspondence/absence,
  and non-owner/non-negative-authority checks. Twelve checks per stage define
  216 required API/CLI/official MCP initial witness units before reacquisition
  (`cr39-required-initial-witnesses.json`). No task, source, prior oracle value or
  JSON scalar type, membership, threshold, review flag or eligibility flag changes.
- Pure regrading of the retained captures rejects all 216 units on the broken
  CR-36 source and passes all 216 on CR-38. Twenty-six missing/changed/strengthened
  fact mutations also reject (`cr39-initial-oracle-recheck.json`). The evaluator
  constructs no observer or process. Original receipts/outcomes remain intact;
  the new oracle has its own identity and does not retroactively rebind them.
- All twelve workflows and twenty-four source trees pass source admission under
  the augmented grader. Display, complete task/causal-test and capability review
  remain incomplete. Fresh acquisition under the new grader identity follows;
  a passing narrow initial source fact is not a complete task-sufficiency claim.
- Fresh candidate `cr39-initial-oracle/source.zip`, SHA-256
  `43086d4c04631c2ed75a0417f7441a415d810fe4e62e9eaf026f7fee1eaff2e9`,
  source identity
  `sha256:0ddc283c20ba054e71e3a9f9f3a1e0f9e5267b0dd96c642eebe72375a0e850fb`,
  retains the CR-38 observer/evaluator implementations and augments only the
  source-authored oracle/docs. All 48 independent extracted grader/source-workflow
  tests pass, zero skips (`cr39-oracle-extracted.xml`). No production, test or
  evaluator Python changes are required for this oracle addition.
- Its fresh before/after API/CLI/official MCP acquisition passes every admitted
  common gate, including the newly exercised `initial_evidence` gate
  (`cr39-provider-genuine/summary.json`). All 216/216 required initial witnesses
  are artifact/source-bound and PASS, zero missing
  (`cr39-initial-witness-accounting.json`); all 114 source-line witnesses also
  pass. Maximum required initial reply cost is 3,998 tokens. Observer-free pure
  regrading reproduces the outcomes and complete witness membership
  (`cr39-provider-pure-regrade.json`).
- Independent source-reviewed correspondence over these fresh artifacts again
  passes 60 native/readable observations and rejects 32 corruptions
  (`cr39-field-correspondence.json`). The eleven unselected workflows and
  independent display/task/causal-test/eligibility/capability reviews keep the
  overall result INCOMPLETE. Passing this source slice does not change any
  review or eligibility flag. Completed CR-39 acquisition has no live handle to
  restart. Result prose postdates the archive; qualified input bytes stay frozen.

CR-40 expose bounded task-local source excerpts — 2026-10-18:

- The genuine cached-yield source guard is not a call edge. A neutral public
  reduction reproduces the missing source text in eight parent cases, while
  denied/outline controls pass (`cr40-source-context-parent.xml`). The exact
  parent source/test archive is `cr40-source-context-parent/source.zip`.
- Responsibility: EXTRACT RESPONSIBILITY for bounded lexical source disclosure
  inside Tasks. Loaded identifier spellings in one caller-named Python file
  nominate up to three source lines using the existing query normalization and
  lexical match rules. Existing declared field spans are excluded from duplicate
  nomination. The process-local cached AST supplies candidate positions only;
  RepositorySource remains the sole byte/revision/line/context authority. No
  call edge, runtime conditional meaning, field compatibility, owner selection
  or verification selection is inferred. No new state/cache owner is added.
- Observer ownership note: observed evidence is exact selected repository lines;
  authority comes from canonical Source observations. Source freshness and
  completeness stay unchanged; separate lexical selection stays incomplete,
  bounded and non-negative. Tasks/Source are extended. Consumers still interpret
  behavior and choose edits/tests; execution stays external. Decision: OBSERVER.
- The first genuine API probe exposes the guard at line 65, but adds redundant
  source presentation and exceeds the then-current 4,000-token ceiling
  (`cr40-genuine-api-probe/summary.json`). Those measurements remain retained.
  The initial source view now preserves exact anchors/member/qualification and
  references remaining native metadata through one explicit `metadata_ref`.
  Consumer reconstruction retains all native/future values and JSON types.
  No admitted native source facts are deleted. Current pure reprojection of the
  same retained packets estimates 4,749 provider / 4,001 cached-yield compact
  tokens; this is not fresh CLI/MCP qualification.
- All seventeen neutral source-context tests pass, including source visibility,
  comments/strings, omissions, truncated AST lookup, reopen, output-format
  invariance, canonical Source equality and a causally controlled edit between
  lookup and observation. The user-authorized 6,000-token criterion has a direct
  valid-wire boundary regression: 5,999/6,000 accept, 6,001 rejects; no other
  population, oracle, threshold or review flag changes. Current full typing,
  broader affected tests and frozen genuine public qualification follow.

CR-41 complete source disclosure under the user-approved budget — 2026-10-18:

- The user explicitly approves a 6,000-token final initial ceiling while retaining
  every other acceptance requirement. The executable matrix owner and current
  plan targets reflect that change; old 4,000-token receipts remain unchanged.
- Source excerpts now prefer more matched query families, then locally rarer
  families and source order. Single-term assignments remain candidates. This
  repairs a second observed omission: the earlier multiword-only selector hid
  the genuine before-change `self.use_cache = use_cache` assignment. Source
  member admission is checked before AST reads and rechecked afterward; Source
  refusal overrides weaker index hints. No source refusal becomes absence.
- Exact candidate `cr41-source-disclosure/source.zip`, SHA-256
  `09dc1b1753eee11f6959e1d96237d64be4a37aaeb5ab1bcb0ee6f165e345ba24`,
  passes 264 independently extracted affected tests and all 179 unchanged
  predecessor tests, zero skips. The latter is an explicit test-only overlay;
  the closed architecture-family inventory is the only excluded changed
  contract. Full configured Ty/Pyright, source compilation, lock convergence
  and preflight pass. Observer identity is
  `sha256:da69abcf29da35a55861218714c3e7f47d5c05c4fe91e8fe605f15af1351ebbb`;
  evaluator identity is
  `sha256:48a34c591ef85a5115618d6a1a9add6925929adfb707f14c92d2c4a374c2544f`.
- The cached-yield initial oracle now comes from the earlier reviewed exact
  source lines: before assignment 74; after condition 65, raise 66 and message
  67. Path/member revision and anchor digest scopes bind the facts; source and
  lexical-selection qualification stay separate. Thirteen before and fifteen
  after checks preserve every existing oracle/task/source/review value and make
  no assertion that a guard was semantically absent before. Existing runtime,
  relevant-test, eligibility and capability review flags remain unchanged.
- Fresh before/after API/CLI/official MCP acquisition for default-provider and
  cached-yield passes every admitted common gate, including initial evidence
  and size (`cr41-genuine-public/summary.json`). The largest required initial
  reply is **5,333 tokens**, measured from actual MCP bytes; structured output
  is intentionally outside the compact/text ceiling. All **468/468** required
  initial witnesses pass, zero missing. Observer-free, process-free regrading
  rechecks exact artifact hashes and reproduces gates and witness membership
  (`cr41-pure-regrade.json`). The required membership was frozen from the oracle
  before capture completed; no delivered-fact average replaces recall.
- Independent source correspondence checks **120** native/readable observations
  against pinned file bytes, including every delivered anchor and context line,
  and rejects **56** mutations (`cr41-source-correspondence.json`). Restoring
  metadata from each initial view recovers the exact native Source packet.
  This delivered-fact integrity check is separate from the 468 required-fact
  recall witnesses. Both selected source-disclosure gaps are closed for this
  scope; runtime behavior and causal verification are not certified.
- Ten bounded locality observations retain complete caller accounting for their
  selected scopes, but locality remains INCOMPLETE. The supplement orchestrator
  has 17 unresolved calls; the source collector and ranker have three and one
  respectively, with overlapping scopes (`cr41-source-locality/summary.json`).
  These counts are observations, not distinct defects or permission to suppress
  uncertainty. Ten unselected configuration workflows and independent
  task/causal-test/capability review also keep overall qualification INCOMPLETE.
  Result prose postdates the archive; qualified code and oracle bytes stay fixed.
- The complete twelve-workflow CR-41 extension has now finished, reusing the
  two exact completed receipts. All twelve pass every admitted common gate and
  stay within 6,000; maximum actual reply remains 5,333 tokens. Observer-free,
  process-free full regrading reproduces all outcomes and artifacts
  (`cr41-full-pure-regrade.json`). Independent existing source-oracle membership
  closes **1,698/1,698** required source-fact/presentation witnesses, zero missing
  (`cr41-full-source-witness-accounting.json`); initial recall remains 468/468.
  The earlier two-workflow summary/regrade are separately preserved. There is
  no live CR-41 acquisition to restart. Semantic/causal-test/capability review
  remains incomplete; ten workflows have no admitted initial-sufficiency oracle.

CR-42 retain exact verification identity in initial readable replies — 2026-10-18:

- The CR-41 native cached-yield packet carries the exact regression test symbol
  and file revision; its readable verification locator drops both. Six neutral
  regressions reproduce the omission for structured/compact/text with unique
  and ambiguous test symbols (`cr42-verification-parent.xml`). The parent
  archive/observer and new regression bytes are recorded separately; no old
  candidate or test receipt is overwritten.
- Responsibility: REFACTOR INTERNALLY in the existing task presentation owner.
  One pure locator projection now preserves supplied test identity, revision,
  reference qualifications, selection authority, edit relationship and negative-
  evidence qualification in all three readable formats. Null remains null.
  Existing shared qualifier encoding handles repeated values; native packets,
  owner proof, selected tests and execution authority are unchanged.
- Independent source review records six existing regression declarations for
  four after-change problems, with exact imports/calls/assertions and source
  hashes (`backend-configuration-v1/verification-source-oracle-review.json`).
  Additive full/initial checks require path, symbol, revision and uncertainty
  together; either reviewed sync/async variant is accepted where applicable.
  Exact test labels extend task witness binding only, not native nominations.
  No before counterpart, runtime sensitivity or test sufficiency is invented;
  all original oracle values, tasks, review flags and eligibility are preserved.
- Exact candidate `cr42-verification-disclosure/source.zip`, SHA-256
  `b54176c5431db0c657f9c3bb0c147fb1ce1841aacf7d633ccaf21a837c1d8b4f`,
  passes 157 independently extracted affected/transport tests, zero skips.
  Its three fresh genuine default-provider, cached-yield and constructor-
  metadata workflows pass every admitted common gate; maximum required reply
  cost is 5,992 tokens (`cr42-genuine-public/summary.json`). Initial relevant-test
  checks pass after the latter two changes. Before-test counterparts remain
  unqualified, so the constructor workflow's combined initial-evidence gate is
  INCOMPLETE. No eligibility/review flag changes. Full typing passes on this
  candidate; later new-test typing issues belong to the CR-43 iteration.
- Source-authored probes expose two further initial test-identity gaps: bound-
  method and stateful-cleanup modules retain no unique test symbol. Equally
  relevant sync/async tests must remain ambiguous; a new oracle cannot authorize
  forcing one into selected identity. Their independently reviewed declarations
  are the missing disclosure (`cr42-existing-verification-probe.json`).
  The complete CR-41 twelve-workflow acquisition is now terminal. Its results
  are not rebound to later projection or oracle changes, which have their own
  candidate identities.

CR-43 disclose bounded test declarations without changing selection — 2026-10-18:

- Observer ownership note: Tasks exposes existing indexed test declarations
  around its already returned verification candidates. Reads/Index own symbol
  spans and current source revision; Files owns visibility. Lexical name
  matching remains incomplete and non-negative. It grants no ownership,
  verification selection, execution or sufficiency authority. No graph, cache,
  provider registry or lifecycle owner is added. Decision: OBSERVER.
- Responsibility: REFACTOR INTERNALLY in the existing task disclosure and
  presentation owners. Reuse the full generation-bound per-file symbol
  observation and existing query families. Return at most three matching
  declaration locators with exact source revision and explicit omitted count.
  The selected test symbol remains unchanged, including null. More matched
  query families, then locally rarer families, order lexical disclosure only.
  An initial genuine probe exposed source-order hiding of late bound-method
  tests; the repaired probe retains both reviewed declarations without choosing
  between them (`cr43-api-probe/`, `cr43-api-probe-02/`).
- Two corrected neutral probes fail over the complete unchanged CR-42
  production (`cr43-declarations-parent-valid.xml`). An earlier missing test
  import and a cache-directory refusal were invalid probes and do not count as
  semantic failures. The 90-test focused ring now passes, including preserved
  selection, tied/omitted declarations, rare late names, denied files, changed
  revisions, shared presentation qualifiers and scoped oracle alternatives.
- The same six source-reviewed regression declarations can be admitted as an
  existing unique locator or an exactly source-bound declaration. Positive
  scoped alternatives retain each scope's own path/revision/range and remain
  prohibited for authority checks. Eight positive controls pass; 56 wrong-path,
  revision, symbol, range, scope or authority mutations reject
  (`verification-declaration-oracle-review.json`). Tasks, source/test population,
  existing expectations, eligibility, thresholds and review flags are retained.
- Readable locators retain the complete new declaration context. Repeated
  qualification copies are removed only when identical values remain beside
  the exact referenced record. Unknown/different qualifications stay explicit.
  The earlier pure MCP-shaped estimates were at most 5,745 tokens for the four
  selected after-change probes. They remain estimates; fresh wire results below
  provide qualification.
- Exact candidate `cr43-test-declarations/source.zip`, SHA-256
  `94e7ff688b82408b536b31b03ca40a6df58dc8cefd955ab3faf8c83fba38eded`,
  passes **296** independently extracted affected/transport tests and all **287**
  unchanged predecessor tests, with zero skips, failures or exclusions. Full
  configured Ty/Pyright, current preflight, lock convergence and source
  compilation pass. Observer identity is
  `sha256:43e41a6a7b3cfaa0516e4d1c1ad3183393def4a700a99dbebfadcff78bc787e6`.
  Required membership was frozen before acquisition: **504** initial facts plus
  **36** default test facts, total **540** exact witnesses. Fresh before/after
  API/CLI/official MCP acquisition is complete for all five selected configuration
  workflows. Every admitted common gate passes, with maximum required initial
  reply **5,748 tokens** (`cr43-genuine-public/summary.json`). Before-test
  counterparts remain unknown in three cases; their combined initial-evidence
  gate stays INCOMPLETE rather than being promoted from after-only evidence.
- Observer-free, process-free regrading revalidates all retained artifact hashes,
  source bindings, gate outcomes and **540/540** independently required witnesses,
  zero missing (`cr43-pure-regrade.json`). Independent source/readable
  correspondence passes **150** observations and rejects **126** mutations
  (`cr43-correspondence.json`). Every delivered initial test locator and
  declaration context is recovered exactly, including unknowns and qualifiers.
  No review flag, metric eligibility, population or non-budget threshold changes.
- Twelve matched/introduced locality observations have complete selected caller
  bounds and zero unresolved-call counters, but locality stays **INCOMPLETE**:
  external/unindexed classifications still contain repository-candidate leads
  requiring independent qualification (`cr43-locality-external-accounting.json`).
  Candidate IDs alone prove no call target; a zero counter is not architecture
  acceptance. No external-library inspection or suppression is authorized.
- The original metadata-future and sender-node-failure tasks are now freshly
  requalified against the active core corpus on this same candidate
  (`cr43-core-public/summary.json`). Both pass all admitted fact, authority,
  revision, freshness, CLI/MCP, presentation, owner-top-three, initial-evidence
  and initial-size gates. Actual compact/text maxima are **4,527** metadata and
  **5,251** sender tokens. Their unchanged stage-specific initial oracles were
  already present; no oracle addition or eligibility change is needed.
- All **108/108** original core initial witnesses pass with exact membership
  (`cr43-core-original-initial-witnesses.json`). A separate pure audit also
  verifies the original source-reviewed changed-symbol/test-file facts across
  initial API and every CLI/MCP format, and independently reads declaration
  tables/text when facts occur there (`cr43-core-initial-audit.json`). Initial
  methods may remain class-declaration candidates; this does not resolve owner
  ambiguity or certify test execution. Both fresh acquisitions are terminal;
  no live capture remains to restart.
- CR-43's seven selected genuine workflows therefore close the demonstrated
  source/test-disclosure and 6,000-token failures in their stated scope. Overall
  qualification remains INCOMPLETE for broader corpus/oracle/capability review,
  the seven other configuration workflows on CR-43, architecture acceptance and
  final same-candidate product/native/economics/artifact qualification. Passing
  CR-41's full configuration population does not rebind that evidence to CR-43.
  Qualified code/oracle bytes remain frozen; result prose postdates the archive.
- The subsequent **complete twelve-workflow** CR-43 configuration extension is
  now terminal. It reuses all five completed receipts and passes every admitted
  common gate through before/after API/CLI/official MCP, max **5,748 tokens**.
  Pure full regrading reproduces retained gates, artifacts and source bindings
  (`cr43-full-pure-regrade.json`). All **1,698/1,698** required source witnesses
  pass with zero missing (`cr43-full-source-witness-accounting.json`), alongside
  **540/540** selected initial/default test witnesses. Earlier selected summaries
  are separately preserved. Independent semantic, causal-test and capability
  reviews remain incomplete; this is not a capability-11 or overall 5/5 pass.

CR-44 architecture correspondence and project-provenance conservation — 2026-10-18:

- A current CR-00/CR-43 definition census replaces stale introduction counts
  with an identity-bound source inventory (`cr44-stage-census/summary.json`).
  It accounts for 2,342 baseline and 2,474 current CodeMap definitions: 1,336
  unchanged, 294 exact AST moves, 65 restricted owner-annotation changes, 222
  changed definitions, 324 moved/new definitions sharing older names and 233
  new names. This is source correspondence, not automatic semantic, owning-test
  or locality proof. Constructors and same-name helpers remain unreviewed until
  actual responsibility correspondence is established.
- Six neutral receiver probes confirm dynamic/local receiver calls remain
  unresolved targets in the documented external/unindexed category; candidate
  IDs do not create exact calls. These conservative results do not justify an
  analyzer rewrite merely to lower locality counters. Architecture-wide
  external/unindexed qualification remains incomplete.
- Cross-repository owner review reproduces an observer defect through the real
  declared-project provider: parallel link kinds and the second path of a
  diamond are admitted in the native store, then silently lost when traversal
  skips an already visited project. The affected-project count can still say
  complete while provenance is missing (`cr44-project-cycle-probe/`).
- Responsibility: REFACTOR INTERNALLY under RepositoryNativeEvidence. Keep
  project selection, minimum depth and the caller's project bound unchanged.
  The existing reverse-edge observation now supplies distinct explicit
  provenance among the selected projects and observed traversal frontier.
  Existing kind/producer deduplication remains authoritative. No inferred edge,
  semantic graph, runtime action or new cache/authority owner is introduced.
- Nine public behavior tests now pass for verbose/compact/cross-repository and
  readable projections, parallel links, diamonds at the exact membership limit,
  cycles and exclusion of unselected projects. The focused pre-extraction ring
  passes 37 tests with two transport nodes deliberately not selected for that
  iteration. Final parent reproduction, exact extraction, unchanged predecessor
  tests, full transport/freshness rings and current typing follow.
- Final regression bytes reproduce **8 failures / 1 positive cycle control**
  over unchanged CR-43 production (`cr44-project-frozen-parent.xml`), with
  asserted import origin/observer and an explicit test-only overlay. No fixture
  import or operation-name error counts as semantic proof.
- Exact production candidate `cr44-project-provenance/source.zip`, SHA-256
  `6ee18871f76245e61190a4b7df0f71b08206cba352116d76175aab519f7f8e63`,
  passes **136** independently extracted affected/native/CLI/daemon/MCP tests,
  zero skips (`cr44-project-extracted.xml`). Observer identity is
  `sha256:effd97a12f37b95e4384b29b718ac4653ab0787bd73876d37d526f98c49f1890`.
  All **127** unchanged predecessor tests also pass over the complete new
  production, zero skips or exclusions (`cr44-project-original-receipt.json`).
  Five matched/introduced locality observations retain complete selected caller
  bounds, but one unresolved repository call and external/unindexed candidates
  keep locality INCOMPLETE (`cr44-project-locality/summary.json`). This does
  not qualify the whole architecture or genuine service corpus.
- The cross-repository family now has nine manually reviewed source/behavior
  slices bound to exact current public owning-test executions, including five
  exact AST moves (`cr44-cross-owner-review.json`). Constructor/read-scope and
  generation-routing changes are described explicitly; helper execution through
  public composition is not mislabeled standalone helper coverage. Positive
  resolved ownership/verification and full locality remain separate gaps.
- Matched 100-project parent/current/parent-repeat measurements use two warmups
  and nine samples (`cr44-provenance-economics/summary.json`). Medians are
  0.863 / 1.245 / 0.696 ms; fragment sizes 11,410 / 35,542 / 11,410 bytes.
  Project membership/depths stay identical and parent edges are preserved.
  Additional exact declared links explain the extra output/work; this is an
  explicit new-evidence cost, not an unchanged-packet performance improvement
  or full capability-20 qualification.
- CR-43's full twelve-workflow configuration extension is live on its original
  immutable extraction and reuses the five completed receipts. This production
  repair does not alter or restart that acquisition. Its result remains bound
  to CR-43, while CR-44 requires its own source identity and qualification.

CR-45 independent project-provenance benchmark checks — 2026-10-18:

- Reviewing the existing cross-repository scale benchmark exposes a false pass:
  complete project/depth recall plus an unchanged producer name can report
  `fully_correct` when a declared link is missing, invented or has the wrong
  kind. Its old source oracle also mirrors the producer's first-visit edge
  loss. These are benchmark evidence defects, not new product responsibilities.
- The existing benchmark now derives reachability independently as bounded
  fixed-point layers over its declared input edges, then retains the explicit
  edge set within that observed scope. Shared-input expectations include their
  declared contract links and already selected projects. No transitive shortcut
  is invented. The success gate separately requires exact relationship-set
  equality, no duplicate rows and the existing producer qualification; positive
  project/depth scores cannot compensate for missing or incorrect links.
- New mutations preserve 100% project/depth recall while removing, duplicating,
  inventing or relabeling relationships. The corrected checker rejects them.
  Fixed source expectations now distinguish the six-edge fan-in and five-edge
  diamond from their four-edge spanning trees. The eight generated source/
  shared-input workflows all pass exact relationship conservation on the
  repaired product (`cr44-scale-probe-02/`). These are synthetic development
  scenarios, not genuine service breadth or capability-16/20 qualification.
- Historical oracle failures, the incomplete shared-input oracle iteration,
  original identities and benchmark results remain retained. This stronger
  benchmark requires its own frozen source/evaluator evidence; it cannot
  retroactively certify an older result or substitute for the missing genuine
  cross-service population.
- Exact strengthened-oracle source `cr45-project-oracle/source.zip`, SHA-256
  `a9396dacd63bb30b8c073c700af1c39cf7ae8683f546e004f56487d3010467b4`,
  passes **79** extracted benchmark/project/freshness/public-transport tests,
  zero skips (`cr45-extracted.xml`). The standalone benchmark ring passes 15
  tests. Frozen-oracle pure controls reject six relationship corruptions despite
  perfect project/depth recall (`cr45-oracle-audit.json`). Production observer is
  unchanged from CR-44; benchmark source identity and results remain separate.

CR-46 same-name project declarations retain ambiguity — 2026-10-18:

- A genuine all-project observation of the frozen Hashmarks source fails before
  provenance comparison: eight admitted native-fixture package manifests share
  a package name, producing duplicate `project_node` keys. The complete failed
  observation is retained (`cr44-genuine-projects/`). These are explicitly
  admitted repository files; no dependency implementation is inspected.
- A neutral two-package reduction reproduces the publication failure, while a
  denied-duplicate control passes (`cr46-project-names-parent.xml`). Replacing
  insertion with last-writer-wins would invent unique ownership and is rejected.
- Responsibility: REFACTOR INTERNALLY in the existing npm project adapter.
  Duplicate names receive deterministic IDs from the explicit name/manifest
  pair, with ambiguous-name metadata and a warning. The dependency target map
  contains only unique names; ambiguous declarations can still originate
  independently proven edges to unique targets. Ordinary unique name identities
  remain unchanged. Encoding the explicit pair also prevents collisions with
  literal names using the declaration prefix. No core schema, store authority,
  dependency resolver, provider registry or execution behavior is added.
- Four semantic controls pass: duplicate publication without guessed targets,
  denied duplicate isolation, identity-prefix collision resistance and reopened
  observation after removal of name ambiguity. The first affected ring passes
  19 cases. Current full typing, exact parent replay/extraction, unchanged tests,
  genuine Hashmarks re-observation and final qualification follow.
- The final four new controls reproduce three failures and one denied-input
  positive on the complete unchanged CR-45 production
  (`cr46-frozen-parent.xml`). Exact candidate `cr46-project-names/source.zip`,
  SHA-256 `eaa92e8040a4acceb91cd18eb449b65968f560e779397828ca37cca83043bed5`,
  passes **234** independently extracted affected/public/native tests and all
  **230** unchanged predecessor tests, with zero skips, errors, failures or
  exclusions. Observer identity is
  `sha256:272c0c4224980de3bc0979dc2b953ddacd542338ade3296be50b96d63c818240`.
  Full Ty/Pyright, source compilation, preflight and lock convergence pass.
- Genuine Hashmarks publication/reopen now succeeds for all eight admitted
  same-name declarations (`cr46-genuine-projects/`). An observer-free,
  process-free audit re-proves each name/manifest-derived ID and exact source
  bytes (`cr46-genuine-project-source-audit.json`). The source has zero project
  edges: relationship conservation is explicitly INCOMPLETE for that population
  and cannot gain authority from this successful identity proof. Nonempty
  provenance is proved by the separate explicit-graph regressions/benchmarks.
- Six comparable npm-stage locality observations preserve complete selected
  caller bounds. Zero unresolved counters still do not close external/unindexed
  repository-candidate qualification (`cr46-locality/summary.json`). Current
  architecture correspondence therefore remains INCOMPLETE. The full CR-43
  configuration extension has now finished; no live acquisition remains to
  restart or relabel.
- CR-43's complete configuration extension remains live against its frozen
  producer; neither later project repair restarts or relabels those results.

CR-47 read-scope diagnostic failure cleanup — 2026-10-18:

- Internal-stage review of DecisionScope reproduces two lifecycle failures:
  failed diagnostics on exit leaves a non-null old scope/generation/cache at
  depth zero, and failed diagnostics initialization publishes a scope before
  entry succeeds. A failed newer diagnostic collection also exposes the older
  receipt as though collection had completed. These are existing owner defects,
  not permission to add a second lifecycle or diagnostic authority.
- Responsibility: REFACTOR INTERNALLY in DecisionScope. Fallible counter setup
  completes before publishing the read binding. Exit clears the old diagnostic
  receipt before collection and releases observation/generation/scope/caches in
  `finally`, preserving the diagnostic exception for the caller. Normal nested
  scopes, generation checks and fresh-read reuse remain unchanged. No new
  retry, execution, cache or repository generation owner is introduced.
- Three source-authored public-session controls exercise entry failure, exit
  failure, stale-receipt rejection and recovery with a distinct fresh scope.
  The first 28-case scope/freshness/diagnostic ring passes. Final parent replay,
  expanded input/source-binding tests, extraction, unchanged predecessor tests,
  current typing and comparable locality follow.
- All three final controls fail on complete unchanged CR-46 production with
  exact imported source/observer asserted (`cr47-scope-frozen-parent.xml`). The
  repaired six-file scope/freshness/input/source ring passes **53** tests. An
  optional test variable identified by full Pyright was initialized explicitly;
  the earlier CR-47 archive retains that test-only typing failure rather than
  being silently replaced.

CR-48 exact read-scope qualification and owning-stage review — 2026-10-18:

- Exact source `cr48-scope-qualified/source.zip`, SHA-256
  `f2f2606a54352be90ea4928b03fbe89fa90777069ad067ebfc4e9009168be2b5`,
  retains the CR-47 production repair and corrects only that test annotation.
  Observer identity is
  `sha256:06d0c46551d657d97274d10be4d343b54c2cfce9d5ffb7f7ee2b52838a855358`.
  All **158** independently extracted scope/publication/source/ownership/native
  LSP/CLI/IPC/official MCP tests pass, and all **155** unchanged predecessor
  tests pass over complete new production, zero skips/failures/exclusions
  (`cr48-extracted.xml`, `cr48-original-receipt.json`). Full Ty/Pyright,
  source compilation, preflight and lock convergence pass.
- Fourteen DecisionScope lifecycle/freshness stages now have manually inspected
  responsibility/source correspondence and exact executed owning-test evidence
  (`cr48-scope-owner-review.json`). Nested/ended scopes, input binding,
  incomplete generations, whole-observation source reconciliation, detached
  diagnostics and failure cleanup are individually scoped. Public composition
  coverage is not mislabeled standalone private-helper testing. Primitive bulk
  query/cache stages and other owner families remain separate unreviewed work.
- Twelve comparable parent/current locality observations use depth three and
  both 1,024 bounds. Selected caller accounting is complete and unresolved
  counters are zero; external/unindexed repository candidates still require
  qualification, so the report remains INCOMPLETE
  (`cr48-scope-locality/summary.json`). Neither the repair nor these tests waive
  complete architecture/internal-stage/caller/baseline qualification.
- A matched normal-path measurement uses the same source and 100 successful
  scopes per sample, two warmups/nine samples and parent repeat
  (`cr48-scope-economics/summary.json`). Medians are 8.572 / 8.212 / 8.954 ms.
  Source names and scope teardown agree; this shows no material regression in
  that bounded slice and is not full cold/warm/churn economics qualification.

CR-49 genuine producer–consumer data source intake — 2026-10-18:

- The missing capability-9 catalog now pins twelve genuine data-boundary changes
  across FastAPI, Litestar and FastStream, four per repository, with twenty-four
  exact Git trees (`backend-data-v1/source-catalog.json`). Existing exact source
  trees are reused only after content/commit identity checks. Archive hashes,
  selected component/test file hashes and direct parent revisions are verified
  independently (`cr49-data-source-intake/source-admission.json`). No reserved
  holdout source is inspected and no upstream repository is changed.
- Cases cover default serialization propagation, iterable and stream response
  metadata, dependency-produced frontend response metadata, serializer exception
  scope, nested/DTOData renamed fields, URL-encoded scalar representation, keyed
  null messages, decoded null caching, parser/decoder propagation and address
  declaration escaping. Distinct commits/triggers are source nominations,
  not a completed independent semantic-distinctness or causal-test review.
- Source-authored lexical review binds **53** exact declaration scopes and
  **809** direct-body source sites to pinned file/range/line hashes
  (`backend-data-v1/source-pair-review.json`). Observer-free/process-free
  revalidation passes every delivered fact. One before-stage helper is
  undeclared and remains a syntactic unknown, without semantic absence. An
  incorrectly nominated frontend helper was corrected from the pinned source
  before observer acquisition, preserving the original review and correction.
- This is **INCOMPLETE intake**, outside active campaign membership. All
  semantic/capability/distinctness flags stay false. The existing data-pair
  provider supports exact top-level functions, literal dict returns and direct
  named subscripts; many real nominations require methods, nested handlers or
  dynamic data observations. No guessed runtime pair, vacuous unknown-only
  capability pass, new graph or parser framework is added. Exact pair/test/
  unknown/eligibility/adversarial oracles and executable workflow/witness/
  transport/revision qualification remain required.
- Exact source-only intake artifact `cr49-data-intake/source.zip`, SHA-256
  `5a641fa9bf129f1416187c8571838b3e05dc74b47120f9fc0b33e3c646a6ae0f`,
  preserves CR-48 production/test/evaluator Python bytes and observer identity.
  Independent extraction checks source-review/catalog identity, false review
  flags and finite 12/3/24 input membership, then passes **59** existing grader/
  gate tests (`cr49-extracted.xml`). This is intake-integrity/evaluator proof,
  not executable data-workflow or capability qualification. Current preflight
  passes and qualified code/catalog/review inputs have zero drift.

CR-50 executable data source baseline — 2026-10-18:

- `backend-data-v1/suite.json` and `grader.json` admit all twelve pinned
  workflows using existing Source and changed-line function syntax surfaces:
  **143** positive physical-line facts and **24** direct call/argument stages.
  Cross-file nominations are observed separately; runtime data flow and pair
  compatibility remain unestablished. Only genuinely differing files enter
  changed-path membership. Source-authored oracle review precedes acquisition.
- All twenty-four trees pass executable admission. Pure re-derivation checks
  every source line, declaration, call and argument without constructing
  CodeMap or launching a process. **1,289** wrong/missing/truncated/stronger-
  authority mutations are rejected. Required source/call witness membership is
  frozen at **3,873** units before public acquisition. All capability and
  metric-eligibility reviews remain false; campaign membership is unchanged.
- Exact source ZIP `cr50-data-source-workflows/source.zip`, SHA-256
  `628892ace7928d5c7dcaa884c739ba494c003a809f9c6e85eff2815fea3dc9e5`,
  has observer `sha256:06d0c46551d657d97274d10be4d343b54c2cfce9d5ffb7f7ee2b52838a855358`.
  Its independent extraction passes **217** evaluator/source/boundary tests
  and **47** primitive read/cache tests, zero skips. The first socket-restricted
  batch was stopped as incomplete environment evidence; only the complete
  local-transport rerun counts. Current full Ty/Pyright, lock convergence,
  compilation and preflight pass.
- Frontend metadata, renamed DTOData and decoded-null cache workflows pass
  every admitted common API/CLI/official MCP gate on both revisions. Their
  exact receipts are terminal; the same-candidate twelve-workflow extension
  reuses them. `cr50-selected-data-public-summary.json` retains the selected
  result; the later full-population source inventory completes below.
  Owner and initial-answer recall remain ineligible/unreviewed.
- Source-only test review records **23** existing declaration scopes and
  **47** direct assertions (`cr50-data-test-source-review.json`). The serializer
  KeyError commit has no added test; the broad catalog nomination does not
  establish its regression. Two before test files are missing. URL-encoded
  status-only assertions do not prove exact scalar preservation. Runtime
  sensitivity, test sufficiency and complete verification admission stay open.
- `cr50-primitive-owner-review.json` independently reviews eleven scope-local
  symbol/file/module/reference/edge cache stages against executed owning tests
  and their recorded baseline. Symbols-for-paths/lexical stages, full qualified
  native/source locality and other architecture families remain incomplete.

CR-51 primitive read proof — 2026-10-18:

- Two direct read-owner tests now prove bounded symbol projection preserves
  later-file evidence and source edits, and normalized lexical-frequency reuse
  is released between scopes. Existing lexical path-scope coverage proves
  filtering precedes bounds and separates unscoped/empty/selected paths.
- Exact ZIP `cr51-primitive-proof/source.zip`, SHA-256
  `728336763ead32a4ccfea7e0205946783625a36bde37ff22d46c4a39cd402d42`,
  independently passes **52** primitive/source/cache/negative-evidence tests,
  zero skips. Full typing and preflight remain green. Production and evaluator
  bytes, observer identity and CR-50 executable oracles are unchanged; CR-50
  public acquisition remains bound to its original artifact and receipts.
- `cr51-primitive-owner-review.json` binds **fourteen** reviewed primitive
  cache/read stages to exact baseline/current source and executed owning-test
  assertions. This extends CR-48's lifecycle review and closes the specifically
  missing primitive-stage correspondence slice. It does not close other
  architecture families, full qualified locality, broader adversaries or final
  same-candidate qualification. The independent test-source review is retained
  as `backend-data-v1/test-source-review.json`; it changes no executable oracle.
- CR-50 admission controls also reject **108** wrong source/range/symbol/request
  and missing-display mutations without constructing an observer. These are
  evaluator sanity controls, separate from product and semantic adversaries.
- Fourteen current source-locality requests retain complete bounded caller
  scopes and zero reported unresolved sites, but **59** external/unindexed calls
  carry repository candidate IDs. Those IDs are not exact edge proof; broader
  native/source locality remains INCOMPLETE (`cr51-primitive-locality`).

CR-52 initial source-qualification compression — 2026-10-18:

- CR-50's Iterable workflow reproduces an official MCP compact budget failure:
  **6,284/6,285** tokens before/after, despite passing admitted fact, authority,
  freshness and revision gates. CLI compact stays at 5,990/5,991. The failed
  receipt is preserved; other formats and source facts must not be dropped to
  make it pass. The old twelve-case inventory continues on its own extraction.
- The canonical initial-presentation owner now factors JSON-identical source
  anchor/context qualification fields into explicit common mappings, retaining
  every row, optional field, source pointer and ordering. Missing, false, zero,
  floating zero and null stay distinct. Encoding is used only when smaller.
  An exact duplicate source qualification context is removed only when every
  field already appears identically in the displayed source record. Native
  evidence/identity, selection and standalone Source output are unchanged.
- Pure reprojection of retained packets measures the failing maximum at
  **5,924** tokens. Independent recovery reconstitutes all source values without
  repository observation or process launch. This is diagnostic/recovery proof;
  fresh CLI/official MCP acquisition remains required. The focused repair ring
  passes **66** tests and full configured typing/preflight pass.
- Frozen repair ZIP `cr52-source-qualifiers/source.zip`, SHA-256
  `bc1d8993db4972768ea68e3267b2505802cbed654463d116c3666a65a24e7907`,
  observer `sha256:676afd5f1ddbbcbead15c4644308fff2fdeef93ef3e55ae6d805848c191a80f1`,
  independently passes **208** affected presentation/evaluator tests, zero
  skips. Fresh genuine Iterable before/after API/CLI/official MCP acquisition
  passes every admitted common gate, with **324/324** required source/call
  witnesses and maximum initial compact/text response **5,923** tokens. The
  retained old 6,285-token failure is closed only for this exact repaired case.
  Do not relabel CR-50 receipts. The same-candidate twelve-case extension now
  passes every admitted common gate and **3,873/3,873** required source/call
  witnesses, zero missing/failed, max **5,923** tokens. Pure regrading re-proves
  exact receipt/artifact/source identities without observer/process construction.
  Semantic pair/test/adversarial/capability review remains INCOMPLETE.
- Exact unchanged predecessor tests over complete repaired production record
  **295 passes / 1 failure / 0 skips**. The failed compact source recovery test
  overlays the former flat record shape without expanding shared qualifiers;
  its unchanged text counterpart and all other behaviors pass. The updated
  independent recovery assertion expands both qualifier levels and checks
  exact JSON spelling/types, plus missing/optional/future fields. The original
  failure remains in `cr52-original-tests.xml`; it is an intentional public
  representation change, not an unchanged-test clean-pass claim.
- The complete current affected verification/presentation/evaluator ring then
  passes **297** tests from the exact CR-52 extraction, zero skips
  (`cr52-source-qualifiers/complete-affected-tests.xml`). Frozen Python and
  executable oracle inputs have zero drift. The old twelve-case inventory now
  completes all **3,873/3,873** required source/call witnesses, with zero missing
  or failed witnesses. Its only failed common gate is the retained Iterable
  size failure; the complete old report remains FAIL. Repaired population
  acquisition is now terminal with the clean admitted source baseline above.
- Matched compact-formatting measurements on the exact retained Iterable packet
  use two warmups, nine samples of fifty calls and an independent same-version
  control (`cr52-presentation-economics.json`). Before/current/noise medians are
  **2.449 / 3.010 / 2.624 ms**; presentation bytes fall **13,461 → 12,155**.
  The repair trades about half a millisecond of pure formatting work for smaller
  complete output. This is not a runtime speedup or full repository-economics
  claim. Independent recovery preserves exact values.

CR-53 distinct matching verification declarations — 2026-10-18:

- The genuine keyed-null workflow exposes its nominated test file but hides
  `TestPublish.test_publish_none_sends_a_real_tombstone` behind a different
  selected lexical test name. A neutral public regression reproduces the
  omission on unchanged production (`cr53-verification-parent.xml`). The
  source-authored after-test expectation also fails against retained genuine
  default/initial packets (`cr53-genuine-parent-failure.json`).
- The existing task evidence owner now retains bounded distinct matching test
  declarations even when the selected lexical name has an equal or higher
  match count. Selected test identity, canonical verification, candidate bounds,
  source revision, incomplete coverage and false selection/negative authority
  are preserved. No framework rule or runtime test claim is added.
- `backend-data-v1/verification-declaration-review.json` binds the added
  after-change regression test to exact pinned declaration/assertion bytes:
  literal null publication with a nonempty key, raw-value consumption and a
  null assertion. Eight wrong path/revision/symbol/missing controls reject.
  The before counterpart, runtime sensitivity and full capability review remain
  unqualified. All original assertions/tasks/source/review flags are preserved.
- Frozen ZIP `cr53-verification-alternatives/source.zip`, SHA-256
  `781226f2adbd836c6d1ffaaebd5cdb286e86670c9bc4589ddcc07ae640d40f59`,
  observer `sha256:753485cb271747c3f3a72cf40f61dc704998a34f7d26fbc1ef654f57db460787`,
  passes the initial 34-test focused ring, **204** extracted affected tests,
  zero skips, all **203** exact unchanged predecessor tests (zero skips or
  exclusions), and full configured typing/preflight. Fresh genuine before/after
  API/CLI/official MCP acquisition passes every admitted common gate, retaining
  all **354** original source/call witnesses and all **18/18** new after-test
  witnesses. The new test declaration and non-authoritative qualifications
  survive all six readable CLI/MCP formats; the selected lexical test name is
  unchanged. Maximum selected initial compact/text reply is **5,173** tokens.
  Combined initial-evidence remains unknown for the unreviewed before stage;
  runtime sensitivity and capability promotion are not established. Pure audits
  re-prove exact receipts/artifacts/source bindings without observer/process
  construction. CR-52's prior full source acquisition is terminal on its own
  unchanged extraction and must not be relabeled as CR-53.
- Current deterministic membership is frozen at **3,562** selected test nodes,
  **64** shards, plan identity
  `sha256:cb7d9a3073c947b0c63f26a393e5bce8455763b4a74a7417d223edb9b93ff9c4`
  (`cr53-regression-batches/selection.json`). Complete named batches zero and
  one pass; the remaining bounded batches run through the existing developer
  entrypoint. Partial/in-flight batches do not count. This is current regression
  work, separate from the historical full CR-25 result and broad backend score.

CR-54 selected-verifier freshness repair — 2026-10-18:

- Current full regression batch two stops on an existing provenance test:
  changing the selected test after sync returns `unknown` and drops that
  selection instead of preserving it as `stale`. The same test fails on CR-52,
  proving this predates CR-53 alternative declaration disclosure. Failed shard
  9 and complete batch logs are retained; batches zero/one remain historical
  CR-53 proof, and partial batch two does not count as a pass.
- A traced public operation selects the indexed verifier, then optional
  task-keyword enrichment reconciles that stale test and restarts selection.
  The second action has no verifier and the final state becomes unknown.
  The task-disclosure caller now skips keyword enrichment for an already stale
  candidate. The existing closing fence retains and qualifies the selected
  verifier as `stale` with `verification-changed-since-selection`.
- Direct keyword observation still rejects same-scope source drift through
  the canonical Source contract. An intermediate callee-level guard failed
  those tests and was removed; only caller-local optional admission changes.
  No test expectation, authority rule, retry mechanism or source-binding policy
  is weakened. Current focused provenance/disclosure/refresh/keyword tests pass
  **58** cases. Parent and repaired traces are retained separately.
- The exact repair ZIP is `cr54-verifier-freshness/source.zip`, SHA-256
  `d86916abef0acfa9506e01fbe3813a4f1d8bdd3a514d0d6d59df6645bfb047af`,
  observer `sha256:482c312e62ad01e87ae8b0590f568c75d6dff68e74841f2fca3f05eb3fb3b502`.
  Its independent extraction passes the same **58** focused cases. The failed
  named deterministic batch two now passes all four shards: **371** executed
  pytest cases, zero skips. Selection membership remains the recorded 3,562
  nodes/64 shards. Other batches are not silently rebound to this new candidate.
  Current full Ty/Pyright, preflight and lock convergence pass. CR-52's twelve-case
  source acquisition is terminal and passes its admitted baseline, separately
  from current CR-54 proof.

Next work after this checkpoint:

This retained list describes the deferred exhaustive qualification track.
For the user-approved active delivery, follow only S1–S6 in
[`STABILIZATION_PLAN.md`](STABILIZATION_PLAN.md); do not execute the corpus and
research expansion below as a stabilization prerequisite.

1. Preserve CR-43's complete twelve-workflow source/test/budget proof and the
   separate metadata/sender qualification. Both are terminal; do not restart
   them or relabel them with CR-46. Preserve CR-44/45 provenance/oracle and CR-46
   duplicate-name repairs with their exact parent/current/extraction evidence.
   Preserve CR-48 read-scope lifetime repair and its 158/155 extracted/original
   test proof. Preserve the terminal CR-50 failure inventory and CR-52 clean
   twelve-workflow source baseline and witness closure; complete exact source-pair/capability and causal
   test/adversary review. Intake/executable/source slices are not full capability
   qualification.
   Continue architecture/internal-stage and independent corpus review, then
   qualify all required public/native populations on the eventual final
   candidate. Complete independent
   relevant-test and capability review. The ordinary call index cannot supply a conditional guard; canonical
   Source now exposes its exact text without inventing a call edge or runtime
   behavior. Complete independent
   semantic/causal-test/adversarial review and required
   witness membership for all twelve configuration slices, then acquire the
   complete selected population on one final candidate. The two missing source
   slices and generic source-line acquisition/replay/witness integration are
   implemented at CR-34; do not redo them or add a redundant production parser.
   Source spelling still does not prove runtime provider/filter behavior.
   The complete CR-36 acquisition is retained; do not restart it. The separate
   CR-38 provider acquisition retains its earlier source-disclosure/size proof.
   CR-41 closes the cached-yield source guard; causal relevant-test gaps remain.
   CR-43 closes static disclosure of six reviewed after-change regression tests
   across four problems; missing before counterparts, default-provider identity
   sensitivity, non-init-field sensitivity and the other causal-test reviews
   remain unqualified.
   CR-31/32 close the measured repeated-work concern for the retained warm task;
   broader cold/churn economics and the unresolved locality site remain open.
2. Complete configuration/data capability review and the four missing source
   populations, independent oracles and witnesses. The Iterable disclosure and
   size failure is closed at CR-30; do not reopen it by hiding syntax facts or
   tuning ranks for an expected filename. Retained owner failures still need
   correction and current-candidate qualification.
3. Close introduced/internal-stage owning-test and pre/post baseline/locality
   correspondence. The 95-operation public review inventory is now closed for
   its recorded behaviors and named tests; it must not be redone or treated
   as complete internal-stage/architecture proof.
4. Complete CR-12 and Q-00–Q-05 on one eventual final candidate, including all
   corpus/oracle/witness breadth and retained current failures. The full goal
   remains unchanged and is not complete.

Continue CR-11 locality/caller/direct-test closure, then CR-12.
Complete structural-locality/read-binding/lifecycle
qualification and current full-project typing remain mandatory before the final
twenty-capability corpus/oracle/witness campaign can claim 5/5.
Use `.hashmarks/canonical-component-rewrite/` for the retained evidence. Earlier
`cr02-index-v2` extraction failures remain historical; three test call sites and
one repository-Git-only proof requirement were corrected in later qualification.
Full configured typing also passes for the current codec candidate. Full
architecture, structural-locality and the independent
twenty-capability 5/5 campaign are not complete.

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
   and current 6,000-token ceiling. Preserve earlier failing acquisitions.
5. If the component candidate regresses size or verifier retrieval, reproduce
   the generic defect in the relevant owner and repair it there. Do not raise
   the user-approved ceiling, delete facts, hard-code these repositories or alter oracle paths.

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

## 10. Deferred twenty-capability 5/5 research — nonblocking

This section is the unchanged future qualification specification. The user
explicitly deferred it from the stabilization finish line on 2026-10-18.
Do not execute Q-00–Q-05 automatically to complete stabilization, lower its
matrix minima or promote unreviewed capabilities. Resume it only as a separately
requested capability/release increment.

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

Seven catalogs still lack qualified populations: **8 handlers, 9 producer/consumer data, 11 DI/config,
15 dependency/build, 16 cross-service, 18 additional native evidence, and
20 economics**. Debugging has four problems from one repository and still needs
eight genuine problems across two additional repositories. Existing catalogs
also need their remaining qualification, not just source intake.

Handler source intake now contains twelve pinned problems over three repositories
in `backend-handler-v1/source-catalog.json`, outside active campaign membership.
Its semantic/capability review flags remain false. One genuine seven-expression
interface case has bounded source/transport proof; it does not qualify the full
handler population. Configuration source intake now also pins twelve changes
over the three admitted repositories in
`backend-configuration-v1/source-catalog.json`, with all twenty-four tree/file
identities independently rechecked. Its executable suite now covers twelve
source-authored declaration/call/exact-line slices. Corpus intake is executable;
complete semantic and capability qualification remain outstanding.
Semantic, capability and problem-distinctness reviews remain false, and it is
outside active campaign membership. Data-correspondence intake now pins twelve
nominations and twenty-four trees in `backend-data-v1/source-catalog.json`;
exact lexical source review and twelve executable source workflows are present,
while semantic pair/test/adversary review and public qualification remain
incomplete. The other four populations
remain to be built; all seven still need qualification. Current configured full typing is green; Q-04 still requires those
same gates on the eventual final candidate.

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
adversarial freshness detection, required presentation parity and the 6,000-token
initial ceiling. Required native/language/economics gates must have actual proof.

The evaluator must report twenty qualified rows with no required failure or
incomplete member. Full configured project checks and exact-artifact proof must
also be clean before the overall clean-pass claim. If any requirement remains,
publish the exact remaining gap and keep the overall result INCOMPLETE or FAIL.
No architecture result, test count or selected workflow pass substitutes for it.

## 11. Handoff and definition of done

The active entry point is S1–S6 in
[`STABILIZATION_PLAN.md`](STABILIZATION_PLAN.md). Preserve existing components,
repairs and historical failures. Do not re-enter the exhaustive per-stage/corpus
work or rewrite the architecture to close this milestone.

An implementation handoff must state:

- the last coherent completed package and exact source identity;
- actual component/API/state moves and obsolete paths removed;
- focused, integrated, transport, typing and extracted-artifact results with
  their scope and remaining uncertainty;
- any unfinished S1–S6 item, its exact missing proof and required next step;
- stabilization completion separately from the deferred twenty-capability result.

Stabilization is complete when canonical responsibility boundaries and supported
changed behavior pass their current contracts, full configured typing and
deterministic regression checks pass, the fixed representative genuine public
workflows and required witnesses pass with actual reply costs reported, and the source
artifact/extraction and final report are current. Exhaustive private-helper
locality, missing corpora, broad economics, unseen heldouts and wheel/sdist
promotion proof do not block this source milestone. Do not claim backend 5/5,
complete semantic correspondence or release certification: those require the
separate research/release evidence retained above.
