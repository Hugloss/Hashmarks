# EC-14 Fresh Current-Debt Selection

## Exact authority

Fresh main: `edc321cf9231f7cf127710ccbd767120e045c65b`.

CI run **624** completed successfully and emitted the exact executable `hashmarks.ruff-debt.v3` inventory.

Current repository inventory:

- excess: **1,543**
- functions: **128**
- rule findings: **255**
- production line ceiling: **1,600**

The historical `ruff-debt-baseline.json` is not selection authority.

## Fresh production ranking

The largest current production debt item is:

`hashmarks/codemap/structural_locality.py`
- excess: **69**
- functions: **5**
- rule findings: **15**
- current source lines: **974**
- source blob: `ed2af86f41dbb7fb8fa7d7eba5f69eec241b272c`

Other high current production items include `task_action_owner_resolution.py` (40), `task_retrieval.py` (39), `evidence_graph.py` (39), `indexing_lifecycle.py` (35), and `repository_evidence_bindings.py` (32).

The executable inventory contains no `task_action_projection.py` debt row, so the previous task-action selection is closed and must not be carried forward.

## Line-ceiling findings

Two production modules independently exceed the 1,600-line ceiling:

- `hashmarks/codemap/evidence_verification.py`: 1,696
- `hashmarks/codemap/indexing_lifecycle.py`: 1,662

These are first-class maintainability findings, but this phase does not automatically rank a line-ceiling violation above function-level excess. They require responsibility/owner review before any module split.

## Selected next review

Fresh executable evidence selects `structural_locality.py` as the current production function-debt leader.

Direct owning test:
`tests/test_structural_locality.py`
- blob: `24ffaa0d77627eddfdf207226ede8f56e8ab3082`
- 785 lines

The owner is particularly authority-sensitive because it establishes structural locality, exact caller evidence and bounded-reference completeness used by behavior-preserving workflows. A cleanup must not weaken fail-closed handling of exhausted reference bounds, exact target identity, method/receiver ownership, or caller completeness.

## Admission before edit

Do not mechanically extract helpers from this module. Before production editing:

1. obtain exact per-function Ruff diagnostics for the five debt-bearing functions;
2. map each candidate to direct tests and callers;
3. freeze source and direct-test identities;
4. establish complete structural-locality evidence, raising reference bounds when incomplete;
5. select a responsibility seam that plausibly reduces the measured rule values;
6. preserve exact target/caller identity and fail-closed bound-completeness semantics.

If no seam can satisfy those conditions, stop rather than move code.
