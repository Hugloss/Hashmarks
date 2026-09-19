# Agent Economics behavior-preserving split dogfood

> [!IMPORTANT]
> Temporary experiment branch. Do not merge or delete until the experiment evidence has converged.
> Hashmarks remains the behavior, policy, and qualification authority. Agent Economics is measurement/evidence only.

## Bound identities

- Hashmarks source: `e8e2146273401cbe7de0b5239727a396426953df`
- agentsCookbook qualified source: `acf435e124d963bb56033b9d5f5f83cb93630916`
- agentsCookbook exact-main CI: Validate cookbook run `35457831326` PASS
- Agent Economics capability under dogfood: behavior-preservation BP1

## Phase HBP0 — fresh current-main measurement

Do not choose a target from the historical `ruff-debt` branch. Materialize the exact agentsCookbook commit above into `.agent-economics` and run the existing parity harness against these Hashmarks bytes.

Required commands in a real checkout:

```sh
sh /path/to/agentsCookbook/scripts/bootstrap-agent-economics.sh \
  --revision acf435e124d963bb56033b9d5f5f83cb93630916 \
  --destination .agent-economics
export PYTHONPATH="$PWD/.agent-economics/scripts"
UV_PROJECT_ENVIRONMENT=.ruff-venv uv sync --only-group lint --python 3.11
PATH="$PWD/.ruff-venv/bin:$PATH" uv run --no-sync python \
  scripts/agent_evaluation/ruff_debt_agent_economics_parity.py
```

The committed `ruff-debt-baseline.json` is only the no-growth baseline, not the current measurement. Its historical total is 2472 excess. Target selection must use the fresh Agent Economics output.

## Phase HBP1 — candidate selection

Select exactly one production candidate from the fresh `ranked_hotspots` output. Ranking is investigation priority only.

For the selected path:

1. run Agent Economics `test-focus` with Hashmarks source/test roots and repository gates;
2. use Hashmarks repository intelligence to inspect direct behavior/authority boundaries and affected dependents;
3. declare the concrete behaviors that the split must preserve;
4. identify tests that directly protect each declared boundary;
5. run those tests against the exact pre-edit source bytes;
6. bind their PASS execution receipt to the source/test identities;
7. feed that evidence into `behavior_preservation_readiness`.

Do not edit production code unless the evidence contract reaches `READY_FOR_BEHAVIOR_PRESERVING_EDIT`. READY is not edit authority; it means only that the pre-edit protection is adequate to attempt the externally owned refactor.

If the result is `TEST_STRENGTHENING_REQUIRED`, add focused behavioral/adversarial tests first and qualify them before production edits.

If the result is `EVIDENCE_REQUIRED`, resolve the missing/stale/mismatched evidence rather than bypassing it.

## Phase HBP2 — one bounded split

Perform one structural split with no intentional behavior change.

Preferred forms are narrow typed state/configuration objects or focused helpers that make ownership clearer. Do not add compatibility paths, duplicate implementations, policy changes, or abstractions whose only purpose is lowering a metric.

The pre-edit behavioral tests are frozen as the invariant across the split.

## Phase HBP3 — verification ladder

After the edit:

1. rerun the exact bound focused behavioral tests;
2. run affected/component verification selected from repository evidence;
3. run Hashmarks repository-owned broader gates;
4. run Ruff correctness/format/debt diagnostics;
5. rerun the Agent Economics debt measurement.

A focused PASS never closes the change. If a strong frozen test fails, repair the implementation unless the test is proven to violate the intended behavior contract.

## Phase HBP4 — accept or revert

Retain the split only when:

- frozen behavior remains protected;
- broader repository verification passes;
- no authority/policy boundary moved unintentionally;
- structural complexity was removed rather than hidden or redistributed;
- fresh debt evidence is compatible and does not introduce a per-file regression.

Then select the next candidate from the newly measured repository bytes, never from a static list.

## Current evidence available before native execution

The committed Hashmarks no-growth baseline records historical hotspots including `hashmarks/codemap/task_action_projection.py` (189 excess), `hashmarks/qualification_units.py` (115), and `hashmarks/codemap/work_context.py` (105). These are **not selected targets**. They demonstrate why a fresh measurement is required: the baseline predates later cleanup and cannot authorize the next edit.

This GitHub/API environment cannot execute the repository-local Ruff/uv/pytest commands, so HBP0 remains `NATIVE_MEASUREMENT_REQUIRED` until the exact commands above run against a checkout.
