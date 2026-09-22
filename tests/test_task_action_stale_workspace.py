from pathlib import Path

import pytest

from hashmarks.codemap.engine import CodeMap


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_deleted_edit_owner_cannot_remain_safe_action_without_watcher(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.task_action_map("fix calculate_total")
        assert before["edit"]["path"] == "src/foo.py"
        (tmp_path / "src/foo.py").unlink()
        after = codemap.task_action_map("fix calculate_total")
    assert after["edit"] is None
    assert after["ownership_authority"]["owner_resolved"] is False


def test_rewritten_edit_owner_cannot_reuse_stale_symbol_evidence(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        assert (
            codemap.task_action_map("fix calculate_total")["edit"]["path"]
            == "src/foo.py"
        )
        _write(tmp_path, "src/foo.py", "def unrelated(): return 2\n")
        after = codemap.task_action_map("fix calculate_total")
    assert after["edit"] is None
    assert after["ownership_authority"]["owner_resolved"] is False


def test_cold_map_rejects_module_only_owner_when_imported_symbol_is_gone(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/foo.py", "def unrelated(): return 2\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("fix calculate_total")
    assert action["edit"] is None
    assert action["ownership_authority"]["owner_resolved"] is False


def test_changed_projected_owner_reconciles_before_cached_authority_is_reused(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.task_action_map("fix calculate_total")
        _write(
            tmp_path,
            "src/foo.py",
            "def calculate_total(): return 1\n# harmless change\n",
        )
        after = codemap.task_action_map("fix calculate_total")
    assert before["edit"]["path"] == "src/foo.py"
    assert after["edit"]["path"] == "src/foo.py"
    authority = after["ownership_authority"]
    assert authority["schema"] == "hashmarks.ownership-authority.v1"
    assert authority["status"] == "resolved"
    assert authority["owner_resolved"] is True
    assert authority["resolved_owner"] == "src/foo.py"
    assert authority["candidate_owner"] == "src/foo.py"
    assert authority["reason"] == "unique-owner-established"
    assert authority["authority"] == "repository-ownership-only"
    assert authority["consumer_action"] == "external"
    assert authority["proof_complete"] is True
    assert authority["authority_proof_identity"].startswith("sha256:")


def test_unsignaled_owner_rename_converges_to_cold_truth(tmp_path: Path) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        assert (
            codemap.task_action_map("fix calculate_total")["edit"]["path"]
            == "src/foo.py"
        )
        (tmp_path / "src/foo.py").rename(tmp_path / "src/bar.py")
        _write(
            tmp_path,
            "tests/test_foo.py",
            "from src.bar import calculate_total\ndef test_total(): assert calculate_total()==1\n",
        )
        live = codemap.task_action_map("fix calculate_total")
    assert live["edit"]["path"] == "src/bar.py"


@pytest.mark.parametrize(
    ("before_path", "after_path"),
    (("src/foo.py", "src/foo/__init__.py"), ("src/foo/__init__.py", "src/foo.py")),
)
def test_unsignaled_module_package_transition_converges(
    tmp_path: Path, before_path: str, after_path: str
) -> None:
    _write(tmp_path, before_path, "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        assert (
            codemap.task_action_map("fix calculate_total")["edit"]["path"]
            == before_path
        )
        (tmp_path / before_path).unlink()
        parent = (tmp_path / before_path).parent
        if parent != tmp_path / "src" and parent.exists():
            parent.rmdir()
        _write(tmp_path, after_path, "def calculate_total(): return 1\n")
        live = codemap.task_action_map("fix calculate_total")
    assert live["edit"]["path"] == after_path


def test_unsignaled_aba_owner_restoration_reconciles_from_recent_authority(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        assert (
            codemap.task_action_map("fix calculate_total")["edit"]["path"]
            == "src/foo.py"
        )
        _write(tmp_path, "src/foo.py", "def unrelated(): return 2\n")
        assert codemap.task_action_map("fix calculate_total")["edit"] is None
        _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
        restored = codemap.task_action_map("fix calculate_total")
    assert restored["edit"]["path"] == "src/foo.py"


def test_unsignaled_rename_reconciliation_retires_obsolete_history(
    tmp_path: Path, monkeypatch
) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        assert (
            codemap.task_action_map("fix calculate_total")["edit"]["path"]
            == "src/foo.py"
        )
        original_sync = codemap.sync
        sync_calls: list[tuple[str, ...]] = []

        def counted_sync(paths=None):
            sync_calls.append(tuple(paths or ()))
            return original_sync(paths)

        monkeypatch.setattr(codemap, "sync", counted_sync)
        (tmp_path / "src/foo.py").rename(tmp_path / "src/bar.py")
        _write(
            tmp_path,
            "tests/test_foo.py",
            "from src.bar import calculate_total\ndef test_total(): assert calculate_total()==1\n",
        )
        assert (
            codemap.task_action_map("fix calculate_total")["edit"]["path"]
            == "src/bar.py"
        )
        for _ in range(3):
            assert (
                codemap.task_action_map("fix calculate_total")["edit"]["path"]
                == "src/bar.py"
            )

    assert sync_calls == [()]


def test_unsignaled_rename_converges_after_task_cache_pressure(tmp_path: Path) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        assert (
            codemap.task_action_map("fix calculate_total")["edit"]["path"]
            == "src/foo.py"
        )
        for index in range(270):
            codemap.task_action_map(f"noise_{index}_target")
        assert ("fix calculate_total", 20) not in codemap._task_recent_authority_paths
        (tmp_path / "src/foo.py").rename(tmp_path / "src/bar.py")
        _write(
            tmp_path,
            "tests/test_foo.py",
            "from src.bar import calculate_total\ndef test_total(): assert calculate_total()==1\n",
        )
        live = codemap.task_action_map("fix calculate_total")

    with CodeMap(tmp_path) as cold:
        cold.sync()
        expected = cold.task_action_map("fix calculate_total")

    assert live["edit"]["path"] == "src/bar.py"
    assert live["edit"]["path"] == expected["edit"]["path"]
    assert live["ownership_authority"] == expected["ownership_authority"]


def test_unsignaled_delete_recreate_recovers_first_task_decision_after_disappearance(
    tmp_path: Path,
) -> None:
    """A stale persisted owner becomes a bounded resurrection tombstone before retirement."""
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    original = (tmp_path / "src/foo.py").read_bytes()
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        # No warm task-action history exists before the unsignaled deletion.
        (tmp_path / "src/foo.py").unlink()
        assert codemap.task_action_map("fix calculate_total")["edit"] is None
        (tmp_path / "src/foo.py").write_bytes(original)
        restored = codemap.task_action_map("fix calculate_total")

    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".cold-state",
        artifact_db=tmp_path / "cold-artifacts.sqlite3",
    ) as cold:
        cold.sync()
        expected = cold.task_action_map("fix calculate_total")

    assert restored["edit"]["path"] == expected["edit"]["path"] == "src/foo.py"
    assert restored["ownership_authority"] == expected["ownership_authority"]


def test_unsignaled_file_symlink_file_transition_recovers_without_following_symlink(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    source = tmp_path / "src/foo.py"
    original = source.read_bytes()
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("def calculate_total(): return 999\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        source.unlink()
        try:
            source.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
        during = codemap.task_action_map("fix calculate_total")
        assert during["edit"] is None
        assert codemap.store.file_row("src/foo.py") is None

        source.unlink()
        source.write_bytes(original)
        restored = codemap.task_action_map("fix calculate_total")

    assert restored["edit"]["path"] == "src/foo.py"
    assert restored["ownership_authority"]["owner_resolved"] is True


def test_missing_resurrection_tombstone_does_not_poll_repository_and_recovers_path_scoped(
    tmp_path: Path, monkeypatch
) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    source = tmp_path / "src/foo.py"
    original = source.read_bytes()
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original_sync = codemap.sync
        sync_calls: list[tuple[str, ...]] = []

        def counted_sync(paths=None):
            sync_calls.append(tuple(paths or ()))
            return original_sync(paths)

        monkeypatch.setattr(codemap, "sync", counted_sync)
        source.unlink()
        assert codemap.task_action_map("fix calculate_total")["edit"] is None
        for _ in range(3):
            assert codemap.task_action_map("fix calculate_total")["edit"] is None
        source.write_bytes(original)
        assert (
            codemap.task_action_map("fix calculate_total")["edit"]["path"]
            == "src/foo.py"
        )

    assert sync_calls == [(), ("src/foo.py",)]


def test_delete_recreate_resurrection_survives_recent_authority_cache_pressure(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/foo.py", "def calculate_total(): return 1\n")
    _write(
        tmp_path,
        "tests/test_foo.py",
        "from src.foo import calculate_total\ndef test_total(): assert calculate_total()==1\n",
    )
    source = tmp_path / "src/foo.py"
    original = source.read_bytes()
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        for index in range(256):
            codemap.task_action_map(f"noise_{index}_target")
        source.unlink()
        assert codemap.task_action_map("fix calculate_total")["edit"] is None
        assert ("fix calculate_total", 20) in codemap._task_recent_authority_paths
        source.write_bytes(original)
        restored = codemap.task_action_map("fix calculate_total")

    assert restored["edit"]["path"] == "src/foo.py"
