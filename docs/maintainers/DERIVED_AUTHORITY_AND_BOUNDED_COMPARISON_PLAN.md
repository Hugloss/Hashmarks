# Derived authority and bounded comparison plan

**Status: implementation plan.** This plan translates useful ideas from versioned-data systems into Hashmarks' existing repository-observer architecture without turning Hashmarks into a history database, version-control engine, or execution system.

The governing product boundary remains `PRODUCT_BOUNDARY.md`: Hashmarks observes repository state and evidence. Git owns repository history and mutation. Consumers own the work loop. Historical support, where useful, is a bounded working set rather than repository-lifetime time travel.

## Objective

Improve Hashmarks so a consumer can answer two high-value questions cheaply and precisely:

1. **Why does this derived result exist?**
2. **What meaning or evidence changed between two explicit repository observations?**

Every derived Hashmarks result should be capable of identifying the repository authority, physical evidence, adapter/observer semantics, and prior observations that produced it, while keeping semantic identity producer-neutral and keeping comparison endpoint-oriented.

This is not a plan to add branch, merge, rollback, PITR, Git-history crawling, or an unbounded observation archive.

## What to borrow — and how to translate it

Versioned-data systems demonstrate several useful principles. Hashmarks should borrow the principles, not their storage or mutation machinery.

| Useful principle | Hashmarks translation | Explicit non-adoption |
| --- | --- | --- |
| Immutable version reference | Existing repository/member/source/observation identities bound to explicit caller-selected authority | No Hashmarks-managed repository snapshots or commits |
| Cheap diff over changed material | Existing repository delta, changed-path/member revision, invalidation, and stable evidence identity owners | No scan of all Git history and no second delta store |
| Traceable lineage | A derivation-provenance projection from a result to its direct input observations and physical evidence | No branch ancestry, merge-base, or repository lineage engine |
| Auditability | Result-local evidence closure: the result can explain which authorities and evidence made it true | No append-only global audit/history log |
| Compare old/new state | Endpoint comparison between two explicit packets/observations | No arbitrary time-travel query over retained history |
| Work proportional to change | Reuse member revisions, changed paths, stable identities, maintained indexes, and freshness/invalidation | No full-repository rescans merely to preserve history |
| Reproducible derived output | Bind derivation semantics and observer capability separately from semantic definition identity | No producer identity inside producer-neutral semantic IDs |

The architectural shorthand is:

> **Borrow immutable reference, provenance, endpoint diff, and change-proportional work. Reject historical archive, branch, merge, rollback, and repository mutation.**

## Existing owners to reuse

This work must compose existing Hashmarks authorities rather than introduce parallel state families.

- `RepositoryObservation` and canonical repository identity own repository-state observation.
- `RepositoryDeltaMixin` / `OBSERVER_DELTA.md` own endpoint comparison and the separation of repository change from observer/capability change.
- Member revisions and source identities own physical repository evidence.
- `REPOSITORY_EVIDENCE_BINDINGS.md` owns bounded consumer evidence projections and binding observation identity.
- `DEPENDENCY_EVIDENCE.md` already separates physical source identity, semantic authority, definition identity, resolution identity, observation identity, producer metadata, and coverage.
- `REPOSITORY_DECLARATIONS.md` owns cross-artifact correspondence, ambiguity, provenance, and factual declaration delta.
- `STATE_AND_SEMANTIC_OWNERS.md` remains the gate against introducing a second identity, generation, graph, cache, or freshness owner.

If a proposed implementation needs a new global "history", "snapshot", "lineage", "result store", or "delta generation", stop and re-express the requirement as a projection over those existing owners.

## Core invariants for the implementation

### 1. No orphan derived results

A derived result that claims repository meaning must retain a traversable provenance path to the repository evidence that supports it.

Conceptually:

```text
derived result
  -> derivation semantics
  -> direct input observation(s)
  -> physical source/member evidence
  -> repository authority
```

The path may be compact references rather than embedded copies. The requirement is traceability, not duplication.

### 2. Semantic identity stays producer-neutral

Do not put adapter names, source IDs, digests, implementation module names, or producer versions into semantic definition identity merely to make provenance convenient.

Keep separate:

- **semantic identity** — what repository fact/question means;
- **observation authority** — where and under what evidence the fact was observed;
- **adapter/observer semantics** — which interpretation contract produced the observation;
- **physical evidence identity** — which admitted source/member supplied bytes/evidence.

### 3. Physical identity is not content digest

Identical bytes may occur in different physical sources. A rename/move may preserve bytes while changing physical evidence topology.

Therefore Hashmarks must be able to report:

```text
semantic meaning unchanged
physical evidence topology changed
```

without collapsing physical identity to a digest.

### 4. Adapter semantics must be identifiable without becoming implementation provenance

A semantic interpretation change must be distinguishable from a code refactor that preserves interpretation.

The implementation should prefer a bounded **adapter/observer semantic contract identity** over "package version means semantics". If the existing observer-capability identity is sufficient, extend/reuse it rather than introducing another owner.

### 5. Equal derivation authority implies equal semantic meaning

For deterministic repository-derived surfaces:

```text
same repository authority
+ same physical evidence identities/content
+ same semantic inputs
+ same adapter/observer semantics
= same semantic output
```

Execution timestamps, cache hits, serialization order, and other non-semantic metadata may differ.

A violation is either nondeterminism or evidence that an input is missing from the authority model.

### 6. Projection must not destroy traceability

Compact CLI/MCP/query responses do not need to embed the full provenance closure, but they must retain stable references that let a consumer obtain or validate the supporting evidence.

Principle:

> **Compact by default; traceable by construction.**

### 7. Endpoint comparison first; no history composition

`OBSERVER_DELTA.md` already defines endpoint comparison as the first implementation model. Keep it that way.

The useful operation is conceptually:

```text
compare(before_packet, after_packet)
```

not:

```text
search repository history and reconstruct every intermediate state
```

Intermediate-history composition remains out of scope unless a future, separately justified repository-intelligence requirement survives the product-boundary and economics gates.

### 8. Historical retention is optional optimization, never correctness authority

The first implementation must require **no Hashmarks history store**. The caller may hold the before/after packets.

Only if measurement proves repeated endpoint comparison is materially harmed without local retention may Hashmarks add a small bounded working-set cache. Any such cache must be:

- scoped to an active process/session/workspace or similarly bounded task window;
- bounded by explicit count, bytes, and/or age;
- evictable without changing semantic correctness;
- incapable of crawling Git history to refill itself;
- reconstructible from caller/Git-supplied authority;
- separate from repository identity and semantic authority.

## Proposed derivation-provenance projection

Do not begin by inventing a universal new schema. Start on one mature surface and prove the minimum reusable fields.

The conceptual information needed is:

```text
semantic result identity / existing result identity
repository identity / generation authority
direct input observation identities
physical evidence references
adapter / observer semantic-contract identity
derivation semantic-contract identity, when derivation adds meaning
freshness and completeness axes
observer capability identity
```

Prefer references to canonical existing identities over copied nested packets.

A generic public projection should be admitted only after at least two independent surfaces need the same semantics.

## Implementation phases

### Phase 0 — Freeze the boundary and establish baseline economics

Already established by the product constitution:

- no branch/merge/rollback/repository mutation;
- no Git-history crawl/pre-index;
- no unbounded historical archive;
- bounded observations are evictable working-set evidence.

Before product changes, record baseline cost for the selected existing operations using the normal benchmark path. Do not create a special benchmark framework for this feature.

**Exit:** current correctness and performance baseline is recorded; no production code added.

### Phase 1 — Prove derivation authority on dependency evidence

Use dependency evidence first because it already has the cleanest separation among:

- definition identity;
- resolution identity;
- observation identity;
- physical source identity;
- producer metadata;
- semantic authorities;
- coverage;
- repository binding.

Add the smallest projection necessary to answer:

> Which repository authority, physical sources, semantic authorities, and adapter semantics produced this dependency result?

Do not add persistence or a generic provenance graph.

**Required regressions:**

1. same semantic definition + same evidence + same semantics -> same semantic result identity;
2. same bytes in two distinct physical sources -> distinct physical source identities;
3. producer/adapter metadata changes without semantic change -> observation changes while semantic comparability remains;
4. semantic adapter contract changes -> interpretation authority changes explicitly;
5. multi-source derived result preserves every contributing source;
6. missing or malformed ancestry/reference fails closed rather than yielding an apparently authoritative orphan fact.

**Exit:** one mature surface can explain its derivation without creating a new global state owner.

### Phase 2 — Add a pure explain/provenance projection

Build a read-only function over an already-produced result/packet, conceptually:

```text
explain_result(result_or_identity)
```

The projection should expose direct ancestry first and optionally a bounded transitive evidence closure where canonical references already exist.

It must not:

- search Git history;
- mutate repository state;
- execute producers/tools;
- infer a winning source;
- manufacture missing provenance;
- persist consumer workflow history.

Keep this Python/domain-first. CLI/MCP exposure comes later.

**Exit:** a consumer can explain a result from current explicit inputs with no extra history store.

### Phase 3 — Enrich endpoint delta with evidence-cause classification

Extend the existing observer/delta owner rather than adding a new diff engine.

Useful classifications include:

- semantic value changed;
- semantic value unchanged, physical evidence topology changed;
- repository bytes changed;
- observer/adapter semantic contract changed;
- observer capability changed;
- evidence appeared/disappeared;
- ambiguity introduced/resolved;
- completeness/freshness changed;
- result became non-comparable because interpretation semantics differ.

These are independent axes where necessary. Do not flatten them into one "changed" flag or confidence score.

**Exit:** before/after endpoint comparison can distinguish repository change from observation/interpretation change.

### Phase 4 — Generalize only after a second independent surface proves reuse

Choose one additional surface, preferably repository declarations or repository evidence bindings.

Prove that the same derivation semantics can be reused without importing dependency-specific concepts into core.

If the second surface needs materially different semantics, keep separate typed projections rather than forcing a universal provenance ontology.

**Exit:** either a genuinely producer-neutral derivation projection emerges, or the design explicitly remains typed per evidence family.

### Phase 5 — Expose compact consumer surfaces

Only after domain semantics are stable, add bounded CLI/MCP projection if useful.

Preferred user concepts:

- `explain` / `explain-evidence`;
- endpoint `delta` / `compare`;
- provenance/evidence references.

Avoid product language such as:

- time travel;
- checkout;
- branch;
- merge;
- rollback;
- restore;
- history database.

MCP remains read-only and workspace-bound.

**Exit:** consumers receive compact facts plus stable provenance handles, without a new agent workflow.

### Phase 6 — Measure whether bounded retention is needed

Do **not** implement session history merely because it sounds convenient.

Dogfood the explicit-packet design first. Measure:

- packet size;
- explain latency;
- endpoint-delta latency;
- repeated source reads;
- repeated parse/index work;
- cache hit value;
- memory/storage amplification.

Only if retained measurements show a clear economic benefit may a bounded working-set cache be proposed.

If admitted, choose conservative limits from measurement rather than architecture folklore. Eviction must be ordinary and semantics-preserving.

**Exit:** either no retention is needed, or measured evidence justifies a small cache with explicit budgets.

### Phase 7 — Dogfood across real producer pairs

Use existing dependency fixtures/corpora and agent benchmark workflows.

Important attacks:

- uv before/after lock evidence;
- Maven before/after evidence;
- equivalent semantic dependency result from different producers;
- same bytes at different physical paths;
- path move with unchanged semantic fact;
- adapter semantic-contract change without repository-byte change;
- source disappearance creating ambiguity/unknown;
- bounded packet eviction/reconstruction if Phase 6 is ever admitted.

Feed every reproduced defect back into the same branch and repeat until two clean passes, following the existing attack/dogfood discipline.

**Exit:** cross-producer semantics remain neutral, provenance remains complete, and endpoint delta remains correctly classified under adversarial cases.

## Performance design

The desired cost shape is **change-proportional**, not history-proportional.

Prefer:

```text
current canonical index
+ changed paths/member revisions
+ stable evidence identities
+ explicit before/after packet
```

over:

```text
walk commits
+ rebuild old repositories
+ retain every generation
+ diff all observations ever seen
```

A feature that requires work proportional to total Git history is presumed out of profile unless extraordinary repository-intelligence evidence proves otherwise.

A feature that requires storing every observed generation is rejected.

## Deferred ideas

The following are explicitly deferred, not hidden future phases:

- intermediate-generation history composition;
- repository-lifetime time travel;
- Hashmarks-created repository snapshots;
- Git ancestry/LCA modeling for Hashmarks observations;
- branch/merge/cherry-pick/rebase/reset/revert/rollback semantics;
- permanent audit/event log of agent work;
- persistent agent-session memory;
- arbitrary old-state recovery without caller/Git authority;
- universal provenance ontology before multiple evidence families prove one is needed.

## Decision gates

Before each phase, answer:

1. **Can this be implemented as a projection over existing owners?**
2. **Can the caller supply the endpoints instead of Hashmarks retaining history?**
3. **Does this preserve producer-neutral semantic identity?**
4. **Can every derived claim still reach physical repository evidence?**
5. **Does eviction/recomputation change only cost, never meaning?**
6. **Is work bounded by current state/change rather than repository-history length?**
7. **Does this remain read-only repository intelligence?**

Any "no" blocks the phase until the design is narrowed.

## Recommended implementation order

The recommended sequence is deliberately conservative:

```text
dependency derivation proof
    -> pure explain projection
    -> endpoint delta cause classification
    -> second-surface reuse proof
    -> compact CLI/MCP projection
    -> measure
    -> bounded retention only if proven necessary
    -> cross-producer dogfood to saturation
```

This captures the useful idea—derived facts are reproducible, explainable, and cheaply comparable—without making Hashmarks responsible for repository history.
