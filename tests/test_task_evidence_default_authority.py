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
from hashmarks.repository_cli import add_repository_cli

if TYPE_CHECKING:
    from pathlib import Path


def test_task_evidence_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = TASK_EVIDENCE_DEFAULT_OPTIONS
    for owner in (
        CodeMap.task_evidence,
        HashmarksMcpSurface.task_evidence,
        CodeMapServiceClient.task_evidence,
    ):
        parameters = inspect.signature(owner).parameters
        assert parameters["limit"].default == defaults.limit
        assert parameters["per_role"].default == defaults.per_role
        assert parameters["token_budget"].default == defaults.token_budget

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
            return {"schema": "hashmarks.task-evidence.v3"}

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())
    service._task_evidence_response({"task": "inspect widget"})

    assert captured["options"] == defaults
