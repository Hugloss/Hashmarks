# Hashmarks HM33-R — Warm Reference Projection Reuse Proof

## Parent authority

Exact parent SHA-256: `aa7c92a0ab0243e5ccee46963b29cf6c9fc81d3fbbfc33c9675cb6516e1090ab`.

## Decision

**CLOSE-NO-CHANGE** — Retain the freshness-bound projection cache; do not add a broader decision or repository cache.

## Proof

The projection cache is already keyed by absolute path, exact filesystem identity, and AST object identity. Mutation regression proves stale projection is not reused. No broader cache is justified.

## Qualification

- focused affected ring: **51/51 PASS**
- compileall: **PASS**
- scale selection correctness: **4/4**
- unsafe regressions: **0**

## Guardrail

No source change is admitted without current-parent measurement or semantic proof. Hashmarks remains repository intelligence; no execution/resume authority is added.
