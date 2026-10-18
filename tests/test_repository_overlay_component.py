"""An overlay borrows explicit base capabilities, never a base construction root."""

import shutil
from collections.abc import Iterable
from pathlib import Path

import pytest
from test_repository_index_component import index as index
from test_repository_search_component import _search

from hashmarks.codemap.decision_session import DecisionScope
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.model import SearchHit, SyncResult
from hashmarks.codemap.worktree_overlay import (
    WorktreeOverlay,
    WorktreeOverlayBaseChangedError,
)


def test_overlay_works_with_an_independently_constructed_base_index_and_search(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def calculate_total(): return 1\n")
    index.sync()
    search = _search(index)
    worktree = index.workspace.parent / "worktree"
    shutil.copytree(index.workspace, worktree)
    (worktree / "owner.py").write_text("def calculate_total(): return 2\n")
    with WorktreeOverlay(
        index,
        search,
        search.reads,
        worktree,
        worker_id="independent",
        artifact_db=index.artifact_db_path,
    ) as overlay:
        stats = overlay.sync(["owner.py"])
        hits = overlay.find_task("calculate_total")
        assert hits[0].path == "owner.py"
        assert (
            stats.base_generation,
            stats.base_workspace_fingerprint,
        ) == index.publication_binding()
        assert not hasattr(overlay, "base")


def test_overlay_rejects_an_unrelated_base_read_scope(index: RepositoryIndex) -> None:
    search = _search(index)
    other = DecisionScope(index)
    with pytest.raises(ValueError, match="share one repository authority"):
        WorktreeOverlay(
            index, search, other, index.workspace.parent / "worktree", worker_id="mixed"
        )


def test_overlay_rejects_fingerprint_drift_during_sync_without_adopting_stats(
    index: RepositoryIndex,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): pass\n")
    index.sync()
    search = _search(index)
    worktree = index.workspace.parent / "worktree"
    shutil.copytree(index.workspace, worktree)
    with WorktreeOverlay(
        index, search, search.reads, worktree, worker_id="sync-drift"
    ) as overlay:
        original = overlay.overlay.index.sync

        def publish_during_sync(
            paths: Iterable[str | Path] | None = None,
        ) -> SyncResult:
            result = original(paths)
            with index.store.publication_transaction():
                index.store.set_meta("workspace_fingerprint", "changed-during-sync")
            return result

        monkeypatch.setattr(overlay.overlay.index, "sync", publish_during_sync)
        with pytest.raises(
            WorktreeOverlayBaseChangedError, match="advanced during overlay sync"
        ):
            overlay.sync(["owner.py"])
        with pytest.raises(RuntimeError, match="overlay has not been synced"):
            overlay.stats()


def test_overlay_rejects_fingerprint_only_drift_during_a_fused_read(
    index: RepositoryIndex,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): pass\n")
    index.sync()
    search = _search(index)
    worktree = index.workspace.parent / "worktree"
    shutil.copytree(index.workspace, worktree)
    with WorktreeOverlay(
        index, search, search.reads, worktree, worker_id="read-drift"
    ) as overlay:
        overlay.sync(["owner.py"])
        original = overlay.overlay.search.find_task

        def publish_during_read(task: str, *, limit: int = 20) -> tuple[SearchHit, ...]:
            hits = original(task, limit=limit)
            with index.store.publication_transaction():
                index.store.set_meta("workspace_fingerprint", "changed-during-read")
            return hits

        monkeypatch.setattr(overlay.overlay.search, "find_task", publish_during_read)
        with pytest.raises(
            WorktreeOverlayBaseChangedError,
            match="canonical base advanced after overlay sync",
        ):
            overlay.find_task("owner")
