from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request

import pytest

import hashmarks.cli as cli
import hashmarks.release_update as release_update
from hashmarks.release_update import InstallationOwner, ReleaseInfo


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
        "latest_version": "0.25.0",
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


def test_network_failure_is_non_fatal_and_throttled(monkeypatch, tmp_path: Path) -> None:
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


def test_uv_tool_environment_maps_to_native_uv_upgrade(monkeypatch) -> None:
    monkeypatch.setattr(
        release_update.sys,
        "prefix",
        "/home/user/.local/share/uv/tools/hashmarks",
    )
    monkeypatch.setattr(release_update.sys, "base_prefix", "/usr")

    owner = release_update.detect_installation_owner()

    assert owner == InstallationOwner(
        kind="uv",
        label="uv",
        command=("uv", "tool", "upgrade", "hashmarks"),
    )
    assert release_update.manual_upgrade_command(owner, "0.25.0") == (
        "uv tool upgrade hashmarks"
    )


def test_python_environment_is_not_guessed_as_an_installation_owner(monkeypatch) -> None:
    monkeypatch.setattr(release_update.sys, "prefix", "/repo/.venv")
    monkeypatch.setattr(release_update.sys, "base_prefix", "/usr")

    owner = release_update.detect_installation_owner()

    assert owner.kind == "environment"
    assert owner.command is None
    assert release_update.can_delegate_upgrade(owner) is False


def test_native_uv_delegation_replaces_hashmarks_process(monkeypatch) -> None:
    owner = InstallationOwner(
        kind="uv",
        label="uv",
        command=("uv", "tool", "upgrade", "hashmarks"),
    )
    monkeypatch.setattr(
        release_update.shutil,
        "which",
        lambda name: "/tools/uv" if name == "uv" else None,
    )
    seen: dict[str, object] = {}

    def execve(executable: str, argv: list[str], environ: dict[str, str]) -> None:
        seen["executable"] = executable
        seen["argv"] = argv
        seen["version"] = environ["HASHMARKS_VERSION"]
        raise OSError("blocked by test")

    monkeypatch.setattr(release_update.os, "execve", execve)

    with pytest.raises(release_update.UpgradeDelegationError):
        release_update.delegate_upgrade(owner, "0.25.0")

    assert seen == {
        "executable": "/tools/uv",
        "argv": ["/tools/uv", "tool", "upgrade", "hashmarks"],
        "version": "0.25.0",
    }


def test_periodic_cli_check_skips_unmanaged_installation(monkeypatch) -> None:
    owner = InstallationOwner(
        kind="environment",
        label="the current Python environment",
        command=None,
    )
    monkeypatch.setattr(cli, "detect_installation_owner", lambda: owner)
    monkeypatch.setattr(
        cli,
        "periodic_release_check",
        lambda *args, **kwargs: pytest.fail(
            "unmanaged/source environments must not perform automatic release checks"
        ),
    )

    cli._maybe_offer_periodic_upgrade("find")


def test_cli_upgrade_offers_two_explicit_choices_and_skip_does_not_mutate(
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    owner = InstallationOwner(
        kind="uv",
        label="uv",
        command=("uv", "tool", "upgrade", "hashmarks"),
    )
    monkeypatch.setattr(
        cli,
        "fetch_latest_release",
        lambda current_version, *, timeout: ReleaseInfo(
            current_version=current_version,
            latest_version="0.25.0",
        ),
    )
    monkeypatch.setattr(cli, "detect_installation_owner", lambda: owner)
    monkeypatch.setattr(cli, "can_delegate_upgrade", lambda value: value == owner)
    monkeypatch.setattr(cli, "_interactive_terminal", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    monkeypatch.setattr(
        cli,
        "delegate_upgrade",
        lambda *args, **kwargs: pytest.fail("skip must not mutate"),
    )

    assert cli.main(["upgrade"]) == 0

    output = capsys.readouterr().out
    assert "Hashmarks 0.24.0" in output
    assert "Latest: 0.25.0" in output
    assert "This installation is managed by uv." in output
    assert "Native upgrade command:" in output
    assert "uv tool upgrade hashmarks" in output
    assert output.index("uv tool upgrade hashmarks") < output.index("[1] Upgrade now")
    assert "[1] Upgrade now" in output
    assert "[2] Skip for now" in output
    assert "Upgrade skipped." in output


def test_cli_upgrade_noninteractive_prints_native_command_without_mutation(
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    owner = InstallationOwner(
        kind="uv",
        label="uv",
        command=("uv", "tool", "upgrade", "hashmarks"),
    )
    monkeypatch.setattr(
        cli,
        "fetch_latest_release",
        lambda current_version, *, timeout: ReleaseInfo(
            current_version=current_version,
            latest_version="0.25.0",
        ),
    )
    monkeypatch.setattr(cli, "detect_installation_owner", lambda: owner)
    monkeypatch.setattr(cli, "_interactive_terminal", lambda: False)
    monkeypatch.setattr(
        cli,
        "delegate_upgrade",
        lambda *args, **kwargs: pytest.fail("noninteractive use must not mutate"),
    )

    assert cli.main(["upgrade"]) == 0

    output = capsys.readouterr().out
    assert "Hashmarks does not modify its own installation directly." in output
    assert "uv tool upgrade hashmarks" in output


def test_cli_upgrade_reports_up_to_date_without_owner_detection(
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
        "detect_installation_owner",
        lambda: pytest.fail("owner is irrelevant when already current"),
    )

    assert cli.main(["upgrade"]) == 0

    assert "Hashmarks 0.24.0 is up to date." in capsys.readouterr().out


def test_managed_standalone_owner_requires_canonical_installed_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    installed_name = "hashmarks.exe" if release_update.os.name == "nt" else "hashmarks"
    executable = tmp_path / installed_name
    monkeypatch.setattr(release_update.sys, "frozen", True, raising=False)
    monkeypatch.setattr(release_update.sys, "executable", str(executable))

    owner = release_update.detect_installation_owner()

    assert owner.kind == "standalone"
    command = release_update.manual_upgrade_command(owner, "0.25.0")
    assert command is not None
    assert "HASHMARKS_VERSION" in command
    assert "0.25.0" in command
    assert "HASHMARKS_INSTALL_DIR" in command
    assert str(tmp_path.resolve()) in command


def test_raw_frozen_release_asset_is_not_guessed_as_managed_install(
    monkeypatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "hashmarks-linux-x86_64"
    monkeypatch.setattr(release_update.sys, "frozen", True, raising=False)
    monkeypatch.setattr(release_update.sys, "executable", str(executable))

    owner = release_update.detect_installation_owner()

    assert owner.kind == "frozen-unmanaged"
    assert owner.command is None
    assert release_update.can_delegate_upgrade(owner) is False


def test_standalone_delegation_executes_the_displayed_native_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    installed_name = "hashmarks.exe" if release_update.os.name == "nt" else "hashmarks"
    executable = tmp_path / installed_name
    monkeypatch.setattr(release_update.sys, "executable", str(executable))
    owner = InstallationOwner(
        kind="standalone",
        label="Hashmarks standalone installer",
        command=None,
    )
    displayed = release_update.manual_upgrade_command(owner, "0.25.0")
    assert displayed is not None

    def which(name: str) -> str | None:
        if release_update.os.name == "nt":
            return "C:\\Tools\\pwsh.exe" if name == "pwsh" else None
        return f"/tools/{name}" if name in {"sh", "curl"} else None

    monkeypatch.setattr(release_update.shutil, "which", which)
    seen: dict[str, object] = {}

    def exec_owner(
        native_executable: str,
        argv: tuple[str, ...],
        environment: dict[str, str],
    ) -> None:
        seen["executable"] = native_executable
        seen["argv"] = argv
        seen["version"] = environment["HASHMARKS_VERSION"]

    monkeypatch.setattr(release_update, "_exec_owner", exec_owner)

    release_update.delegate_upgrade(owner, "0.25.0")

    argv = seen["argv"]
    assert isinstance(argv, tuple)
    if release_update.os.name == "nt":
        assert argv[-1] == displayed
    else:
        assert argv == ("/tools/sh", "-c", displayed)
    assert seen["version"] == "0.25.0"\n