from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.ownership_relation_defaults import (
    OWNERSHIP_RELATION_DEFAULT_OPTIONS,
    OwnershipRelationOptions,
)
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def test_ownership_relation_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = OWNERSHIP_RELATION_DEFAULT_OPTIONS
    for owner in (
        CodeMap.ownership_relation_graph,
        CodeMapServiceClient.ownership_relation_graph,
    ):
        parameters = inspect.signature(owner).parameters
        assert parameters["max_depth"].default == defaults.max_depth

    captured: list[OwnershipRelationOptions] = []

    class _Map:
        def ownership_relation_graph(
            self,
            task: str,
            start_path: str,
            *,
            max_depth: int,
        ) -> dict[str, object]:
            del task, start_path
            captured.append(OwnershipRelationOptions(max_depth=max_depth))
            return {"schema": "hashmarks.ownership-relation-graph.v1"}

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())

    service._ownership_relation_response(
        {
            "task": "inspect widget",
            "start_path": "src/widget.py",
        }
    )

    assert captured == [defaults]
