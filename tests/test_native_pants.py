from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hashmarks.native_pants import collect_pants_targets


def test_collect_pants_targets_normalizes_valid_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[0] == ["pants", "peek", "--exclude-defaults", "::"]
        assert kwargs["cwd"] == tmp_path
        return subprocess.CompletedProcess(
            args[0],
            0,
            stdout=(
                '[null, {"target_type": "python_sources"}, '
                '{"address": "src:lib", "sources": ["src\\\\lib.py", 4], '
                '"dependencies": ["src:base", null], "goals": ["lint", 2]}]'
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    snapshot = collect_pants_targets(tmp_path, executable="pants")
    assert snapshot.warnings == ()
    assert len(snapshot.targets) == 1
    target = snapshot.targets[0]
    assert target.address == "src:lib"
    assert target.target_type == "target"
    assert target.dependencies == ("src:base",)
    assert target.sources == ("src/lib.py",)
    assert target.goals == ("lint",)


@pytest.mark.parametrize(
    ("stdout", "returncode", "stderr", "warning"),
    [
        ("[]", 2, "first\nlast\n", "pants peek failed: last"),
        ("not-json", 0, "", "pants peek returned invalid JSON"),
        ('{"address": "src:lib"}', 0, "", "pants peek JSON must be a list"),
    ],
)
def test_collect_pants_targets_rejects_failed_or_invalid_peek(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stdout: str,
    returncode: int,
    stderr: str,
    warning: str,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], returncode, stdout=stdout, stderr=stderr
        ),
    )
    snapshot = collect_pants_targets(tmp_path, executable="pants")
    assert snapshot.targets == ()
    assert snapshot.warnings == (warning,)


def test_collect_pants_targets_reports_process_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("cannot start")

    monkeypatch.setattr(subprocess, "run", fail)
    snapshot = collect_pants_targets(tmp_path, executable="pants")
    assert snapshot.targets == ()
    assert snapshot.warnings == ("pants peek failed: cannot start",)
