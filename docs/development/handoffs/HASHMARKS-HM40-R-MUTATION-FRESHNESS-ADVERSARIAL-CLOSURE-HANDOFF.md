# Hashmarks HM40-R — Mutation Freshness Adversarial Closure

## Parent authority

Exact parent SHA-256: `8449f77817d4cceb0c699845abff3def51c02b181978f7f70bbdb7b8093a3c2e`.

## Decision

**CLOSE** — Preserve exact freshness invalidation after the HM32-R optimization.

## Proof

Existing mutation test rewrites a verifier from reachable symbol use to TYPE_CHECKING-only and the second decision observes type-checking-only, proving the optimization does not reuse stale reference evidence.

## Qualification

- focused affected ring: **51/51 PASS**
- compileall: **PASS**
- scale selection correctness: **4/4**
- unsafe regressions: **0**

## Guardrail

No source change is admitted without current-parent measurement or semantic proof. Hashmarks remains repository intelligence; no execution/resume authority is added.
