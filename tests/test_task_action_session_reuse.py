from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> str:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "owner.py").write_text(
        "def widget(value: str) -> str:\n    return value + '-old'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\n\n"
        "def test_widget():\n    assert widget('x') == 'x-new'\n",
        encoding="utf-8",
    )
    return "fix widget behavior and verify owner test"


def test_identical_task_action_requests_reuse_one_session_composition(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = 0
        original = codemap.find_task

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(codemap, "find_task", counted)
        with codemap.decision_session():
            first = codemap.task_action_map(task, limit=20, per_role=3)
            second = codemap.task_action_map(task, limit=20, per_role=3)
            stats = codemap.decision_session_stats()

        assert second == first
        assert calls == 1
        assert stats["task_action_miss"] == 1
        assert stats["task_action_hit"] == 1


def test_task_action_reuse_key_includes_task_limit_and_per_role(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = 0
        original = codemap.find_task

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(codemap, "find_task", counted)
        with codemap.decision_session():
            codemap.task_action_map(task, limit=20, per_role=3)
            codemap.task_action_map(task + " safely", limit=20, per_role=3)
            codemap.task_action_map(task, limit=21, per_role=3)
            codemap.task_action_map(task, limit=20, per_role=4)
            codemap.task_action_map(task, limit=20, per_role=3)
            stats = codemap.decision_session_stats()

        assert calls == 4
        assert stats["task_action_miss"] == 4
        assert stats["task_action_hit"] == 1


def test_cached_task_action_isolated_from_caller_mutation(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with codemap.decision_session():
            first = codemap.task_action_map(task)
            original_canonical = list(first["canonical"])
            first["canonical"].clear()
            first["bounds"]["limit"] = -1
            second = codemap.task_action_map(task)

        assert second["canonical"] == original_canonical
        assert second["bounds"]["limit"] == 20


def test_task_action_cache_is_not_reused_across_decision_sessions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = 0
        original = codemap.find_task

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(codemap, "find_task", counted)
        with codemap.decision_session():
            codemap.task_action_map(task)
            codemap.task_action_map(task)
        with codemap.decision_session():
            codemap.task_action_map(task)

        assert calls == 2
