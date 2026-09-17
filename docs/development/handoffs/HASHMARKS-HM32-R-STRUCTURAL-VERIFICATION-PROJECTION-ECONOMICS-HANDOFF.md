# Hashmarks HM32-R — Structural Verification Projection Economics

## Parent authority

Exact parent SHA-256: `369b1e564345c9f23d6b3d93a7d059febce35c39bb34f8a99aac30e5d0f9469f`.

## Decision

**ADMIT** — Eliminate the duplicate first-touch AST snapshot read before reference projection.

## Proof

cProfile proves 1,328 read_python_ast calls for 664 candidate rows. After the change there are 664 reads for 664 rows; focused ring 51/51 PASS; compileall PASS; selection 4/4 and unsafe regressions 0.

## Qualification

- focused affected ring: **51/51 PASS**
- compileall: **PASS**
- scale selection correctness: **4/4**
- unsafe regressions: **0**

## Guardrail

No source change is admitted without current-parent measurement or semantic proof. Hashmarks remains repository intelligence; no execution/resume authority is added.
