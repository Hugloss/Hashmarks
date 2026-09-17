# Hashmarks HM39-R — Reference Visitor Economics Boundary

## Parent authority

Exact parent SHA-256: `a1821a821fe0f30c001bcdff352270188a41eae3e0c21c47838bc28dc80d4d03`.

## Decision

**REJECT-FUSION** — Do not fuse verification-specific reference semantics into the generic Python parser.

## Proof

After duplicate-read removal, reference-index projection is about 0.067 s cumulative for 664 first-touch candidates. This is real work, but fusing product-specific reachable-reference semantics into python_ast_cache would blur ownership for modest residual cost.

## Qualification

- focused affected ring: **51/51 PASS**
- compileall: **PASS**
- scale selection correctness: **4/4**
- unsafe regressions: **0**

## Guardrail

No source change is admitted without current-parent measurement or semantic proof. Hashmarks remains repository intelligence; no execution/resume authority is added.
