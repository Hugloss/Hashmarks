# CodeMap maintainer guide

This guide is for developers who need to change Hashmarks implementation code, especially developers who understand the public product but do not yet know where a behavior is owned.

It is deliberately **not** another product contract. Normative behavior remains in `docs/reference/`, `docs/integration/`, tests, and public API documentation. This file is a navigation map for the implementation.

## Why the code can feel hard to enter

`CodeMap` is composed from many responsibility-specific mixins. That keeps ownership boundaries explicit, but reading `engine.py` top-to-bottom does not reveal a request flow. A new maintainer therefore needs two maps before reading implementation bodies:

1. **Which module owns which fact or decision?**
2. **What path does a common request take through those owners?**

Do not infer ownership from import order or file size. Use the responsibility map below.

## The shortest mental model

```text
repository bytes / metadata
        │
        ▼
indexing_lifecycle.py ──► repository_index_store.py
        │                       │
        │                       ├─ files / symbols / refs / edges
        │                       └─ derived, rebuildable CodeMap state
        ▼
query / evidence producers
        │
        ├─ retrieval and context
        ├─ import and graph evidence
        ├─ ownership / impact / verification
        └─ freshness / repository-intelligence projections
        │
        ▼
consumer-facing bounded evidence
```

Canonical content identity is separate from CodeMap. CodeMap state is derived and reconstructible. Execution/certification is external.

## Responsibility map

### Construction and shared state

- `engine.py` — assembles `CodeMap` and initializes long-lived dependencies. Domain owners retain cache meaning and invalidation; shared fields do not transfer that authority to construction.
- `repository_index_store.py` — persistent derived CodeMap storage and bulk query primitives.
- `decision_session.py` — read-only, generation-bound reuse of immutable evidence inside one decision scope, including exact repository-intelligence snapshots when task, changed paths, and all bounds match.

### Indexing and repository ingestion

- `indexing_lifecycle.py` — discovery, incremental/full sync lifecycle, stale-row removal, preflight economics, base snapshot reuse, build-state publication.
- `index_watch.py` — foreground CodeMap watcher orchestration over the existing sync and observation authorities; it starts/stops the observer, publishes watcher state, and forces full reconciliation when observation continuity becomes UNKNOWN.
  - Discovery owns the admission-time file-size observation in an immutable internal record; preflight consumes that observation instead of re-reading file metadata. Later digest/freshness checks remain authoritative for indexing bytes.
- `parsers.py` — source parsing dispatch and parse-artifact keys.
- `index_surfaces.py` — classifies indexed paths into source/test/docs/config-like surfaces.
- `policy.py` — repository context/index visibility policy.
- `file_store.py` (in `hashmarks/`) — stable bytes/content digests; repository admission remains with discovery and qualified member observation remains with `repository_delta.py`.

### Retrieval and context

- `find_engine.py` — independent `RepositorySearch`, indexed search and retrieval-owned state.
- `task_retrieval.py`, `retrieval_diagnostics.py` — internal Search retrieval/ranking, bounded reuse and diagnostics over the same owner/cache.
- `query_router.py`, `query_primitives.py`, `query_surface.py` — query intent/formulation and public query projections.
- `repository_context.py`, `work_context.py`, `context_cache.py` — independent `RepositoryContext`, stateless supplied-action projection and borrowed context persistence.

### Repository relationships

- `import_resolution.py` — repository import identity/re-export resolution. **Produces import identity; does not rank ownership.**
- `evidence_graph.py` — independently constructed `RepositoryRelationships`, file/reverse cache validity and dependency/reference/project/affected/test queries.
- `native_evidence.py`, `evidence_freshness.py`, `project_graph.py`, `typescript_resolver.py` — independent native publication/qualification and producer translation.
- `relationships.py` — task adjacency and task relationship composition owned by `RepositoryTasks`.
- `structural_locality.py` — independent `RepositoryStructure`: structural search, fresh exact-symbol call/caller/navigation locality and forwarding-shape evidence. `structural_locality_model.py` owns typed packet values and serialization identity; `structural_locality_delta.py` compares supplied packets without constructing the live observer.

### Ownership

- `import_ownership.py` — static diagnostics for dynamic-loader/module-cache ownership hazards; not normal import resolution.
- `cache_ownership.py`, `cache_invalidation.py`, `concurrency_risk.py` — specialized repository ownership evidence.
- `ownership_analysis.py` — composes import/cache/invalidation/concurrency evidence into repository ownership findings.
- `ownership_graph.py` — independent `RepositoryOwnership`: risk/relationship observations, import-path reuse and candidate proof through `ownership_nomination.py` and the `ownership_candidate_*.py` algorithms.

### Change impact and verification

- `change_impact.py`, `post_change.py` — impact evidence around repository changes.
- `evidence_verification.py` — independent `RepositoryVerification`, with owner-bound scoped requests and no task-service dependency. `verification_relevance_model.py` holds explicit request/value bindings.
- `verification_plan.py` — bounded runner/argv projection for an already-known verification surface; it does not execute verification or choose repository work.
- `verification_explanation.py` — explanation projection over verification selection.

### Freshness and higher-level repository intelligence

- `evidence_freshness.py` — low-level fact-local freshness evidence used by graph/intelligence producers.
- `freshness_map.py` — consumer-facing freshness-map projection.
- `change_intelligence.py`, `repository_delta.py`, `evidence_profiles.py`, `cross_repository_evidence.py`, `intelligence_economics.py` — derived repository-intelligence projections. `repository_delta.py` owns snapshot composition and repository/observer delta vocabulary; inside one explicit decision session, an exact snapshot request may be reused by profile/economics/delta consumers without creating a second truth source.
- `repository_evidence_bindings.py` — independent `RepositoryBindings`, exposed by `CodeMap.bindings`, observes opaque consumer bindings through Source. `repository_evidence_binding_delta.py` and `repository_evidence_coverage.py` belong to that component; `repository_evidence_binding_validation.py` supplies pure retained-packet integrity checks. They do not create a second repository change/freshness model.
- `evidence_correlation.py` — independent `RepositoryCorrelation`, exposed by `CodeMap.correlation`, borrows Source and Bindings. `evidence_correlation_delta.py` compares explicit endpoints; `evidence_correlation_model.py` and `evidence_correlation_replay.py` own pure values and retained-packet integrity shared with diagnostics. Correlation owns only claim/correspondence/source-equivalence projection semantics; interpretation, causation, persistence, execution, and recovery remain external.
- `dependency_resolution_contract.py` — owns the v3 schema identity, semantic-authority vocabulary, and fail-closed dependency field allowlists, including the adjacent dependency-correlation request vocabulary; it contains no qualification or query behavior.
- `dependency_resolution_evidence.py` — owns typed producer-neutral external dependency-resolution observations. V3 separates logical components from concrete selections, resolved inventory from graph reachability, physical source format from semantic evidence authority, and resolution identity from the full qualified observation. One physical source may support several semantic authorities; core qualification must never infer authority from a Maven/uv/other producer kind or require a package-manager-specific source shape. It preserves multi-context relationships, contextual module/distribution ownership, compact producer-evidence references, scoped completeness/truncation, repository-generation binding, factual delta, and bounded traversal with explicit omissions. Distribution names never prove import ownership; ownership must be supplied independently and ambiguity is preserved. Package-manager syntax and parsing terminate in `hashmarks/adapters/*`; see `docs/reference/DEPENDENCY_EVIDENCE.md`. It does not run package managers, inspect dependency implementations, own repository-declared dependency intent, or duplicate `project_graph.py`, `import_resolution.py`, repository freshness/delta, or `evidence_correlation.py`.
- `dependency_resolution_derivation.py` — read-only derivation and explain projections from an already-qualified dependency observation. It reuses dependency qualification, identity, repository binding, and source authority; it owns only compact provenance/explanation shape and deterministic derivation identity. It can explain a caller-retained old endpoint without requiring current repository state. It does not create a history store, repository generation, provenance graph, or producer execution/redetection path.
- `dependency_resolution_delta.py` — factual before/after comparison for explicit qualified dependency endpoints. It reports repository identity and generation, semantic, adapter, producer, physical-evidence, coverage, and ownership change axes independently. Repository identity change is observed rather than rejected; caller endpoint selection does not become Git-lineage or causal authority. It does not reconstruct historical endpoints, infer causation, or introduce another repository-delta/history owner.
- `repository_declaration_contract.py` — producer-neutral cross-artifact declaration request contract: scoped correspondence/value-state validation, exact normalized equality/difference, and coverage-qualified absence. It owns no repository reads and no source precedence.
- `repository_declarations.py` — projection owner that binds declaration/provider claims to existing exact repository-evidence bindings, issues definition/observation identities, and preserves provider authority separately from repository authority.
- `repository_declaration_derivation.py` — typed read-only derivation/explain projection over an already-qualified declaration packet. It reuses declaration/group identities plus canonical repository-evidence binding identities and exact bound evidence, can explain a caller-retained endpoint without current-state lookup, and owns no provider semantics, history store, repository generation, or universal provenance graph.
- `repository_declaration_delta.py` — factual before/after declaration packet comparison only; it does not decide whether a changed value or correspondence is correct.
- `repository_file_discovery.py` — one format-neutral owner for repository-file admission and bounded traversal; indexing and declaration-provider discovery reuse it instead of creating parallel filesystem scanners.
  - Packaging import-root refresh, project-manifest discovery, project evidence admission, and manifest freshness also terminate at this owner. Producer-specific project parsers/native tools may discover semantic candidates, but denied/internal/pruned/symlinked repository files cannot become persisted/current project evidence.
- `repository_declaration_provider.py` — explicit provider SPI plus bounded revision-bound reads and tracked admitted path enumeration; no raw workspace handle, ambient plugin loading, or repository evidence ownership.
- `repository_declaration_discovery.py` — deterministic caller-selected provider composition and bounded admitted repository-file enumeration through `repository_file_discovery.py`, plus provider-run delta around the canonical declaration packet; no parser-format requirement and no second declaration or repository-evidence authority.
- `repository_intelligence_query.py` — thin query facade over those producers; it is not a second source of truth.

### Task evidence packets

- `configuration_evidence.py` — config-file evidence extraction/selection.
- `evidence_packet.py`, `evidence_decision_packet.py` — internal `RepositoryTasks` packet/brief composition over its existing scoped observation; no CodeMap inheritance or back-reference.
- `task_evidence_retrieval.py`, `task_evidence_scoped_method.py` — bounded source/declaration disclosure after canonical retrieval; supplements do not select an edit owner or verifier.
- `repository_tasks.py`, `task_entry_points.py`, `task_action_projection.py`, `task_verification.py`, `task_receipts.py`, `task_freshness.py` — independent task composition, one normalized observation, supplied owner/verification values and selected-authority freshness. `change_relationship_projection.py` projects supplied relationship values without querying Tasks or Changes.
- `ownership_candidates.py`, `ownership_candidate_evidence.py`, `ownership_candidate_resolution.py`, `task_action_projection.py`, `task_action_types.py` — existing task-specific candidate/owner composition. `ownership_decision.py` (in `hashmarks/`) owns the authority-proof semantics; intermediate candidate promotion is not a second final owner decision.
- `task_evidence_initial.py`, `task_evidence_types.py` — lossless initial codec and typed default/initial packet shapes. `evidence_presentation.py` (in `hashmarks/`) formats those facts without changing their authority.

## Start with an owner and its direct tests

The normative [cross-owner contracts](../reference/STATE_AND_SEMANTIC_OWNERS.md#cross-owner-operations)
define the boundaries. This table only helps locate implementation and tests;
it does not create another ownership registry.

| Requested change | Start with / operation | Direct test entry points |
| --- | --- | --- |
| Stable source/revision binding | `file_store.py::read_bytes_stable`, `indexing_lifecycle.py::RepositoryIndex._parse_or_reuse`, `repository_source.py::RepositorySource.member` | `test_file_store_metadata_portability.py`, `test_repository_evidence_bindings.py`, `test_codemap_publication_authority.py` |
| Admission or policy changes | `repository_file_discovery.py::RepositoryFiles`, `indexing_lifecycle.py::RepositoryIndex` | `test_repository_files_component.py`, `test_repository_file_admission_convergence.py`, `test_context_policy.py` |
| New parser or artifact mechanism | `parsers.py::parse_source`, `artifact_key_for`, `providers.py` | `test_codemap.py`, `test_python_call_definition_scope.py` |
| Query/storage mechanism | `repository_index_store.py`, `store_queries.py` | `test_efficiency_architecture.py`, `test_codemap.py` |
| Import/call identity | `import_resolution.py`, `structural_locality.py` | `test_structural_locality.py`, `test_structural_locality_import_call_scope.py` |
| Better task localization | `task_retrieval.py`, `task_evidence_retrieval.py` | `test_task_evidence_declaration_context.py`, `test_task_evidence.py` |
| Task-owner qualification | `ownership_candidate_resolution.py`, `task_action_projection.py`, `ownership_decision.py` | `test_task_action_map.py`, `test_decision_evidence_adversarial.py` |
| Relevant tests | `evidence_verification.py::RepositoryVerification.for_owner` | `test_verification_reference_fallback.py`, `test_task_evidence_candidate_verification.py` |
| Initial response or formatting | `task_evidence_initial.py`, `evidence_presentation.py` | `test_task_evidence_initial.py`, `test_evidence_presentation_contract.py` |
| Public operation / transport | `operation_contract.py`, `repository_cli.py`, `mcp_surface.py`, `codemap/service.py` | `test_operation_contract.py`, `test_codemap_service_client_protocol.py`, `test_native_evidence_transport.py` |

All test filenames in this table are under `tests/`. Add a mechanism inside its
existing owner; a new parser, query implementation, or wire format does not earn
another freshness, admission, ownership, or schema authority. Meaningful boundary
changes name their callers, dependencies, owned state, and direct tests in the
same change. Use the [component rewrite plan](../plans/CANONICAL_COMPONENT_REWRITE_PLAN.md)
for the current staged implementation and qualification. Files, identity
observation access, Index, DecisionScope, Source, Imports, Native evidence, Relationships, Structure, Search and Context are independent components;
the remaining domain compositions are still being migrated. Context nominates
instruction-query seed paths; Source observes already-selected path scopes.

## Trace common requests before reading everything

### `CodeMap.index.sync()`

Start here when indexing, stale state, discovery, or store contents look wrong:

```text
CodeMap.index.sync
  -> indexing_lifecycle._sync_discovery
       -> _discover / _discover_subtree
  -> _preflight_from_discovered
  -> _sync_begin_build
  -> parse/reuse + repository_index_store writes
  -> _sync_remove_stale_paths
       -> repository_index_store.paths_under()
       -> indexed exact/descendant path query
  -> derived graph/update bookkeeping
  -> complete build metadata
```

For incremental sync, distinguish three sets:

- **requested paths** — what the caller says changed;
- **discovered paths** — what currently exists and is indexable under that request;
- **stored paths** — previous derived rows that may now be stale.

Do not optimize one of those by silently changing the semantic meaning of another.

Stale-prefix reconciliation crosses a responsibility boundary: `indexing_lifecycle.py` owns *when* stale paths must be reconciled, while `repository_index_store.py` owns *how* persisted exact/descendant paths are queried. When profiling path-batch slowdowns, follow that handoff instead of assuming the lifecycle caller owns the query shape. Descendant lookup must remain segment-safe: `src` may include `src/a.py`, but must never capture lexical neighbors such as `src0` or `src2`.


### `CodeMap.index.watch_forever()`

```text
CodeMap.watch_forever
  -> index_watch.py
       -> hashmarks.watcher.create_default_watcher()
       -> CodeMap.index.sync()
       -> observation.ChangeTracker
```

Watcher backends remain in `hashmarks/watcher.py`; repository reconciliation remains in `indexing_lifecycle.py`; observation state remains in `observation.py`. `index_watch.py` owns only their foreground orchestration and must not create a second sync or freshness model.

### Repository-intelligence snapshot composition

When several derived surfaces need the same snapshot, trace the flow as:

```text
decision_session()
  -> repository_intelligence_snapshot(task, changed_paths, bounds)
       -> change_intelligence_brief
       -> evidence_freshness_map
       -> path/symbol/dependency projection
       -> generation-bound exact-request snapshot reuse
  -> profile / economics / delta derived from that snapshot
```

Snapshot reuse is **not** a persistent repository cache. It exists only while one explicit decision session is active, is keyed by the current CodeMap generation plus the exact task/path/bounds request, and is discarded when the session closes. Callers receive copies so mutation cannot alter the cached evidence. A changed generation, task, path sequence, or bound must recompute.

### `CodeMap.ownership.repository_graph()`

```text
repository_ownership_graph
  -> ownership_analysis
       -> import_ownership
       -> cache_ownership
       -> cache_invalidation
       -> concurrency_risk
  -> ownership_graph selection/projection where required
```

Reuse is allowed only when producer arguments and repository generation are equivalent. Scoped cache-invalidation candidates still resolve against repository-wide cache-owner evidence.

### Import-related ownership bug

Ask which responsibility failed:

```text
"What repository path does this import mean?"
    -> import_resolution.py

"Does this dynamic loading pattern bypass normal module ownership?"
    -> import_ownership.py

"Which candidate owns this task/path after evidence is available?"
    -> ownership_graph.py / ownership_analysis.py
```

Those are intentionally separate.

### Verification bug

Start at `evidence_verification.py` for relevance/selection or `verification_plan.py` for bounded runner/argv projection, then follow existing bulk/session helpers in `decision_session.py` and store primitives before adding a new cache or query API.

## How to choose where new code belongs

Use these questions in order:

1. **What fact does the code produce?** Put it with the producer of that fact.
2. **Is it only a projection of an existing fact?** Keep authority with the existing producer; make the new surface derived.
3. **Does it require repository bytes/state or execution results?** Execution results do not belong in Hashmarks.
4. **Would two modules become writers for the same fact?** Stop and redesign.
5. **Is a new cache necessary?** First look for operation-local or generation-bound reuse in `decision_session.py` and existing store bulk APIs.
6. **Is a new serialized state word or delta concept necessary?** Read `docs/reference/STATE_AND_SEMANTIC_OWNERS.md` and reuse the existing state family/owner first.

Every direct `CodeMap` mixin is a responsibility boundary and must be named in this responsibility map. CI enforces that rule so adding a mixin cannot silently add an undocumented semantic owner.

Before adding any evidence owner or public evidence schema, also complete the admission/persistence template in `docs/reference/STATE_AND_SEMANTIC_OWNERS.md`. The review must name existing owners first, state the missing fact, classify persistence, and justify any public Python or MCP promotion. A useful agent workflow is not sufficient admission evidence.

## Reading strategy for a new maintainer

Do not read every module in filename order.

1. Read `README.md`, `docs/reference/ARCHITECTURE.md`, and `docs/reference/PRODUCT_BOUNDARY.md`.
2. Read this guide.
3. Use `uv run hashmarks --workspace . orient` and `outline`/`refs` on the public method you are changing.
4. Read the owning module plus its focused tests.
5. Read adjacent producers/consumers only after you know the boundary being crossed.
6. Run the smallest focused test ring before the full bounded qualification suite.

A junior developer should be able to explain **producer → store/evidence → consumer** before editing a cross-module path.

## Things that are easy to misunderstand

- A mixin name in `engine.py` is not a call sequence.
- `all_file_rows()` is a materialization primitive, not an invitation to reconstruct repository-wide state repeatedly inside one composition.
- `decision_session.py` caches immutable evidence primitives only; it does not own final decisions.
- `import_resolution.py` and `import_ownership.py` solve different problems.
- `evidence_graph.py` no longer owns import resolution or freshness; those responsibilities were deliberately extracted.
- Git and merged pull requests preserve prior implementation decisions; historical handoffs are not a current documentation authority.
- Passing tests are necessary but do not justify moving execution, retry, certification, or agent reasoning into Hashmarks.

## When documentation must change with code

Update this guide when a change alters:

- module responsibility;
- a common request flow;
- producer/consumer boundaries;
- where a maintainer should begin debugging a class of problem.

Do **not** update it for every private helper rename. The goal is stable navigation, not a duplicate API reference.

### Exact task-identifier ownership discrimination

`CodeMap.tasks.action_map()` may use exact active symbol identity already present in canonical task rows to prevent a uniquely proven class/method/function owner from being displaced by a weaker structural continuation. This is discrimination over existing retrieval evidence, not a second ranker or a new discovery path. Multiple exact source owners remain ambiguous, test-only exact symbols never become edit authority, generic task wording still uses structural ownership, and literal repository paths retain their existing authority.

### Structural owner start accounting

When structural ownership is eligible, `CodeMap.tasks.action_map()` freezes the canonical retrieved rows before role display limits, then observes each distinct task-anchored source or test start and the existing selected start once. The action map exposes filterable `structural_starts` entries with start path, matched anchor terms, graph completeness and bounds, observed owner, and status; the decision packet carries a compact count/status summary. Competing observed owners or incomplete/stale start observations preserve ambiguity. A complete graph with no selected owner stays visible as `no-selected-owner` and does not assert a competing owner. The scope is the returned canonical hits plus the selected start: `retrieval_completeness` remains `unknown`, and `limit_reached` only describes the caller's retrieval bound. Neither the list nor a single observed owner proves repository-wide uniqueness.

### Decision-session task-action reuse

`CodeMap.tasks.action_map()` is a derived projection over canonical task evidence. Within one explicit `CodeMap.reads.session()`, the decision-session projection cache may reuse an exact projection keyed by repository generation, task, `limit`, and `per_role`. This is disposable performance state, not evidence authority: the first computation still performs normal authority-path freshness bookkeeping, callers receive deep copies, and a new session or generation recomputes.

### Decision-session change-impact owner-chain reuse

Repeated repository-intelligence surfaces can call `task_change_impact()` several times with one exact task-action request. the change-impact owner-chain cache may reuse only `_change_impact_owner_chain()` inside the explicit decision session, keyed by repository generation, task, and task-action `limit`/`per_role`. This is a derived owner-chain optimization, not freshness authority. `task_change_impact()` must still run its caller-reported path sync and declared-project freshness refresh on every call before the owner-chain cache can be consulted.

### Decision-session composition diagnostics

Use `with codemap.decision_session(diagnostics=True): ...` when measuring repository-intelligence composition. After the session, `codemap.decision_session_diagnostics()` returns `hashmarks.decision-session-diagnostics.v1` with a bounded producer span tree, inclusive and exclusive nanoseconds, unique semantic request counts, duplicate calls, cache hit/miss counters, and authoritative store-read counters already exposed by the session.

The receipt is runtime diagnostics only (`authority=runtime-diagnostics-only`, `storage=derived-not-persisted`, `execution_effect=none`). It must not become repository evidence, persistent telemetry, scheduling input, or an exporter platform. Normal decision sessions do not collect spans.

### Producer implementation provenance

`hashmarks.producer_identity.producer_implementation_provenance()` is an opt-in diagnostic projection over the exact Python package files already contributing to the producer implementation identity. It exposes only package-relative paths, byte counts, and content SHA-256 values. Use it to explain same-version byte drift or path/rename churn.

The projection does **not** make producer identity consumer-computable authority. The implementation identity remains Hashmarks-issued and opaque for conformance; absolute host paths, file contents, mtimes, and inodes are intentionally absent.


### Generation-bound ownership import-path reuse

Structural ownership expansion may revisit the same exact `(source_path, import_target)` request while one task-action decision traverses overlapping paths. Inside an explicit `CodeMap.reads.session()`, the import-resolution session cache may reuse that exact resolved repository-relative result for the current generation. This is disposable performance state only: the cache is keyed by generation + source + target, cleared at session boundaries, returns fresh lists, and never replaces import-resolution, visibility, freshness, ranking, or ownership authority.

### Build-state existence probe

`_sync_begin_build()` needs only the boolean distinction between an empty persisted file map and an existing one. Use `WorkspaceMapStore.has_files()` for that readiness decision rather than `stats()`, which counts unrelated persisted surfaces. This does not skip reconciliation or currentness work.
