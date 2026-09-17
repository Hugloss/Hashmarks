from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> tuple[str, list[str]]:
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
    return "fix widget behavior and verify owner test", ["src/owner.py"]


def test_identical_snapshot_requests_reuse_one_generation_bound_composition(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = {"brief": 0, "freshness": 0}
        original_brief = codemap.change_intelligence_brief
        original_freshness = codemap.evidence_freshness_map

        def counted_brief(*args, **kwargs):
            calls["brief"] += 1
            return original_brief(*args, **kwargs)

        def counted_freshness(*args, **kwargs):
            calls["freshness"] += 1
            return original_freshness(*args, **kwargs)

        monkeypatch.setattr(codemap, "change_intelligence_brief", counted_brief)
        monkeypatch.setattr(codemap, "evidence_freshness_map", counted_freshness)

        with codemap.decision_session():
            first = codemap.repository_intelligence_snapshot(task, paths)
            profile = codemap.repository_intelligence_profile(
                task, paths, profile="compact"
            )
            economics = codemap.intelligence_economics_receipt(task, paths)
            repeated = codemap.repository_intelligence_snapshot(task, paths)
            stats = codemap.decision_session_stats()

        assert repeated == first
        assert profile["source_snapshot_identity"] == first["snapshot_identity"]
        assert economics["source_snapshot_identity"] == first["snapshot_identity"]
        assert calls == {"brief": 1, "freshness": 1}
        assert stats["snapshot_miss"] == 1
        assert stats["snapshot_hit"] == 3


def test_snapshot_reuse_key_includes_task_paths_and_all_bounds(
    tmp_path: Path, monkeypatch
) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = 0
        original = codemap.change_intelligence_brief

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(codemap, "change_intelligence_brief", counted)
        with codemap.decision_session():
            codemap.repository_intelligence_snapshot(task, paths)
            codemap.repository_intelligence_snapshot(task + " safely", paths)
            codemap.repository_intelligence_snapshot(
                task, [*paths, "tests/test_owner.py"]
            )
            codemap.repository_intelligence_snapshot(task, paths, limit=21)
            codemap.repository_intelligence_snapshot(task, paths, per_role=4)
            codemap.repository_intelligence_snapshot(
                task, paths, impact_limit_per_surface=5
            )
            codemap.repository_intelligence_snapshot(task, paths, max_depth=4)
            codemap.repository_intelligence_snapshot(task, paths)
            stats = codemap.decision_session_stats()

        assert calls == 7
        assert stats["snapshot_miss"] == 7
        assert stats["snapshot_hit"] == 1


def test_cached_snapshot_isolated_from_caller_mutation(tmp_path: Path) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with codemap.decision_session():
            first = codemap.repository_intelligence_snapshot(task, paths)
            identity = first["snapshot_identity"]
            first["repository"] = {"mutated": True}
            first["paths"].clear()
            second = codemap.repository_intelligence_snapshot(task, paths)

        assert second["snapshot_identity"] == identity
        assert second["repository"] != {"mutated": True}
        assert "src/owner.py" in second["paths"]


def test_snapshot_cache_is_not_reused_across_decision_sessions(
    tmp_path: Path, monkeypatch
) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = 0
        original = codemap.change_intelligence_brief

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(codemap, "change_intelligence_brief", counted)
        with codemap.decision_session():
            codemap.repository_intelligence_snapshot(task, paths)
            codemap.repository_intelligence_snapshot(task, paths)
        with codemap.decision_session():
            codemap.repository_intelligence_snapshot(task, paths)

        assert calls == 2
