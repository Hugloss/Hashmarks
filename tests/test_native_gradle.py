from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hashmarks.native_gradle import collect_gradle_projects


def test_collect_gradle_projects_normalizes_workspace_projects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "settings.gradle").write_text("include ':core'\n", encoding="utf-8")
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "build.gradle").write_text("plugins {}\n", encoding="utf-8")
    payload = [
        {
            "path": ":core",
            "projectDir": str(tmp_path / "core"),
            "dependencies": [":base", 4],
            "tasks": ["test", None],
        },
        {"projectDir": str(tmp_path.parent)},
        "invalid",
    ]

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["cwd"] == tmp_path
        return subprocess.CompletedProcess(
            args[0],
            0,
            stdout="noise\n__HASHMARKS_GRADLE_JSON__" + json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    snapshot = collect_gradle_projects(tmp_path, executable="gradle")
    assert snapshot.warnings == ()
    assert len(snapshot.projects) == 1
    project = snapshot.projects[0]
    assert (project.path, project.name, project.root) == (":core", "core", "core")
    assert project.dependencies == (":base",)
    assert project.tasks == ("test",)
    assert project.manifests == ("settings.gradle", "core/build.gradle")


@pytest.mark.parametrize(
    ("stdout", "returncode", "stderr", "warning"),
    [
        ("", 2, "first\nlast\n", "Gradle project report failed: last"),
        ("noise", 0, "", "Gradle project report marker was not emitted"),
        (
            "__HASHMARKS_GRADLE_JSON__broken",
            0,
            "",
            "Gradle project report returned invalid JSON",
        ),
    ],
)
def test_collect_gradle_projects_reports_failed_or_invalid_result(
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
    snapshot = collect_gradle_projects(tmp_path, executable="gradle")
    assert snapshot.projects == ()
    assert snapshot.warnings == (warning,)


def test_collect_gradle_projects_reports_process_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("cannot start")

    monkeypatch.setattr(subprocess, "run", fail)
    snapshot = collect_gradle_projects(tmp_path, executable="gradle")
    assert snapshot.projects == ()
    assert snapshot.warnings == ("Gradle project report failed: cannot start",)
