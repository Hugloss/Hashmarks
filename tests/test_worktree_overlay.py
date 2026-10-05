import shutil
from pathlib import Path

import pytest

from hashmarks.codemap import (
    CodeMap,
    WorktreeOverlay,
    WorktreeOverlayBaseChangedError,
)


def _repo(root: Path, value: int = 1) -> None:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(f"def target():\n    return {value}\n")
    (root / "src" / "helper.py").write_text("def helper():\n    return 2\n")
    (root / "tests" / "test_engine.py").write_text("from src.engine import target\n")


def test_overlay_indexes_only_changed_paths_and_reuses_base_artifacts(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    worktree = tmp_path / "worker-a"
    _repo(base_dir)
    shutil.copytree(base_dir, worktree)
    (worktree / "src" / "engine.py").write_text("def target():\n    return 99\n")
    with CodeMap(base_dir) as base:
        base.sync()
        with WorktreeOverlay(base, worktree, worker_id="agent-a") as overlay:
            stats = overlay.sync(["src/engine.py"])
            hits = overlay.find_task("target engine", limit=10)
            assert stats.base_generation == base.store.generation()
            assert (
                stats.base_workspace_fingerprint
                == base.store.meta("workspace_fingerprint")
            )
    assert stats.changed_paths == ("src/engine.py",)
    assert stats.as_dict()["schema"] == "hashmarks.worktree-overlay-stats.v2"
    assert stats.parsed_artifacts <= 1
    assert hits[0].path == "src/engine.py"
    assert any(hit.path == "tests/test_engine.py" for hit in hits)


def test_overlays_are_worker_isolated(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    a = tmp_path / "a"
    b = tmp_path / "b"
    _repo(base_dir)
    shutil.copytree(base_dir, a)
    shutil.copytree(base_dir, b)
    (a / "src" / "engine.py").write_text("def alpha_only():\n    return 1\n")
    (b / "src" / "engine.py").write_text("def beta_only():\n    return 1\n")
    with CodeMap(base_dir) as base:
        base.sync()
        with (
            WorktreeOverlay(base, a, worker_id="agent-a") as oa,
            WorktreeOverlay(base, b, worker_id="agent-b") as ob,
        ):
            oa.sync(["src/engine.py"])
            ob.sync(["src/engine.py"])
            a_hits = oa.find_task("alpha_only", limit=5)
            b_hits = ob.find_task("beta_only", limit=5)
            leak_a = ob.find_task("alpha_only", limit=5)
            leak_b = oa.find_task("beta_only", limit=5)
    assert a_hits[0].path == "src/engine.py"
    assert b_hits[0].path == "src/engine.py"
    assert not leak_a or leak_a[0].name != "alpha_only"
    assert not leak_b or leak_b[0].name != "beta_only"


def test_overlay_rejects_base_workspace_and_parent_escape(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as base:
        base.sync()
        try:
            WorktreeOverlay(base, tmp_path, worker_id="same")
        except ValueError:
            pass
        else:
            raise AssertionError("same workspace must be rejected")


def test_overlay_rejects_later_base_generation_until_explicit_resync(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    worktree = tmp_path / "worker-a"
    _repo(base_dir)
    shutil.copytree(base_dir, worktree)
    (worktree / "src" / "engine.py").write_text("def worker_target():\n    return 99\n")

    with CodeMap(base_dir) as base:
        base.sync()
        with WorktreeOverlay(base, worktree, worker_id="agent-a") as overlay:
            initial = overlay.sync(["src/engine.py"])

            (base_dir / "src" / "helper.py").write_text(
                "def base_two_only():\n    return 22\n"
            )
            base.sync(["src/helper.py"])

            with pytest.raises(
                WorktreeOverlayBaseChangedError,
                match="canonical base advanced after overlay sync",
            ):
                overlay.find_task("base_two_only", limit=10)

            refreshed = overlay.sync(["src/engine.py", "src/helper.py"])
            hits = overlay.find_task("helper", limit=10)

    assert refreshed.base_generation > initial.base_generation
    assert any(hit.path == "src/helper.py" for hit in hits)
    assert not any(hit.name == "base_two_only" for hit in hits)


def test_overlay_rejects_generation_only_base_advance(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    worktree = tmp_path / "worker-a"
    _repo(base_dir)
    shutil.copytree(base_dir, worktree)
    (worktree / "src" / "engine.py").write_text("def worker_target():\n    return 99\n")

    with CodeMap(base_dir) as base:
        base.sync()
        with WorktreeOverlay(base, worktree, worker_id="agent-a") as overlay:
            stats = overlay.sync(["src/engine.py"])
            fingerprint = stats.base_workspace_fingerprint

            with base.store.publication_transaction():
                base.store.bump_generation()

            assert base.store.meta("workspace_fingerprint") == fingerprint
            with pytest.raises(
                WorktreeOverlayBaseChangedError,
                match="canonical base advanced after overlay sync",
            ):
                overlay.find_task("helper", limit=10)


def test_overlay_rejects_base_generation_change_during_fused_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_dir = tmp_path / "base"
    worktree = tmp_path / "worker-a"
    _repo(base_dir)
    shutil.copytree(base_dir, worktree)
    (worktree / "src" / "engine.py").write_text("def worker_target():\n    return 99\n")

    with CodeMap(base_dir) as base:
        base.sync()
        with WorktreeOverlay(base, worktree, worker_id="agent-a") as overlay:
            overlay.sync(["src/engine.py"])
            original_find = overlay.overlay.find_task

            def advance_base_during_overlay_read(task: str, *, limit: int = 20):
                hits = original_find(task, limit=limit)
                with base.store.publication_transaction():
                    base.store.bump_generation()
                return hits

            monkeypatch.setattr(
                overlay.overlay,
                "find_task",
                advance_base_during_overlay_read,
            )

            with pytest.raises(
                RuntimeError,
                match="CodeMap generation changed before nested decision session",
            ):
                overlay.find_task("target engine", limit=10)
