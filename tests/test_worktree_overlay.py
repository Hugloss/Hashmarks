import shutil
from pathlib import Path

from hashmarks.codemap import CodeMap, WorktreeOverlay


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
    assert stats.changed_paths == ("src/engine.py",)
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
