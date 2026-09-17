# Hashmarks HM26-R — Residual Candidate / Store / Classification / Ranking Economics

## Parent authority

Exact HM25-R SHA-256: `d3ab0ef5a72f35dc7ed3373628a2a4df768683cb115e84d981f28fb24cefa771`.

## Result

HM26-R is intentionally measurement-only. It does not add another cache or alter selection semantics.

The scale corpus remained 4/4 correct with zero unsafe regressions. Candidate membership was 11, 51, 101, and 501 surfaces; action time was approximately 25.67, 60.79, 92.42, and 282.25 ms in this run.

A cProfile run on the 501-surface case attributes the dominant residual inside `task_action_map()` to verification relevance and specifically per-candidate projection/reference-strength work. `symbols_for_paths_many()` is already batched. Repository-path classification is already bounded path-only `lru_cache` derived metadata. Final ranking/top-N was not the dominant measured cost.

Therefore HM26-R admits no speculative source optimization. The next optimization must prove that an inexpensive candidate-admission/prefilter stage is complete for every candidate that could affect selection or ambiguity before expensive reference-strength work is skipped.

## Qualification

- focused residual ring: **54/54 PASS**
- compileall: **PASS**
- selection correctness: **4/4**
- unsafe regressions: **0**

## Next phase

**HM27-R — Candidate Admission / Prefilter Equivalence Proof.** Build an instrumented scorer that compares full evaluation against candidate subsets across adversarial and real-repository tasks. No source optimization is admitted unless selected verification, ambiguity state, fail-closed behavior, and candidate evidence are semantically equivalent.
