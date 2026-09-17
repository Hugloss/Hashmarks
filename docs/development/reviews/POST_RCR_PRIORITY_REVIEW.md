# Post-RCR Product-Value Priority Review

## Starting point

RCR-01 through RCR-08 are closed. The next work is selected from exact BQ by product value, not by file size or a desire to drive Ruff to zero.

## Fresh BQ evidence

The repository-wide Ruff diagnostic reports 556 findings across 310 functions. That ledger is not a work queue. No production source function is >=200 lines after RCR closure, and the remaining >1,000-line CodeMap owners were explicitly reviewed as cohesive.

The highest-value remaining structural signal is task retrieval. `_task_local_lexical_island_hits` is on the repository-understanding hot path and reports C901=55, PLR0912=17, PLR0914=25, PLR0915=44. It also repeatedly classifies the same island paths while deciding whether the island is admissible. This combines a maintenance signal with a real repository-economics signal.

## PRI-01 — Task-local lexical-island projection

Decision: **REFACTOR INTERNALLY**.

Keep task retrieval as one owner. Separate rare-term eligibility, island validation/domain evidence, indexed-symbol binding, and final SearchHit projection. Cache path-domain classification only inside one call; do not introduce persistent ranking state or a new retrieval authority.

Contracts:
- normal RRF remains authoritative when the locality island does not qualify;
- exact one-token/symbol lookup behavior remains unchanged;
- same lexical index and document frequencies are used;
- same small-island, one-test-surface, actionable-source gates apply;
- same ordering, scores, visibility fallback, symbol projection, and limit semantics apply;
- no execution/recovery/admission behavior enters Hashmarks.

## Deferred measured candidates

The next review, if product evidence still justifies work, should compare retrieval scoring/prescore and evidence-graph construction against measured runtime/economics. `change_impact` and recovery remain correctness-sensitive and should not be churned again without a concrete defect or economics result. Large cohesive files are not candidates merely because they remain large.

## Stop rule

After each post-RCR phase, remeasure the affected hot path and its observable outputs. Stop when the remaining signal is diagnostic-only or when the next change would mainly redistribute complexity.
