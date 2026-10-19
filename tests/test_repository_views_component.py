"""Aggregate views consume exact lower owners and a shared snapshot projection."""

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from test_repository_changes_component import _publishing_after
from test_repository_index_component import index as index
from test_repository_tasks_component import tasks as tasks
from test_worktree_overlay import _publish_generation_only

from hashmarks.codemap.cross_repository_evidence import RepositoryCrossRepository
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.intelligence_economics import RepositoryEconomics
from hashmarks.codemap.repository_changes import RepositoryChanges
from hashmarks.codemap.repository_intelligence_query import RepositoryViews
from hashmarks.codemap.repository_tasks import RepositoryTasks


def _views(tasks: RepositoryTasks) -> RepositoryViews:
    changes = RepositoryChanges(tasks, tasks.repository_relationships)
    return RepositoryViews(
        changes,
        RepositoryCrossRepository(changes),
        RepositoryEconomics(changes),
        tasks.structure,
    )


def test_independent_views_and_economics_use_the_same_scoped_snapshot(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
) -> None:
    (index.workspace / "owner.py").write_text("def calculate_total(): return 1\n")
    index.sync()
    views = _views(tasks)
    with views.reads.session():
        profile = views.profile("Change owner.calculate_total", ["owner.py"])
        receipt = views.economics.receipt("Change owner.calculate_total", ["owner.py"])
    assert profile["source_snapshot_identity"] == receipt["source_snapshot_identity"]


def test_index_status_and_full_status_have_distinct_observation_scope(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): pass\n")
    index.sync()
    own = index.status()
    full = _views(tasks).status()
    assert own["schema"] == "hashmarks.codemap-index-status.v1"
    assert full["schema"] == "hashmarks.codemap-status.v1"
    assert own["generation"] == full["generation"] == index.publication_binding()[0]
    assert own["workspace_fingerprint"] == full["workspace_fingerprint"]
    assert "native_evidence" not in own
    assert "native_evidence" in full


def test_cross_repository_composition_rejects_a_moved_input_publication(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def calculate_total(): return 1\n")
    index.sync()
    views = _views(tasks)
    monkeypatch.setattr(
        views.changes,
        "task_impact",
        _publishing_after(views.changes.task_impact, index),
    )
    with pytest.raises(RuntimeError, match="generation changed"):
        views.cross_repository.packet("Change owner.calculate_total", ["owner.py"])


def test_economics_comparison_rejects_a_moved_current_snapshot(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def calculate_total(): return 1\n")
    index.sync()
    views = _views(tasks)
    task = "Change owner.calculate_total"
    before = views.changes.snapshot(task, ["owner.py"])
    monkeypatch.setattr(
        views.changes, "snapshot", _publishing_after(views.changes.snapshot, index)
    )
    with pytest.raises(RuntimeError, match="generation changed"):
        views.economics.receipt(task, ["owner.py"], previous_snapshot=before)


def test_full_status_rejects_same_connection_publication_during_native_observation(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): pass\n")
    index.sync()
    views = _views(tasks)
    generation = index.store.generation()
    original = views.native.status

    def publish_during_status() -> list[dict[str, object]]:
        result = original()
        _publish_generation_only(index)
        return result

    monkeypatch.setattr(views.native, "status", publish_during_status)
    with pytest.raises(RuntimeError, match="nested CodeMap publication transactions"):
        views.status()
    assert index.store.generation() == generation


def test_economics_comparison_observes_its_current_snapshot_once(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def calculate_total(): return 1\n")
    index.sync()
    views = _views(tasks)
    task = "Change owner.calculate_total"
    before = views.changes.snapshot(task, ["owner.py"])
    original = views.changes.snapshot
    calls = 0

    def counted_snapshot(
        task: str, paths: Sequence[str | Path], **bounds: int
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return original(task, paths, **bounds)

    monkeypatch.setattr(views.changes, "snapshot", counted_snapshot)
    views.economics.receipt(task, ["owner.py"], previous_snapshot=before)
    assert calls == 1


def test_profile_projection_import_needs_no_live_repository_or_task_service() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.evidence_profiles import EvidenceProfileProjection; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_changes' not in sys.modules; assert 'hashmarks.codemap.repository_tasks' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_root_is_a_composition_root_without_domain_inheritance() -> None:
    from hashmarks.codemap import CodeMap

    assert CodeMap.__bases__ == (object,)
    for name in (
        "status",
        "derived_graph",
        "repository_intelligence_query",
        "repository_intelligence_profile",
        "intelligence_economics_receipt",
        "cross_repository_evidence_packet",
    ):
        assert not hasattr(CodeMap, name)
