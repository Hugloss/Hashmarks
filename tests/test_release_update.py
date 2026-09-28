from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request

import pytest

import hashmarks.cli as cli
import hashmarks.release_update as release_update
from hashmarks.release_update import ReleaseInfo


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self._payload
        return self._payload[:size]


def _latest(version: str) -> bytes:
    return json.dumps(
        {
            "tag_name": f"v{version}",
            "draft": False,
            "prerelease": False,
        }
    ).encode()


def test_latest_release_request_is_public_and_repository_neutral(monkeypatch) -> None:
    seen: list[Request] = []

    def urlopen(request: Request, *, timeout: float):
        assert timeout == 1.0
        seen.append(request)
        return _Response(_latest("0.25.0"))

    monkeypatch.setattr(release_update, "urlopen", urlopen)

    release = release_update.fetch_latest_release("0.24.0")

    assert release == ReleaseInfo(current_version="0.24.0", latest_version="0.25.0")
    assert release.update_available is True
    assert len(seen) == 1
    request = seen[0]
    assert request.full_url == release_update._RELEASE_API
    headers = {key.lower(): value for key, value in request.header_items()}
    assert "authorization" not in headers
    assert headers["user-agent"] == "hashmarks-update-check"
    assert "workspace" not in request.full_url


@pytest.mark.parametrize(
    ("command", "interactive", "environ"),
    [
        ("mcp", True, {}),
        ("daemon", True, {}),
        ("find", False, {}),
        ("find", True, {"CI": "1"}),
        ("find", True, {"GITHUB_ACTIONS": "true"}),
        ("find", True, {"HASHMARKS_NO_UPDATE_CHECK": "1"}),
    ],
)
def test_automatic_update_check_respects_hard_skip_boundaries(
    command: str,
    interactive: bool,
    environ: dict[str, str],
) -> None:
    assert (
        release_update.automatic_check_allowed(
            command=command,
            interactive=interactive,
            environ=environ,
        )
        is False
    )


def test_periodic_check_is_cached_outside_repository_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def fetch(current_version: str, *, timeout: float) -> ReleaseInfo:
        calls.append(f"{current_version}:{timeout}")
        return ReleaseInfo(current_version=current_version, latest_version="0.25.0")

    monkeypatch.setattr(release_update, "fetch_latest_release", fetch)
    environ = {"XDG_CACHE_HOME": str(tmp_path / "cache")}

    first = release_update.periodic_release_check(
        "0.24.0",
        command="find",
        interactive=True,
        environ=environ,
        now=1000.0,
    )
    second = release_update.periodic_release_check(
        "0.24.0",
        command="find",
        interactive=True,
        environ=environ,
        now=1001.0,
    )

    assert first == ReleaseInfo(current_version="0.24.0", latest_version="0.25.0")
    assert second is None
    assert calls == ["0.24.0:1.0"]
    cache = tmp_path / "cache" / "hashmarks" / "update-check.json"
    assert json.loads(cache.read_text(encoding="utf-8")) == {
        "checked_at": 1000.0,
    }
    assert not (tmp_path / ".hashmarks").exists()


def test_corrupt_periodic_cache_is_disposable(monkeypatch, tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "hashmarks" / "update-check.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(
        release_update,
        "fetch_latest_release",
        lambda current_version, *, timeout: ReleaseInfo(
            current_version=current_version,
            latest_version="0.25.0",
        ),
    )

    result = release_update.periodic_release_check(
        "0.24.0",
        command="find",
        interactive=True,
        environ={"XDG_CACHE_HOME": str(tmp_path / "cache")},
        now=2000.0,
    )

    assert result is not None
    assert json.loads(cache.read_text(encoding="utf-8"))["checked_at"] == 2000.0


def test_network_failure_is_non_fatal_and_throttled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def fail(current_version: str, *, timeout: float) -> ReleaseInfo:
        nonlocal calls
        del current_version, timeout
        calls += 1
        raise release_update.ReleaseCheckError("offline")

    monkeypatch.setattr(release_update, "fetch_latest_release", fail)
    environ = {"XDG_CACHE_HOME": str(tmp_path / "cache")}

    assert (
        release_update.periodic_release_check(
            "0.24.0",
            command="find",
            interactive=True,
            environ=environ,
            now=3000.0,
        )
        is None
    )
    assert (
        release_update.periodic_release_check(
            "0.24.0",
            command="find",
            interactive=True,
            environ=environ,
            now=3001.0,
        )
        is None
    )
    assert calls == 1


def test_package_manager_environment_configuration_does_not_create_authority(
    monkeypatch,
) -> None:
    monkeypatch.delattr(release_update.sys, "frozen", raising=False)
    monkeypatch.setenv("UV_TOOL_DIR", "/arbitrary/uv-tools")
    monkeypatch.setenv("PIPX_HOME", "/arbitrary/pipx")
    monkeypatch.setenv("PIPX_GLOBAL_HOME", "/arbitrary/pipx-global")

    assert release_update.is_standalone_installation() is False
    assert release_update.standalone_upgrade_command("0.25.0") is None


def test_external_python_upgrade_reports_native_tool_handoff_without_mutation(
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "fetch_latest_release",
        lambda current_version, *, timeout: ReleaseInfo(
            current_version=current_version,
            latest_version="0.25.0",
        ),
    )
    monkeypatch.setattr(cli, "is_standalone_installation", lambda: False)
    monkeypatch.setattr(
        cli,
        "_prompt_upgrade",
        lambda: pytest.fail(
            "external package-manager installs must not prompt mutation"
        ),
    )
    monkeypatch.setattr(
        cli,
        "delegate_standalone_upgrade",
        lambda *args, **kwargs: pytest.fail(
            "external package-manager installs must not delegate standalone mutation"
        ),
    )

    assert cli.main(["upgrade"]) == 0

    output = capsys.readouterr().out
    assert "Hashmarks 0.24.0" in output
    assert "Latest: 0.25.0" in output
    assert "managed outside Hashmarks" in output
    assert "Use the native mechanism that installed or owns" in output
    assert "does not detect, validate, or certify that package-manager state" in output
    assert "uv tool upgrade hashmarks" in output
    assert "pipx upgrade hashmarks" in output
    assert "pip install --upgrade hashmarks" in output
    assert "No changes were made." in output


def test_periodic_external_installation_reports_update_without_manager_selection(
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(
        cli,
        "automatic_check_allowed",
        lambda *, command, interactive: command == "find" and interactive,
    )
    monkeypatch.setattr(
        cli,
        "periodic_release_check",
        lambda current_version, *, command, interactive: ReleaseInfo(
            current_version=current_version,
            latest_version="0.25.0",
        ),
    )
    monkeypatch.setattr(cli, "is_standalone_installation", lambda: False)
    monkeypatch.setattr(
        cli,
        "_prompt_upgrade",
        lambda: pytest.fail("external installs must not prompt mutation"),
    )

    cli._maybe_offer_periodic_upgrade("find")

    output = capsys.readouterr().out
    assert "A newer Hashmarks version is available." in output
    assert "managed outside Hashmarks" in output
    assert "[1] Upgrade now" not in output


def test_cli_upgrade_reports_up_to_date_without_installation_detection(
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "fetch_latest_release",
        lambda current_version, *, timeout: ReleaseInfo(
            current_version=current_version,
            latest_version=current_version,
        ),
    )
    monkeypatch.setattr(
        cli,
        "is_standalone_installation",
        lambda: pytest.fail("installation mode is irrelevant when already current"),
    )

    assert cli.main(["upgrade"]) == 0

    assert "Hashmarks 0.24.0 is up to date." in capsys.readouterr().out


def test_managed_standalone_requires_canonical_installed_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    installed_name = "hashmarks.exe" if release_update.os.name == "nt" else "hashmarks"
    executable = tmp_path / installed_name
    monkeypatch.setattr(release_update.sys, "frozen", True, raising=False)
    monkeypatch.setattr(release_update.sys, "executable", str(executable))

    assert release_update.is_standalone_installation() is True

    command = release_update.standalone_upgrade_command("0.25.0")
    assert command is not None
    assert "HASHMARKS_VERSION" in command
    assert "0.25.0" in command
    assert "HASHMARKS_INSTALL_DIR" in command
    assert str(tmp_path.resolve()) in command


def test_raw_frozen_release_asset_is_not_treated_as_installed_standalone(
    monkeypatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "hashmarks-linux-x86_64"
    monkeypatch.setattr(release_update.sys, "frozen", True, raising=False)
    monkeypatch.setattr(release_update.sys, "executable", str(executable))

    assert release_update.is_standalone_installation() is False
    assert release_update.standalone_upgrade_command("0.25.0") is None


def test_standalone_upgrade_offers_two_explicit_choices_and_skip_does_not_mutate(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installed_name = "hashmarks.exe" if release_update.os.name == "nt" else "hashmarks"
    monkeypatch.setattr(release_update.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        release_update.sys, "executable", str(tmp_path / installed_name)
    )
    monkeypatch.setattr(
        cli,
        "fetch_latest_release",
        lambda current_version, *, timeout: ReleaseInfo(
            current_version=current_version,
            latest_version="0.25.0",
        ),
    )
    monkeypatch.setattr(cli, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(
        release_update.shutil,
        "which",
        lambda name: pytest.fail(
            f"skip must not preflight installer prerequisite {name}"
        ),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    monkeypatch.setattr(
        cli,
        "delegate_standalone_upgrade",
        lambda *args, **kwargs: pytest.fail("skip must not mutate"),
    )

    assert cli.main(["upgrade"]) == 0

    output = capsys.readouterr().out
    assert "This installation uses the Hashmarks standalone installer." in output
    assert "Native upgrade command:" in output
    assert "[1] Upgrade now" in output
    assert "[2] Skip for now" in output
    assert "Upgrade skipped." in output


def test_standalone_prerequisites_are_resolved_only_after_upgrade_consent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    installed_name = "hashmarks.exe" if release_update.os.name == "nt" else "hashmarks"
    monkeypatch.setattr(release_update.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        release_update.sys,
        "executable",
        str(tmp_path / installed_name),
    )
    monkeypatch.setattr(
        cli,
        "fetch_latest_release",
        lambda current_version, *, timeout: ReleaseInfo(
            current_version=current_version,
            latest_version="0.25.0",
        ),
    )
    monkeypatch.setattr(cli, "_interactive_terminal", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "1")
    monkeypatch.setattr(release_update.shutil, "which", lambda name: None)

    expected = (
        "PowerShell is required for the installer"
        if release_update.os.name == "nt"
        else "sh is required for the installer"
    )
    with pytest.raises(SystemExit, match=expected):
        cli.main(["upgrade"])


def test_standalone_upgrade_noninteractive_prints_command_without_mutation(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installed_name = "hashmarks.exe" if release_update.os.name == "nt" else "hashmarks"
    monkeypatch.setattr(release_update.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        release_update.sys, "executable", str(tmp_path / installed_name)
    )
    monkeypatch.setattr(
        cli,
        "fetch_latest_release",
        lambda current_version, *, timeout: ReleaseInfo(
            current_version=current_version,
            latest_version="0.25.0",
        ),
    )
    monkeypatch.setattr(cli, "_interactive_terminal", lambda: False)
    monkeypatch.setattr(
        cli,
        "delegate_standalone_upgrade",
        lambda *args, **kwargs: pytest.fail("noninteractive use must not mutate"),
    )

    assert cli.main(["upgrade"]) == 0

    output = capsys.readouterr().out
    assert "Native upgrade command:" in output
    assert "No changes were made." in output


def test_standalone_delegation_executes_the_displayed_native_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    installed_name = "hashmarks.exe" if release_update.os.name == "nt" else "hashmarks"
    executable = tmp_path / installed_name
    monkeypatch.setattr(release_update.sys, "frozen", True, raising=False)
    monkeypatch.setattr(release_update.sys, "executable", str(executable))
    displayed = release_update.standalone_upgrade_command("0.25.0")
    assert displayed is not None

    def which(name: str) -> str | None:
        if release_update.os.name == "nt":
            return "C:\\Tools\\pwsh.exe" if name == "pwsh" else None
        return f"/tools/{name}" if name in {"sh", "curl"} else None

    monkeypatch.setattr(release_update.shutil, "which", which)
    seen: dict[str, object] = {}

    def exec_installer(
        native_executable: str,
        argv: tuple[str, ...],
        environment: dict[str, str],
    ) -> None:
        seen["executable"] = native_executable
        seen["argv"] = argv
        seen["version"] = environment["HASHMARKS_VERSION"]

    monkeypatch.setattr(
        release_update,
        "_exec_standalone_installer",
        exec_installer,
    )

    release_update.delegate_standalone_upgrade("0.25.0")

    argv = seen["argv"]
    assert isinstance(argv, tuple)
    if release_update.os.name == "nt":
        assert argv[-1] == displayed
    else:
        assert argv == ("/tools/sh", "-c", displayed)
    assert seen["version"] == "0.25.0"
