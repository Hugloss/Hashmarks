# EC-17A Ruff Debt Authority Activation

## Fresh authority

Exact starting `main`: `7a77bd0e4ff602bc09152b3def4d1733f058fa35`.

EC-16 PR head `f95c00edf471efac894231791a331980fa5ac8a5` and the resulting merge commit were compared directly. GitHub reports the merge commit one commit ahead with **zero changed files**, proving the qualified PR source tree is byte-identical to this fresh main tree.

Therefore the exact Ruff inventory emitted by CI #685 is the current-main inventory:
- excess: **1,513**
- functions: **128**
- rule findings: **245**
- oversized production files: **0**

## Problem

The repository already had the correct no-growth implementation:

`make lint-debt-gate`
→ `scripts/ruff_debt.py --baseline ruff-debt-baseline.json`

The gate checks schema/threshold compatibility, rejects new debt files, rejects per-file excess growth, rejects total excess growth, and enforces the 1,600-line production ceiling.

But two authority defects remained:
1. the committed baseline was historical/stale at a much larger debt state;
2. CI and `dev-check` treated current debt as diagnostic-only and did not invoke the gate authoritatively.

## Closure

EC-17A:
- rewrites `ruff-debt-baseline.json` from the exact qualified current-main inventory;
- changes CI fast validation to run `make lint-debt-gate` without `continue-on-error`;
- changes `dev-check` to run the same blocking no-growth gate;
- retains the exact JSON inventory as a diagnostic surface;
- adds a static regression proving both CI and `dev-check` keep the gate authoritative.

No Ruff thresholds, inventory semantics, or baseline comparison semantics are changed.

## Explicit non-claim

EC-17A does **not** claim baseline-mutation authority closure.

A pull request can still modify `ruff-debt-baseline.json` in the same candidate it is testing. The newly activated gate binds current inventory to the candidate baseline, but does not yet bind candidate-baseline changes monotonically to the previous `main` baseline.

That bypass is intentionally reserved for the next phase, after this one-time stale-baseline convergence is merged. The next phase must compare baseline mutations against the previous-main baseline so a candidate cannot authorize its own debt growth.

## Qualification rule

Merge only if the exact PR head passes the complete CI matrix with the new blocking debt gate.

After merge:
1. establish the exact new `main` SHA;
2. prove the fresh baseline equals the fresh exact inventory;
3. implement baseline-mutation monotonicity without a reset exception;
4. add adversarial regressions for same-PR baseline inflation.
