from __future__ import annotations

import argparse
import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.evidence_packet import (
    TASK_EVIDENCE_DEFAULT_OPTIONS,
    TaskEvidenceOptions,
)
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient
from hashmarks.mcp_surface import HashmarksMcpSurface
from hashmarks.operation_contract import operation_schema
from hashmarks.repository_cli import add_repository_cli

if TYPE_CHECKING:
    from pathlib import Path


def test_task_evidence_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = TASK_EVIDENCE_DEFAULT_OPTIONS
    for owner in (
        CodeMap.task_evidence,
        CodeMap.task_post_change_delta,
        CodeMapServiceClient.task_evidence,
        CodeMapServiceClient.task_post_change_delta,
    ):
        parameters = inspect.signature(owner).parameters
        assert parameters["limit"].default == defaults.limit
        assert parameters["per_role"].default == defaults.per_role
        assert parameters["token_budget"].default == defaults.token_budget

    surface_parameters = inspect.signature(HashmarksMcpSurface.task_evidence).parameters
    assert surface_parameters["limit"].default == defaults.limit
    assert surface_parameters["per_role"].default == defaults.per_role
    assert surface_parameters["token_budget"].default == defaults.token_budget
    post_change_parameters = inspect.signature(HashmarksMcpSurface.post_change).parameters
    assert post_change_parameters["token_budget"].default == defaults.token_budget

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_repository_cli(
        sub,
        add_common_arguments=lambda _parser, *, inherited=False: None,
    )
    args = parser.parse_args(["task-evidence", "inspect widget"])
    assert args.limit == defaults.limit
    assert args.per_role == defaults.per_role
    assert args.budget == defaults.token_budget

    captured: dict[str, object] = {}

    class _Map:
        def task_evidence(
            self,
            task: str,
            *,
            limit: int,
            per_role: int,
            token_budget: int,
        ) -> dict[str, object]:
            captured.update(
                task=task,
                options=TaskEvidenceOptions(
                    limit=limit,
                    per_role=per_role,
                    token_budget=token_budget,
                ),
            )
            return {"schema": operation_schema("task_evidence")}

        def task_post_change_delta(
            self,
            task: str,
            changed_paths: list[str],
            *,
            previous_evidence: dict[str, object],
            limit: int,
            per_role: int,
            token_budget: int,
        ) -> dict[str, object]:
            del changed_paths, previous_evidence
            captured.update(
                post_change_task=task,
                post_change_options=TaskEvidenceOptions(
                    limit=limit,
                    per_role=per_role,
                    token_budget=token_budget,
                ),
            )
            return {"schema": operation_schema("post_change")}

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())
    service._task_evidence_response({"task": "inspect widget"})
    service._post_change_delta_response(
        {
            "task": "inspect widget",
            "changed_paths": ["src/widget.py"],
            "previous_evidence": {},
        }
    )

    assert captured["options"] == defaults
    assert captured["post_change_options"] == defaults

    surface = HashmarksMcpSurface(str(tmp_path), state_dir=str(tmp_path / "state"))
    real_map = surface._map
    surface._map = _Map()
    try:
        surface.post_change(
            "inspect widget",
            ["src/widget.py"],
            {},
        )
    finally:
        real_map.close()
    assert captured["post_change_options"] == defaults
