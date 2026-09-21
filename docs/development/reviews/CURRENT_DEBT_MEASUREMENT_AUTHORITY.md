# Current Debt Measurement Authority

## Defect exposed by EC-14

The EC-14 review incorrectly treated `ruff-debt-baseline.json` as a fresh current-state measurement.

That file is a **no-growth ratchet authority**, not a current inventory. On the qualified PR #44 bytes, the baseline recorded repository excess **2,472**, while executable `make lint-debt-summary` reported current excess **1,543** across 128 functions / 255 findings and also reported two current production line-ceiling violations.

Therefore the earlier 2,472/189 ranking is not valid fresh-selection evidence. The behavior qualification of PR #44 remains valid; the cleanup-selection/debt-reduction interpretation does not.

## Correct rule

- `ruff-debt-baseline.json`: historical per-file no-growth ceiling.
- `make lint-debt-summary`: current aggregate diagnostic.
- `make lint-debt-json`: exact current per-file/function diagnostic for selection and before/after measurement.
- `make lint-debt-gate`: regression gate against the historical ratchet.

A fresh cleanup phase must select from executable current inventory, never by sorting the baseline.

## CI evidence

CI now emits both the concise current summary and exact current JSON inventory. The exact-inventory step is diagnostic and preserves Ruff's expected exit status semantics: 0 means no findings, 1 means findings were measured, and any other exit status fails the step.

## EC-14 correction

Do not continue the task-action cleanup from the stale baseline ranking. After this correction qualifies and merges, restart EC-14 selection from exact fresh main using `make lint-debt-json`. Treat the current line-ceiling violations reported by executable measurement as first-class candidates in that fresh review.
