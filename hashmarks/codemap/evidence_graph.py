from __future__ import annotations

import json
import posixpath
import time
from pathlib import Path
from typing import Iterable

from ..paths import normalize_relative_path

from ..native_vitest import collect_vitest_vite_graph, local_vitest
from .model import EvidenceVisibility
from .repository_domains import is_test_path
from .scip_adapter import load_scip_json


class EvidenceGraphMixin:
    @staticmethod
    def _is_test_path(path: str) -> bool:
        # Cache ownership belongs to the lightweight pure repository-domain module,
        # never to a CodeMap instance or dynamically reloaded heavy module.
        return is_test_path(path)


    def _file_graph(self) -> dict[str, set[str]]:
        rows = [dict(row) for row in self.store.all_file_rows()]
        graph: dict[str, set[str]] = {str(row["path"]): set() for row in rows}
        language_by_path = {str(row["path"]): str(row.get("language") or "") for row in rows}
        module_paths: dict[str, list[str]] = {}
        for row in rows:
            module = str(row.get("module_name") or "")
            if module:
                module_paths.setdefault(module, []).append(str(row["path"]))
        known_paths = set(graph)

        for edge in self.store.all_edges("import"):
            source = str(edge["path"])
            target = str(edge["target"] or "").strip()
            if not target:
                continue
            language = language_by_path.get(source, "")
            if language == "python":
                if target.startswith("."):
                    continue
                candidate = target
                while candidate:
                    resolved = module_paths.get(candidate)
                    if resolved:
                        graph.setdefault(source, set()).update(resolved)
                        break
                    candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
                continue
            if language in {"javascript", "typescript"} and target.startswith("."):
                base = (Path(source).parent / target).as_posix()
                try:
                    normalized = normalize_relative_path(base, allow_root=False)
                except ValueError:
                    continue
                candidates = [normalized]
                for suffix in (".ts", ".tsx", ".js", ".jsx"):
                    candidates.append(normalized + suffix)
                for suffix in ("/index.ts", "/index.tsx", "/index.js", "/index.jsx"):
                    candidates.append(normalized.rstrip("/") + suffix)
                graph.setdefault(source, set()).update(candidate for candidate in candidates if candidate in known_paths)

        for edge in self._fresh_native_file_edges():
            source = str(edge["source"])
            target = str(edge["target"])
            if source in graph and target in graph:
                graph[source].add(target)
        return graph


    def _recent_changed_paths(self) -> set[str]:
        raw = self.store.meta("recent_changed_paths", "[]") or "[]"
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return set()
        return {str(item) for item in value if isinstance(item, str)} if isinstance(value, list) else set()


    def _python_reverse_levels(self, roots: set[str], *, max_depth: int) -> list[list[str]] | None:
        """Traverse Python reverse imports without materializing the repository graph.

        Returns ``None`` when the bounded fast path cannot prove semantic
        equivalence, causing callers to use the established full graph.
        """
        root_rows = [self._session_file_row(path) for path in sorted(roots)]
        if any(row is None or str(row.get("language") or "") != "python" or not str(row.get("module_name") or "") for row in root_rows):
            return None
        # Native file evidence can add cross-language/path relationships that
        # raw Python imports do not represent. Preserve existing semantics by
        # falling back whenever such evidence is currently authoritative.
        if any(row.get("kind") == "native-file" and row.get("fresh") for row in self._native_evidence_status()):
            return None

        seen = set(roots)
        frontier = set(roots)
        levels: list[list[str]] = []
        for _ in range(max_depth):
            rows = [self._session_file_row(path) for path in sorted(frontier)]
            modules_by_path = {
                path: str(row.get("module_name") or "")
                for path, row in zip(sorted(frontier), rows, strict=True)
                if row is not None and str(row.get("module_name") or "")
            }
            if len(modules_by_path) != len(frontier):
                return None
            candidates = self.store.python_import_candidates_for_modules(modules_by_path.values())
            raw_rows = [row for bucket in candidates.values() for row in bucket]
            targets = {str(row.get("target") or "") for row in raw_rows}
            prefixes = {
                prefix
                for target in targets
                for prefix in (".".join(target.split(".")[:i]) for i in range(1, len(target.split(".")) + 1))
                if prefix
            }
            resolved = self.store.module_paths_many(prefixes)
            target_paths = set(frontier)
            nxt: set[str] = set()
            for row in raw_rows:
                target = str(row.get("target") or "")
                parts = target.split(".")
                resolved_paths: list[str] = []
                for i in range(len(parts), 0, -1):
                    resolved_paths = resolved.get(".".join(parts[:i]), [])
                    if resolved_paths:
                        break
                if len(resolved_paths) == 1 and target_paths.intersection(resolved_paths):
                    source = str(row.get("path") or "")
                    if source and source not in seen:
                        nxt.add(source)
            if not nxt:
                break
            level = sorted(nxt)
            levels.append(level)
            seen.update(nxt)
            frontier = nxt
        return levels

    def _reverse_file_graph(self) -> dict[str, set[str]]:
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
        try:
            rel = normalize_relative_path(query, allow_root=False)
        except ValueError:
            rel = ""
        if rel and self._session_file_row(rel) is not None:
            return {rel}
        return {
            str(row["path"])
            for row in self.store.symbol(query)
            if EvidenceVisibility(str(row["evidence_visibility"])) is not EvidenceVisibility.DENY
        }


    def import_scip(self, path: str | Path) -> dict[str, object]:
        """Import compiler/language-server definitions and references from SCIP."""
        self._ensure_map_ready()
        raw_path = Path(path)
        if not raw_path.is_absolute():
            raw_path = self.workspace / raw_path
        producer, occurrences, warnings = load_scip_json(raw_path, workspace=self.workspace)
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
            if file_row is None or EvidenceVisibility(str(file_row["evidence_visibility"])) is EvidenceVisibility.DENY:
                skipped += 1
                continue
            if occurrence.definition:
                definitions.append({
                    "path": rel,
                    "symbol": occurrence.symbol,
                    "display_name": occurrence.display_name,
                    "line": occurrence.line,
                    "end_line": occurrence.end_line,
                })
                continue
            enclosing = None
            candidates = [
                row for row in self._session_symbols_for_path(rel)
                if int(row["start_line"]) <= occurrence.line <= int(row["end_line"])
            ]
            if candidates:
                candidates.sort(key=lambda row: (int(row["end_line"]) - int(row["start_line"]), -int(row["start_line"])))
                enclosing = str(candidates[0]["qualname"])
            edges.append({
                "path": rel,
                "source": enclosing,
                "target_symbol": occurrence.symbol,
                "target_name": occurrence.display_name,
                "line": occurrence.line,
            })
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


    def enrich_projects(self, providers: Iterable[str] | None = None) -> dict[str, object]:
        """Collect slower/native package graph evidence explicitly in the enrichment lane."""
        selected = None if providers is None else {str(value) for value in providers}
        results = []
        warnings: list[str] = []
        for provider in self.project_graph_providers:
            if selected is not None and provider.name not in selected:
                continue
            if not provider.detect(self.workspace):
                continue
            evidence = provider.collect(self.workspace)
            self.store.replace_project_graph(provider.name, evidence.nodes, evidence.edges)
            project_manifests = [
                manifest
                for node in evidence.nodes
                for manifest in (
                    node.manifest,
                    *(node.metadata.get("freshness_manifests") or ()),
                )
            ]
            # Declared links can contain only edges and therefore no provider-
            # owned nodes.  The declaration file still owns that topology and
            # must always participate in freshness even for links-only graphs.
            if provider.name == "declared-project-links":
                project_manifests.insert(0, ".hashmarks-project-links.toml")
            self._record_evidence_snapshot(
                "project",
                provider.name,
                bind_generation=(provider.name in {"go-list", "nx-project-graph", "pants-target-graph"}),
                manifests=project_manifests,
            )
            results.append({
                "producer": evidence.producer,
                "projects": len(evidence.nodes),
                "edges": len(evidence.edges),
            })
            warnings.extend(evidence.warnings)
        if selected is None or self.typescript_resolver.name in selected:
            if self.typescript_resolver.detect(self.workspace):
                ts = self.typescript_resolver.collect(self.workspace)
                self.store.replace_native_file_edges(self.typescript_resolver.name, ts.edges)
                self._record_evidence_snapshot(
                    "native-file",
                    ts.producer,
                    bind_generation=True,
                    manifests=("tsconfig.json",),
                )
                results.append({"producer": ts.producer, "file_edges": len(ts.edges)})
                warnings.extend(ts.warnings)
        if selected is None or self.pyright_type_server.name in selected:
            if self.pyright_type_server.detect(self.workspace):
                python_sources = [
                    str(row["path"])
                    for row in self.store.all_file_rows()
                    if str(row.get("language") or "") == "python"
                ]
                pyright = self.pyright_type_server.collect(self.workspace, python_sources)
                self.store.replace_native_file_edges(self.pyright_type_server.name, pyright.edges)
                self._record_evidence_snapshot(
                    "native-file",
                    pyright.producer,
                    bind_generation=True,
                    manifests=("pyrightconfig.json", "pyproject.toml"),
                )
                results.append({
                    "producer": pyright.producer,
                    "file_edges": len(pyright.edges),
                    "protocol_version": pyright.protocol_version,
                })
                warnings.extend(pyright.warnings)
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
                            "vitest.config.ts", "vitest.config.js", "vitest.config.mts", "vitest.config.mjs",
                            "vite.config.ts", "vite.config.js", "vite.config.mts", "vite.config.mjs",
                        ),
                    )
                    results.append({"producer": vite.producer, "file_edges": len(vite.edges)})
                warnings.extend(vite.warnings)
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
