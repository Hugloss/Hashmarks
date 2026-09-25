from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .model import EvidenceVisibility
from .repository_domains import is_test_path
from .scip_adapter import load_scip_json

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .engine import CodeMap


class EvidenceGraphMixin:
    @staticmethod
    def _is_test_path(path: str) -> bool:
        # Cache ownership belongs to the lightweight pure repository-domain module,
        # never to a CodeMap instance or dynamically reloaded heavy module.
        return is_test_path(path)

    @staticmethod
    def _python_file_graph_targets(
        target: str, module_paths: dict[str, list[str]]
    ) -> set[str]:
        if target.startswith("."):
            return set()
        candidate = target
        while candidate:
            resolved = module_paths.get(candidate)
            if resolved:
                return set(resolved)
            candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
        return set()

    @staticmethod
    def _script_file_graph_targets(
        source: str,
        target: str,
        language: str,
        known_paths: set[str],
    ) -> set[str]:
        if language not in {"javascript", "typescript"} or not target.startswith("."):
            return set()
        base = (Path(source).parent / target).as_posix()
        try:
            normalized = normalize_relative_path(base, allow_root=False)
        except ValueError:
            return set()
        candidates = [
            normalized,
            *(normalized + suffix for suffix in (".ts", ".tsx", ".js", ".jsx")),
            *(
                normalized.rstrip("/") + suffix
                for suffix in ("/index.ts", "/index.tsx", "/index.js", "/index.jsx")
            ),
        ]
        return {candidate for candidate in candidates if candidate in known_paths}

    def _file_graph(self) -> dict[str, set[str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rows = [dict(row) for row in self.store.all_file_rows()]
        graph: dict[str, set[str]] = {str(row["path"]): set() for row in rows}
        language_by_path = {
            str(row["path"]): str(row.get("language") or "") for row in rows
        }
        module_paths: dict[str, list[str]] = {}
        for row in rows:
            module = str(row.get("module_name") or "")
            module_paths.setdefault(module, []).append(str(row["path"]))
        known_paths = set(graph)

        for edge in self.store.all_edges("import"):
            source = str(edge["path"])
            target = str(edge["target"] or "").strip()
            if not target:
                continue
            language = language_by_path.get(source, "")
            if language == "python":
                targets = self._python_file_graph_targets(target, module_paths)
            else:
                targets = self._script_file_graph_targets(
                    source, target, language, known_paths
                )
            graph.setdefault(source, set()).update(targets)

        for edge in self._fresh_native_file_edges():
            source = str(edge["source"])
            target = str(edge["target"])
            if source in graph and target in graph:
                graph[source].add(target)
        return graph

    def _recent_changed_paths(self) -> set[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        raw = self.store.meta("recent_changed_paths", "[]") or "[]"
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return set()
        return (
            {str(item) for item in value if isinstance(item, str)}
            if isinstance(value, list)
            else set()
        )

    @staticmethod
    def _longest_module_paths(target: str, resolved: dict[str, list[str]]) -> list[str]:
        parts = target.split(".")
        for index in range(len(parts), 0, -1):
            paths = resolved.get(".".join(parts[:index]), [])
            if paths:
                return paths
        return []

    def _python_reverse_frontier(
        self, frontier: set[str], seen: set[str]
    ) -> set[str] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        ordered_frontier = sorted(frontier)
        rows = [self._session_file_row(path) for path in ordered_frontier]
        modules_by_path = {
            path: str(row.get("module_name") or "")
            for path, row in zip(ordered_frontier, rows, strict=True)
            if row is not None and str(row.get("module_name") or "")
        }
        if len(modules_by_path) != len(frontier):
            return None
        candidates = self.store.python_import_candidates_for_modules(
            modules_by_path.values()
        )
        raw_rows = [row for bucket in candidates.values() for row in bucket]
        prefixes = {
            prefix
            for row in raw_rows
            for prefix in (
                ".".join(str(row.get("target") or "").split(".")[:index])
                for index in range(1, len(str(row.get("target") or "").split(".")) + 1)
            )
            if prefix
        }
        resolved = self.store.module_paths_many(prefixes)
        nxt: set[str] = set()
        for row in raw_rows:
            paths = self._longest_module_paths(str(row.get("target") or ""), resolved)
            if len(paths) == 1 and frontier.intersection(paths):
                source = str(row.get("path") or "")
                if source and source not in seen:
                    nxt.add(source)
        return nxt

    def _python_reverse_levels(
        self, roots: set[str], *, max_depth: int
    ) -> list[list[str]] | None:
        """Traverse Python reverse imports without materializing the repository graph.

        Returns ``None`` when the bounded fast path cannot prove semantic
        equivalence, causing callers to use the established full graph.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        root_rows = [self._session_file_row(path) for path in sorted(roots)]
        if any(
            row is None
            or str(row.get("language") or "") != "python"
            or not str(row.get("module_name") or "")
            for row in root_rows
        ):
            return None
        # Native file evidence can add cross-language/path relationships that
        # raw Python imports do not represent. Preserve existing semantics by
        # falling back whenever such evidence is currently authoritative.
        if any(
            row.get("kind") == "native-file" and row.get("fresh")
            for row in self._native_evidence_status()
        ):
            return None

        seen = set(roots)
        frontier = set(roots)
        levels: list[list[str]] = []
        for _ in range(max_depth):
            nxt = self._python_reverse_frontier(frontier, seen)
            if nxt is None:
                return None
            if not nxt:
                break
            level = sorted(nxt)
            levels.append(level)
            seen.update(nxt)
            frontier = nxt
        return levels

    def _reverse_file_graph(self) -> dict[str, set[str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        generation = self.store.generation()
        cached = self._reverse_file_graph_cache
        if cached is not None and cached[0] == generation:
            return cached[1]
        reverse: dict[str, set[str]] = {}
        for source, targets in self._file_graph().items():
            for target in targets:
                reverse.setdefault(target, set()).add(source)
        self._reverse_file_graph_cache = (generation, reverse)
        return reverse

    def _query_paths(self, query: str) -> set[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        try:
            rel = normalize_relative_path(query, allow_root=False)
        except ValueError:
            rel = ""
        if rel and self._session_file_row(rel) is not None:
            return {rel}
        return {
            str(row["path"])
            for row in self.store.symbol(query)
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        }

    def import_scip(self, path: str | Path) -> dict[str, object]:
        """Import compiler/language-server definitions and references from SCIP."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        raw_path = Path(path)
        if not raw_path.is_absolute():
            raw_path = self.workspace / raw_path
        producer, occurrences, warnings = load_scip_json(
            raw_path, workspace=self.workspace
        )
        definitions: list[dict[str, object]] = []
        edges: list[dict[str, object]] = []
        skipped = 0
        for occurrence in occurrences:
            try:
                rel = normalize_relative_path(occurrence.path, allow_root=False)
            except ValueError:
                skipped += 1
                continue
            file_row = self._session_file_row(rel)
            if (
                file_row is None
                or EvidenceVisibility(str(file_row["evidence_visibility"]))
                is EvidenceVisibility.DENY
            ):
                skipped += 1
                continue
            if occurrence.definition:
                definitions.append(
                    {
                        "path": rel,
                        "symbol": occurrence.symbol,
                        "display_name": occurrence.display_name,
                        "line": occurrence.line,
                        "end_line": occurrence.end_line,
                    }
                )
                continue
            enclosing = None
            candidates = [
                row
                for row in self._session_symbols_for_path(rel)
                if int(row["start_line"]) <= occurrence.line <= int(row["end_line"])
            ]
            if candidates:
                candidates.sort(
                    key=lambda row: (
                        int(row["end_line"]) - int(row["start_line"]),
                        -int(row["start_line"]),
                    )
                )
                enclosing = str(candidates[0]["qualname"])
            edges.append(
                {
                    "path": rel,
                    "source": enclosing,
                    "target_symbol": occurrence.symbol,
                    "target_name": occurrence.display_name,
                    "line": occurrence.line,
                }
            )
        self.store.replace_native_occurrences(producer, definitions, edges)
        self._record_evidence_snapshot("scip", producer, bind_generation=True)
        self.store.set_meta("scip_last_import_unix", str(time.time()))
        return {
            "schema": "hashmarks.scip-import.v1",
            "producer": producer,
            "definitions": len(definitions),
            "references": len(edges),
            "skipped": skipped,
            "warnings": list(warnings),
        }

    @staticmethod
    def _project_node_value(node: object, name: str) -> object:
        if isinstance(node, dict):
            return node.get(name)
        return getattr(node, name, None)

    def _project_node_admitted(self, node: object) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        manifest = str(self._project_node_value(node, "manifest") or "")
        metadata_raw = self._project_node_value(node, "metadata")
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        freshness = metadata.get("freshness_manifests") or ()
        manifests = (manifest, *(str(value) for value in freshness))
        if any(self._visible_repository_file(value) is None for value in manifests):
            return False
        root = str(self._project_node_value(node, "root") or "").strip("/")
        if root in {"", "."}:
            return True
        return self._repository_scope_has_visible_file(root)

    def _admitted_external_project_ids(self, producer: str) -> set[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return {
            str(row.get("project_id") or "")
            for row in self._fresh_project_nodes()
            if str(row.get("producer") or "") != producer
            and self._project_node_admitted(row)
        }

    def _admit_project_graph(
        self,
        provider_name: str,
        nodes: tuple[object, ...],
        edges: tuple[object, ...],
    ) -> tuple[tuple[object, ...], tuple[object, ...], int, int]:
        admitted_nodes = tuple(node for node in nodes if self._project_node_admitted(node))
        admitted_ids = {
            str(self._project_node_value(node, "project_id") or "")
            for node in admitted_nodes
        }
        known_ids = admitted_ids | self._admitted_external_project_ids(provider_name)
        admitted_edges = tuple(
            edge
            for edge in edges
            if str(self._project_node_value(edge, "source") or "") in known_ids
            and str(self._project_node_value(edge, "target") or "") in known_ids
        )
        return (
            admitted_nodes,
            admitted_edges,
            len(nodes) - len(admitted_nodes),
            len(edges) - len(admitted_edges),
        )

    def _enrich_project_graphs(
        self,
        selected: set[str] | None,
        results: list[dict[str, object]],
        warnings: list[str],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for provider in self.project_graph_providers:
            if selected is not None and provider.name not in selected:
                continue
            if not provider.detect(self.workspace):
                continue
            evidence = provider.collect(self.workspace)
            nodes, edges, filtered_nodes, filtered_edges = self._admit_project_graph(
                provider.name,
                evidence.nodes,
                evidence.edges,
            )
            if (
                provider.name == "declared-project-links"
                and self._visible_repository_file(".hashmarks-project-links.toml")
                is None
            ):
                nodes = ()
                edges = ()
                filtered_nodes = len(evidence.nodes)
                filtered_edges = len(evidence.edges)
            self.store.replace_project_graph(provider.name, nodes, edges)
            project_manifests = [
                manifest
                for node in nodes
                for manifest in (
                    node.manifest,
                    *(node.metadata.get("freshness_manifests") or ()),
                )
            ]
            # Declared links can contain only edges and therefore no provider-
            # owned nodes. The declaration file still owns that topology.
            if provider.name == "declared-project-links":
                project_manifests.insert(0, ".hashmarks-project-links.toml")
            self._record_evidence_snapshot(
                "project",
                provider.name,
                bind_generation=(
                    provider.name
                    in {"go-list", "nx-project-graph", "pants-target-graph"}
                ),
                manifests=project_manifests,
            )
            results.append(
                {
                    "producer": evidence.producer,
                    "projects": len(nodes),
                    "edges": len(edges),
                }
            )
            warnings.extend(evidence.warnings)
            if filtered_nodes or filtered_edges:
                warnings.append(
                    f"{provider.name}: filtered project evidence outside repository admission "
                    f"(projects={filtered_nodes}, edges={filtered_edges})"
                )

    def _enrich_typescript_graph(
        self,
        selected: set[str] | None,
        results: list[dict[str, object]],
        warnings: list[str],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if selected is None or self.typescript_resolver.name in selected:
            if self.typescript_resolver.detect(self.workspace):
                ts = self.typescript_resolver.collect(self.workspace)
                self.store.replace_native_file_edges(
                    self.typescript_resolver.name, ts.edges
                )
                self._record_evidence_snapshot(
                    "native-file",
                    ts.producer,
                    bind_generation=True,
                    manifests=("tsconfig.json",),
                )
                results.append({"producer": ts.producer, "file_edges": len(ts.edges)})
                warnings.extend(ts.warnings)

    def _enrich_pyright_graph(
        self,
        selected: set[str] | None,
        results: list[dict[str, object]],
        warnings: list[str],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if selected is None or self.pyright_type_server.name in selected:
            if self.pyright_type_server.detect(self.workspace):
                python_sources = [
                    str(row["path"])
                    for row in self.store.all_file_rows()
                    if str(row.get("language") or "") == "python"
                ]
                pyright = self.pyright_type_server.collect(
                    self.workspace, python_sources
                )
                self.store.replace_native_file_edges(
                    self.pyright_type_server.name, pyright.edges
                )
                self._record_evidence_snapshot(
                    "native-file",
                    pyright.producer,
                    bind_generation=True,
                    manifests=("pyrightconfig.json", "pyproject.toml"),
                )
                results.append(
                    {
                        "producer": pyright.producer,
                        "file_edges": len(pyright.edges),
                        "protocol_version": pyright.protocol_version,
                    }
                )
                warnings.extend(pyright.warnings)

    def _enrich_vitest_graph(
        self,
        selected: set[str] | None,
        results: list[dict[str, object]],
        warnings: list[str],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if selected is None or "vitest-vite" in selected:
            # Preserve the historical monkeypatch seam on codemap.engine while
            # implementation ownership lives in this mixin.
            from . import engine as engine_module

            if engine_module.local_vitest(self.workspace) is not None:
                vite = engine_module.collect_vitest_vite_graph(self.workspace)
                if vite.command or vite.edges:
                    self.store.replace_native_file_edges(vite.producer, vite.edges)
                    self._record_evidence_snapshot(
                        "native-file",
                        vite.producer,
                        bind_generation=True,
                        manifests=(
                            "package.json",
                            "vitest.config.ts",
                            "vitest.config.js",
                            "vitest.config.mts",
                            "vitest.config.mjs",
                            "vite.config.ts",
                            "vite.config.js",
                            "vite.config.mts",
                            "vite.config.mjs",
                        ),
                    )
                    results.append(
                        {"producer": vite.producer, "file_edges": len(vite.edges)}
                    )
                warnings.extend(vite.warnings)

    def enrich_projects(
        self, providers: Iterable[str] | None = None
    ) -> dict[str, object]:
        """Collect slower/native package graph evidence explicitly in the enrichment lane."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        selected = None if providers is None else {str(value) for value in providers}
        results: list[dict[str, object]] = []
        warnings: list[str] = []
        self._enrich_project_graphs(selected, results, warnings)
        self._enrich_typescript_graph(selected, results, warnings)
        self._enrich_pyright_graph(selected, results, warnings)
        self._enrich_vitest_graph(selected, results, warnings)
        self.store.set_meta("project_graph_last_sync_unix", str(time.time()))
        self._reverse_file_graph_cache = None
        return {
            "schema": "hashmarks.codemap-project-enrichment.v1",
            "providers": results,
            "projects": self._fresh_project_nodes(),
            "edges": self._fresh_project_edges(),
            "native_file_edges": self._fresh_native_file_edges(),
            "warnings": list(dict.fromkeys(warnings)),
        }
