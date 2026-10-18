"""Task-level entry-point projection over one supplied candidate observation."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from .decision_session import ReadScopeOwner, decision_scoped
from .query_router import NormalizedTaskQuery, normalize_task_query
from .task_action_types import TaskObservation

if TYPE_CHECKING:
    from .repository_tasks import RepositoryTasks


class TaskEntryPointsMixin(ReadScopeOwner):
    def _task_query(self, task: str) -> NormalizedTaskQuery:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        scope = self.reads.scope
        if scope is None:
            raise RuntimeError("task queries require an active read scope")
        reuse = self._task_observation_reuse
        if reuse.scope is not scope:
            reuse.scope = scope
            reuse.entries.clear()
            reuse.queries.clear()
        if task not in reuse.queries:
            reuse.queries[task] = normalize_task_query(task)
        return reuse.queries[task]

    def _task_observation(self, task: str, limit: int) -> TaskObservation:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        scope = self.reads.scope
        if scope is None:
            raise RuntimeError("task observations require an active read scope")
        query = self._task_query(task)
        reuse = self._task_observation_reuse
        key = (task, int(limit))
        if key not in reuse.entries:
            reuse.entries[key] = TaskObservation(
                query,
                self.search.observe_task(task, limit=limit),
                scope,
            )
        return reuse.entries[key]

    @decision_scoped
    def entry_points(
        self, task: str, *, limit: int = 20, per_role: int = 2
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if per_role < 1:
            raise ValueError("per_role must be >= 1")
        if per_role > 8:
            raise ValueError("per_role must be <= 8")
        observation = self._task_observation(task, limit)
        return self.ownership.entry_points_for_candidates(
            observation,
            limit=limit,
            per_role=per_role,
        )
