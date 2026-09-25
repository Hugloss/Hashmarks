from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hashmarks.native_gradle import collect_gradle_projects
from hashmarks.native_maven import collect_maven_modules
from hashmarks.native_nx import collect_nx_graph, find_nx
from hashmarks.native_pants import collect_pants_targets

if TYPE_CHECKING:
    from collections.abc import Iterable

_PRUNE = {
    ".git",
    ".hashmarks",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "dist",
    "build",
    ".next",
}


@dataclass(frozen=True)
class ProjectNode:
    project_id: str
    kind: str
    root: str
    manifest: str
    producer: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectEdge:
    source: str
    target: str
    kind: str
    confidence: str
    producer: str


@dataclass(frozen=True)
class ProjectGraphEvidence:
    producer: str
    nodes: tuple[ProjectNode, ...] = ()
    edges: tuple[ProjectEdge, ...] = ()
    warnings: tuple[str, ...] = ()


ManifestFinder = Callable[[str], tuple[Path, ...]]


class ProjectGraphProvider:
    name = "project-graph"

    def __init__(self, manifest_finder: ManifestFinder | None = None) -> None:
        self._manifest_finder = manifest_finder

    def _manifest_paths(self, workspace: Path, filename: str) -> tuple[Path, ...]:
        if self._manifest_finder is not None:
            return self._manifest_finder(filename)
        return tuple(_walk_manifests(workspace, filename))

    def detect(self, workspace: Path) -> bool:
        raise NotImplementedError

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        raise NotImplementedError


def _walk_manifests(workspace: Path, filename: str) -> list[Path]:
    out: list[Path] = []
    for root, dirs, files in os.walk(workspace, topdown=True, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in _PRUNE)
        if filename in files:
            path = Path(root) / filename
            if not path.is_symlink():
                out.append(path)
    return out


def _rel(workspace: Path, path: Path) -> str:
    return path.relative_to(workspace).as_posix()


class NpmProjectGraphProvider(ProjectGraphProvider):
    name = "npm-package-graph"

    def detect(self, workspace: Path) -> bool:
        return bool(self._manifest_paths(workspace, "package.json"))

    def _package_rows(
        self, workspace: Path
    ) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
        rows: list[tuple[Path, dict[str, Any]]] = []
        warnings: list[str] = []
        for manifest in self._manifest_paths(workspace, "package.json"):
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                warnings.append(f"cannot parse {_rel(workspace, manifest)}: {exc}")
                continue
            if isinstance(value, dict):
                rows.append((manifest, value))
        return rows, warnings

    @staticmethod
    def _npm_name(workspace: Path, manifest: Path, value: dict[str, Any]) -> str:
        root_rel = (
            _rel(workspace, manifest.parent) if manifest.parent != workspace else "."
        )
        return str(value.get("name") or f"npm:{root_rel}")

    def _npm_node(
        self, workspace: Path, manifest: Path, value: dict[str, Any]
    ) -> ProjectNode:
        root = manifest.parent
        root_rel = _rel(workspace, root) if root != workspace else "."
        name = self._npm_name(workspace, manifest, value)
        scripts = value.get("scripts")
        script_names = sorted(scripts) if isinstance(scripts, dict) else []
        return ProjectNode(
            project_id=f"npm:{name}",
            kind="npm",
            root=root_rel,
            manifest=_rel(workspace, manifest),
            producer=self.name,
            metadata={
                "name": name,
                "private": bool(value.get("private", False)),
                "scripts": script_names,
            },
        )

    def _npm_nodes(
        self, workspace: Path, rows: list[tuple[Path, dict[str, Any]]]
    ) -> tuple[list[ProjectNode], dict[str, str]]:
        nodes = [self._npm_node(workspace, manifest, value) for manifest, value in rows]
        return nodes, {str(node.metadata["name"]): node.project_id for node in nodes}

    def _npm_edges(
        self,
        workspace: Path,
        rows: list[tuple[Path, dict[str, Any]]],
        names: dict[str, str],
    ) -> list[ProjectEdge]:
        edges: list[ProjectEdge] = []
        fields = (
            "dependencies",
            "devDependencies",
            "peerDependencies",
            "optionalDependencies",
        )
        for manifest, value in rows:
            source = f"npm:{self._npm_name(workspace, manifest, value)}"
            for field_name in fields:
                deps = value.get(field_name)
                if not isinstance(deps, dict):
                    continue
                for dep_name in deps:
                    target = names.get(str(dep_name))
                    if target is not None and target != source:
                        edges.append(
                            ProjectEdge(
                                source, target, field_name, "manifest", self.name
                            )
                        )
        return edges

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        rows, warnings = self._package_rows(workspace)
        nodes, names = self._npm_nodes(workspace, rows)
        edges = self._npm_edges(workspace, rows, names)
        return ProjectGraphEvidence(
            self.name, tuple(nodes), tuple(edges), tuple(warnings)
        )


class NxProjectGraphProvider(ProjectGraphProvider):
    """Native Nx project graph provider in the derived CodeMap lane."""

    name = "nx-project-graph"

    @staticmethod
    def _executable(workspace: Path) -> str | None:
        return find_nx(workspace)

    def detect(self, workspace: Path) -> bool:
        return bool(self._manifest_paths(workspace, "nx.json"))

    @staticmethod
    def _node_manifest(workspace: Path, root: str) -> str:
        project_root = workspace if root in {"", "."} else workspace / root
        for name in ("project.json", "package.json"):
            candidate = project_root / name
            if candidate.is_file() and not candidate.is_symlink():
                return _rel(workspace, candidate)
        return "nx.json"

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        graph = collect_nx_graph(workspace, executable=self._executable(workspace))
        nodes: list[ProjectNode] = []
        for row in graph.nodes:
            manifest = self._node_manifest(workspace, row.root)
            freshness = ["nx.json", manifest]
            for candidate in (
                "package.json",
                "pnpm-workspace.yaml",
                "package-lock.json",
                "pnpm-lock.yaml",
                "yarn.lock",
            ):
                if (workspace / candidate).is_file():
                    freshness.append(candidate)
            nodes.append(
                ProjectNode(
                    project_id=f"nx:{row.name}",
                    kind=f"nx-{row.type}",
                    root=row.root,
                    manifest=manifest,
                    producer=self.name,
                    metadata={
                        "name": row.name,
                        "source_root": row.source_root,
                        "targets": list(row.targets),
                        "tags": list(row.tags),
                        "freshness_manifests": list(dict.fromkeys(freshness)),
                    },
                )
            )
        edges = tuple(
            ProjectEdge(
                source=f"nx:{row.source}",
                target=f"nx:{row.target}",
                kind=row.kind,
                confidence="native-dynamic" if row.kind == "dynamic" else "native",
                producer=self.name,
            )
            for row in graph.edges
        )
        return ProjectGraphEvidence(self.name, tuple(nodes), edges, graph.warnings)


class PantsProjectGraphProvider(ProjectGraphProvider):
    name = "pants-target-graph"

    def detect(self, workspace: Path) -> bool:
        return bool(self._manifest_paths(workspace, "pants.toml"))

    @staticmethod
    def _root(address: str, sources: tuple[str, ...]) -> str:
        if sources:
            parents = [Path(value).parent.as_posix() for value in sources]
            common = os.path.commonpath(parents).replace("\\", "/") if parents else "."
            return common or "."
        path = address.split(":", 1)[0].split("#", 1)[0].strip("/")
        return path or "."

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        snapshot = collect_pants_targets(workspace)
        known = {row.address for row in snapshot.targets}
        nodes = tuple(
            ProjectNode(
                project_id=f"pants:{row.address}",
                kind=f"pants-{row.target_type}",
                root=self._root(row.address, row.sources),
                manifest="pants.toml",
                producer=self.name,
                metadata={
                    "address": row.address,
                    "target_type": row.target_type,
                    "sources": list(row.sources),
                    "goals": list(row.goals),
                    "freshness_manifests": ["pants.toml"],
                },
            )
            for row in snapshot.targets
        )
        edges = tuple(
            ProjectEdge(
                source=f"pants:{row.address}",
                target=f"pants:{dependency}",
                kind="dependency",
                confidence="native",
                producer=self.name,
            )
            for row in snapshot.targets
            for dependency in row.dependencies
            if dependency in known and dependency != row.address
        )
        return ProjectGraphEvidence(self.name, nodes, edges, snapshot.warnings)


class MavenProjectGraphProvider(ProjectGraphProvider):
    name = "maven-pom-graph"

    def detect(self, workspace: Path) -> bool:
        return bool(self._manifest_paths(workspace, "pom.xml"))

    @staticmethod
    def _module_indexes(modules):
        ids = {row.module_id: f"maven:{row.module_id}" for row in modules}
        by_ga = {(row.group_id, row.artifact_id): row.module_id for row in modules}
        by_artifact: dict[str, list[str]] = {}
        for row in modules:
            by_artifact.setdefault(row.artifact_id, []).append(row.module_id)
        return ids, by_ga, by_artifact

    def _maven_nodes(self, modules, ids: dict[str, str]) -> tuple[ProjectNode, ...]:
        return tuple(
            ProjectNode(
                project_id=ids[row.module_id],
                kind="maven-module",
                root=row.root,
                manifest=row.manifest,
                producer=self.name,
                metadata={
                    "group_id": row.group_id,
                    "artifact_id": row.artifact_id,
                    "freshness_manifests": [row.manifest],
                },
            )
            for row in modules
        )

    @staticmethod
    def _resolve_maven_target(
        group_id: str, artifact_id: str, by_ga, by_artifact
    ) -> str | None:
        target_id = by_ga.get((group_id, artifact_id))
        if target_id is not None:
            return target_id
        candidates = by_artifact.get(artifact_id, ())
        return candidates[0] if not group_id and len(candidates) == 1 else None

    def _maven_edges(self, modules, ids, by_ga, by_artifact) -> tuple[ProjectEdge, ...]:
        edges: list[ProjectEdge] = []
        for row in modules:
            for group_id, artifact_id in row.dependencies:
                target_id = self._resolve_maven_target(
                    group_id, artifact_id, by_ga, by_artifact
                )
                if target_id is not None and target_id != row.module_id:
                    edges.append(
                        ProjectEdge(
                            ids[row.module_id],
                            ids[target_id],
                            "dependency",
                            "manifest",
                            self.name,
                        )
                    )
        return tuple(edges)

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        snapshot = collect_maven_modules(workspace)
        ids, by_ga, by_artifact = self._module_indexes(snapshot.modules)
        nodes = self._maven_nodes(snapshot.modules, ids)
        edges = self._maven_edges(snapshot.modules, ids, by_ga, by_artifact)
        return ProjectGraphEvidence(self.name, nodes, edges, snapshot.warnings)


class GradleProjectGraphProvider(ProjectGraphProvider):
    name = "gradle-project-graph"

    def detect(self, workspace: Path) -> bool:
        return any(
            self._manifest_paths(workspace, name)
            for name in (
                "settings.gradle",
                "settings.gradle.kts",
                "build.gradle",
                "build.gradle.kts",
            )
        )

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        snapshot = collect_gradle_projects(workspace)
        known = {row.path for row in snapshot.projects}
        nodes = tuple(
            ProjectNode(
                project_id=f"gradle:{row.path}",
                kind="gradle-project",
                root=row.root,
                manifest=(row.manifests[0] if row.manifests else "settings.gradle"),
                producer=self.name,
                metadata={
                    "path": row.path,
                    "name": row.name,
                    "targets": list(row.tasks),
                    "freshness_manifests": list(row.manifests),
                },
            )
            for row in snapshot.projects
        )
        edges = tuple(
            ProjectEdge(
                source=f"gradle:{row.path}",
                target=f"gradle:{dependency}",
                kind="project-dependency",
                confidence="native",
                producer=self.name,
            )
            for row in snapshot.projects
            for dependency in row.dependencies
            if dependency in known and dependency != row.path
        )
        return ProjectGraphEvidence(self.name, nodes, edges, snapshot.warnings)


class GoProjectGraphProvider(ProjectGraphProvider):
    name = "go-list"

    def detect(self, workspace: Path) -> bool:
        return bool(self._manifest_paths(workspace, "go.mod"))

    @staticmethod
    def _json_stream(text: str) -> Iterable[dict[str, Any]]:
        decoder = json.JSONDecoder()
        idx = 0
        size = len(text)
        while idx < size:
            while idx < size and text[idx].isspace():
                idx += 1
            if idx >= size:
                return
            value, idx = decoder.raw_decode(text, idx)
            if isinstance(value, dict):
                yield value

    def _run_go_list(
        self, workspace: Path, go: str
    ) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
        try:
            completed = subprocess.run(
                [go, "list", "-json", "./..."],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                env={**os.environ, "GOWORK": os.environ.get("GOWORK", "auto")},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"go list failed: {exc}"
        if completed.returncode == 0:
            return completed, None
        detail = (
            completed.stderr.strip().splitlines()[-1]
            if completed.stderr.strip()
            else f"exit {completed.returncode}"
        )
        return None, f"go list failed: {detail}"

    @staticmethod
    def _go_ids(packages: list[dict[str, Any]]) -> dict[str, str]:
        return {
            str(row["ImportPath"]): f"go:{row['ImportPath']}"
            for row in packages
            if row.get("ImportPath")
        }

    def _go_node(
        self, workspace: Path, row: dict[str, Any], ids: dict[str, str]
    ) -> ProjectNode | None:
        import_path = row.get("ImportPath")
        directory = row.get("Dir")
        if not import_path or not directory:
            return None
        try:
            root = (
                Path(str(directory))
                .resolve(strict=False)
                .relative_to(workspace)
                .as_posix()
                or "."
            )
        except ValueError:
            return None
        return ProjectNode(
            project_id=ids[str(import_path)],
            kind="go-package",
            root=root,
            manifest="go.mod",
            producer=self.name,
            metadata={
                "import_path": str(import_path),
                "name": str(row.get("Name") or ""),
            },
        )

    def _go_edges(
        self, row: dict[str, Any], source: str, ids: dict[str, str]
    ) -> list[ProjectEdge]:
        edges: list[ProjectEdge] = []
        for field_name in ("Imports", "TestImports", "XTestImports"):
            for imported in row.get(field_name) or ():
                target = ids.get(str(imported))
                if target is not None and target != source:
                    edges.append(
                        ProjectEdge(
                            source, target, field_name.lower(), "native", self.name
                        )
                    )
        return edges

    def _go_graph(
        self, workspace: Path, packages: list[dict[str, Any]]
    ) -> tuple[list[ProjectNode], list[ProjectEdge]]:
        ids = self._go_ids(packages)
        nodes: list[ProjectNode] = []
        edges: list[ProjectEdge] = []
        for row in packages:
            node = self._go_node(workspace, row, ids)
            if node is None:
                continue
            nodes.append(node)
            edges.extend(self._go_edges(row, node.project_id, ids))
        return nodes, edges

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        go = shutil.which("go")
        if go is None:
            return ProjectGraphEvidence(
                self.name,
                warnings=(
                    "go executable unavailable; native Go package graph not collected",
                ),
            )
        completed, error = self._run_go_list(workspace, go)
        if completed is None:
            return ProjectGraphEvidence(
                self.name, warnings=(error or "go list failed",)
            )
        packages = list(self._json_stream(completed.stdout))
        nodes, edges = self._go_graph(workspace, packages)
        return ProjectGraphEvidence(self.name, tuple(nodes), tuple(edges))


class CargoProjectGraphProvider(ProjectGraphProvider):
    name = "cargo-metadata"

    def detect(self, workspace: Path) -> bool:
        return bool(self._manifest_paths(workspace, "Cargo.toml"))

    def _fallback_rows(
        self, workspace: Path
    ) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
        rows: list[tuple[Path, dict[str, Any]]] = []
        warnings: list[str] = []
        for manifest in self._manifest_paths(workspace, "Cargo.toml"):
            try:
                value = tomllib.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                warnings.append(f"cannot parse {_rel(workspace, manifest)}: {exc}")
                continue
            package = value.get("package")
            if isinstance(package, dict) and package.get("name"):
                rows.append((manifest, value))
        return rows, warnings

    def _fallback_nodes(
        self, workspace: Path, rows
    ) -> tuple[list[ProjectNode], dict[str, str]]:
        nodes: list[ProjectNode] = []
        names: dict[str, str] = {}
        for manifest, value in rows:
            package = value["package"]
            name = str(package["name"])
            project_id = f"cargo:{name}"
            root = (
                _rel(workspace, manifest.parent)
                if manifest.parent != workspace
                else "."
            )
            nodes.append(
                ProjectNode(
                    project_id,
                    "cargo",
                    root,
                    _rel(workspace, manifest),
                    self.name,
                    {"name": name},
                )
            )
            names[name] = project_id
        return nodes, names

    @staticmethod
    def _cargo_dependency_name(dep_name: object, dep_value: object) -> str:
        if isinstance(dep_value, dict) and dep_value.get("package"):
            return str(dep_value["package"])
        return str(dep_name)

    def _fallback_edges(self, rows, names: dict[str, str]) -> list[ProjectEdge]:
        edges: list[ProjectEdge] = []
        for _manifest, value in rows:
            source = names.get(str(value["package"].get("name")))
            if source is None:
                continue
            for field_name in (
                "dependencies",
                "dev-dependencies",
                "build-dependencies",
            ):
                deps = value.get(field_name)
                if not isinstance(deps, dict):
                    continue
                for dep_name, dep_value in deps.items():
                    target = names.get(self._cargo_dependency_name(dep_name, dep_value))
                    if target is not None and target != source:
                        edges.append(
                            ProjectEdge(
                                source, target, field_name, "manifest", self.name
                            )
                        )
        return edges

    def _fallback(
        self, workspace: Path, warning: str | None = None
    ) -> ProjectGraphEvidence:
        rows, parse_warnings = self._fallback_rows(workspace)
        warnings = ([warning] if warning else []) + parse_warnings
        nodes, names = self._fallback_nodes(workspace, rows)
        edges = self._fallback_edges(rows, names)
        return ProjectGraphEvidence(
            self.name, tuple(nodes), tuple(edges), tuple(warnings)
        )

    @staticmethod
    def _run_cargo_metadata(
        workspace: Path, cargo: str
    ) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
        try:
            completed = subprocess.run(
                [cargo, "metadata", "--format-version", "1", "--no-deps"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"cargo metadata failed; using manifest graph: {exc}"
        if completed.returncode != 0:
            return None, "cargo metadata failed; using Cargo.toml manifest graph"
        return completed, None

    @staticmethod
    def _cargo_packages(stdout: str) -> tuple[list[dict[str, Any]] | None, str | None]:
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError:
            return None, "cargo metadata returned invalid JSON; using manifest graph"
        packages = value.get("packages") if isinstance(value, dict) else None
        return (packages if isinstance(packages, list) else []), None

    def _cargo_native_node(
        self, workspace: Path, row: dict[str, Any], ids: dict[str, str]
    ) -> ProjectNode | None:
        name = row.get("name")
        manifest_path = row.get("manifest_path")
        if not name or not manifest_path:
            return None
        manifest = Path(str(manifest_path)).resolve(strict=False)
        try:
            root = manifest.parent.relative_to(workspace).as_posix() or "."
            manifest_rel = manifest.relative_to(workspace).as_posix()
        except ValueError:
            return None
        return ProjectNode(
            ids[str(name)], "cargo", root, manifest_rel, self.name, {"name": str(name)}
        )

    def _cargo_native_edges(
        self, row: dict[str, Any], source: str, ids: dict[str, str]
    ) -> list[ProjectEdge]:
        edges: list[ProjectEdge] = []
        for dep in row.get("dependencies") or ():
            target = ids.get(str(dep.get("name") or ""))
            if target is not None and target != source:
                edges.append(
                    ProjectEdge(source, target, "dependency", "native", self.name)
                )
        return edges

    def _cargo_native_graph(
        self, workspace: Path, packages: list[dict[str, Any]]
    ) -> tuple[list[ProjectNode], list[ProjectEdge]]:
        ids = {
            str(row["name"]): f"cargo:{row['name']}"
            for row in packages
            if row.get("name")
        }
        nodes: list[ProjectNode] = []
        edges: list[ProjectEdge] = []
        for row in packages:
            node = self._cargo_native_node(workspace, row, ids)
            if node is not None:
                nodes.append(node)
                edges.extend(self._cargo_native_edges(row, node.project_id, ids))
        return nodes, edges

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        cargo = shutil.which("cargo")
        if cargo is None:
            return self._fallback(
                workspace,
                "cargo executable unavailable; using Cargo.toml manifest graph",
            )
        completed, error = self._run_cargo_metadata(workspace, cargo)
        if completed is None:
            return self._fallback(workspace, error)
        packages, error = self._cargo_packages(completed.stdout)
        if packages is None:
            return self._fallback(workspace, error)
        nodes, edges = self._cargo_native_graph(workspace, packages)
        return ProjectGraphEvidence(self.name, tuple(nodes), tuple(edges))


class DeclaredProjectLinksProvider(ProjectGraphProvider):
    """Compose independent native project graphs with explicit repo-owned links.

    The file is intentionally small and declarative. ``source`` depends on
    ``target``. Shared inputs are represented as synthetic path-root projects so
    a change to e.g. ``openapi.yaml`` can flow to backend and frontend projects
    without teaching Hashmarks either ecosystem's build semantics.
    """

    name = "declared-project-links"
    filename = ".hashmarks-project-links.toml"

    def detect(self, workspace: Path) -> bool:
        return bool(self._manifest_paths(workspace, self.filename))

    def _read_links(
        self, workspace: Path
    ) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
        paths = self._manifest_paths(workspace, self.filename)
        if not paths:
            return None, ()
        path = paths[0]
        try:
            value = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            return None, (f"cannot parse {self.filename}: {exc}",)
        if not isinstance(value, dict):
            return None, (f"{self.filename} must contain a TOML object",)
        return value, ()

    def _declared_edges(
        self, value: dict[str, Any], warnings: list[str]
    ) -> list[ProjectEdge]:
        raw_links = value.get("link", [])
        if not isinstance(raw_links, list):
            warnings.append("project link entries must be [[link]] tables")
            return []
        edges: list[ProjectEdge] = []
        for index, row in enumerate(raw_links):
            edge = self._declared_edge(index, row, warnings)
            if edge is not None:
                edges.append(edge)
        return edges

    @staticmethod
    def _link_values(row: dict[str, Any]) -> tuple[str, str, str]:
        source = str(row.get("source") or "").strip()
        target = str(row.get("target") or "").strip()
        kind = str(row.get("kind") or "declared").strip() or "declared"
        return source, target, kind

    def _declared_edge(
        self, index: int, row: object, warnings: list[str]
    ) -> ProjectEdge | None:
        if not isinstance(row, dict):
            warnings.append(f"link[{index}] must be a table")
            return None
        source, target, kind = self._link_values(row)
        if len({source, target}) != 2 or "" in {source, target}:
            warnings.append(
                f"link[{index}] requires distinct non-empty source and target project ids"
            )
            return None
        return ProjectEdge(source, target, kind, "declared", self.name)

    def _shared_input(
        self, index: int, row: object, warnings: list[str]
    ) -> tuple[ProjectNode | None, list[ProjectEdge]]:
        if not isinstance(row, dict):
            warnings.append(f"shared_input[{index}] must be a table")
            return None, []
        raw_path = str(row.get("path") or "").strip()
        projects = row.get("projects", [])
        kind = str(row.get("kind") or "shared-input").strip() or "shared-input"
        try:
            from hashmarks.paths import normalize_relative_path

            rel = normalize_relative_path(raw_path, allow_root=False)
        except ValueError:
            warnings.append(f"shared_input[{index}] has invalid path: {raw_path!r}")
            return None, []
        project_ids = self._shared_projects(index, projects, warnings)
        if not project_ids:
            return None, []
        synthetic = f"shared-input:{rel}"
        node = ProjectNode(
            project_id=synthetic,
            kind="shared-input",
            root=rel,
            manifest=self.filename,
            producer=self.name,
            metadata={"path": rel, "freshness_manifests": [self.filename, rel]},
        )
        edges = [
            ProjectEdge(project_id, synthetic, kind, "declared", self.name)
            for project_id in project_ids
        ]
        return node, edges

    @staticmethod
    def _shared_projects(
        index: int, projects: object, warnings: list[str]
    ) -> tuple[str, ...]:
        valid_list = isinstance(projects, list) and all(
            isinstance(item, str) and item.strip() for item in projects
        )
        if not valid_list:
            warnings.append(
                f"shared_input[{index}] projects must be a non-empty string list"
            )
            return ()
        project_ids = tuple(
            dict.fromkeys(item.strip() for item in projects if item.strip())
        )
        if not project_ids:
            warnings.append(f"shared_input[{index}] projects must not be empty")
        return project_ids

    def _shared_inputs(
        self, value: dict[str, Any], warnings: list[str]
    ) -> tuple[list[ProjectNode], list[ProjectEdge]]:
        raw_inputs = value.get("shared_input", [])
        if not isinstance(raw_inputs, list):
            warnings.append("shared inputs must be [[shared_input]] tables")
            return [], []
        nodes: list[ProjectNode] = []
        edges: list[ProjectEdge] = []
        for index, row in enumerate(raw_inputs):
            node, row_edges = self._shared_input(index, row, warnings)
            if node is not None:
                nodes.append(node)
                edges.extend(row_edges)
        return nodes, edges

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        value, read_warnings = self._read_links(workspace)
        if value is None:
            return ProjectGraphEvidence(self.name, warnings=read_warnings)
        warnings = list(read_warnings)
        edges = self._declared_edges(value, warnings)
        nodes, shared_edges = self._shared_inputs(value, warnings)
        edges.extend(shared_edges)
        return ProjectGraphEvidence(
            self.name, tuple(nodes), tuple(edges), tuple(warnings)
        )


def default_project_graph_providers(
    manifest_finder: ManifestFinder | None = None,
) -> tuple[ProjectGraphProvider, ...]:
    return (
        NxProjectGraphProvider(manifest_finder),
        PantsProjectGraphProvider(manifest_finder),
        NpmProjectGraphProvider(manifest_finder),
        MavenProjectGraphProvider(manifest_finder),
        GradleProjectGraphProvider(manifest_finder),
        GoProjectGraphProvider(manifest_finder),
        CargoProjectGraphProvider(manifest_finder),
        DeclaredProjectLinksProvider(manifest_finder),
    )
