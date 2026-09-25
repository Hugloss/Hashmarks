from __future__ import annotations

import subprocess
from pathlib import Path

import hashmarks.cli as cli


def test_install_opencode_registers_exact_hashmarks_executable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    hashmarks = tmp_path / "hashmarks"
    opencode = tmp_path / "opencode"
    hashmarks.write_text("", encoding="utf-8")
    opencode.write_text("", encoding="utf-8")

    def which(name: str) -> str | None:
        return {
            "hashmarks": str(hashmarks),
            "opencode": str(opencode),
        }.get(name)

    calls: list[list[str]] = []

    def run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert check is False
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli.shutil, "which", which)
    monkeypatch.setattr(cli.subprocess, "run", run)

    assert cli.main(["install", "--opencode"]) == 0
    assert calls == [
        [
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
    ]


def test_install_opencode_reports_registration_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    hashmarks = tmp_path / "hashmarks"
    opencode = tmp_path / "opencode"
    hashmarks.write_text("", encoding="utf-8")
    opencode.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        cli.shutil,
        "which",
        lambda name: {
            "hashmarks": str(hashmarks),
            "opencode": str(opencode),
        }.get(name),
    )
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda command, *, check: subprocess.CompletedProcess(command, 17),
    )

    try:
        cli.main(["install", "--opencode"])
    except SystemExit as exc:
        assert str(exc) == "OpenCode rejected Hashmarks MCP registration (exit 17)"
    else:
        raise AssertionError("failed OpenCode registration must fail closed")
