## Summary

Describe the problem and the smallest change that addresses it.

## Product-boundary classification

Choose one and explain why:

- [ ] In-profile defect
- [ ] In-profile optimization
- [ ] New repository-intelligence primitive — admission record included below
- [ ] Boundary-debt reduction/removal
- [ ] Measurement/test/docs only

If this adds a new production capability, complete the admission record:

```text
Product purpose:
Repository source of authority:
Neutral inputs:
New persistent/cached state:
Semantic cold/reconciled oracle:
Why Hashmarks is the correct owner:
What remains owned by the consumer/execution layer:
Why existing repository-intelligence primitives are insufficient:
Boundary decision: ADMIT / SPLIT / REJECT
```

A proposal that belongs to agent reasoning/workflow or execution/certification should be split or rejected rather than implemented in Hashmarks.

## Semantic ownership / state reuse

For repository-intelligence changes, identify the existing owner before adding a new surface:

```text
Repository fact being exposed:
Existing semantic owner extended:
Existing state family reused:
New serialized state vocabulary: NONE / <values and owner>
New semantic owner: NO / <owner and why existing owners are insufficient>
```

Read `docs/reference/STATE_AND_SEMANTIC_OWNERS.md` before introducing a new state word, delta concept, generation, freshness result, completeness result, or CodeMap mixin.

## Authority / invariants affected

List the repository authority, freshness, ownership, identity, provenance, or compatibility rules touched by this change.

## Evidence

Describe the tests, cold/reconciled oracle comparisons, benchmarks, or documentation checks that support the change.

## Compatibility / migration

Describe any public API, schema, cache, persisted-state, or consumer impact. Write `None` when there is no compatibility impact.
