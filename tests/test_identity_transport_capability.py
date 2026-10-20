from __future__ import annotations

import errno
import socket
from pathlib import Path

import pytest
from contract_assertions import assert_object

from hashmarks import File, RepositoryIdentity
from hashmarks.cli import main
from hashmarks.client import DaemonUnavailableError, IdentityClient
from hashmarks.codemap import CodeMap


@pytest.fixture(params=["missing-family", "unsupported-family"])
def unavailable_unix_socket(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    if request.param == "missing-family":
        monkeypatch.delattr(socket, "AF_UNIX", raising=False)
    else:
        monkeypatch.setattr(
            socket, "AF_UNIX", getattr(socket, "AF_UNIX", 1), raising=False
        )

        def unsupported(*_args: object, **_kwargs: object) -> socket.socket:
            raise OSError(errno.EAFNOSUPPORT, "Unix-domain sockets are unavailable")

        monkeypatch.setattr(socket, "socket", unsupported)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "example.py").write_text("def handler():\n    return 1\n")
    return root


@pytest.mark.usefixtures("unavailable_unix_socket")
def test_client_reports_unavailable_native_transport(repository: Path) -> None:
    with pytest.raises(DaemonUnavailableError):
        IdentityClient(repository).status()


@pytest.mark.usefixtures("unavailable_unix_socket")
def test_auto_identity_preserves_local_identity_and_reconciles_edits(
    repository: Path, tmp_path: Path
) -> None:
    with (
        RepositoryIdentity(
            repository, mode="auto", state_dir=tmp_path / "auto-state"
        ) as automatic,
        RepositoryIdentity(
            repository, mode="local", state_dir=tmp_path / "local-state"
        ) as local,
    ):
        before = automatic.snapshot(File("example.py"))
        assert automatic.active_mode == before.mode == "local"
        assert before.hash == local.snapshot(File("example.py")).hash
        (repository / "example.py").write_text("def handler():\n    return 2\n")
        after = automatic.snapshot(File("example.py"))
        assert after.mode == "local"
        assert after.hash != before.hash
        assert after.hash == local.snapshot(File("example.py")).hash


@pytest.mark.usefixtures("unavailable_unix_socket")
def test_required_daemon_rejects_before_local_state_materialization(
    repository: Path, tmp_path: Path
) -> None:
    state = tmp_path / "required-state"
    with pytest.raises(DaemonUnavailableError):
        RepositoryIdentity(repository, mode="daemon", state_dir=state)
    assert not state.exists()


@pytest.mark.usefixtures("unavailable_unix_socket")
def test_codemap_sync_and_source_reads_do_not_invent_daemon_evidence(
    repository: Path, tmp_path: Path
) -> None:
    with CodeMap(repository, state_dir=tmp_path / "map-state") as codemap:
        synced = codemap.index.sync()
        assert synced.indexed == 1
        assert synced.identity_generation is None
        with codemap.reads.session():
            assert codemap.reads.observation is None
            observation = codemap.source.observe("example.py", lines=[1])
            assert assert_object(observation["member"])["path"] == "example.py"


@pytest.mark.usefixtures("unavailable_unix_socket")
def test_default_map_cli_succeeds_with_unavailable_optional_daemon(
    repository: Path, tmp_path: Path
) -> None:
    common = [
        "--workspace",
        str(repository),
        "--state-dir",
        str(tmp_path / "cli-state"),
        "map",
    ]
    assert main([*common, "sync"]) == 0
    assert main([*common, "status"]) == 0


def test_unexpected_socket_failure_is_not_reclassified(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*_args: object, **_kwargs: object) -> socket.socket:
        raise AttributeError("unexpected native socket bug")

    monkeypatch.setattr(socket, "AF_UNIX", getattr(socket, "AF_UNIX", 1), raising=False)
    monkeypatch.setattr(socket, "socket", unexpected)
    with pytest.raises(AttributeError, match="unexpected native socket bug"):
        IdentityClient(repository).status()
