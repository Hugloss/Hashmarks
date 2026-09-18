from __future__ import annotations

import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_PRUNE = {
    ".git",
    ".hashmarks",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "build",
    "dist",
}


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
    wrapper = workspace / "mvnw"
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


def _maven_manifests(workspace: Path) -> list[Path]:
    """Find repository-owned POMs without descending into generated trees."""
    manifests: list[Path] = []
    for current, dirs, files in os.walk(workspace, topdown=True, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in _PRUNE)
        if "pom.xml" in files:
            manifest = Path(current) / "pom.xml"
            if not manifest.is_symlink():
                manifests.append(manifest)
    return sorted(manifests)


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
    parent = _child(root, "parent")
    group_id = _text(root, "groupId") or _text(parent, "groupId") or ""
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


def collect_maven_modules(workspace: Path) -> MavenSnapshot:
    warnings: list[str] = []
    modules: list[MavenModuleData] = []
    for manifest in _maven_manifests(workspace):
        try:
            root = ET.parse(manifest).getroot()
        except (ET.ParseError, OSError) as exc:
            warnings.append(
                f"cannot parse {manifest.relative_to(workspace).as_posix()}: {exc}"
            )
            continue
        module = _maven_module(root, manifest, workspace)
        if module is not None:
            modules.append(module)
    return MavenSnapshot(find_maven(workspace), tuple(modules), tuple(warnings))
