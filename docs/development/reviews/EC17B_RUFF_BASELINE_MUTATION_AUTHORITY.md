# EC-17B Ruff Baseline Mutation Authority Closure

## Fresh authority

Exact starting `main`: `edfda5f10cdb50f2af151e335b370a932cbf422f`.

EC-17A is already merged on this main:
- current Ruff baseline excess: **1,513**
- current functions with debt: **128**
- current rule findings: **245**
- production line ceiling: **1,600**
- oversized production files: **0**
- CI and `dev-check` already run `make lint-debt-gate` authoritatively.

The qualified EC-17A head and merge commit compare with zero changed files, so the merged baseline is the exact qualified baseline.

## Reproduced authority gap

EC-17A bound live inventory to the candidate's committed baseline, but the same candidate could edit `ruff-debt-baseline.json` and thereby authorize its own debt growth.

A second related gap existed in `_baseline_failures()`: Ruff rule thresholds were identity-bound, but `max_python_file_lines` was not compared between baseline snapshots. A candidate could therefore drift the configured structural ceiling together with its baseline unless another check caught it.

## Pre-edit adversarial regression

Commit `09d6bfe14545b84768dc0daeb6a3eb86abfaf832` freezes:
- line-ceiling drift must be rejected;
- a new debt file must be rejected;
- per-file excess growth must be rejected;
- downward ratchets and debt-file removal remain allowed;
- CI must bind the candidate baseline to a previous-main baseline rather than trusting the candidate baseline alone.

## Closure

`scripts/ruff_debt.py` now:
- compares `max_python_file_lines` as part of baseline authority;
- accepts `--previous-baseline`;
- validates previous-main baseline → candidate baseline before candidate baseline → live inventory;
- reports baseline-mutation failures separately while preserving the existing no-growth semantics.

`Makefile` accepts `RUFF_DEBT_PREVIOUS_BASELINE` and forwards it to the existing `lint-debt-gate`.

The CI fast gate now:
1. checks out enough history to resolve the first parent;
2. materializes `HEAD^1:ruff-debt-baseline.json` into runner-temporary storage;
3. passes that previous-main baseline into `make lint-debt-gate`;
4. remains blocking.

For pull-request merge refs, `HEAD^1` is the base/main parent. For a main push commit, `HEAD^1` is the previous main commit. No network fetch or mutable external baseline service is introduced.

## Authority properties

A candidate can no longer make debt growth pass merely by editing its own baseline:
- new debt files fail against previous main;
- per-file excess growth fails against previous main;
- total excess growth fails against previous main;
- Ruff threshold changes fail against previous main;
- production line-ceiling changes fail against previous main;
- current live inventory must still fit inside the candidate baseline.

A legitimate ratchet may:
- reduce per-file excess;
- remove debt files;
- reduce total excess;
- preserve the same rule thresholds and line ceiling.

This deliberately makes baseline mutation one-way. A responsibility split that creates a new debt-bearing file must first remove that debt or be handled as an explicit future governance change rather than silently laundering debt into a new owner.

## Qualification rule

Merge only if the exact PR head passes:
- the previous-main baseline resolution step;
- the blocking Ruff debt gate;
- all new adversarial tests;
- Python 3.11-3.14;
- release qualification;
- artifact and MCP qualification;
- final Qualification convergence.
