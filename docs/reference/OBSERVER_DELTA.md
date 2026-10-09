# Observer and delta model

Hashmarks is a repository observer, not an agent policy engine and not a policy engine for policing its own policy. This document fixes the ownership boundary for delta work so later features do not create parallel graphs, generations, caches, or decision engines.

## Canonical ownership

Existing repository identity and CodeMap generation remain canonical. Delta is a projection over existing repository facts, relationships, and observations. It does not introduce a delta generation, verification generation, test graph, or second repository snapshot model.

Hashmarks may describe repository facts, relationship provenance, observation completeness, freshness, externally supplied observations, and differences between those facts. It must not decide which check an agent should run next or whether evidence is sufficient for a task.

## Delta axes

A delta must keep repository change, observer change, observation-only change, and combined change distinct. A newly observable relationship after an observer upgrade is not silently reported as a repository change.

## Stable identity

Rows participate in identity-based delta only when they carry a stable identity. Hashmarks does not infer identity from path/name similarity. Move/rename correlation must have explicit evidence and provenance before it can replace add/remove semantics.

## Completeness and negative evidence

Empty results are not automatically negative evidence. Public projections keep evidence availability, freshness, and completeness on separate axes: presence may be known-present/known-absent/unknown/unsupported, freshness is current/stale/unknown, and completeness is complete/incomplete/unknown. Delta reports completeness transitions independently from added/removed rows, so unknown → known-absent cannot be misreported as “nothing changed.”

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

## Repository evidence bindings

Opaque repository evidence bindings are a consumer-facing projection over the same member revision, relationship, freshness, completeness, and repository-delta authorities. They may own binding-definition and binding-impact projection shape, but they do not introduce another repository generation, member revision model, relationship graph, freshness authority, or generic change-set authority.

Binding deltas keep direct range/member evidence, declared dependencies, relationship evidence, and binding-definition change separate. Coverage may consume either caller-asserted changed paths or an atomic `RepositoryObservation`, and it must preserve which source established change-set completeness. See [`REPOSITORY_EVIDENCE_BINDINGS.md`](REPOSITORY_EVIDENCE_BINDINGS.md).


## Relationship evidence identity

Snapshot symbol and dependency rows carry deterministic evidence identities and producer provenance. Identity is derived from the repository relationship fact, not from presentation metadata. Provenance therefore remains explainable without causing a false semantic relationship delta when only observer metadata changes.

Stable evidence identity is not a claim of runtime behavior coverage. Static relationship evidence remains bounded by the snapshot completeness declaration, including unknown dynamic-runtime relationships.


## External diagnostic observations

Hashmarks can normalize externally produced diagnostic rows without running the producer. Diagnostic identity is based on tool/rule/location/symbol/message facts and is order-independent. Delta compares those identities, so equal aggregate counts do not imply equal evidence.

The projection reports added, removed, unchanged, and newly added diagnostics intersecting an explicitly supplied changed-path scope. Outcomes distinguish pass, fail, not-run, blocked-environment, blocked-supply, blocked-permission, invalid-baseline, and stale. These remain observation-only facts; Hashmarks does not decide whether a dirty repository gate is acceptable.

Environment identity is optional provenance for externally supplied observations and must not be confused with repository identity.


## Exact source and observability evidence

The existing repository member observer additionally exposes bounded, exact
single-member literal occurrences and physical UTF-8 source shape through
`CodeMap.source_observation`. Its member revision and stable byte-read authority
are reused from the canonical member owner; the projection does not create a
parallel full-text index or claim repository-wide search completeness.

`index_preflight` includes descriptive discovery scope, known pruned directory
classes and explicit unknown excluded/unreadable member counts. An omitted
subtree must never be converted into a proven empty subtree.

External diagnostic observations may preserve producer-claimed collection state
independently from execution outcome. Location-shift candidate correspondence
is non-authoritative: unchanged diagnostic messages do not prove identical
source-span identity. See [SOURCE_OBSERVATION.md](SOURCE_OBSERVATION.md).

## Explicit multi-member occurrence evidence

`CodeMap.scoped_source_occurrences` composes bounded, exact literal
source occurrences over caller-supplied members. The source-read owner,
visibility decisions, member revision, and generation remain canonical.
Partial member coverage, read-budget exhaustion, result truncation and stale
revisions have distinct representations; absence is qualified only within
the complete explicit member set. See [SOURCE_OBSERVATION.md](SOURCE_OBSERVATION.md).

## Diagnostic delta collection qualification

A raw removed identity means absent from the *supplied after observation*,
not necessarily absent from the repository or fixed. The diagnostic delta
now also includes `diagnostics.qualification`, partitioning changed row
identities by whether producer-claimed completeness, outcome, shared
repository/producer/environment binding and explicit overlapping path scope
permit a bounded presence/absence comparison. Partial or timed-out observations
never silently certify disappearance. This is a projection over existing
external observations, not an execution check, workflow authority, or
diagnostic identity replacement.

## Post-edit diagnostic path locality (Hermes-inspired)

The canonical `diagnostic_observation_delta` now projects
`diagnostics.path_locality` over exactly the **same added/removed diagnostic
identities** and existing `diagnostics.qualification` used elsewhere.

For an explicitly caller-reported edit path set, each added and removed
diagnostic receives one conservative locality:

- `on-reported-changed-path` — the external diagnostic's explicit path
  appears in the caller-reported changed set.
- `outside-reported-changed-paths` — the external diagnostic names another
  path. **This does not prove that path was unchanged, that an edit caused the
  diagnostic, or that an import/reference/dependency relationship exists.**
- `unknown` — no changed paths were reported, or a diagnostic path is absent
  or invalid. An empty changed-path list is **not** a proven empty change set.

The packet retains the exact normalized `changed_paths`, independent
`change_set_completeness: unknown`, per-kind counts, and a per-diagnostic
`collection_qualification` inherited from the existing diagnostic claim owner.
An incomplete/timed-out collection cannot upgrade a removed fact to a
resolved defect. Both raw `added` and `removed`, candidate relocation,
source revision comparison and unchanged identity count remain intact.
There is **no causality assertion**, test execution, or new timeline.

The existing agent-native diagnostic presenter displays this native locality
packet as a separate producer claim without hiding the original diagnostic
records. In `compact`/`text` formats, native detail is retained beside the
bounded presentation; raw identity claims are not strengthened by formatting.

Implementation: `hashmarks.codemap.diagnostic_path_locality`, called by the
existing `RepositoryDeltaMixin`; regression:
`tests/test_diagnostic_path_locality.py`. The agent/harness still owns edits,
verification execution, and interpreting whether an observed diagnostic on a
different file is related to the edit.

## Source-backed location correspondence

The member observer may emit bounded exact physical-line fingerprints for
explicit requested lines. The existing diagnostic delta can compare
caller-retained before/after canonical member observations to distinguish
a **unique preserved source line** from message-only possible relocation.
Proof is deliberately restricted to byte-identical unique lines, consistent
columns, exact member revisions, generation/source freshness, collection and
scope provenance. It never upgrades diagnostic identity, masks raw changes,
or creates source-history ownership. See [SOURCE_OBSERVATION.md](SOURCE_OBSERVATION.md).

## Scope-sensitive freshness

External observations may declare the repository paths they directly observed.
Freshness is not automatically destroyed by every repository generation change,
but **a disjoint partial changed-path list does not prove freshness**. This follows
the same fail-closed negative-evidence rule as diagnostic disappearance.

`RepositoryDeltaMixin.external_observation_freshness` now accepts the optional
`change_set_complete` boolean (default `False`). This is a **caller assertion**
about the *entire* repository change set between the bound observation and
current endpoint, **not** an independently verified CodeMap/Git receipt.

| Endpoint and changed-path evidence | Freshness | Reason |
| --- | --- | --- |
| Repository identity **and** generation unchanged | `current` | Same observed endpoint |
| Changed endpoint; direct/dependency-scope intersection observed | `stale` | Relevant edit, even for partial change sets |
| Changed endpoint; no declared observation/dependency scope | `stale` | Scope absent; cannot safely reuse |
| Changed endpoint; disjoint or empty changed-path list, completeness not asserted | `unknown` | Unreported relevant edits remain possible |
| Changed endpoint; completeness asserted, but zero changed paths supplied | `unknown` | Changed endpoint not explained by path evidence |
| Changed endpoint; nonempty, disjoint, caller-asserted complete path set | `current` | **Conditional on the caller's completeness claim** |

The result preserves `change_set_completeness` separately:
`caller-claimed-complete` or `unknown`. The latter is **not** a proven
absence of changes. Even conditional `current` says nothing about whether a
producer actually ran against current source bytes: producer freshness,
collection completeness, repository binding, execution outcome, and path scope
remain separate evidence dimensions.

The public `validate_repository_intelligence_evidence` validator accepts
`unknown` freshness and preserves it as `freshness_state="unknown"` with
`stale=None`; `require_fresh=True` rejects unknown or stale evidence. Its
normalized external-freshness projection retains `change_set_completeness`
and the original reason as `freshness_reason`, so conditional currentness
remains distinguishable from an unchanged endpoint.

Consumers that can independently prove a complete changed-path set may pass
`change_set_complete=True`; callers with a filtered `git diff`, sampled
watcher events, or otherwise partial set must leave the default unchanged.
Hashmarks does not run verification, read the consumer's session history, or
certify the caller's completeness claim. A canonically qualified repository
observation should be preferred when available.

Regression coverage: `tests/test_external_verification_coverage.py` and
`tests/test_repository_intelligence_delta.py`.

## Verification relationship evidence

Hashmarks may classify an observed verification relationship as direct, related, or unknown and gives that relationship a stable evidence identity plus provenance. These are repository relationship facts only. The vocabulary deliberately excludes policy terms such as sufficient or recommended; consumers decide whether a relationship satisfies a risk boundary.


## Observer constitution

Observer evolution should add facts or improve the quality of existing facts: identity, relationships, provenance, completeness, freshness, uncertainty, capability, and delta. Boundary protection must not become another runtime policy subsystem. When an implementation needs a recommendation, sufficiency decision, workflow rule, execution choice, or certification rule, keep that decision outside Hashmarks and expose only the repository evidence needed by the consumer.
