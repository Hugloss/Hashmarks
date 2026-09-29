from __future__ import annotations

import json
import subprocess
from pathlib import Path

import hashmarks.cli as cli


def _which(hashmarks: Path, opencode: Path):
    def which(name: str) -> str | None:
        return {
            "hashmarks": str(hashmarks),
            "opencode": str(opencode),
        }.get(name)

    return which


def test_install_opencode_registers_exact_hashmarks_executable(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    hashmarks = tmp_path / "hashmarks"
    opencode = tmp_path / "opencode"
    hashmarks.write_text("", encoding="utf-8")
    opencode.write_text("", encoding="utf-8")

    calls: list[list[str]] = []

    def run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        calls.append(command)
        if command[1:] == ["debug", "config"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "mcp": {
                            "hashmarks": {
                                "type": "local",
                                "command": [
                                    str(hashmarks.resolve()),
                                    "--workspace",
                                    ".",
                                    "mcp",
                                ],
                                "enabled": True,
                            }
                        }
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli.shutil, "which", _which(hashmarks, opencode))
    monkeypatch.setattr(cli.subprocess, "run", run)

    assert cli.main(["install", "--opencode"]) == 0
    assert calls[0] == [
        str(opencode),
        "mcp",
        "add",
        "hashmarks",
        "--",
        str(hashmarks.resolve()),
        "--workspace",
        ".",
        "mcp",
    ]
    assert calls[1] == [str(opencode), "debug", "config"]
    output = capsys.readouterr().out
    assert '"effective_registration": "active"' in output


def test_install_opencode_reports_project_shadowing_without_rewriting(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    hashmarks = tmp_path / "hashmarks"
    opencode = tmp_path / "opencode"
    hashmarks.write_text("", encoding="utf-8")
    opencode.write_text("", encoding="utf-8")

    def run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        if command[1:] == ["debug", "config"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "mcp": {
                            "hashmarks": {
                                "type": "local",
                                "command": [
                                    "uv",
                                    "run",
                                    "--frozen",
                                    "--no-sync",
                                    "hashmarks",
                                    "--workspace",
                                    ".",
                                    "mcp",
                                ],
                                "enabled": True,
                            }
                        }
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli.shutil, "which", _which(hashmarks, opencode))
    monkeypatch.setattr(cli.subprocess, "run", run)

    assert cli.main(["install", "--opencode"]) == 0
    output = capsys.readouterr().out
    assert '"effective_registration": "shadowed"' in output
    assert '"effective_command": [' in output
    assert '"uv"' in output
    assert '"--no-sync"' in output
    assert "did not modify project configuration" in output


def test_install_opencode_keeps_registration_when_effective_config_unverifiable(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    hashmarks = tmp_path / "hashmarks"
    opencode = tmp_path / "opencode"
    hashmarks.write_text("", encoding="utf-8")
    opencode.write_text("", encoding="utf-8")

    def run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        if command[1:] == ["debug", "config"]:
            return subprocess.CompletedProcess(
                command,
                4,
                stdout="",
                stderr="unavailable",
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli.shutil, "which", _which(hashmarks, opencode))
    monkeypatch.setattr(cli.subprocess, "run", run)

    assert cli.main(["install", "--opencode"]) == 0
    output = capsys.readouterr().out
    assert '"effective_registration": "unverified"' in output
    assert "opencode debug config exited 4" in output


def test_install_opencode_reports_registration_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    hashmarks = tmp_path / "hashmarks"
    opencode = tmp_path / "opencode"
    hashmarks.write_text("", encoding="utf-8")
    opencode.write_text("", encoding="utf-8")

    monkeypatch.setattr(cli.shutil, "which", _which(hashmarks, opencode))

    def run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 17)

    monkeypatch.setattr(cli.subprocess, "run", run)

    try:
        cli.main(["install", "--opencode"])
    except SystemExit as exc:
        assert str(exc) == "OpenCode rejected Hashmarks MCP registration (exit 17)"
    else:
        raise AssertionError("failed OpenCode registration must fail closed")
