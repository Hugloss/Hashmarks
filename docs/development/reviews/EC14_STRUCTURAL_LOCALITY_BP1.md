# EC-14 Structural Locality BP1

## Candidate

Fresh-main authority: `4f825902327d464afe5b6925a7be44464b6791c8`.

Selected owner: `hashmarks/codemap/structural_locality.py`.

Frozen source blob: `ed2af86f41dbb7fb8fa7d7eba5f69eec241b272c`.

Direct owning test: `tests/test_structural_locality.py`.

Frozen direct-test blob: `24ffaa0d77627eddfdf207226ede8f56e8ab3082`.

## Why this BP1 repairs tooling first

CI #624 proves the module has 69 current excess across five functions and 15 rule findings, but the previous JSON projection aggregated away the function line and rule values. That made the next edit impossible to bind to exact measured causes without scraping human output.

The executable inventory already owns those exact facts. The JSON projection must preserve them rather than discard them.

This phase therefore adds the raw normalized `findings` rows to `hashmarks.ruff-debt.v3`. Existing aggregate fields remain unchanged.

## Edit admission

After CI emits the exact five rows, one coherent production PR may repair multiple related functions when they share one responsibility seam. We intentionally prefer a larger qualified edit over repeated one-helper PRs.

The production edit must preserve:

- exact `path::qualname` target authority;
- evidence visibility denial;
- Python import/re-export ownership semantics;
- `self`/`cls` method and inheritance resolution;
- ambiguous calls never promoted to exact;
- reference/call bound exhaustion represented as incomplete/unresolved;
- exact caller identity and caller-bound completeness;
- packet identity and freshness semantics;
- no refactor recommendation or execution authority.

The direct owning test bytes stay frozen until a demonstrated missing invariant requires a focused regression. Additional relevant tests may be included in the qualification ring.

## Loop

For the larger edit, use executable Hashmarks evidence iteratively inside the working phase:

1. exact current debt findings;
2. structural locality with sufficient reference bounds;
3. direct/focused tests;
4. fresh debt measurement;
5. repeat edits while evidence improves and authority invariants remain protected;
6. push one coherent candidate to GitHub CI.

Stop if evidence becomes incomplete, a seam creates a second semantic owner, or measured debt does not improve.
