from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.evidence_packet import (
    TASK_ACTION_BRIEF_BUDGET_DEFAULT_OPTIONS,
)
from hashmarks.codemap.repository_tasks import RepositoryTasks
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient
from hashmarks.codemap.task_action_projection import (
    TASK_ACTION_DEFAULT_OPTIONS,
    TaskActionOptions,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_task_action_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selection = TASK_ACTION_DEFAULT_OPTIONS
    budget = TASK_ACTION_BRIEF_BUDGET_DEFAULT_OPTIONS

    for owner in (RepositoryTasks.action_map, CodeMapServiceClient.task_action_map):
        parameters = inspect.signature(owner).parameters
        assert parameters["limit"].default == selection.limit
        assert parameters["per_role"].default == selection.per_role

    for owner in (RepositoryTasks.action_brief, CodeMapServiceClient.task_action_brief):
        parameters = inspect.signature(owner).parameters
        assert parameters["limit"].default == selection.limit
        assert parameters["per_role"].default == selection.per_role
        assert parameters["token_budget"].default == budget.token_budget

    brief_parameters = inspect.signature(RepositoryTasks.action_brief).parameters
    assert brief_parameters["candidate_budgets"].default == budget.candidate_budgets

    captured: list[tuple[str, TaskActionOptions, int | None]] = []

    class _TaskViews:
        def action_map(
            self, task: str, *, limit: int, per_role: int
        ) -> dict[str, object]:
            del task
            captured.append(("map", TaskActionOptions(limit, per_role), None))
            return {"schema": "hashmarks.task-action-map.v1"}

        def action_brief(
            self,
            task: str,
            *,
            limit: int,
            per_role: int,
            token_budget: int | None,
        ) -> dict[str, object]:
            del task
            captured.append(("brief", TaskActionOptions(limit, per_role), token_budget))
            return {"schema": "hashmarks.task-action-brief.v1"}

    class _Map:
        def __init__(self) -> None:
            self.tasks = _TaskViews()

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())

    service._task_action_map_response({"task": "inspect widget"})
    service._task_action_brief_response({"task": "inspect widget"})

    assert captured == [
        ("map", selection, None),
        ("brief", selection, budget.token_budget),
    ]
