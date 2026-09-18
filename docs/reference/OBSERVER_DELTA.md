# Observer and delta model

Hashmarks is a repository observer, not an agent policy engine. This document fixes the ownership boundary for delta work so later features do not create parallel graphs, generations, caches, or decision engines.

## Canonical ownership

Existing repository identity and CodeMap generation remain canonical. Delta is a projection over existing repository facts, relationships, and observations. It does not introduce a delta generation, verification generation, test graph, or second repository snapshot model.

Hashmarks may describe repository facts, relationship provenance, observation completeness, freshness, externally supplied observations, and differences between those facts. It must not decide which check an agent should run next or whether evidence is sufficient for a task.

## Delta axes

A delta must keep repository change, observer change, observation-only change, and combined change distinct. A newly observable relationship after an observer upgrade is not silently reported as a repository change.

## Stable identity

Rows participate in identity-based delta only when they carry a stable identity. Hashmarks does not infer identity from path/name similarity. Move/rename correlation must have explicit evidence and provenance before it can replace add/remove semantics.

## Completeness and negative evidence

Empty results are not automatically negative evidence. Public projections preserve known-present, known-absent, unknown, incomplete, stale, and unsupported evidence. Delta reports completeness transitions independently from added/removed rows, so unknown → known-absent cannot be misreported as “nothing changed.”

## Delta taxonomy

Content, structure, relationship, ownership, evidence, observation, capability, and diagnostic deltas must share the same repository identity/generation authority. They are views, not independent stores.

## Endpoint and history semantics

Endpoint comparison answers what differs between two observations. History delta answers what happened across intermediate generations. The first implementation is intentionally endpoint-oriented. History composition must not be added until transient add/remove, restore, unknown-to-known, and observer-upgrade semantics can be preserved without false certainty.

## External observations

Test, lint, type, timing, or other execution results may be imported as observations with provenance and repository binding. Hashmarks records what was observed; it does not promote that result into execution authority or agent policy. Environment-blocked execution remains an environment observation, not a repository defect.

## Current implementation slice

The canonical implementation owner is `hashmarks.codemap.repository_delta.RepositoryDeltaMixin`. Observer identity, completeness, semantic change, and endpoint delta extend that existing repository-intelligence snapshot/delta lifecycle. There is deliberately no separate observation-delta module, generation, cache, graph, or store.

The current slice keeps observer capability identity separate from repository identity, represents bounded completeness explicitly, and refuses to promote same-name/same-kind symbol disappearance and appearance into proven move identity. Such correlations are emitted only as possible moves with provenance and `identity_authority: false`.

Further work must continue through this owner and the existing change-intelligence/evidence projections.


## Relationship evidence identity

Snapshot symbol and dependency rows carry deterministic evidence identities and producer provenance. Identity is derived from the repository relationship fact, not from presentation metadata. Provenance therefore remains explainable without causing a false semantic relationship delta when only observer metadata changes.

Stable evidence identity is not a claim of runtime behavior coverage. Static relationship evidence remains bounded by the snapshot completeness declaration, including unknown dynamic-runtime relationships.


## External diagnostic observations

Hashmarks can normalize externally produced diagnostic rows without running the producer. Diagnostic identity is based on tool/rule/location/symbol/message facts and is order-independent. Delta compares those identities, so equal aggregate counts do not imply equal evidence.

The projection reports added, removed, unchanged, and newly added diagnostics intersecting an explicitly supplied changed-path scope. Outcomes distinguish pass, fail, not-run, blocked-environment, blocked-supply, blocked-permission, invalid-baseline, and stale. These remain observation-only facts; Hashmarks does not decide whether a dirty repository gate is acceptable.

Environment identity is optional provenance for externally supplied observations and must not be confused with repository identity.


## Scope-sensitive freshness

External observations may declare the repository paths they directly observed. Freshness is not automatically destroyed by every repository generation change. When Hashmarks can prove that all changed paths are outside the observation and dependency scope, the observation remains fresh and the reason records that proof.

The rule fails closed: an observation with no declared scope becomes stale after repository/generation change. A direct or dependency-scope intersection also makes it stale. This avoids both false reuse and the opposite economics failure where an unrelated documentation edit invalidates a focused test observation.

Dependency scope is supplied by repository-intelligence relationships; it is not inferred by the consumer.
