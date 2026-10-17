from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from contract_assertions import assert_object

from hashmarks import CodeMap

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _counted(
    calls: dict[str, int], name: str, function: Callable[_P, _R]
) -> Callable[_P, _R]:
    def counted(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        calls[name] += 1
        return function(*args, **kwargs)

    return counted


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        calls = {"brief": 0, "freshness": 0}
        monkeypatch.setattr(
            codemap,
            "change_intelligence_brief",
            _counted(calls, "brief", codemap.change_intelligence_brief),
        )
        monkeypatch.setattr(
            codemap,
            "evidence_freshness_map",
            _counted(calls, "freshness", codemap.evidence_freshness_map),
        )

        with codemap.reads.session():
            first = codemap.repository_intelligence_snapshot(task, paths)
            profile = codemap.repository_intelligence_profile(
                task, paths, profile="compact"
            )
            economics = codemap.intelligence_economics_receipt(task, paths)
            repeated = codemap.repository_intelligence_snapshot(task, paths)
            stats = codemap.reads.stats()

        assert repeated == first
        assert profile["source_snapshot_identity"] == first["snapshot_identity"]
        assert economics["source_snapshot_identity"] == first["snapshot_identity"]
        assert calls == {"brief": 1, "freshness": 1}
        assert stats["snapshot_miss"] == 1
        assert stats["snapshot_hit"] == 3


def test_snapshot_reuse_key_includes_task_paths_and_all_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        calls = {"brief": 0}
        monkeypatch.setattr(
            codemap,
            "change_intelligence_brief",
            _counted(calls, "brief", codemap.change_intelligence_brief),
        )
        with codemap.reads.session():
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
            stats = codemap.reads.stats()

        assert calls["brief"] == 7
        assert stats["snapshot_miss"] == 7
        assert stats["snapshot_hit"] == 1


def test_cached_snapshot_isolated_from_caller_mutation(tmp_path: Path) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session():
            first = codemap.repository_intelligence_snapshot(task, paths)
            identity = first["snapshot_identity"]
            first["repository"] = {"mutated": True}
            assert_object(first["paths"]).clear()
            second = codemap.repository_intelligence_snapshot(task, paths)

        assert second["snapshot_identity"] == identity
        assert second["repository"] != {"mutated": True}
        assert "src/owner.py" in assert_object(second["paths"])


def test_snapshot_cache_is_not_reused_across_decision_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        calls = {"brief": 0}
        monkeypatch.setattr(
            codemap,
            "change_intelligence_brief",
            _counted(calls, "brief", codemap.change_intelligence_brief),
        )
        with codemap.reads.session():
            codemap.repository_intelligence_snapshot(task, paths)
            codemap.repository_intelligence_snapshot(task, paths)
        with codemap.reads.session():
            codemap.repository_intelligence_snapshot(task, paths)

        assert calls["brief"] == 2
