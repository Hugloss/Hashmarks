from __future__ import annotations

import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MavenModuleData:
    module_id: str
    group_id: str
    artifact_id: str
    root: str
    manifest: str
    dependencies: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class MavenSnapshot:
    executable: str | None
    modules: tuple[MavenModuleData, ...]
    warnings: tuple[str, ...] = ()


def find_maven(workspace: Path) -> str | None:
    for name in ("mvnw", "mvnw.cmd"):
        wrapper = workspace / name
        if wrapper.is_file():
            return str(wrapper)
    return shutil.which("mvn")


def _text(parent: ET.Element | None, name: str) -> str | None:
    if parent is None:
        return None
    child = next(
        (value for value in parent if value.tag.rsplit("}", 1)[-1] == name), None
    )
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _child(parent: ET.Element | None, name: str) -> ET.Element | None:
    if parent is None:
        return None
    return next(
        (value for value in parent if value.tag.rsplit("}", 1)[-1] == name), None
    )


def _maven_dependencies(root: ET.Element) -> tuple[tuple[str, str], ...]:
    deps_parent = _child(root, "dependencies")
    if deps_parent is None:
        return ()
    dependencies: list[tuple[str, str]] = []
    for dep in deps_parent:
        if dep.tag.rsplit("}", 1)[-1] != "dependency":
            continue
        dep_group = _text(dep, "groupId") or ""
        dep_artifact = _text(dep, "artifactId") or ""
        if dep_artifact:
            dependencies.append((dep_group, dep_artifact))
    return tuple(dependencies)


def _maven_module(
    root: ET.Element, manifest: Path, workspace: Path
) -> MavenModuleData | None:
    group_id = _text(root, "groupId") or ""
    artifact_id = _text(root, "artifactId") or ""
    if not artifact_id:
        return None
    rel_root = manifest.parent.relative_to(workspace).as_posix() or "."
    rel_manifest = manifest.relative_to(workspace).as_posix()
    module_id = f"{group_id}:{artifact_id}" if group_id else artifact_id
    return MavenModuleData(
        module_id,
        group_id,
        artifact_id,
        rel_root,
        rel_manifest,
        _maven_dependencies(root),
    )


def _effective_pom(
    workspace: Path,
    manifest: Path,
    maven: str,
    *,
    timeout: float,
) -> tuple[ET.Element | None, str | None]:
    with tempfile.TemporaryDirectory(prefix="hashmarks-maven-") as temp_dir:
        output = Path(temp_dir) / "effective-pom.xml"
        command = [
            maven,
            "-q",
            "-N",
            "-f",
            str(manifest),
            "help:effective-pom",
            f"-Doutput={output}",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"Maven effective POM failed for {manifest}: {exc}"
        if completed.returncode != 0:
            detail = (
                completed.stderr.strip().splitlines()[-1]
                if completed.stderr.strip()
                else f"exit {completed.returncode}"
            )
            return None, f"Maven effective POM failed for {manifest}: {detail}"
        if not output.is_file():
            return None, f"Maven effective POM was not produced for {manifest}"
        try:
            return ET.parse(output).getroot(), None
        except (ET.ParseError, OSError) as exc:
            return None, f"Maven effective POM is invalid for {manifest}: {exc}"


def collect_maven_modules(
    workspace: Path,
    manifests: tuple[Path, ...],
    *,
    executable: str | None = None,
    timeout: float = 60.0,
) -> MavenSnapshot:
    maven = executable or find_maven(workspace)
    if maven is None:
        return MavenSnapshot(
            None,
            (),
            ("Maven POMs detected but mvn/mvnw is unavailable",),
        )
    warnings: list[str] = []
    modules: list[MavenModuleData] = []
    for manifest in manifests:
        root, warning = _effective_pom(
            workspace,
            manifest,
            maven,
            timeout=timeout,
        )
        if root is None:
            if warning is not None:
                warnings.append(warning)
            continue
        module = _maven_module(root, manifest, workspace)
        if module is None:
            warnings.append(
                f"Maven effective POM has no artifactId: "
                f"{manifest.relative_to(workspace).as_posix()}"
            )
            continue
        modules.append(module)
    return MavenSnapshot(maven, tuple(modules), tuple(warnings))
