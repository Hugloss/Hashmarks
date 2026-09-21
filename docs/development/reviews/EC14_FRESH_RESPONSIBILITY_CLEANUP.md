# EC-14 Fresh Responsibility-First Cleanup

## Fresh authority

Exact starting `main`: `8e344b0550ab08b374dff2a7e6ff501b78a2fb41`.

This measurement was taken only after EC-13 merged. No historical hotspot was selected in advance.

## Current repository debt measurement

Current `ruff-debt-baseline.json` records:

- total excess: **2,472**
- functions with findings: **192**
- rule findings: **386**

Highest current files by measured excess:

| Rank | File | Excess | Functions | Rule findings |
| ---: | --- | ---: | ---: | ---: |
| 1 | `hashmarks/codemap/task_action_projection.py` | **189** | 4 | 16 |
| 2 | `hashmarks/codemap/change_impact.py` | 135 | 4 | 14 |
| 3 | `scripts/agent_evaluation/metrics_agent_experiment_set.py` | 118 | 2 | 5 |
| 4 | `hashmarks/qualification_units.py` | 115 | 3 | 8 |
| 5 | `hashmarks/codemap/work_context.py` | 105 | 3 | 10 |
| 6 | `scripts/agent_evaluation/metrics_agent_regret.py` | 100 | 1 | 4 |
| 7 | `hashmarks/codemap/indexing_lifecycle.py` | 90 | 10 | 21 |
| 8 | `scripts/agent_evaluation/metrics_agent_trace.py` | 85 | 3 | 8 |
| 9 | `scripts/agent_evaluation/internal_agent_ledger.py` | 75 | 1 | 3 |
| 10 | `hashmarks/codemap/freshness_map.py` | 72 | 1 | 5 |

The freshly selected production candidate is therefore `task_action_projection.py`. Its historical appearance as a hotspot is not selection authority; the current exact-main measurement independently selects it again.

## Candidate responsibility review

Current file size: **816 lines**.

The module remains the task-action projection owner. Its named internal stages already separate context acquisition, surface-owner state, promoted edit selection, local contract, projection choices/final state/result, explicit/initial surface selection, verification/config surfaces, and ambiguity projection.

Classification for the next bounded phase: **REFACTOR INTERNALLY**, not module extraction.

The current evidence does not justify a second semantic owner. The cleanup target is the four currently debt-bearing functions selected by the exact Ruff inventory, with behavior frozen before edits.

## Required pre-edit proof

Before production edits:

1. identify the exact four debt-bearing functions and their rule/observed values from a fresh Ruff inventory;
2. establish direct owning tests for each changed responsibility;
3. freeze exact source identity and direct test bytes under the BP1 workflow;
4. obtain complete structural-locality evidence with bounds raised when an observer reports exhaustion;
5. add focused behavior/adversarial tests only where an invariant is not already directly protected.

The preserved authority includes canonical `find_task()` retrieval, canonical rank/provenance, decision-session cache identity and copy isolation, explicit test/build/config selection, structural ownership, verification relevance, ambiguity/freshness fail-closed behavior, and public packet ordering/schema.

## Edit rule

Reduce accidental control-flow complexity by responsibility-named internal stages or cohesive typed state only. Do not add forwarding-only helpers, `*_utils`, `*_core`, parallel projection paths, new public surfaces, or changed authority.

After each bounded production edit, replay frozen tests, run the broader repository gate, measure exact post-edit debt/locality, and ratchet only measured improvement.

## Stop rule

Do not assume `change_impact.py` is next. After the selected candidate closes, restart from exact then-current main and remeasure. The current ranking is evidence for this point in time only.
