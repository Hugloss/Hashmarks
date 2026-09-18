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

Empty results are not automatically negative evidence. Public projections must preserve the difference between known-present, known-absent, unknown, incomplete, stale, and unsupported evidence whenever the producer can establish those states.

## Delta taxonomy

Content, structure, relationship, ownership, evidence, observation, capability, and diagnostic deltas must share the same repository identity/generation authority. They are views, not independent stores.

## Endpoint and history semantics

Endpoint comparison answers what differs between two observations. History delta answers what happened across intermediate generations. The first implementation is intentionally endpoint-oriented. History composition must not be added until transient add/remove, restore, unknown-to-known, and observer-upgrade semantics can be preserved without false certainty.

## External observations

Test, lint, type, timing, or other execution results may be imported as observations with provenance and repository binding. Hashmarks records what was observed; it does not promote that result into execution authority or agent policy. Environment-blocked execution remains an environment observation, not a repository defect.

## Current implementation slice

hashmarks.codemap.observation_delta.observation_delta establishes the first anti-drift primitive: repository and observer changes are independent axes; rows match only by explicit stable identity; missing identity is not guessed; and output remains repository-intelligence-only. Further integration should extend existing change-intelligence/evidence projections rather than introducing a parallel owner.
