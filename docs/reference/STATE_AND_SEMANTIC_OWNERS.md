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

## State families are separate axes

Similar-looking state words are not interchangeable. A consumer must know which axis a value belongs to. New public schemas must reuse the canonical state spelling for an existing axis rather than introduce a local synonym.

| State family | Meaning | Canonical owner | Extension rule |
| --- | --- | --- | --- |
| Repository continuity | Whether the observer has a clean, dirty, or unknown repository observation | `hashmarks/observation.py::ObservationState` and `client.py::RepositoryObservation` | Reuse the atomic observation. Never reconstruct continuity from separate samples. |
| Repository / CodeMap generation | Which admitted derived repository state a projection is bound to | CodeMap store + `decision_session.py` | Reuse the existing generation. Do not create feature-local generations. |
| Repository identity | Content/repository identity independent of a consumer projection | canonical identity owners and `_repository_packet_identity()` | A projection may reference identity; it does not redefine it. |
| Member revision | Content identity of one admitted indexed repository member | CodeMap file row / repository-intelligence snapshot path revision | Reuse the indexed revision semantics. A projection must distinguish missing, unindexed/unknown, denied/unsupported, and present members rather than treating them as one state. |
| Evidence availability | Whether a requested repository fact is known present, known absent, unavailable/unknown, or unsupported | repository-intelligence evidence producers; endpoint delta vocabulary is coordinated by `repository_delta.py` | Do not invent synonyms in a new packet. Add a new value only at the owning evidence layer. |
| Freshness | Whether a previously observed fact is still current for the claim being made | `evidence_freshness.py`, `freshness_map.py`, and repository-delta freshness projections | The serialized state vocabulary is exactly `current`, `stale`, or `unknown`. Proof strength such as `proven` belongs in a separate proof/provenance field; `invalidated` is a delta consequence, not a freshness-state synonym. Never turn unknown into current. |
| Completeness | Whether the observation covers the declared scope strongly enough to make negative claims | repository observation + repository snapshot/delta completeness | The serialized state vocabulary is exactly `complete`, `incomplete`, or `unknown`. Keep completeness independent from presence and freshness; a bounded or incomplete observation cannot prove absence outside its scope. |
| Repository semantic delta | What repository-intelligence facts differ between admitted endpoint observations | `repository_delta.py::RepositoryDeltaMixin` | New domain-specific deltas are projections over this authority, not a second notion of repository change. |
| Relationship evidence | Repository-derived dependency/reference/ownership/project relationships and their provenance | relationship/graph producers; stable snapshot relationship identity in `repository_delta.py` | Reuse relationship identity/provenance. Observation bounds changing is not a repository relationship change. |
| External diagnostic observation | Imported lint/test/type/timing facts bound to repository evidence | `repository_delta.py` external diagnostic observation/delta helpers | Keep execution result authority external; Hashmarks records the observation only. |
| Consumer binding definition | Opaque consumer-declared repository evidence scope | repository-evidence binding projection | Definition identity is separate from repository observation identity. Changing the declaration is not a repository change. |
| Consumer binding impact | Which declared bindings intersect changed repository evidence | repository-evidence coverage/delta projection consuming canonical repository observation/delta facts | Report projection facts and reasons; do not create a feature-local change authority. |
| External evidence claim | Request-scoped caller observation that may point into repository truth | `evidence_correlation.py` owns only the claim/correlation projection; repository facts remain with existing owners | Preserve the claim separately. Opaque metadata never becomes repository authority by naming convention. |
| Evidence correlation resolution | Whether a bounded path/line/symbol/module claim maps uniquely, ambiguously, not at all, or conflicts with admitted repository evidence | `evidence_correlation.py` over canonical member observation plus bounded indexed symbol/module queries | State vocabulary is `resolved-unique | resolved-ambiguous | unresolved | claim-conflict`; it describes correspondence, never causation. |
| Source equivalence | Whether explicitly qualified external source identity matches the correlated repository member/range identity | `evidence_correlation.py` comparison over repository-evidence binding identities | State vocabulary is `proven | mismatch | unknown`. Keep it independent from repository freshness and correlation resolution. |

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

`hashmarks.adapters.maven_dependency_observation` is an execution-free qualification adapter for already-produced Maven dependency evidence. It translates caller-supplied dependency-tree JSON and dependency-list text into the typed dependency-resolution v2 observation contract.

The adapter is not a second dependency semantic owner. It must not invoke Maven, resolve packages, inspect dependency implementation source, parse a POM as resolved truth, or infer repair/vulnerability/causal conclusions. Tree evidence owns graph relationships and effective Maven scope; list evidence owns resolved inventory and reported Java-module ownership. A package present only in list evidence remains inventory-only rather than being invented into graph reachability. Maven contexts such as compile/runtime/test remain observation contexts and are not interchangeable with each edge's effective scope.

### uv lock adapter

`hashmarks.adapters.uv_lock_dependency_observation` is an execution-free qualification adapter for already-produced `uv.lock` bytes. It translates lock selections, sources, inventory membership, and lock-declared dependency relationships into the existing dependency-resolution v2 observation contract.

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

`dependency_resolution_evidence.py` owns qualified external dependency-resolution observations. Its admitted fact is correspondence between caller-supplied, producer-neutral resolution evidence and existing repository evidence. Dependency observations remain request-scoped by default; retaining workflow labels or historical observations is consumer-owned unless a separate persistence contract is admitted.

It owns:
- the typed dependency-resolution observation contract;
- logical component identity separately from concrete resolved selection identity;
- resolved inventory membership separately from graph reachability;
- multi-context dependency relationships, roots, and effective-scope observations;
- compact producer-evidence references and context/source-kind coverage;
- resolution definition, resolution graph, and full qualified-observation identities;
- comparability and factual component/selection/inventory/relationship delta for equivalent definitions;
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

Inventory membership does not prove graph reachability, and absence from a graph or inventory is authoritative only when the corresponding context/source-kind coverage is explicitly complete and non-truncated. Producer evidence may support individual selections, inventory memberships, and relationships without becoming repository authority.

A producer claim that a resolution came from a repository input is not source-equivalence proof. Without an independently comparable member revision, source equivalence remains `unknown`; matching and mismatching revisions produce `proven` and `mismatch` respectively.

## Evidence correlation work

Evidence correlation is a request-scoped projection over external claims plus existing repository authorities. Its only new semantic ownership is the declaration/correspondence layer: the exact claim supplied by the caller, the conservative resolution state, and qualified source-equivalence comparison.

It must reuse:

- canonical repository member observation for presence/admission/revision;
- bounded indexed symbol and exact module evidence for structural correspondence;
- repository evidence bindings for range/member identities, relationships, freshness, completeness, and provenance;
- repository evidence binding delta for before/after repository change.

It must not create a second repository observer, source identity, freshness model, completeness model, relationship graph, repository delta, persistent runtime-evidence store, or causal interpretation layer.
