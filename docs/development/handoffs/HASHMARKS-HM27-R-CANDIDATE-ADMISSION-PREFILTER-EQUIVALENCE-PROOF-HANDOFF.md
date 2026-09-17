# Hashmarks HM27-R — Candidate Admission Prefilter Equivalence Proof

## Parent authority

Exact parent SHA-256: `afae7be19f567dda9eda45352ea1add5d536f28962e829f2000964b6f8708105`.

## Decision

REJECT cheap candidate exclusion; preserve full semantic candidate evaluation.

## Evidence

- Cheap path/task/canonical prefiltering is not admitted: candidate score semantics allow reference strength to dominate locality and task anchors.
- Existing adversarial reachable-symbol, reachable-import, type-checking-only, statically-dead, ambiguity, re-export, alias, and indirect-reference tests demonstrate that syntactically similar candidates can differ semantically.
- At 501 surfaces the correct local verifier remains selected; dropping candidates before reference-strength evidence would require a completeness theorem not established by current evidence.

## Qualification

- focused affected ring: **57/57 PASS**
- compileall: **PASS**
- scale selection correctness: **4/4**
- unsafe regressions: **0**
- 501-surface action sample: **293.26 ms**
