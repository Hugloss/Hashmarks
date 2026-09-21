# EC-15 Verification Plan Ownership Closure

## Fresh authority

Exact starting `main`: `db5de75cd473058cf9d78d28ae29557b3cf54f22`.

Selection comes from the exact Ruff inventory emitted by CI run 679 on the bytes that were merged unchanged into this main. The committed `ruff-debt-baseline.json` is a historical no-growth budget, not the fresh measurement.

Fresh inventory:
- total excess: **1,513**
- functions with findings: **128**
- rule findings: **245**
- `task_action_projection.py`: **no live findings**
- oversized production files:
  - `hashmarks/codemap/evidence_verification.py`: **1,696** measured lines
  - `hashmarks/codemap/indexing_lifecycle.py`: **1,662** measured lines
- production ceiling: **1,600**

## Responsibility review

`evidence_verification.py` contained two separable repository responsibilities:

1. verification relevance/ownership evidence and selection;
2. bounded verification-plan projection for known test surfaces.

The second responsibility already has one public CodeMap contract, `verification_plan()`, and does not own task ranking, verification relevance, ownership, decision receipts, execution, or certification.

The plan owner covers Python/pytest, Go test packages, local Vitest/native node:test, and TypeScript project checking. It consumes an already-known repository test surface and emits bounded argv evidence only.

## Pre-edit contract freeze

`tests/test_verification_plan.py` already directly covered Python node selection and refusal of non-test source paths. Before moving production bytes, EC-15 added direct contract coverage for:
- Go package argv;
- TypeScript project argv;
- native `node:test` argv.

Test-freeze commit: `96783707f909d1ca797e7d778babff819b656348`.

## Bounded edit

The existing verification-plan methods were moved intact into:
`hashmarks/codemap/verification_plan.py` as `VerificationPlanMixin`.

`CodeMap.verification_plan()` remains the same public method through the CodeMap mixin composition. No compatibility wrapper or parallel plan implementation was added.

`evidence_verification.py` falls from **1,697 fetched lines to 1,506 fetched lines**, closing its line-ceiling violation with material headroom.

## Preserved boundaries

- Hashmarks still does not execute verification.
- Verification relevance and ownership stay in `VerificationMixin`.
- Selection envelope/downstream-consumption semantics stay in `hashmarks.verification_selection`.
- Decision receipts and packet identities are unchanged.
- Public method names and packet schemas are unchanged.
- No runner-discovery fallback or shell execution path is added.

## Qualification rule

Merge only if the exact PR head passes the complete repository CI matrix. After merge, remeasure fresh main before selecting the second oversized file or any Ruff hotspot.
