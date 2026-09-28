# Semantic identity without repository ownership

**Status: accepted.** This decision records how Hashmarks adopts semantic identity and immutable-observation ideas without becoming a version-control system, history database, or repository mutation owner.

## Context

Versioned-data systems demonstrate useful separation between the identity of a conceptual subject, the exact declaration/evidence that describes it, and an immutable observed state. Hashmarks benefits from that separation because repository declarations can describe the same conceptual fact across files and formats while exact provenance, ambiguity, freshness, and evidence location must remain independently observable.

Hashmarks already owns typed repository-declaration definition and observation identities plus endpoint-local comparison. Creating a parallel identity framework or retained history service would duplicate authority and violate the product boundary.

## Decision

Extend the existing repository-declaration owner rather than introduce a new semantic owner.

The identity layers are:

1. **Semantic subject identity** — `semantic_subject_identity` is a deterministic digest of the provider-declared opaque `concept + scope` pair. It identifies what conceptual subject the provider says the group concerns.
2. **Declaration definition identity** — the existing `declaration_definition_identity` identifies one exact declaration definition, including its repository-evidence binding. Moving the declaration or changing its exact evidence definition changes this identity without necessarily changing the semantic subject.
3. **Observation identity** — the existing declaration, group, and packet observation identities identify exact qualified observed state, including values, provenance, evidence state, and the repository observation that supports it.

The semantic subject identity deliberately excludes request-local group labels, declaration membership, file/range locators, values, coverage, and current evidence state. Those facts remain in their existing declaration/observation owners.

Repository-declaration delta may report `semantic_subject_changed` when a stable request-local group ID changes its provider-declared `concept + scope`. This is a factual endpoint comparison only.

## Authority boundary

The borrowed identity model does **not** introduce:

- branches, heads, refs, commits, or mutable history lines owned by Hashmarks;
- merge, rebase, cherry-pick, rollback, revert, reset, or checkout semantics;
- push/pull, worktree/ref mutation, or conflict resolution;
- Git-history crawling or reconstruction of intermediate repository state;
- a permanent observation timeline or history database;
- a second source-of-truth precedence model;
- a universal repository ontology.

Git and the caller remain the owners of repository history and mutation. Native tools remain the owners of their domain state. Hashmarks observes and compares explicit authority.

The governing rule is:

> **Identity without ownership; compare without mutation; bounded evidence without repository-lifetime history.**

## Why this is not a new ontology

`concept` and `scope` stay opaque provider vocabulary. Core hashes those already-admitted semantic inputs; it does not understand names such as `service.owner`, `runtime.python`, dependency coordinates, or organization-specific precedence.

Two declarations become one semantic subject only because the provider placed them in the same explicit concept/scope. Similar names, values, file paths, or model inference do not create semantic identity.

## Why this is not a history store

The current declaration APIs operate on current or caller-supplied explicit endpoint packets. Explain/derivation is endpoint-local. Comparison receives the previous observation from the caller. No server-side sequence of observations is required for correctness.

This change therefore admits **no history store and no retention layer**. A future retention proposal remains a separate architecture/economics decision and must prove that explicit packets are materially insufficient before adding state.

## Consequences

A declaration may move between file/range locations while retaining the same semantic subject identity. Its declaration-definition identity still changes, preserving exact evidence provenance.

Changing `concept` or `scope` changes semantic subject identity, even when the normalized value and physical evidence stay equal.

All declarations projected in one group carry the group's semantic subject identity. Validation recomputes it from the provider-declared semantic inputs so resigning a forged identity does not gain authority.

Derived relationships remain recomputable from source evidence and do not become independent source truth.

## Future design gate

If future work appears to require branch/history machinery, answer these questions before implementation:

1. Which external authority already owns the state?
2. Why can the caller or native tool not perform the operation?
3. Why are explicit immutable endpoint observations insufficient?
4. Would the proposal create a second source of truth?
5. Would correctness require retaining history indefinitely?
6. Can the requirement remain read-only?
7. Can it instead be satisfied by semantic identity, exact declaration identity, provenance, and endpoint comparison?

If the need can be satisfied by the read-only primitives, keep repository lifecycle outside Hashmarks.

## Implementation ownership

This decision extends the existing owners:

- `repository_declaration_contract.py` — provider-neutral declaration inputs;
- `repository_declarations.py` — semantic-subject projection plus declaration/group observation identities;
- `repository_declaration_delta.py` — factual endpoint comparison;
- `repository_declaration_derivation.py` — read-only provenance/explain projection.

**New semantic owner introduced: NO.**

Persistence remains `derived-not-persisted`. No new cache, generation, history, or retention authority is introduced.
