from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.client import RepositoryObservation
from hashmarks.codemap import CodeMap
from hashmarks.observation import ObservationState


def _write_repo(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "src" / "auth.py").write_text(
        "from src.users import User\n\nclass AuthService:\n    pass\n",
        encoding="utf-8",
    )
    (root / "src" / "users.py").write_text(
        "class User:\n    pass\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_auth.py").write_text(
        "from src.auth import AuthService\n\ndef test_login():\n    assert AuthService\n",
        encoding="utf-8",
    )


def test_codemap_sync_does_not_claim_daemon_generation_if_generation_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_repo(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        generations = iter((10, 11))

        def sample() -> RepositoryObservation:
            return RepositoryObservation(
                state=ObservationState.CLEAN,
                generation=next(generations),
                dirty_paths=(),
                paths_complete=True,
                dirty_path_count=0,
            )

        monkeypatch.setattr(codemap, "_daemon_observation", sample)
        result = codemap.sync()
        assert result.identity_generation is None
        assert any("generation changed" in warning for warning in result.warnings)
        assert codemap.store.meta("identity_generation") == ""


def test_codemap_never_follows_source_symlinks_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-secret.py"
    outside.write_text(
        "def outside_secret():\n    return 'DO_NOT_LEAK'\n",
        encoding="utf-8",
    )
    link = tmp_path / "leak.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        result = codemap.sync()
        assert result.discovered == 0
        assert codemap.store.file_row("leak.py") is None
        assert not codemap.find("outside_secret")


def test_incremental_file_to_symlink_removes_old_codemap_row(tmp_path: Path) -> None:
    target = tmp_path / "real.py"
    target.write_text("def original():\n    return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert codemap.store.file_row("real.py") is not None
        outside = tmp_path.parent / f"{tmp_path.name}-replacement.py"
        outside.write_text("def outside():\n    return 2\n", encoding="utf-8")
        target.unlink()
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
        result = codemap.sync(["real.py"])
        assert result.removed == 1
        assert codemap.store.file_row("real.py") is None


def test_custom_state_dir_inside_workspace_is_never_indexed(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    custom = tmp_path / "control-state"
    custom.mkdir()
    (custom / "should_not_exist.py").write_text(
        "def hidden_control():\n    pass\n",
        encoding="utf-8",
    )
    with CodeMap(
        tmp_path,
        state_dir=custom,
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        result = codemap.sync()
        assert result.discovered == 3
        assert codemap.store.file_row("control-state/should_not_exist.py") is None


def test_index_denial_policy_purges_previous_shared_artifact(tmp_path: Path) -> None:
    source = tmp_path / "private.py"
    source.write_text("def previously_allowed():\n    return 1\n", encoding="utf-8")
    artifact_db = tmp_path / "shared.sqlite3"
    with CodeMap(tmp_path, artifact_db=artifact_db) as codemap:
        codemap.sync()
        row = codemap.store.file_row("private.py")
        assert row is not None
        key = str(row["artifact_key"])
        assert codemap.artifacts.get(key) is not None

    (tmp_path / ".hashmarks-context.toml").write_text(
        "[[rule]]\npattern='private.py'\nindex=false\nvisibility='deny'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=artifact_db) as codemap:
        codemap.sync()
        assert codemap.store.file_row("private.py") is None
        assert codemap.artifacts.get(key) is None


def test_interrupted_sync_leaves_durable_incomplete_generation_and_decision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text(
        "def run(value):\n    return value + 1\n",
        encoding="utf-8",
    )
    artifact_db = tmp_path / "artifacts.sqlite3"
    with CodeMap(tmp_path, artifact_db=artifact_db) as codemap:

        def explode(*args, **kwargs):
            raise RuntimeError("synthetic interruption")

        monkeypatch.setattr(codemap, "_parse_or_reuse", explode)
        with pytest.raises(RuntimeError, match="synthetic interruption"):
            codemap.sync()
        assert codemap.status()["build"]["state"] == "BUILDING"
    with CodeMap(tmp_path, artifact_db=artifact_db) as reopened:
        status = reopened.status()
        packet = reopened.task_decision_packet("Fix run behavior")
    assert status["build"]["complete"] is False
    assert packet["identity"]["codemap_complete"] is False
    assert packet["identity"]["stale"] is True
    assert packet["discrimination"]["needed"] is True
    assert packet["discrimination"]["reason"] == "codemap-generation-incomplete"
    assert packet["context_budget"]["safe"] is False
