from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_MARKER = "__HASHMARKS_GRADLE_JSON__"


@dataclass(frozen=True, slots=True)
class GradleProjectData:
    path: str
    name: str
    root: str
    dependencies: tuple[str, ...]
    tasks: tuple[str, ...]
    manifests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GradleSnapshot:
    executable: str | None
    projects: tuple[GradleProjectData, ...] = ()
    warnings: tuple[str, ...] = ()


def find_gradle(workspace: Path) -> str | None:
    wrapper = workspace / "gradlew"
    if wrapper.is_file():
        return str(wrapper)
    return shutil.which("gradle")


def _manifest_candidates(workspace: Path, project_root: Path) -> tuple[str, ...]:
    values: list[str] = []
    for base, names in (
        (
            workspace,
            (
                "settings.gradle",
                "settings.gradle.kts",
                "build.gradle",
                "build.gradle.kts",
                "gradle.properties",
            ),
        ),
        (project_root, ("build.gradle", "build.gradle.kts", "gradle.properties")),
        (workspace / "gradle", ("libs.versions.toml",)),
    ):
        for name in names:
            candidate = base / name
            if candidate.is_file() and not candidate.is_symlink():
                try:
                    values.append(candidate.relative_to(workspace).as_posix())
                except ValueError:
                    continue
    return tuple(dict.fromkeys(values))


def _gradle_report_payload(stdout: str) -> tuple[list[object] | None, str | None]:
    """Read the last marked project report without treating other output as evidence."""
    payload = None
    for line in stdout.splitlines():
        if line.startswith(_MARKER):
            try:
                payload = json.loads(line[len(_MARKER) :])
            except json.JSONDecodeError:
                return None, "Gradle project report returned invalid JSON"
    if not isinstance(payload, list):
        return None, "Gradle project report marker was not emitted"
    return payload, None


def _gradle_project_rows(
    workspace: Path, payload: list[object]
) -> tuple[GradleProjectData, ...]:
    """Keep only projects whose resolved directory belongs to this workspace."""
    projects: list[GradleProjectData] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        project_dir = Path(str(raw.get("projectDir") or "")).resolve(strict=False)
        try:
            root = project_dir.relative_to(workspace).as_posix() or "."
        except ValueError:
            continue
        path = str(raw.get("path") or ":")
        name = str(raw.get("name") or path.strip(":") or workspace.name)
        deps = tuple(
            str(value)
            for value in raw.get("dependencies") or ()
            if isinstance(value, str)
        )
        tasks = tuple(
            str(value) for value in raw.get("tasks") or () if isinstance(value, str)
        )
        projects.append(
            GradleProjectData(
                path,
                name,
                root,
                deps,
                tasks,
                _manifest_candidates(workspace, project_dir),
            )
        )
    return tuple(projects)


def collect_gradle_projects(
    workspace: Path, *, executable: str | None = None, timeout: float = 60.0
) -> GradleSnapshot:
    gradle = executable or find_gradle(workspace)
    if gradle is None:
        return GradleSnapshot(
            None,
            warnings=(
                "Gradle settings/build detected but gradle/gradlew is unavailable",
            ),
        )
    script = r"""
import groovy.json.JsonOutput

gradle.projectsEvaluated {
    def rows = gradle.rootProject.allprojects.collect { p ->
        def deps = [] as Set
        p.configurations.each { c ->
            c.dependencies.withType(org.gradle.api.artifacts.ProjectDependency).each { d ->
                try {
                    if (d.hasProperty('path')) deps << d.path
                    else if (d.hasProperty('dependencyProject')) deps << d.dependencyProject.path
                } catch (Throwable ignored) {}
            }
        }
        [
            path: p.path,
            name: p.name,
            projectDir: p.projectDir.canonicalPath,
            dependencies: deps.toList().sort(),
            tasks: p.tasks.names.toList().sort()
        ]
    }
    println('__HASHMARKS_GRADLE_JSON__' + JsonOutput.toJson(rows))
}
""".strip()
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".gradle", prefix="hashmarks-", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(script)
            temp_path = Path(handle.name)
        completed = subprocess.run(
            [gradle, "--no-daemon", "-q", "-I", str(temp_path), "help"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=dict(os.environ),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return GradleSnapshot(
            gradle, warnings=(f"Gradle project report failed: {exc}",)
        )
    finally:
        if temp_path is not None:
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip().splitlines()[-1]
            if completed.stderr.strip()
            else f"exit {completed.returncode}"
        )
        return GradleSnapshot(
            gradle, warnings=(f"Gradle project report failed: {detail}",)
        )
    payload, warning = _gradle_report_payload(completed.stdout)
    if warning is not None:
        return GradleSnapshot(gradle, warnings=(warning,))
    assert payload is not None
    return GradleSnapshot(gradle, _gradle_project_rows(workspace, payload))
