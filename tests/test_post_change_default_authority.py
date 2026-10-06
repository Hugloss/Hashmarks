from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.post_change import (
    POST_CHANGE_DEFAULT_OPTIONS,
    PostChangeOptions,
)
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def test_post_change_defaults_have_one_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = POST_CHANGE_DEFAULT_OPTIONS
    assert (
        inspect.signature(CodeMap.refresh_after_change_delta)
        .parameters["options"]
        .default
        is defaults
    )
    assert (
        inspect.signature(CodeMapServiceClient.refresh_after_change_delta)
        .parameters["options"]
        .default
        is defaults
    )

    for owner in (CodeMap, CodeMapServiceClient):
        for method_name in ("refresh_after_change_brief", "refresh_after_change"):
            parameters = inspect.signature(getattr(owner, method_name)).parameters
            assert parameters["limit"].default == defaults.limit
            assert parameters["per_role"].default == defaults.per_role
            assert parameters["token_budget"].default == defaults.token_budget

    captured: dict[str, object] = {}

    class _Map:
        def refresh_after_change_delta(
            self,
            task: str,
            changed_paths: list[str],
            *,
            options: PostChangeOptions,
        ) -> dict[str, object]:
            captured["delta"] = options
            return {}

        def refresh_after_change_brief(
            self,
            task: str,
            changed_paths: list[str],
            *,
            limit: int,
            per_role: int,
            token_budget: int,
        ) -> dict[str, object]:
            captured["brief"] = (limit, per_role, token_budget)
            return {}

        def refresh_after_change(
            self,
            task: str,
            changed_paths: list[str],
            *,
            limit: int,
            per_role: int,
            token_budget: int,
        ) -> dict[str, object]:
            captured["full"] = (limit, per_role, token_budget)
            return {}

    service = CodeMapService(tmp_path, socket_path=tmp_path / "service.sock")
    monkeypatch.setattr(service, "_map", lambda: _Map())
    request = {
        "task": "inspect widget",
        "changed_paths": ["src/widget.py"],
    }
    service._refresh_delta_response(dict(request))
    service._refresh_brief_response(dict(request))
    service._refresh_response(dict(request))

    assert captured["delta"] == defaults
    expected = (defaults.limit, defaults.per_role, defaults.token_budget)
    assert captured["brief"] == expected
    assert captured["full"] == expected
