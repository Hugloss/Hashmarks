from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.change_impact import (
    CHANGE_IMPACT_DEFAULT_OPTIONS,
    ChangeImpactOptions,
)
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def test_change_impact_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core_default = (
        inspect.signature(CodeMap.task_change_impact).parameters["options"].default
    )
    client_default = (
        inspect.signature(CodeMapServiceClient.task_change_impact)
        .parameters["options"]
        .default
    )
    assert core_default is CHANGE_IMPACT_DEFAULT_OPTIONS
    assert client_default is CHANGE_IMPACT_DEFAULT_OPTIONS

    captured: dict[str, object] = {}

    class _Map:
        def task_change_impact(
            self,
            task: str,
            changed_paths: list[str],
            *,
            limit: int,
            per_role: int,
            options: ChangeImpactOptions,
        ) -> dict[str, object]:
            captured.update(
                task=task,
                changed_paths=changed_paths,
                limit=limit,
                per_role=per_role,
                options=options,
            )
            return {"schema": "hashmarks.task-change-impact.v1"}

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())
    service._change_impact_response(
        {
            "task": "inspect widget",
            "changed_paths": ["src/widget.py"],
        }
    )

    options = captured["options"]
    assert isinstance(options, ChangeImpactOptions)
    assert options == CHANGE_IMPACT_DEFAULT_OPTIONS
