from __future__ import annotations

import argparse
import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.change_impact import (
    CHANGE_IMPACT_DEFAULT_REQUEST,
    ChangeImpactOptions,
)
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient
from hashmarks.repository_cli import add_repository_cli

if TYPE_CHECKING:
    from pathlib import Path


def test_change_impact_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = CHANGE_IMPACT_DEFAULT_REQUEST
    for owner in (CodeMap.task_change_impact, CodeMapServiceClient.task_change_impact):
        parameters = inspect.signature(owner).parameters
        assert parameters["limit"].default == defaults.limit
        assert parameters["per_role"].default == defaults.per_role
        assert parameters["options"].default is defaults.options

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_repository_cli(
        sub,
        add_common_arguments=lambda _parser, *, inherited=False: None,
    )
    args = parser.parse_args(
        ["change-impact", "inspect widget", "--changed", "src/widget.py"]
    )
    assert args.limit == defaults.limit
    assert args.per_role == defaults.per_role
    assert args.impact_limit == defaults.options.impact_limit_per_surface
    assert args.max_depth == defaults.options.max_depth
    assert args.project_impact_limit == defaults.options.project_impact_limit
    assert args.project_impact_encoding == defaults.options.project_impact_encoding

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

    assert captured["limit"] == defaults.limit
    assert captured["per_role"] == defaults.per_role
    options = captured["options"]
    assert isinstance(options, ChangeImpactOptions)
    assert options == defaults.options
