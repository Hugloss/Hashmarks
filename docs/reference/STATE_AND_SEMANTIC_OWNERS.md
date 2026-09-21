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
| Evidence correlation resolution | Whether a bounded path/line/symbol claim maps uniquely, ambiguously, not at all, or conflicts with admitted repository evidence | `evidence_correlation.py` over canonical member observation plus bounded symbol queries | State vocabulary is `resolved-unique | resolved-ambiguous | unresolved | claim-conflict`; it describes correspondence, never causation. |
| Source equivalence | Whether explicitly qualified external source identity matches the correlated repository member/range identity | `evidence_correlation.py` comparison over repository-evidence binding identities | State vocabulary is `proven | mismatch | unknown`. Keep it independent from repository freshness and correlation resolution. |

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

## Evidence correlation work

Evidence correlation is a request-scoped projection over external claims plus existing repository authorities. Its only new semantic ownership is the declaration/correspondence layer: the exact claim supplied by the caller, the conservative resolution state, and qualified source-equivalence comparison.

It must reuse:

- canonical repository member observation for presence/admission/revision;
- bounded indexed symbol evidence for structural correspondence;
- repository evidence bindings for range/member identities, relationships, freshness, completeness, and provenance;
- repository evidence binding delta for before/after repository change.

It must not create a second repository observer, source identity, freshness model, completeness model, relationship graph, repository delta, persistent runtime-evidence store, or causal interpretation layer.
