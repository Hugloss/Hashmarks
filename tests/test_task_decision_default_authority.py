from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.evidence_decision_packet import (
    TASK_DECISION_DEFAULT_OPTIONS,
    TaskDecisionOptions,
)
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def test_task_decision_packet_and_brief_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = TASK_DECISION_DEFAULT_OPTIONS
    for owner in (
        CodeMap.task_decision_packet,
        CodeMap.task_decision_brief,
        CodeMapServiceClient.task_decision_packet,
        CodeMapServiceClient.task_decision_brief,
    ):
        parameters = inspect.signature(owner).parameters
        assert parameters["limit"].default == defaults.limit
        assert parameters["per_role"].default == defaults.per_role
        assert parameters["token_budget"].default == defaults.token_budget

    captured: list[TaskDecisionOptions] = []

    class _Map:
        def task_decision_packet(
            self,
            task: str,
            *,
            limit: int,
            per_role: int,
            token_budget: int,
        ) -> dict[str, object]:
            del task
            captured.append(
                TaskDecisionOptions(
                    limit=limit,
                    per_role=per_role,
                    token_budget=token_budget,
                )
            )
            return {"schema": "hashmarks.task-decision-packet.v2"}

        def task_decision_brief(
            self,
            task: str,
            *,
            limit: int,
            per_role: int,
            token_budget: int,
        ) -> dict[str, object]:
            del task
            captured.append(
                TaskDecisionOptions(
                    limit=limit,
                    per_role=per_role,
                    token_budget=token_budget,
                )
            )
            return {"schema": "hashmarks.task-decision-brief.v1"}

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())

    service._decision_packet_response({"task": "inspect widget"})
    service._decision_brief_response({"task": "inspect widget"})

    assert captured == [defaults, defaults]
