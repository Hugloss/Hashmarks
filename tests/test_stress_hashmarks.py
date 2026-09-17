"""Fast OSS smoke stress for the installed Hashmarks CLI.

These tests exercise the public console-script entry point repeatedly against small,
isolated repositories. They intentionally avoid real MCP hosts, network access, and
large benchmarks so they remain suitable for the normal ``make test`` suite.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.host_console_script


def _hashmarks_executable() -> Path:
    name = "hashmarks.exe" if os.name == "nt" else "hashmarks"
    executable = Path(sys.executable).with_name(name)
    if not executable.is_file():
        pytest.fail(
            "installed hashmarks console script not found next to the test interpreter: "
            f"{executable}"
        )
    return executable


def _run_cli(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_hashmarks_executable()), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    return repo


def _json_output(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"CLI output is not valid JSON: {exc}\n{result.stdout}")
    assert isinstance(payload, dict)
    return payload


def test_cli_version_repeatedly_runs_installed_console_script(tmp_path: Path) -> None:
    for _ in range(5):
        payload = _json_output(_run_cli(["version"], cwd=tmp_path))
        assert isinstance(payload.get("version"), str)
        assert payload["version"]


def test_cli_doctor_repeatedly_emits_identity_contract(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    state = tmp_path / "identity-state"

    for _ in range(5):
        payload = _json_output(
            _run_cli(
                [
                    "doctor",
                    "--workspace",
                    str(repo),
                    "--state-dir",
                    str(state),
                    "--mode",
                    "local",
                ],
                cwd=repo,
            )
        )
        assert payload["schema"] == "fastidentity.identity.v1"
        assert payload["workspace"] == str(repo.resolve())
        assert payload["state_dir"] == str(state.resolve())
        assert payload["requested_mode"] == "local"
        assert payload["active_mode"] == "local"
        assert "daemon" in payload
        assert "daemon_error" in payload


def test_cli_map_sync_repeatedly_reuses_isolated_state(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    state = tmp_path / "codemap-state"
    generations: list[int] = []

    for _ in range(5):
        payload = _json_output(
            _run_cli(
                [
                    "map",
                    "sync",
                    "--workspace",
                    str(repo),
                    "--state-dir",
                    str(state),
                ],
                cwd=repo,
            )
        )
        assert payload["schema"] == "hashmarks.codemap.v1"
        assert payload["build_state"] == "COMPLETE"
        generation = payload["generation"]
        assert isinstance(generation, int)
        generations.append(generation)

    assert generations == sorted(generations)
