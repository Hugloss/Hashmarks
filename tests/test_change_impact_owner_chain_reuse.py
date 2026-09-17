from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks import CodeMap

if TYPE_CHECKING:
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


def test_owner_chain_reuse_keeps_sync_currentness_check(tmp_path: Path) -> None:
    task, paths = _go_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relation_calls = 0
        sync_calls = 0
        original_relation = codemap.ownership_relation_graph
        original_sync = codemap.sync

        def counted_relation(*args, **kwargs):
            nonlocal relation_calls
            relation_calls += 1
            return original_relation(*args, **kwargs)

        def counted_sync(*args, **kwargs):
            nonlocal sync_calls
            sync_calls += 1
            return original_sync(*args, **kwargs)

        codemap.ownership_relation_graph = counted_relation
        codemap.sync = counted_sync
        with codemap.decision_session(diagnostics=True):
            first = codemap.task_change_impact(task, paths)
            second = codemap.task_change_impact(task, paths)
        receipt = codemap.decision_session_diagnostics()

    assert first == second
    assert sync_calls == 2
    assert relation_calls == 2
    assert receipt is not None
    assert receipt["reuse"]["impact_owner_chain_miss"] == 1
    assert receipt["reuse"]["impact_owner_chain_hit"] == 1


def test_owner_chain_reuse_key_includes_task_action_bounds(tmp_path: Path) -> None:
    task, paths = _go_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with codemap.decision_session():
            codemap.task_change_impact(task, paths, limit=20, per_role=3)
            codemap.task_change_impact(task, paths, limit=21, per_role=3)
            codemap.task_change_impact(task, paths, limit=21, per_role=4)
            stats = codemap.decision_session_stats()

    assert stats["impact_owner_chain_miss"] == 3
    assert stats["impact_owner_chain_hit"] == 0


def test_owner_chain_reuse_does_not_cross_decision_sessions(tmp_path: Path) -> None:
    task, paths = _go_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relation_calls = 0
        original_relation = codemap.ownership_relation_graph

        def counted_relation(*args, **kwargs):
            nonlocal relation_calls
            relation_calls += 1
            return original_relation(*args, **kwargs)

        codemap.ownership_relation_graph = counted_relation
        with codemap.decision_session():
            codemap.task_change_impact(task, paths)
            codemap.task_change_impact(task, paths)
        with codemap.decision_session():
            codemap.task_change_impact(task, paths)

    assert relation_calls == 4


def test_owner_chain_cached_result_is_detached(tmp_path: Path) -> None:
    task, paths = _go_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with codemap.decision_session():
            action = codemap.task_action_map(task)
            _, _, _, _, _, _, visible, _ = codemap._change_impact_surface_state(
                tuple(paths),
                max_depth=4,
                impact_limit_per_surface=6,
                effective_project_impact_limit=6,
            )
            first = codemap._change_impact_owner_chain(
                task, action, tuple(paths), visible
            )
            first[3].append("mutated.py")
            second = codemap._change_impact_owner_chain(
                task, action, tuple(paths), visible
            )

    assert "mutated.py" not in second[3]
