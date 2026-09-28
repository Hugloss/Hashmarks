# Semantic identity without repository ownership

**Status: accepted.** This decision records how Hashmarks adopts semantic identity and immutable-observation ideas without becoming a version-control system, history database, or repository mutation owner.

## Context

Versioned-data systems demonstrate useful separation between the identity of a conceptual subject, the exact declaration/evidence that describes it, and an immutable observed state. Hashmarks benefits from that separation because repository declarations can describe the same conceptual fact across files and formats while exact provenance, ambiguity, freshness, and evidence location must remain independently observable.

Hashmarks already owns typed repository-declaration definition and observation identities plus endpoint-local comparison. Creating a parallel identity framework or retained history service would duplicate authority and violate the product boundary.

## Decision

Extend the existing repository-declaration owner rather than introduce a new semantic owner.

The identity layers are:

1. **Semantic subject identity** — `semantic_subject_identity` is a deterministic digest of `semantic_namespace + concept + scope`. Direct callers provide the namespace explicitly; provider discovery binds it to the selected provider name. It identifies one conceptual subject without pretending opaque concept names are globally universal.
2. **Semantic declaration identity** — optional `semantic_declaration_identity` is a deterministic digest of the already-issued subject identity plus a non-empty opaque provider-declared `semantic_role`. It identifies one provider-declared role inside that subject without promoting request-local declaration labels into global identity.
3. **Declaration definition identity** — the existing `declaration_definition_identity` identifies one exact declaration definition, including request-local labels and its repository-evidence binding. Moving the declaration or changing its exact evidence definition changes this identity without necessarily changing the semantic subject or semantic declaration role.
4. **Observation identity** — the existing declaration, group, and packet observation identities identify exact qualified observed state, including values, provenance, evidence state, and the repository observation that supports it.

The semantic subject identity deliberately excludes request-local group labels, declaration membership, file/range locators, values, coverage, and current evidence state. It includes the semantic namespace so independent producers cannot collide merely because their opaque concept/scope objects happen to serialize identically. Those other facts remain in their existing declaration/observation owners.

Semantic declaration identity is opt-in and subject-scoped. It excludes request-local `declaration_id`, exact evidence location, normalized value, producer metadata, and evidence state. Hashmarks creates no child semantic identity when `semantic_role` is absent. The role is opaque provider vocabulary and is never inferred from repository similarity, labels, values, or model output.

Repository-declaration delta may report `semantic_subject_changed` when a stable request-local group ID changes namespace/concept/scope. It also exposes an ambiguity-preserving `semantic_subjects` projection: unique subject identities may be correlated across request-local group-label changes, while duplicate subject identities remain explicitly ambiguous. Inside one uniquely correlated subject, explicitly role-tagged declarations may likewise correlate by unique `semantic_declaration_identity` even when request-local declaration labels change. Untagged children remain request-local. This is factual endpoint comparison only.

## Child-role admission evidence

The motivating repository-intelligence case is a bounded endpoint comparison where the same semantic subject survives caller/provider request-label churn but its distinct semantic sources still need attribution. For example, a runtime-compatibility subject may contain a provider-declared `project-intent` role and `container-runtime` role. A later explicit endpoint may rename both the request-local group and declaration IDs, move one source file, and change only the container value. Subject identity alone proves that the group concerns the same conceptual subject, but request-local declaration IDs cannot safely identify which child changed.

Hashmarks must not solve that gap by treating `declaration_id`, path, value equality, producer names, or similarity as stable identity. The admitted primitive is therefore narrower: the producer may explicitly declare a non-empty opaque `semantic_role`; Hashmarks hashes it under the already-issued subject identity and correlates it only when unique at both endpoints. Without that explicit role, the conservative #212 behavior remains unchanged.

This is useful even when a native tool separately owns domain validation. Hashmarks only preserves repository-intelligence correlation and provenance; it does not become the validator, resolver, source-of-truth selector, or executor for that native domain.

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

Two declarations become one semantic subject only inside the same explicit semantic namespace with the same concept/scope. Similar names, values, file paths, matching opaque JSON from another namespace, or model inference do not create semantic identity. Inside that subject, child declarations become semantically correlatable only when the producer explicitly supplies the same non-empty opaque `semantic_role`; request-local declaration IDs, matching paths/values, or model similarity do not create role identity. Discovery owns namespace binding to provider name and rejects provider namespace spoofing.

## Why this is not a history store

The current declaration APIs operate on current or caller-supplied explicit endpoint packets. Explain/derivation is endpoint-local. Comparison receives the previous observation from the caller. No server-side sequence of observations is required for correctness.

This change therefore admits **no history store and no retention layer**. A future retention proposal remains a separate architecture/economics decision and must prove that explicit packets are materially insufficient before adding state.

## Consequences

A declaration may move between file/range locations while retaining the same semantic subject identity. Its declaration-definition identity still changes, preserving exact evidence provenance.

Changing `semantic_namespace`, `concept`, or `scope` changes semantic subject identity, even when the normalized value and physical evidence stay equal.

Subject-level delta may correlate a unique subject across a request-local `group_id` rename. If either endpoint contains more than one group with the same subject identity, the delta reports ambiguity and performs no arbitrary pairing. Inside that uniquely paired subject, semantic declaration roles follow the same rule: correlation requires one matching role identity at each endpoint, duplicate roles remain ambiguity, and changing the role is removal plus addition rather than guessed rename.

Semantic declaration identity is correlation evidence only. It does not change provider coverage, authorize negative evidence, select precedence, or replace canonical repository-evidence delta for exact member/span/locator changes.

A deterministic identity may disappear from one explicit endpoint and reappear in a later endpoint when the provider again supplies the same semantic namespace/concept/scope or semantic role. Reappearance means only that the later claim resolves to the same semantic identity. It does **not** prove uninterrupted existence between endpoints and does not justify a tombstone, resurrection state, retained timeline, or Git-history search. If a caller needs to compare with an earlier observation, it supplies that bounded packet explicitly.

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
