from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.repository_intelligence_query import (
    REPOSITORY_INTELLIGENCE_QUERY_DEFAULTS,
    RepositoryIntelligenceQueryOptions,
)
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def test_repository_intelligence_query_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core_default = (
        inspect.signature(CodeMap.repository_intelligence_query)
        .parameters["options"]
        .default
    )
    client_default = (
        inspect.signature(CodeMapServiceClient.repository_intelligence_query)
        .parameters["options"]
        .default
    )
    assert core_default is REPOSITORY_INTELLIGENCE_QUERY_DEFAULTS
    assert client_default is REPOSITORY_INTELLIGENCE_QUERY_DEFAULTS

    captured: dict[str, object] = {}

    class _Map:
        def repository_intelligence_query(
            self,
            surface: str,
            task: str,
            changed_paths: list[str],
            *,
            options: RepositoryIntelligenceQueryOptions,
        ) -> dict[str, object]:
            captured.update(
                surface=surface,
                task=task,
                changed_paths=changed_paths,
                options=options,
            )
            return {"schema": "hashmarks.repository-intelligence-query.v1"}

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())
    service._repository_intelligence_query_response(
        {
            "surface": "profile",
            "task": "inspect widget",
            "changed_paths": ["src/widget.py"],
        }
    )

    options = captured["options"]
    assert isinstance(options, RepositoryIntelligenceQueryOptions)
    assert options == REPOSITORY_INTELLIGENCE_QUERY_DEFAULTS
