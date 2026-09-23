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

- `engine.py` — assembles `CodeMap`, owns long-lived object wiring and generation-bound caches. It should not become the home for feature logic.
- `repository_index_store.py` — persistent derived CodeMap storage and bulk query primitives.
- `decision_session.py` — read-only, generation-bound reuse of immutable evidence inside one decision scope, including exact repository-intelligence snapshots when task, changed paths, and all bounds match.

### Indexing and repository ingestion

- `indexing_lifecycle.py` — discovery, incremental/full sync lifecycle, stale-row removal, preflight economics, base snapshot reuse, build-state publication.
- `index_watch.py` — foreground CodeMap watcher orchestration over the existing sync and observation authorities; it starts/stops the observer, publishes watcher state, and forces full reconciliation when observation continuity becomes UNKNOWN.
  - Discovery owns the admission-time file-size observation in an immutable internal record; preflight consumes that observation instead of re-reading file metadata. Later digest/freshness checks remain authoritative for indexing bytes.
- `parsers.py` — source parsing dispatch and parse-artifact keys.
- `index_surfaces.py` — classifies indexed paths into source/test/docs/config-like surfaces.
- `policy.py` — repository context/index visibility policy.

### Retrieval and context

- `find_engine.py` — core indexed search execution.
- `task_retrieval.py` — task-oriented retrieval/ranking and bounded result reuse.
- `query_router.py`, `query_primitives.py`, `query_surface.py` — query intent/formulation and public query projections.
- `repository_context.py`, `work_context.py`, `context_cache.py` — bounded context planning and context materialization.

### Repository relationships

- `import_resolution.py` — repository import identity/re-export resolution. **Produces import identity; does not rank ownership.**
- `evidence_graph.py` — file/reverse graph traversal, SCIP import, project enrichment.
- `relationships.py`, `project_graph.py`, `typescript_resolver.py` — relationship/project/language-specific enrichment.
- `structural_locality.py` — fresh exact-symbol call/caller/navigation locality and forwarding-shape evidence; observes repository structure only and never decides whether a refactor is desirable.

### Ownership

- `import_ownership.py` — static diagnostics for dynamic-loader/module-cache ownership hazards; not normal import resolution.
- `cache_ownership.py`, `cache_invalidation.py`, `concurrency_risk.py` — specialized repository ownership evidence.
- `ownership_analysis.py` — composes import/cache/invalidation/concurrency evidence into repository ownership findings.
- `ownership_graph.py` — consumes resolved repository identity and applies ownership visibility, expansion, ranking, and bounded graph selection.

### Change impact and verification

- `change_impact.py`, `post_change.py` — impact evidence around repository changes.
- `evidence_verification.py` — repository-derived verification relevance, ownership links, and selection evidence.
- `verification_plan.py` — bounded runner/argv projection for an already-known verification surface; it does not execute verification or choose repository work.
- `verification_explanation.py` — explanation projection over verification selection.

### Freshness and higher-level repository intelligence

- `evidence_freshness.py` — low-level fact-local freshness evidence used by graph/intelligence producers.
- `freshness_map.py` — consumer-facing freshness-map projection.
- `change_intelligence.py`, `repository_delta.py`, `evidence_profiles.py`, `cross_repository_evidence.py`, `intelligence_economics.py` — derived repository-intelligence projections. `repository_delta.py` owns snapshot composition and repository/observer delta vocabulary; inside one explicit decision session, an exact snapshot request may be reused by profile/economics/delta consumers without creating a second truth source.
- `repository_evidence_bindings.py`, `repository_evidence_binding_delta.py`, `repository_evidence_coverage.py` — opaque consumer binding projections over existing repository observation, member revision, relationship, freshness, completeness, and delta authorities. They may own binding declaration/projection shape but must not create a second repository change/freshness model.
- `evidence_correlation.py` — request-scoped correlation of bounded external/derived claims to existing repository member, symbol, binding, relationship, completeness, freshness, and delta authorities. It owns only claim/correspondence/source-equivalence projection semantics; interpretation, causation, persistence, execution, and recovery remain external.
- `dependency_resolution_evidence.py` — owns typed producer-neutral external dependency-resolution observations, explicit module/distribution ownership observations, resolution definition/observation identity, comparability, repository-input correspondence, repository-import/dependency correspondence, and factual dependency delta. Distribution names never prove import ownership; ownership must be supplied independently and ambiguity is preserved. It does not run package managers, inspect dependency implementations, or duplicate `project_graph.py`, `import_resolution.py`, repository freshness/delta, or `evidence_correlation.py`.
- `repository_intelligence_query.py` — thin query facade over those producers; it is not a second source of truth.

### Task evidence packets

- `configuration_evidence.py` — config-file evidence extraction/selection.
- `evidence_packet.py`, `evidence_decision_packet.py` — bounded evidence packet composition.
- `repository_task_action.py`, `task_action_evidence.py`, `task_action_projection.py`, `task_action_types.py` — repository evidence used by an external consumer to decide work; Hashmarks itself does not execute the work.

## Trace common requests before reading everything

### `CodeMap.sync()`

Start here when indexing, stale state, discovery, or store contents look wrong:

```text
CodeMap.sync
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


### `CodeMap.watch_forever()`

```text
CodeMap.watch_forever
  -> index_watch.py
       -> hashmarks.watcher.create_default_watcher()
       -> CodeMap.sync()
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

### `CodeMap.repository_ownership_graph()`

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

`task_action_map()` may use exact active symbol identity already present in canonical task rows to prevent a uniquely proven class/method/function owner from being displaced by a weaker structural continuation. This is discrimination over existing retrieval evidence, not a second ranker or a new discovery path. Multiple exact source owners remain ambiguous, test-only exact symbols never become edit authority, generic task wording still uses structural ownership, and literal repository paths retain their existing authority.

### Decision-session task-action reuse

`task_action_map()` is a derived projection over canonical task evidence. Within one explicit `CodeMap.decision_session()`, HM278 may reuse an exact projection keyed by repository generation, task, `limit`, and `per_role`. This is disposable performance state, not evidence authority: the first computation still performs normal authority-path freshness bookkeeping, callers receive deep copies, and a new session or generation recomputes.

### Decision-session change-impact owner-chain reuse

Repeated repository-intelligence surfaces can call `task_change_impact()` several times with one exact task-action request. HM280 may reuse only `_change_impact_owner_chain()` inside the explicit decision session, keyed by repository generation, task, and task-action `limit`/`per_role`. This is a derived owner-chain optimization, not freshness authority. `task_change_impact()` must still run its caller-reported path sync and declared-project freshness refresh on every call before the owner-chain cache can be consulted.

### Decision-session composition diagnostics

Use `with codemap.decision_session(diagnostics=True): ...` when measuring repository-intelligence composition. After the session, `codemap.decision_session_diagnostics()` returns `hashmarks.decision-session-diagnostics.v1` with a bounded producer span tree, inclusive and exclusive nanoseconds, unique semantic request counts, duplicate calls, cache hit/miss counters, and authoritative store-read counters already exposed by the session.

The receipt is runtime diagnostics only (`authority=runtime-diagnostics-only`, `storage=derived-not-persisted`, `execution_effect=none`). It must not become repository evidence, persistent telemetry, scheduling input, or an exporter platform. Normal decision sessions do not collect spans.

### Producer implementation provenance

`hashmarks.producer_identity.producer_implementation_provenance()` is an opt-in diagnostic projection over the exact Python package files already contributing to the producer implementation identity. It exposes only package-relative paths, byte counts, and content SHA-256 values. Use it to explain same-version byte drift or path/rename churn.

The projection does **not** make producer identity consumer-computable authority. The implementation identity remains Hashmarks-issued and opaque for conformance; absolute host paths, file contents, mtimes, and inodes are intentionally absent.


### Generation-bound ownership import-path reuse

Structural ownership expansion may revisit the same exact `(source_path, import_target)` request while one task-action decision traverses overlapping paths. Inside an explicit `CodeMap.decision_session()`, HM284 may reuse that exact resolved repository-relative result for the current generation. This is disposable performance state only: the cache is keyed by generation + source + target, cleared at session boundaries, returns fresh lists, and never replaces import-resolution, visibility, freshness, ranking, or ownership authority.

### Build-state existence probe

`_sync_begin_build()` needs only the boolean distinction between an empty persisted file map and an existing one. Use `WorkspaceMapStore.has_files()` for that readiness decision rather than `stats()`, which counts unrelated persisted surfaces. This does not skip reconciliation or currentness work.
