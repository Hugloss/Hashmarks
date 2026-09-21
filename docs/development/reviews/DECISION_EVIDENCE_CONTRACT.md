# Decision-Evidence Contract Freeze

**Status:** implementation authority for the next Hashmarks task-evidence redesign. This is development guidance, not yet public API documentation.

**Parent authority:** current Hashmarks product constitution and invariants remain normative. This plan does not expand Hashmarks into agent reasoning, editing, execution, retry/recovery, or certification.

## Why this exists

Oh-Goon dogfood exposed a generic task-evidence defect: bounded lexical retrieval could surface a consumer API as the edit owner even when one exact repository implementation symbol existed for the requested mutation.

The tactical exact-owner repair is intentionally narrow. The larger product issue is that the current task-action surface overloads canonical lexical retrieval with ownership, verification and action-oriented projection semantics. Those are related repository observations, but they do not have the same authority.

The redesign therefore separates repository evidence by role and removes compatibility obligations that would preserve the old overloaded model.

## Governing product rule

> Preserve repository-intelligence invariants, not historical task-action behavior.

Hashmarks is pre-1.0. Existing tests, schemas, CLI fields, MCP fields and internal helpers may be rewritten or deleted when they preserve an inferior model. Do not add compatibility aliases, duplicate projection paths, legacy modes or fallback readers solely to retain old behavior.

When an existing test fails during this redesign, classify it as:

- **KEEP** — proves a repository-truth, authority, freshness, provenance, visibility, ambiguity or product-boundary invariant.
- **REWRITE** — protects an old semantic contract that a better repository-intelligence model supersedes.
- **DELETE** — protects compatibility, obsolete schema, duplicate projection machinery or behavior no longer owned by Hashmarks.

## Permanent product boundary

Hashmarks may observe and project repository-derived evidence about identity, topology, symbols, ownership, verification relationships, impact, ambiguity, freshness, completeness, visibility and provenance.

Hashmarks does not decide whether a consumer should edit, what patch to make, whether a solution is sufficient, how execution should run, whether to retry, or whether a result is certified.

A uniquely proven repository owner is therefore valid Hashmarks evidence. An instruction to edit that owner is consumer policy.

## No universal authority score

The redesign must not collapse freshness, ownership, verification, impact, content identity and retrieval relevance into one numerical confidence or total ordering.

Different evidence domains answer different questions.

A weaker domain may not numerically overpower a stronger domain. In particular:

- lexical relevance does not manufacture ownership;
- current freshness does not imply unique ownership;
- a unique retrieval rank does not imply a proven owner;
- external/runtime evidence may correlate to repository evidence but does not establish ownership by itself.

## Role-separated task evidence

The target model separates these concepts:

1. **Retrieval evidence** — bounded repository material relevant to the query.
2. **Explicit target evidence** — literal paths, qualified identifiers and strong exact identifiers named by the query.
3. **Ownership evidence** — repository evidence establishing implementation/semantic ownership.
4. **Verification evidence** — tests/contracts structurally or explicitly related to the target/owner.
5. **Related evidence** — consumers, callers, adapters, configs, contracts and nearby context.
6. **Impact evidence** — bounded affected repository relationships.
7. **Freshness/completeness/provenance** — authority metadata for each projection.

Retrieval is not ownership authority.

## Ownership-domain precedence

Only inside the ownership domain, categorical evidence strength may establish precedence.

Initial order:

1. literal exact repository path constrained by an exact target symbol when supplied;
2. qualified exact symbol;
3. unique strong exact identifier;
4. proven import/module/re-export owner;
5. proven structural owner;
6. repository-backed task-local owner;
7. unresolved or ambiguous.

Lexical score may order equivalent candidates. It may not displace a stronger authority class.

If evidence does not establish uniqueness, preserve ambiguity.

## Saturation invariance

For a current admitted exact owner, changing bounded retrieval context must not change the proven owner solely because the lexical result set changed.

For example, subject to equivalent repository state:

```
limit=1
limit=10
limit=100
```

may return different retrieval context but must preserve a uniquely established owner.

Adding weaker evidence such as comments, documentation, history, tests or API consumers must not displace a stronger owner.

Adding a second valid exact owner must weaken a unique result to ambiguous rather than choose by rank.

Removing or staling the proof of uniqueness must weaken authority rather than preserve cached selection.

## Test/source semantics

Filename shape is evidence, not complete truth.

The redesigned model must distinguish:

- repository domain classification;
- exact symbol identity;
- explicit test-edit intent;
- verification relationship;
- production/import reachability;
- visibility;
- source/test dual-domain evidence.

A task explicitly asking to strengthen a regression may nominate a test surface.

A task asking to change implementation while naming a verifying test should retain implementation ownership and expose the test as verification evidence.

Do not preserve blanket historical rules if stronger repository evidence supports a better distinction.

## Ambiguity

Ambiguity is first-class evidence, not a ranking failure to hide.

Fail closed for cases including:

- duplicate exact functions or methods;
- ambiguous re-exports/facades;
- unresolved import ownership;
- multiple inherited method owners;
- same exact symbol in multiple admitted projects/packages;
- stale/current disagreement;
- competing generated/live owners when authority is not uniquely established.

Expose candidate identities and the evidence required to discriminate them when possible.

## Structured explanation

A resolved owner should expose a stable structured basis, for example:

- `literal-path`
- `qualified-symbol`
- `unique-exact-symbol`
- `exact-import-owner`
- `exact-module-resolution`
- `structural-owner`
- `repository-locality`

Human-readable prose may explain the result but must not itself be authority.

## Freshness is independent

Current evidence may still be ambiguous or unresolved.

The product must support states equivalent to:

```
freshness=current
ownership=ambiguous
```

and:

```
freshness=current
ownership=unresolved
```

Remove or redesign presentation terminology that implies freshness also proves edit/owner safety.

## Public-surface direction

The current overloaded task-action projection may be replaced rather than preserved.

A future public result should conceptually expose:

```
query
repository_identity
freshness

retrieval
explicit_target
ownership
verification
related
impact
provenance
```

Exact field names are deferred to implementation. No compatibility adapter is required for obsolete pre-1.0 fields.

If the term `canonical` remains public, it must have exactly one documented meaning. Otherwise remove it.

## Implementation ownership

The target architecture should have one semantic owner for each of:

- explicit target parsing;
- owner resolution;
- ambiguity projection;
- freshness projection;
- verification relationship projection.

CLI and MCP presentation layers must not independently recreate ranking/ownership semantics.

Once the replacement is qualified, delete redundant late repair paths, displacement guards, reranking helpers and compatibility projections whose only purpose is to correct a weaker earlier selection.

## Required adversarial properties

The implementation phase must prove at least:

- one exact owner + many weaker consumers -> same owner;
- one exact owner + many docs/comments/tests -> same owner;
- retrieval limit changes -> same proven owner;
- second exact owner introduced -> ambiguous;
- owner proof removed -> ambiguous/unresolved;
- stale supporting evidence -> no current owner authority;
- denied evidence -> cannot participate;
- test-only exact symbol -> does not silently become implementation owner;
- explicit test-edit intent -> test may be a legitimate edit/target surface;
- external/runtime observation naming a symbol -> correlation only, not ownership authority.

## Language coverage

The semantics must be qualified across at least:

- Python;
- TypeScript/JavaScript;
- Go;
- Rust.

Language-native import/module resolution may differ, but public ownership/ambiguity semantics must remain equivalent.

## Qualification metrics

Track safety failures separately from retrieval quality:

- FALSE_OWNER
- FALSE_UNIQUE
- FALSE_SAFE_EDIT
- FALSE_VERIFIER
- OWNER_MISSED_BY_RETRIEVAL_BOUND
- RESOLVABLE_REPORTED_AMBIGUOUS
- AMBIGUOUS_REPORTED_RESOLVED
- STALE_REPORTED_CURRENT
- DENIED_EVIDENCE_SELECTED

Useful quality/economics metrics may include owner top-1 accuracy, resolution rate, verification relevance, retrieval precision/recall, context size, latency and index cost.

Safety metrics are not traded away for retrieval score.

## Dogfood qualification

Use real repositories as qualification corpora without adding repository-specific production heuristics.

### Oh-Goon

At minimum:

- `cancel_queued_admission`
- `revoke_executor_trust`
- `drain_executor`
- `seal_owned_outputs`
- `SealedAttemptOutputs.prove_for`
- generation-bound placement
- workspace/global mutation
- release-byte promotion

### Hashmarks

Use task-action, structural-locality, evidence-correlation, evidence-binding, indexing/freshness and producer-identity owners.

### agentsCookbook

Use methodology/evidence owners where docs/tests may lexically dominate implementation.

Every generic defect found through dogfood receives a neutral reduced regression. Do not add named-repository heuristics.

## Planned implementation phases

### D1 — Tactical exact-owner defect closure

Complete and qualify the Oh-Goon-exposed exact-owner recovery repair without broad public redesign.

### D2 — Contract freeze

This document. Recheck against fresh post-D1 main before implementation.

### D3 — Owner-resolution core

Create one retrieval-bound-invariant owner-resolution authority.

### D4 — Public task-evidence rewrite

Replace the overloaded task-action projection in Python/CLI/MCP. Breaking pre-1.0 changes are allowed.

### D5 — Legacy-path deletion

Delete redundant displacement/reranking/recovery/compatibility paths after the replacement is qualified.

### D6 — Adversarial qualification

Limits, lexical saturation, duplicates, re-exports, test/source roles, stale state, deletes/recreates, visibility changes and incremental/cold convergence.

### D7 — Polyglot qualification

Python, JS/TS, Go and Rust.

### D8 — Real-world dogfood closure

Oh-Goon, Hashmarks and agentsCookbook.

### D9 — Evidence economics

Ensure exact owner resolution remains bounded and index-backed at repository scale.

### D10 — 0.15.0 semantic boundary

Update schemas, Python/CLI/MCP docs and version together. Build and qualify exact producer artifacts. No legacy semantic path remains.

## Exit condition

The redesign is complete when bounded retrieval remains economical while repository-derived ownership is stable under lexical saturation, ambiguity is preserved rather than ranked away, agents receive structured evidence they can reason from, and Hashmarks still does not become the agent or execution authority.
