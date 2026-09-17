# Responsibility / Complexity Review — BL

## Candidate: `hashmarks/codemap/task_action_projection.py`

Decision: **REFACTOR INTERNALLY**.

The module owns one cohesive responsibility: projection of canonical repository task evidence into the existing task-action-map contract. The problem was not file ownership; it was the 399-line orchestration method mixing surface selection, structural-owner resolution, verification projection, and ambiguity discrimination.

No new module was introduced. The method was decomposed into responsibility-named private stages:

- `_task_action_initial_surface_selection`: explicit/test/build/config/locality surface selection from already retrieved evidence.
- `_task_action_resolve_structural_owner`: structural owner resolution from existing repository evidence.
- `_task_action_projection_ambiguity_state`: ambiguity discrimination over already selected evidence.

`task_action_map()` is now the orchestration boundary. It remains the public contract owner and still returns `hashmarks.task-action-map.v1` without changing ranking, discovery, identity, negative-evidence, verification-relevance, ownership, or ambiguity semantics.

Measured direct function size / branch-node proxy:

- `task_action_map`: 399 lines / 57 branch nodes at the pre-refactor baseline -> 195 lines / 12 branch nodes.
- initial surface selection: 119 / 26.
- structural owner resolution: 91 / 19.
- ambiguity discrimination: 123 / 6.

The file is larger after decomposition because responsibility boundaries are explicit. That is accepted: LOC is not the optimization target.

## Navigation review

A maintainer looking for task-action projection still has one obvious owner: `task_action_projection.py`. The refactor does not scatter the invariant across modules or introduce forwarding-only files. The helper names describe stages of the responsibility rather than historical file origin.

## Next measured target

`repository_context.py::_context_impl` remains a high-complexity cohesive owner and should receive the same review before any extraction. Current measurement: 268 lines / 67 branch-node proxy.
