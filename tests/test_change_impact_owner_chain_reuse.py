from __future__ import annotations

from typing import TYPE_CHECKING, Never

import pytest
from contract_assertions import assert_object

from hashmarks import CodeMap
from hashmarks.codemap.model import SyncResult
from hashmarks.codemap.ownership_relation_defaults import (
    OWNERSHIP_RELATION_DEFAULT_OPTIONS,
)
from hashmarks.codemap.ownership_relation_types import OwnershipRelationGraph

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


def _go_repo(root: Path) -> tuple[str, list[str]]:
    (root / "go.mod").write_text(
        "module example.local/demo\n\ngo 1.23\n", encoding="utf-8"
    )
    for name in ("route", "service", "engine"):
        (root / name).mkdir()
    (root / "engine/engine.go").write_text(
        'package engine\nfunc ResolveCobaltRidgeAlpha(value string) string { return value + "-old" }\n',
        encoding="utf-8",
    )
    (root / "service/service.go").write_text(
        'package service\nimport "example.local/demo/engine"\nfunc ServiceValue(value string) string { return engine.ResolveCobaltRidgeAlpha(value) }\n',
        encoding="utf-8",
    )
    (root / "route/route.go").write_text(
        'package route\nimport "example.local/demo/service"\nfunc RouteValue(value string) string { return service.ServiceValue(value) }\n',
        encoding="utf-8",
    )
    (root / "route/cobaltridgealpha_test.go").write_text(
        'package route\nimport "testing"\nfunc TestCobaltRidgeAlpha(t *testing.T) {}\n',
        encoding="utf-8",
    )
    return "Change CobaltRidgeAlpha accepted response from old to new", [
        "engine/engine.go"
    ]


def test_owner_chain_reuse_keeps_sync_currentness_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, paths = _go_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        relation_calls = 0
        sync_calls = 0
        original_relation = codemap.ownership.relations
        original_sync = codemap.index.sync

        def counted_relation(
            task: str,
            start_path: str,
            *,
            max_depth: int = OWNERSHIP_RELATION_DEFAULT_OPTIONS.max_depth,
        ) -> OwnershipRelationGraph:
            nonlocal relation_calls
            relation_calls += 1
            return original_relation(task, start_path, max_depth=max_depth)

        def counted_sync(paths: Iterable[str | Path] | None = None) -> SyncResult:
            nonlocal sync_calls
            sync_calls += 1
            return original_sync(paths)

        monkeypatch.setattr(codemap.ownership, "relations", counted_relation)
        monkeypatch.setattr(codemap.index, "sync", counted_sync)
        with codemap.reads.session(diagnostics=True):
            first = codemap.changes.task_impact(task, paths)
            second = codemap.changes.task_impact(task, paths)
        receipt = codemap.reads.diagnostics()

    assert first == second
    assert sync_calls == 2
    assert relation_calls == 2
    assert receipt is not None
    assert assert_object(receipt["reuse"])["impact_owner_chain_miss"] == 1
    assert assert_object(receipt["reuse"])["impact_owner_chain_hit"] == 1


def test_owner_chain_reuse_key_includes_task_action_bounds(tmp_path: Path) -> None:
    task, paths = _go_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session():
            codemap.changes.task_impact(task, paths, limit=20, per_role=3)
            codemap.changes.task_impact(task, paths, limit=21, per_role=3)
            codemap.changes.task_impact(task, paths, limit=21, per_role=4)
            stats = codemap.reads.stats()

    assert stats["impact_owner_chain_miss"] == 3
    assert stats["impact_owner_chain_hit"] == 0


def test_owner_chain_reuse_does_not_cross_decision_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, paths = _go_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        relation_calls = 0
        original_relation = codemap.ownership.relations

        def counted_relation(
            task: str,
            start_path: str,
            *,
            max_depth: int = OWNERSHIP_RELATION_DEFAULT_OPTIONS.max_depth,
        ) -> OwnershipRelationGraph:
            nonlocal relation_calls
            relation_calls += 1
            return original_relation(task, start_path, max_depth=max_depth)

        monkeypatch.setattr(codemap.ownership, "relations", counted_relation)
        with codemap.reads.session():
            codemap.changes.task_impact(task, paths)
            codemap.changes.task_impact(task, paths)
        with codemap.reads.session():
            codemap.changes.task_impact(task, paths)

    assert relation_calls == 4


def test_owner_chain_cached_result_is_detached(tmp_path: Path) -> None:
    task, paths = _go_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session():
            action = codemap.tasks.action_map(task)
            state = codemap.changes._change_impact_surface_state(
                tuple(paths),
                max_depth=4,
                impact_limit_per_surface=6,
                effective_project_impact_limit=6,
            )
            first = codemap.changes._change_impact_owner_chain(
                task, action, state.visible
            )
            first[3].append("mutated.py")
            second = codemap.changes._change_impact_owner_chain(
                task, action, state.visible
            )

    assert "mutated.py" not in second[3]


def test_owner_chain_reconstruction_failure_keeps_selected_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, paths = _go_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()

        def unavailable(*_args: object, **_kwargs: object) -> Never:
            raise ValueError("owner evidence unavailable")

        monkeypatch.setattr(codemap.ownership, "relations", unavailable)
        action = {
            "edit": {"path": paths[0]},
            "verify": {"path": "route/cobaltridgealpha_test.go"},
        }
        edit, verify, verify_path, chain, relations = (
            codemap.changes._change_impact_owner_chain(task, action, lambda _: True)
        )

    assert edit == "engine/engine.go"
    assert verify == action["verify"]
    assert verify_path == "route/cobaltridgealpha_test.go"
    assert chain == []
    assert relations == {}
