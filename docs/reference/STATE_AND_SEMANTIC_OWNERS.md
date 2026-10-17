# Repository state and semantic ownership

**Status: normative maintainer reference.** This document maps repository-intelligence state families to their canonical owners. It exists to prevent a new consumer surface from accidentally inventing a second freshness, delta, relationship, or observation model.

Hashmarks may expose many projections, but a projection does not become a new semantic owner merely because it has a new schema.

## Rule: reuse before adding

Before adding a new state field, state word, delta, identity, freshness result, completeness result, or relationship classification:

1. identify the repository fact being represented;
2. find its canonical owner below and in `docs/maintainers/CODEMAP.md`;
3. extend or project that owner instead of recreating the fact;
4. if no owner exists, document the new owner and why the existing owners are insufficient in the same change;
5. keep new consumer-facing schemas derived from the owner rather than creating parallel generation, cache, graph, or history authority.

A new schema is **not** evidence that a new semantic owner is needed.

## Cross-owner operations

A canonical owner is a responsibility, not necessarily one class or file.
`CodeMap` wires these responsibilities together; its shared `self` does not make
every mixin an authorized writer of every field. Construction may initialize
owned state without acquiring that state's semantic or invalidation authority.

The following existing boundaries are the starting points for changes. They do
not introduce a dispatcher, interface registry, or new public API.

| Responsibility | Existing operation / owner | Contract for consumers |
| --- | --- | --- |
| Stable bytes and content digest | `file_store.py::FileDigestStore.read_bytes_stable` | Returns bytes and their digest from one stable read, or fails with an unavailable/unstable read. It does not establish repository admission, index freshness, or publication. |
| Identity observation source | `repository_observation.py::RepositoryObservationSource.observe` | Reads one atomic observation through its narrow reader. Unavailable/incompatible transport returns unknown (`None`); the source does not cache observations or depend on CodeMap/indexing. Read scopes own reuse. |
| Repository-file admission | `repository_file_discovery.py::RepositoryFiles.is_admitted`, `iter_files`, `visible_file`, `visible_manifests` | Independently constructed owner of admission/traversal and the loaded policy. `CodeMap.files` is a read-only component reference. Host/control roots are canonicalized once; member symlinks remain excluded. Parser support, readable bytes, and complete semantic coverage are separate questions. |
| Qualified member observation | `repository_source.py::RepositorySource.member` | Composes admission, member revision, availability, and optional bytes. Binding, declaration, and correlation consumers reuse this independent Source owner; ingestion uses stable bytes directly and cannot call back through Source. |
| Consumer evidence bindings | `repository_evidence_bindings.py::RepositoryBindings`, exposed by `CodeMap.bindings` | Owns opaque binding observation, exact endpoint comparison and changed-scope coverage over Source and its read scope. It has no Tasks, packet or root dependency. `repository_evidence_binding_validation.py::validate_bindings_packet` owns pure retained-binding integrity checks, reused by binding delta, declarations and diagnostics. Definition, member revision and completeness remain independent. |
| External evidence correlation | `evidence_correlation.py::RepositoryCorrelation`, exposed by `CodeMap.correlation` | Borrows Source and Bindings to qualify external locator claims and compare explicit endpoints. `evidence_correlation_model.py` owns pure projection values; `evidence_correlation_replay.py::CorrelationPacketValidation` owns retained-packet integrity. Diagnostic validation reuses those pure checks without constructing a live correlation service. External claims, source equivalence, completeness and repository freshness do not strengthen one another. |
| Generation-bound read scope | `decision_session.py::DecisionScope.session`, exposed by `CodeMap.reads` | Owns primitive query reuse and diagnostics for one existing store generation and atomic identity observation. Nested scopes share an immutable `ReadScope` value. Ended scopes cannot supply another scope's final task/snapshot/impact/ownership memo; those paired memo values remain domain-owned. The static `ReadScopeOwner` port has no state, registry or runtime policy. |
| Parsed artifact | `parsers.py::parse_source`, `artifact_key_for` | Interprets supplied source under the supplied content revision and parser signature. File-backed ingestion must bind the supplied digest to the bytes actually parsed. Mechanisms do not own repository admission or generation. |
| Index publication | `indexing_lifecycle.py::RepositoryIndex.sync` and `repository_index_store.py::publication_transaction` | The independently constructed Index owns ingestion/reconciliation and import-root projection. The store owns atomic derived writes. Consumers call `CodeMap.index`; the old root sync/preflight/clean/watch entry points are removed. Index has no source/read-scope/relationship-cache dependency. |
| Qualified import identity | `import_resolution.py::RepositoryImports` | Produces bounded repository import/re-export identity. Retrieval, relationship, and verification consumers preserve unresolved/ambiguous results rather than resolve again by short name. |
| Native evidence | `native_evidence.py::RepositoryNativeEvidence`, exposed by `CodeMap.native` | Owns producer import/enrichment, repository admission before publication, and source/provenance freshness qualification through its internal `EvidenceFreshnessMixin`. It consumes Files, Source, DecisionScope and the existing store publication transaction directly; it has no CodeMap or relationship-owner back-reference. Producer translation stays in native adapters. |
| Structural observations | `structural_locality.py::RepositoryStructure`, exposed by `CodeMap.structure` | Owns bounded structural search, source-qualified direct calls/callers, locality and related test-path projection. It borrows Source, Imports, Native and Relationships directly. The filesystem lifecycle analyzer receives Source, Imports, Relationships and one typed direct-call resolver rather than a component back-pointer. Typed packet values and their existing serialization identity live in `structural_locality_model.py`; pure supplied-packet comparison lives in `structural_locality_delta.py`. No task policy or verification-selection owner is a dependency. |
| Candidate retrieval and reuse | `find_engine.py::RepositorySearch`, exposed by `CodeMap.search` | Owns indexed find/task retrieval, ranking, single-flight, bounded query results and retrieval-contributor freshness. Its internal retrieval/diagnostic implementations share this owner. Selected/recent authority paths belong to Tasks. Search exposes immutable cached contributor inputs for reconciliation without claiming currentness; foreign components cannot mutate its caches. A find result carries its original normalized route into presentation. |
| Repository ownership and proof | `ownership_graph.py::RepositoryOwnership`, exposed by `CodeMap.ownership` | Owns repository risk/relationship observations, import-path reuse, candidate nomination and final ownership proof. Internal `ownership_candidates.py`, `ownership_candidate_evidence.py`, `ownership_candidate_resolution.py` and `ownership_nomination.py` preserve the existing algorithms. Analyzers consume Source, Imports and exact relationship/query capabilities rather than CodeMap or Ownership as a service bag. Nomination and proof reject an expired or different read scope. |
| Owner-bound verification | `evidence_verification.py::RepositoryVerification`, exposed by `CodeMap.verification` | Consumes a scoped `VerificationRequest` containing normalized task input, explicit nominee/admitted/unresolved status and supplied owner/test candidates. It has no Tasks or CodeMap dependency and cannot select edit authority. Relevance, declared test plans and explanation/correspondence projections preserve completeness, reference identity and unknowns. |
| Task observations and authority freshness | `repository_tasks.py::RepositoryTasks`, exposed by `CodeMap.tasks` | Owns normalized `TaskObservation` reuse, task action/entry/verification views, receipts and bounded selected/recent authority-path freshness. One active read scope binds the observation and its normalized query; ended scopes cannot replay it. Ownership nominates/finishes proof and Verification returns qualifiers through explicit values. Source owns the shared mechanics of caller-supplied contributor reconciliation/restoration. No execution or certification state is introduced. |
| Context disclosure and reuse | `repository_context.py::RepositoryContext`, exposed by `CodeMap.context.build` | Owns disclosure assembly, instruction-query seed nomination, context single-flight and the meaning of its borrowed `ContextCache`. Source still owns qualified bytes and explicit instruction-path observation. Stateless supplied-action disclosure/role accounting belongs to its `WorkContextProjection` implementation in `work_context.py`; it needs no CodeMap or repository resource construction. |
| Repository relationships and reuse | `evidence_graph.py::RepositoryRelationships`, exposed by `CodeMap.relationships` | Owns dependency/reference/project/affected/test observations and the meaning, contents, and validity of its reverse-graph cache. Cache hits require the published generation and the same freshly qualified native-edge inputs. Index no longer calls or writes this upper cache. A no-change sync may reuse it; source/manifest disqualification of native evidence must invalidate reuse even without a new generation. Search owns recent-change query bias; Tasks owns task-seeded adjacency. Neither responsibility is a dependency of this component. |
| Task retrieval | `task_retrieval.py::_find_task_evidence_impl`; bounded disclosure in `task_evidence_retrieval.py` | Produces ranked candidates and explicit bounds. Retrieval rank and source supplements are not ownership or verification proof. |
| Task-owner qualification | `RepositoryOwnership.nominate`, `qualify`, existing `ownership_decision.py` | Ownership establishes the candidate and finishes its qualified proof from supplied verification facts. Tasks composes and projects those values. Intermediate candidate selection is distinct from the final ownership proof; later source-local test disclosure cannot replace task-owner-bound reference facts. |
| Verification relevance | `evidence_verification.py::_verification_relevance` | Consumes the already-selected edit surface and qualified references/locality. Returns relevance, uncertainty, bounds, and selection evidence; never test sufficiency or execution results. |
| Consumer projection | `evidence_packet.py`, `task_evidence_initial.py`, `evidence_presentation.py` | Composes or projects owner-produced facts while preserving qualification and omission accounting. A format cannot independently resolve ownership or source authority. |
| Operation/schema identity | `operation_contract.py` | Domain operations and CLI/MCP/service adapters consume the same registered operation/mode/schema. Domain validation, untrusted-wire validation, and presentation conformance remain distinct boundaries. |

When a meaningful boundary changes, document the operation's owner, typed inputs
and outputs, bounds and revision requirements, state effects, callers and
dependencies, errors, preserved invariants, replaceable mechanism, and direct
owning tests. An existing typed function plus its tests can express this
contract; a new interface class is not required.

Trace operation dependencies rather than treating the mixin inheritance list as
a semantic dependency graph. In particular, qualified member reads may request
index reconciliation. Indexing must not call back through that reconciliation
path merely to obtain bytes; it uses the stable-byte mechanism after admission.
Keep coordination with the existing composition owner, and preserve fail-closed
validation at every untrusted boundary.

## State families are separate axes

Similar-looking state words are not interchangeable. A consumer must know which axis a value belongs to. New public schemas must reuse the canonical state spelling for an existing axis rather than introduce a local synonym.

| State family | Meaning | Canonical owner | Extension rule |
| --- | --- | --- | --- |
| Repository continuity | Whether the observer has a clean, dirty, or unknown repository observation | `hashmarks/observation.py::ObservationState` and `client.py::RepositoryObservation` | Reuse the atomic observation. Never reconstruct continuity from separate samples. A standalone CodeMap watcher must first acquire the persisted continuity authority with an atomic owner/fence claim; every later publication must match that fence, and a replacement owner advances it so stale writers cannot overwrite current continuity. |
| Repository / CodeMap generation | Which admitted derived repository state a projection is bound to | CodeMap store + `decision_session.py` | Reuse the existing generation. Do not create feature-local generations. Clearing a bound store atomically advances this same generation and preserves its counter, so rebuilding cannot resurrect an older cached/read-scope authority. Retained native/project enrichment that can affect a decision must publish its rows and freshness binding atomically under this same generation authority. Mutation-then-read operations must bind the entire post-mutation composition to the exact generation they published; generation drift before or during composition fails closed. A worktree overlay must capture the exact base generation and workspace fingerprint at overlay sync; fused reads fail if either base authority moves, and only an explicit overlay resync may adopt a new base. |
| Repository identity | Content/repository identity independent of a consumer projection | canonical identity owners; existing packet repository binding projected by `DecisionScope.repository_identity()` | A projection may reference identity; it does not redefine it. Neutral `packet_digest`/`evidence_identity` functions in `repository_observation.py` preserve existing digest domains/encoding without owning domain semantics. |
| Member revision | Content identity of one admitted indexed repository member | CodeMap file row / repository-intelligence snapshot path revision | Reuse the indexed revision semantics. A projection must distinguish missing, unindexed/unknown, denied/unsupported, and present members rather than treating them as one state. |
| Evidence availability | Whether a requested repository fact is known present, known absent, unavailable/unknown, or unsupported | repository-intelligence evidence producers; endpoint delta vocabulary is coordinated by `repository_delta.py` | Do not invent synonyms in a new packet. Add a new value only at the owning evidence layer. |
| Freshness | Whether a previously observed fact is still current for the claim being made | transport-neutral `hashmarks/freshness.py` owns the serialized vocabulary/classifier; `evidence_freshness.py`, `freshness_map.py`, and repository-delta projections consume that authority | The serialized state vocabulary is exactly `current`, `stale`, or `unknown`. Proof strength such as `proven` belongs in a separate proof/provenance field; `invalidated` is a delta consequence, not a freshness-state synonym. Never turn unknown into current. |
| Completeness | Whether the observation covers the declared scope strongly enough to make negative claims | repository observation + repository snapshot/delta completeness | The serialized state vocabulary is exactly `complete`, `incomplete`, or `unknown`. Keep completeness independent from presence and freshness; a bounded or incomplete observation cannot prove absence outside its scope. |
| Repository semantic delta | What repository-intelligence facts differ between admitted endpoint observations | `repository_delta.py::RepositoryDeltaMixin` | New domain-specific deltas are projections over this authority, not a second notion of repository change. |
| Relationship evidence | Repository-derived dependency/reference/ownership/project relationships and their provenance | relationship/graph producers; stable snapshot relationship identity in `repository_delta.py` | Reuse relationship identity/provenance. Observation bounds changing is not a repository relationship change. |
| External diagnostic observation | Imported lint/test/type/timing facts bound to repository evidence | `repository_delta.py` external diagnostic observation/delta helpers | Keep execution result authority external; Hashmarks records the observation only. |
| Consumer binding definition | Opaque consumer-declared repository evidence scope | repository-evidence binding projection | Definition identity is separate from repository observation identity. Changing the declaration is not a repository change. |
| Consumer binding impact | Which declared bindings intersect changed repository evidence | repository-evidence coverage/delta projection consuming canonical repository observation/delta facts | Report projection facts and reasons; do not create a feature-local change authority. |
| External evidence claim | Request-scoped caller observation that may point into repository truth | `evidence_correlation.py` owns only the claim/correlation projection; repository facts remain with existing owners | Preserve the claim separately. Opaque metadata never becomes repository authority by naming convention. |
| Evidence correlation resolution | Whether a bounded path/line/symbol/module claim maps uniquely, ambiguously, not at all, or conflicts with admitted repository evidence | `evidence_correlation.py` over canonical member observation plus bounded indexed symbol/module queries | State vocabulary is `resolved-unique | resolved-ambiguous | unresolved | claim-conflict`; it describes correspondence, never causation. |
| Source equivalence | Whether explicitly qualified external source identity matches the correlated repository member/range identity | `evidence_correlation.py` comparison over repository-evidence binding identities | State vocabulary is `proven | mismatch | unknown`. Keep it independent from repository freshness and correlation resolution. |
| Declaration correspondence/value | Whether provider-normalized declarations are scoped as the same conceptual fact and whether their resolved normalized values are equal, different, ambiguous, or insufficient for comparison | `repository_declaration_contract.py` + `repository_declarations.py`; exact repository evidence remains owned by repository-evidence bindings | Provider correspondence/value claims stay provider-claimed. A cross-provider correlation producer owns a separate namespaced claim rather than merging source identities. Core does not infer correspondence, semantic compatibility, transitive equivalence, reachability, graph paths, connected components, cycle consensus, majority authority, precedence, migration, foreign-key joins, cascade deletion, or a winning value. Provider names in basis/provenance are opaque metadata, not referential-integrity keys. There is no global semantic edge/knowledge-graph owner; explicit correspondence disappears when its producer claim disappears. Previous observations are one-call comparison inputs and never hydrate, restore, cache, or persist correspondence state across calls or CodeMap reopen. Provider-resolved values participate in comparison only while every cited exact repository evidence row is `known-present`. |
| Declaration semantic subject identity | Deterministic namespaced identity of the declared conceptual subject, independent of request-local group labels and exact evidence location | `repository_declarations.py` over explicit `semantic_namespace + concept + scope`; discovery binds namespace to provider name | Extend the declaration owner; do not create a universal ontology, provider alias/migration table, or infer cross-namespace correspondence. Provider build/provenance version is not identity; semantic scope is. Exact declaration and observation identities remain separate. |
| Declaration semantic role identity | Optional deterministic identity of one provider-declared role inside a semantic subject, independent of request-local declaration labels and exact evidence location | `repository_declarations.py` over `semantic_subject_identity + semantic_role` | Roles are opaque provider vocabulary. Never infer them from paths/values/names, never use them as coverage/absence authority, and preserve duplicate-role ambiguity. The same identity may reappear in a later explicit endpoint without implying continuous existence or creating retained history/tombstone authority. |
| Declaration semantic-subject delta | Factual correlation/change of the same namespaced semantic subject and any explicitly role-tagged children across explicit endpoints | `repository_declaration_delta.py` over existing declaration identities/values and repository-evidence delta | Correlate only unique subject/role identities; duplicate multiplicity is ambiguity, never an ordering/winner rule. Untagged children remain request-local. No history store or second repository delta owner. |
| Declaration absence | Whether an expected declaration is proven missing inside a declared semantic scope | `repository_declaration_contract.py` over provider coverage plus explicit expected declaration membership | Absence is authoritative only for complete, explicitly non-truncated coverage. Otherwise unseen expected declarations remain unknown. |

## Evidence strengthening admission and persistence contract

Before an evidence domain adds production state or a new semantic owner, its change must record:

```text
Repository fact being represented:
Concrete repository-intelligence use case / defect:
Existing semantic owner(s):
Missing fact:
Canonical owner after this change:
Repository-derived or external observation:
Persistence class:
Freshness owner:
Completeness owner:
Identity owner:
Delta / comparability owner:
Sensitivity / redaction handling:
Public Python surface: NONE / <surface and justification>
MCP surface: NONE / <surface and justification>
Explicit non-goals:
```

The persistence class is one of:

1. **canonical repository input** — admitted repository bytes or explicit repository-owned metadata;
2. **reconstructible derived state** — indexes/caches/projections that can be rebuilt from admitted authority;
3. **qualified external observation** — caller/producer evidence, request-scoped by default; persistence requires a separate admitted repository-intelligence contract;
4. **consumer/workflow history** — outside Hashmarks authority and never persisted as repository truth.

A useful consumer workflow is not by itself evidence for a new Hashmarks owner. When an existing owner already represents the fact, extend or project it instead.

### Shared evidence axes

A domain may introduce typed facts, but it must identify how these independent axes are represented: authority/origin, definition/scope, identity, freshness, completeness, provenance, ambiguity, bounds/truncation, delta/comparability, persistence, and sensitivity. Reuse the canonical state families in this document rather than introducing local synonyms.

This is a shared vocabulary rule, **not** a universal polymorphic evidence schema. Domain facts remain typed and owned by their domain producer.

### Negative evidence and comparability

Absence is authoritative only for an explicitly declared scope whose relevant producer and Hashmarks projection completeness axes are all complete. Partial evidence may prove observed presence; it cannot prove absence outside the complete scope.

Before a semantic delta is reported, the owning domain must distinguish the same question observed twice from a changed definition, changed scope, changed producer semantics, or otherwise non-comparable observations. Definition/scope change must not masquerade as repository change.

### Public-surface rule

An internal semantic owner does not automatically earn a top-level `CodeMap` method or MCP tool. Public/API/MCP promotion requires a distinct consumer responsibility that existing bounded surfaces cannot represent without weakening semantics. A new schema or transport shape never creates a second semantic owner.

### Dependency/distribution handoff

The admitted dependency-evidence work must keep four layers distinct:

1. repository-declared dependency intent (for example manifests);
2. repository lock state as canonical repository bytes;
3. externally produced dependency-resolution graph observations;
4. externally produced installed/import-module ownership observations.

`project_graph.py` remains the owner of repository/workspace project topology. `import_resolution.py` remains the owner of repository import identity. The dependency-evidence owner may correlate those repository facts with qualified external distribution/resolution observations, but it must not index dependency implementation source, run a resolver/package manager, mutate an environment, infer module ownership from name similarity, or turn dependency correspondence into causal/upgrade advice.

Workspace/local projects may simultaneously have repository-project identity and resolution-node identity; appearing in a resolution graph does not make repository-owned code an external dependency.


### Maven artifact adapter

`hashmarks.adapters.maven_dependency_observation` is an execution-free qualification adapter for already-produced Maven dependency evidence. It translates caller-supplied dependency-tree JSON and dependency-list text into the typed dependency-resolution v3 observation contract.

The adapter is not a second dependency semantic owner. It must not invoke Maven, resolve packages, inspect dependency implementation source, parse a POM as resolved truth, or infer repair/vulnerability/causal conclusions. Tree evidence owns graph relationships and effective Maven scope; list evidence owns resolved inventory and reported Java-module ownership. A package present only in list evidence remains inventory-only rather than being invented into graph reachability. Maven contexts such as compile/runtime/test remain observation contexts and are not interchangeable with each edge's effective scope.

### uv lock adapter

`hashmarks.adapters.uv_lock_dependency_observation` is an execution-free qualification adapter for already-produced `uv.lock` bytes. It translates lock selections, sources, inventory membership, and lock-declared dependency relationships into the existing dependency-resolution v3 observation contract.

The adapter does not invoke uv, synchronize an environment, inspect dependency implementation source, or parse `pyproject.toml` as resolved truth. Lock package source identity is preserved as part of concrete selection identity; a directory selection remains distinct from a registry or other source selection even when name and version match. Name-only dependency references are admitted only when they resolve uniquely within the supplied lock. Ambiguous lock references are rejected rather than guessed.

The lock is qualified as resolution/inventory evidence, not installed-import ownership evidence. Absence of module ownership in a lock therefore does not become a negative module-ownership claim. Repository binding remains explicit through `repository_inputs`; the adapter does not infer source equivalence from nearby manifest files.

## Orthogonal state rule

Do not overload one field with multiple axes.

For example, these are different facts:

- the member exists;
- the requested locator is inside the member;
- the selected bytes are readable text;
- the member revision changed;
- the selected range changed;
- a declared dependency changed;
- indexed relationships changed;
- the observation is complete;
- the evidence is current.

A packet may expose several of them, but each must remain independently observable. An edit elsewhere in a file must not become a direct-range change merely because the containing member revision changed.

## Definition versus observation

A consumer declaration and the repository observation made from it have different identities.

```text
binding definition
  ├─ opaque binding id
  ├─ declared members/ranges
  ├─ declared dependencies
  └─ requested observation bounds
          │
          ▼
repository observation
  ├─ repository/source identity
  ├─ generation
  ├─ member revisions
  ├─ range identities
  ├─ relationship evidence
  ├─ freshness/completeness
  └─ producer provenance
```

Changing the definition, query limit, or optional projection setting is configuration change. It must not masquerade as repository content or relationship change.

## Projection rule

A public Python, CLI, MCP, or interchange schema may make existing repository evidence easier to consume. It must name its source owner and preserve that owner's authority, state, bounds, completeness, freshness, and uncertainty.

MCP `result_mode` is transport vocabulary only. It selects among already-admitted typed projections; it does not create a semantic state family, observation identity, cache, or history owner. Default modes must preserve the established response shape, and any compare mode must require explicit caller-supplied endpoint authority rather than server-retained history.

When a projection needs a fact that an existing owner already knows, add a reusable primitive to that owner or call its existing primitive. Do not recompute the fact from raw files merely because the projection has convenient access to the workspace.

## Maintainer extension checklist

Before creating a new CodeMap mixin or repository-intelligence schema, answer:

```text
Repository fact being exposed:
Existing semantic owner:
Existing state family reused:
Existing identity/provenance reused:
Freshness owner:
Completeness owner:
Why a new projection/schema is needed:
New state vocabulary introduced: NONE / <values and owning module>
New semantic owner introduced: NO / <owner and justification>
```

If the answer to **Existing semantic owner** is unclear, stop implementation and trace the current owner first.

## Binding work

Repository evidence bindings are a consumer-facing projection over existing Hashmarks repository intelligence. They may own the binding declaration and binding-specific projection shape. They do **not** own a second repository observer, repository generation, member revision model, relationship graph, freshness model, or repository change set.

The binding implementation must therefore converge on the existing owners above before it becomes public.

## Dependency/distribution evidence work

`dependency_resolution_contract.py` owns only the v3 schema identity, semantic-authority vocabulary, and fail-closed dependency field allowlists, including the adjacent dependency-correlation request vocabulary. `dependency_resolution_evidence.py` owns qualified external dependency-resolution observations. Its admitted fact is correspondence between caller-supplied, producer-neutral resolution evidence and existing repository evidence. Dependency observations remain request-scoped by default; retaining workflow labels or historical observations is consumer-owned unless a separate persistence contract is admitted.

It owns:
- the typed dependency-resolution observation contract;
- logical component identity separately from concrete resolved selection identity;
- resolved inventory membership separately from graph reachability;
- multi-context dependency relationships, roots, and effective-scope observations;
- compact producer-evidence references and context/semantic-authority coverage;
- resolution definition, resolution graph, and full qualified-observation identities;
- comparability and factual component/selection/inventory/relationship delta for equivalent definitions;
- endpoint comparison across explicit caller-supplied packets without reconstructing repository history;
- independent repository-identity, repository-generation, semantic, adapter, producer, physical-evidence, coverage, and ownership change axes;
- derivation and explain projections over existing qualified observation authority, without a history store or second provenance graph;
- bounded dependency traversal with explicit omission accounting;
- explicit repository-input correspondence using canonical repository member observation;
- repository-generation binding by reusing the existing repository identity/generation owner;
- explicit module/distribution ownership observations without name-based inference.

It does not own:
- repository-declared dependency intent or lockfile authority;
- repository project topology (`project_graph.py`);
- repository import identity (`import_resolution.py`);
- a second repository freshness or repository delta model;
- package-manager execution, environment synchronization, dependency source indexing, or remote discovery;
- module/distribution ownership inference;
- vulnerability authority, causal diagnosis, upgrade advice, or repair recommendation;
- consumer phase labels such as `before`, `after-fix`, or `final`.

Inventory membership does not prove graph reachability, and absence from a graph or inventory is admissible within the caller-declared scope only when the corresponding context/semantic-authority coverage is explicitly complete and non-truncated. Producer evidence may support individual selections, inventory memberships, and relationships without becoming repository authority. Semantic scope and roots define resolution comparability; producer identity is bound to the full observation, not the semantic definition. Complete graph coverage can describe an empty or rootless graph.

A producer claim that a resolution came from a repository input is not source-equivalence proof. Without an independently comparable member revision, source equivalence remains `unknown`; matching and mismatching revisions produce `proven` and `mismatch` respectively.

### Dependency derivation/explain and endpoint-delta admission record

```text
Repository fact being represented:
  provenance of one qualified dependency observation and factual differences between
  two caller-supplied dependency observation endpoints
Concrete repository-intelligence use case / defect:
  explain which repository/evidence/adapter authority produced a result and distinguish
  semantic change from repository-identity/generation, interpretation, or evidence-only change
Existing semantic owner(s):
  dependency_resolution_evidence.py; canonical repository identity/generation;
  dependency source authority/coverage; repository delta state families
Missing fact:
  compact derivation/explain projection plus orthogonal endpoint change classification
Canonical owner after this change:
  dependency_resolution_derivation.py for projection shape;
  dependency_resolution_delta.py for factual dependency endpoint comparison
Repository-derived or external observation:
  qualified external observation bound to explicit repository authority
Persistence class:
  qualified external observation + reconstructible request-local projection; not persisted
Freshness owner:
  existing repository binding / repository observation authority
Completeness owner:
  existing dependency evidence-source and semantic coverage contracts
Identity owner:
  existing definition/resolution/observation identities plus deterministic derivation identity
Delta / comparability owner:
  dependency_resolution_delta.py projecting existing repository-identity/generation and dependency facts
Sensitivity / redaction handling:
  unchanged; projection contains only already-admitted dependency/repository evidence
Public Python surface:
  CodeMap.dependency_resolution_derivation_authority(),
  CodeMap.dependency_resolution_explain(), CodeMap.dependency_resolution_delta()
MCP surface:
  existing read-only dependency_codemap tool;
  result_mode=explain projects dependency_resolution_explain();
  result_mode=compare projects dependency_resolution_delta() over a caller-supplied previous endpoint
Explicit non-goals:
  history retention, Git traversal, branch/merge/rollback, causal diagnosis,
  package-manager execution, second repository generation, universal provenance graph
```

No new persistence authority or repository state family is introduced. The serialized
`change_axes` values are comparison vocabulary local to the dependency delta projection:
`changed | unchanged`, with `unknown` only where explicit provenance is absent and
`not-comparable` only for semantic resolution under a changed definition. They do not
replace repository freshness, completeness, continuity, or semantic-delta owners.

## Evidence correlation work

Evidence correlation is a request-scoped projection over external claims plus existing repository authorities. Its only new semantic ownership is the declaration/correspondence layer: the exact claim supplied by the caller, the conservative resolution state, and qualified source-equivalence comparison.

It must reuse:

- canonical repository member observation for presence/admission/revision;
- bounded indexed symbol and exact module evidence for structural correspondence;
- repository evidence bindings for range/member identities, relationships, freshness, completeness, and provenance;
- repository evidence binding delta for before/after repository change.

It must not create a second repository observer, source identity, freshness model, completeness model, relationship graph, repository delta, persistent runtime-evidence store, or causal interpretation layer.

Producer adapters may derive request-local source-artifact, source-occurrence, normalized-observation, and bounded evidence-projection identities so that transport provenance does not masquerade as observation or repository identity. Those identities remain producer/caller evidence vocabulary: they are deterministic projections of supplied evidence, not a new Hashmarks repository identity owner. Repository locator identity continues to be owned by the existing evidence-correlation claim plus repository correspondence authority.

Producer parser diagnostics are likewise scoped to the syntax layer the adapter actually validates. CSV strict/recovered/malformed state is transport-envelope evidence only; it is not application-payload validity, semantic correctness, or repository authority. Opaque embedded payloads remain `not-assessed` unless a separate typed contract explicitly owns their validation.

Changing producer serialization may change exact artifact/occurrence provenance without changing the normalized observation or bounded evidence projection. Repeated occurrences may share one normalized observation identity. None of these identities authorize retained history, incident identity, Git traversal, branch/ref ownership, merge/rollback semantics, or repository mutation.

## Repository declaration work

`repository_declaration_contract.py` owns the producer-neutral request contract, scope/correspondence/value-state normalization, exact-value equality/difference classification, coverage-qualified declaration absence, and core request/packet byte budgets. `repository_declarations.py` binds those provider claims to existing repository-evidence bindings and issues declaration/group observation identities. `repository_declaration_delta.py` owns only factual before/after comparison of declaration semantics and composes the existing repository-evidence-binding delta rather than inventing another repository/observer change authority.

`repository_file_discovery.py` owns repository-file admission and traversal for CodeMap consumers: internal/pruned/symlink exclusion, context-policy admission, repository-relative identity, and bounded visible traversal. It is format-neutral and does not own parser eligibility, declaration semantics, or repository-evidence byte identity. `indexing_lifecycle.py` consumes that admission surface and adds parser/language/size/index persistence semantics. Packaging-derived Python import roots, project-manifest enumeration, project-node/edge admission, and manifest freshness must consume this same admission owner rather than maintain producer-local filesystem visibility/pruning rules. Project/native producers keep semantic parsing authority, while `RepositoryNativeEvidence` owns the final project-evidence admission filter before persistence and its internal freshness implementation qualifies evidence only after repository-file admission.

`repository_declaration_provider.py` owns the explicit provider SPI, the Hashmarks-owned revision-binding provider read context, bounded provider input/path-enumeration observations, and provider input/evidence envelope validation. `repository_declaration_discovery.py` deterministically composes caller-selected providers into a discovery wrapper around the canonical declaration packet and reuses `repository_file_discovery.py` to enumerate admitted files across producer formats; it then revalidates provider reads/enumerations around nested declaration qualification. The public provider context does not expose a raw workspace filesystem handle. Provider detection/provenance/warnings/input/enumeration observations remain separate from declaration semantics; there is no ambient provider registry, plugin entry-point loading, MCP provider execution authority, provider sandbox, retry/timeout owner, or provider-result certification authority. Provider code is caller-selected trusted in-process extension code under a read-only contract.

This is a new semantic projection owner for **declaration correspondence**, not a new repository observer. It must reuse canonical repository member/span observation, repository identity/generation, freshness, and evidence-binding identities. Semantic extraction, normalized values, expected membership, correspondence, and coverage remain provider claims unless a separate Hashmarks authority explicitly establishes them.

Semantic-subject identity extends this same declaration owner. `repository_declarations.py` deterministically derives `semantic_subject_identity` from explicit `semantic_namespace + concept + scope`; direct callers supply the namespace while discovery binds it to provider name. Request-local group IDs and evidence locators do not define the subject. Declaration-definition identity references the issued subject identity and continues to own the exact declaration/evidence definition, while observation identities own qualified observed state. `repository_declaration_delta.py` may correlate a subject only when that identity is unique at both explicit endpoints; multiplicity remains ambiguity. **New semantic owner introduced: NO.** No history store, retention layer, branch/ref model, or repository mutation authority is introduced.

`repository_declaration_derivation.py` owns only a typed read-only derivation/explain projection over an already-qualified declaration packet. It reuses declaration/group identities and canonical repository-evidence binding identities, validates the retained endpoint structurally, and exposes exact supporting repository evidence without re-reading the workspace. It is not a second declaration semantic owner, evidence-binding owner, repository observer, history store, or provider-execution path.

Repository fact being exposed: traceability of one qualified declaration observation to its existing declaration/group identities and exact repository-evidence bindings. Existing semantic owner: `repository_declarations.py` + repository-evidence bindings. Existing state family reused: repository identity/generation, evidence availability, freshness, completeness, declaration definition/observation identity. Existing identity/provenance reused: declaration/group identities, binding definition/observation identities, bindings packet identity, provider provenance. Freshness owner: canonical repository evidence binding. Completeness owner: declaration coverage + repository evidence binding. Why a new projection/schema is needed: compact derivation/explainability without re-parsing provider formats or requiring current repository state. New state vocabulary introduced: NONE. New semantic owner introduced: NO.

Persistence class: **qualified external observation / derived-not-persisted**. Public Python surfaces: `CodeMap.repository_declarations(...)`, `CodeMap.repository_declaration_derivation_authority(...)`, `CodeMap.repository_declaration_explain(...)`, `CodeMap.discover_repository_declarations(...)`, and the explicit declaration-provider SPI. MCP surface: the existing read-only `repository_declarations` tool exposes observation mode by default and an opt-in explain mode that delegates to `repository_declaration_explain()`; declaration compare is not promoted beyond the current repository-evidence binding delta contract. Explicit non-goals: universal metadata/provenance ontology, source-of-truth precedence, majority voting, fuzzy/model correspondence, edits, generated metadata repair, execution, retained history, Git traversal, and consumer workflow policy.
