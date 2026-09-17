# Hashmarks HM29-R — Store Batch Economics Closure

## Parent authority

Exact parent SHA-256: `2e9c59203895ebc1678002d4af2f3872393727b4f06d3931da79067b8136958c`.

## Decision

NO CHANGE; retain batched store ownership and avoid row-at-a-time regression.

## Evidence

- Candidate symbols are fetched with one symbols_for_paths_many bounded query rather than row-at-a-time symbols_for_path calls.
- The store API preserves an independent per-path symbol bound, avoiding global-LIMIT starvation.
- Changing this path to per-candidate reads would regress store economics; no evidence supports a new store cache.

## Qualification

- focused affected ring: **57/57 PASS**
- compileall: **PASS**
- scale selection correctness: **4/4**
- unsafe regressions: **0**
- 501-surface action sample: **293.26 ms**
