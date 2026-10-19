"""CLI projection preserves the Identity observation, including an empty scope."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashmarks.cli import main
from hashmarks.client import DaemonProtocolError, IdentityClient
from hashmarks.identity import RepositoryIdentity


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "repository"
    (workspace / "src/generated").mkdir(parents=True)
    (workspace / "src/entry").write_bytes(b"entry")
    (workspace / "src/generated/omit").write_bytes(b"omit")
    return workspace


@pytest.mark.parametrize("mode", ["local", "auto"])
def test_cli_projects_complete_identity_and_excluded_inventory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    workspace = _workspace(tmp_path)
    assert (
        main(
            [
                "observe-inputs",
                "--workspace",
                str(workspace),
                "--state-dir",
                str(tmp_path / "state"),
                "--mode",
                mode,
                "--input",
                "src",
                "--exclude",
                "src/generated",
                "--verify",
                "--max-members",
                "2",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["schema"] == "hashmarks.input-observation.v1"
    assert output["snapshot"]["mode"] == "local"
    assert output["scope"]["roots"] == ["src"]
    assert output["scope"]["excluded_paths"] == ["src/generated"]
    assert [member["path"] for member in output["members"]] == ["src", "src/entry"]
    assert output["counts"]["regular_file_bytes"] == 5
    assert output["completeness"] == "complete"
    assert output["authority"] == "repository-evidence-only"
    assert output["execution_effect"] == "none"


@pytest.mark.parametrize(
    "selection",
    [
        [],
        ["--input", "missing*", "--allow-unmatched"],
        ["--input", "src", "--exclude", "src"],
    ],
)
def test_cli_preserves_explicit_empty_selection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], selection: list[str]
) -> None:
    workspace = _workspace(tmp_path)
    assert (
        main(
            [
                "--workspace",
                str(workspace),
                "--state-dir",
                str(tmp_path / "state"),
                "observe-inputs",
                "--mode",
                "local",
                *selection,
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["members"] == output["scope"]["roots"] == []
    assert output["counts"]["entry_count"] == 0
    assert output["completeness"] == "complete"
    assert (workspace / "src/entry").is_file()


@pytest.mark.parametrize(
    ("selection", "message", "error_type"),
    [
        (["--input", "missing"], "matched nothing", FileNotFoundError),
        (["--input", "src", "--max-members", "1"], "member limit exceeded", ValueError),
        (["--max-members", "0"], "positive integer", ValueError),
        (["--input", "../escape"], "must not contain", ValueError),
    ],
)
def test_cli_errors_publish_no_complete_observation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    selection: list[str],
    message: str,
    error_type: type[Exception],
) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(SystemExit, match=message) as raised:
        main(
            [
                "observe-inputs",
                "--workspace",
                str(workspace),
                "--state-dir",
                str(tmp_path / "state"),
                "--mode",
                "local",
                *selection,
            ]
        )
    assert isinstance(raised.value.__cause__, error_type)
    assert capsys.readouterr().out == ""


def test_cli_keeps_unexpected_observation_faults_visible(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_self: RepositoryIdentity, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("implementation fault")

    monkeypatch.setattr(RepositoryIdentity, "observe_inputs", broken)
    with pytest.raises(RuntimeError, match="implementation fault"):
        main(["observe-inputs", "--workspace", str(tmp_path), "--mode", "local"])
    assert capsys.readouterr().out == ""


def test_cli_required_daemon_budget_failure_is_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(IdentityClient, "status", lambda _self: {})

    def oversized(_self: IdentityClient, *_args: object, **_kwargs: object) -> object:
        raise DaemonProtocolError("daemon response exceeded size limit")

    monkeypatch.setattr(IdentityClient, "observe_inputs", oversized)
    with pytest.raises(SystemExit, match="daemon response exceeded size limit"):
        main(["observe-inputs", "--workspace", str(tmp_path), "--mode", "daemon"])
    assert capsys.readouterr().out == ""


def test_cli_daemon_uses_complete_socket_observation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_developer_api import _start_daemon

    workspace = _workspace(tmp_path)
    _server, watcher, socket_path, thread = _start_daemon(workspace, tmp_path)
    monkeypatch.setattr(
        "hashmarks.client.default_socket_path", lambda _workspace: socket_path
    )
    peer = IdentityClient(workspace, socket_path=socket_path)
    try:
        assert (
            main(
                [
                    "observe-inputs",
                    "--workspace",
                    str(workspace),
                    "--mode",
                    "daemon",
                    "--input",
                    "src",
                    "--exclude",
                    "src/generated",
                ]
            )
            == 0
        )
        output = json.loads(capsys.readouterr().out)
        assert output["snapshot"]["mode"] == "daemon"
        assert output["scope"]["excluded_paths"] == ["src/generated"]
        assert output["counts"]["entry_count"] == 2
        assert output["completeness"] == "complete"
    finally:
        peer.stop()
        thread.join(timeout=2)
        assert watcher.stopped
