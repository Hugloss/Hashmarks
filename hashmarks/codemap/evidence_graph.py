from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path

from .decision_session import ReadScopeOwner, decision_scoped
from .model import EvidenceVisibility
from .repository_domains import is_test_path

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .decision_session import DecisionScope
    from .import_resolution import RepositoryImports
    from .native_evidence import RepositoryNativeEvidence
    from .repository_index_store import WorkspaceMapStore
    from .repository_source import RepositorySource


class RepositoryRelationships(ReadScopeOwner):
    """Own repository-only relationship queries and their generation-bound reuse."""

    def __init__(
        self,
        source: RepositorySource,
        reads: DecisionScope,
        store: WorkspaceMapStore,
        imports: RepositoryImports,
        native: RepositoryNativeEvidence,
    ) -> None:
        self.source = source
        self._reads = reads
        self.store = store
        self.imports = imports
        self.native = native
        self.workspace = source.workspace
        self._reverse_file_graph_cache: (
            tuple[int, bytes, dict[str, set[str]]] | None
        ) = None

    @property
    def reads(self) -> DecisionScope:
        return self._reads

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

    def _file_graph(
        self, *, native_edges: Sequence[Mapping[str, object]]
    ) -> dict[str, set[str]]:
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

        for edge in native_edges:
            source = str(edge["source"])
            target = str(edge["target"])
            if source in graph and target in graph:
                graph[source].add(target)
        return graph

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
        ordered_frontier = sorted(frontier)
        rows = [self.reads.file_row(path) for path in ordered_frontier]
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
        root_rows = [self.reads.file_row(path) for path in sorted(roots)]
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
            for row in self.native.status()
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
        generation = self.store.generation()
        # Source/manifest drift can disqualify native edges without publishing
        # another index generation. Qualify before a hit and build from that
        # same observed input, rather than letting indexing clear this cache.
        native_edges = self.native._fresh_native_file_edges()
        native_basis = hashlib.sha256(
            json.dumps(
                native_edges,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).digest()
        cached = self._reverse_file_graph_cache
        if cached is not None and cached[0] == generation and cached[1] == native_basis:
            return cached[2]
        reverse: dict[str, set[str]] = {}
        for source, targets in self._file_graph(native_edges=native_edges).items():
            for target in targets:
                reverse.setdefault(target, set()).add(source)
        self._reverse_file_graph_cache = (generation, native_basis, reverse)
        return reverse

    def _query_paths(self, query: str) -> set[str]:
        try:
            rel = normalize_relative_path(query, allow_root=False)
        except ValueError:
            rel = ""
        if rel and self.reads.file_row(rel) is not None:
            return {rel}
        return {
            str(row["path"])
            for row in self.store.symbol(query)
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        }

    def _resolve_edge(self, edge: dict) -> dict:
        value = dict(edge)
        target = str(value.get("target", ""))
        resolved_paths = (
            self.imports._resolve_import_paths(str(value.get("path", "")), target)
            if value.get("kind") == "import"
            else []
        )
        short = target.rsplit(".", 1)[-1]
        resolved_symbols = [
            {
                "path": row["path"],
                "qualname": row["qualname"],
                "signature": row["signature"],
            }
            for row in self.store.symbols_named(short, limit=8)
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        value["resolved_paths"] = resolved_paths
        value["resolved_symbols"] = resolved_symbols
        return value

    @decision_scoped
    def deps(self, query: str) -> dict[str, object]:
        self.reads.ready()
        matches = self.store.symbol(query)
        if matches:
            visible_matches = [
                match
                for match in matches
                if EvidenceVisibility(str(match["evidence_visibility"]))
                is not EvidenceVisibility.DENY
            ]
            edge_map = self.reads.edges_from_many(
                [
                    (str(match["path"]), str(match["qualname"]))
                    for match in visible_matches
                ],
                limit_per_seed=100,
            )
            rows = [
                row
                for match in visible_matches
                for row in edge_map.get(
                    (str(match["path"]), str(match["qualname"])), ()
                )
            ]
            native_rows = [
                row
                for match in visible_matches
                for row in self.native._fresh_native_edges_from(
                    str(match["path"]), str(match["qualname"])
                )
            ]
            return {
                "schema": "hashmarks.deps.v1",
                "query": query,
                **self.reads.freshness_fields(),
                "edges": [self._resolve_edge(row) for row in rows],
                "native_edges": native_rows,
                "native_file_edges": [
                    row
                    for match in matches
                    for row in self.native._fresh_native_file_edges_from(
                        str(match["path"])
                    )
                ],
            }
        rel = normalize_relative_path(query, allow_root=False)
        self.source.ensure_current(rel)
        return {
            "schema": "hashmarks.deps.v1",
            "query": query,
            **self.reads.freshness_fields(),
            "edges": [self._resolve_edge(row) for row in self.store.edges_from(rel)],
            "native_edges": self.native._fresh_native_edges_from(rel),
            "native_file_edges": self.native._fresh_native_file_edges_from(rel),
        }

    @decision_scoped
    def refs(self, query: str) -> dict[str, object]:
        self.reads.ready()
        rows = [
            row
            for row in self.store.refs(query)
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        native_rows = self.native._fresh_native_refs(query)
        native_file_rows = self.reads.file_rows(str(row["path"]) for row in native_rows)
        native = [
            row
            for row in native_rows
            if (mapped := native_file_rows.get(str(row["path"]))) is not None
            and EvidenceVisibility(str(mapped["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        return {
            "schema": "hashmarks.refs.v1",
            "query": query,
            **self.reads.freshness_fields(),
            "references": rows,
            "native_references": native,
        }

    @operation_response("projects")
    @decision_scoped
    def projects(self) -> dict[str, object]:
        self.reads.ready()
        return {
            "schema": operation_schema("projects"),
            **self.reads.freshness_fields(),
            "projects": self.native._fresh_project_nodes(),
            "edges": self.native._fresh_project_edges(),
            "native_file_edges": self.native._fresh_native_file_edges(),
            "last_enriched_unix": None
            if self.store.meta("project_graph_last_sync_unix") is None
            else float(self.store.meta("project_graph_last_sync_unix") or 0),
        }

    def _affected_roots(self, query: str) -> set[str]:
        roots = self._query_paths(query)
        if roots:
            return roots
        try:
            rel_query = normalize_relative_path(query, allow_root=False)
        except ValueError:
            rel_query = None
        candidate = None if rel_query is None else self.workspace / rel_query
        if (
            rel_query is not None
            and candidate is not None
            and candidate.is_file()
            and not candidate.is_symlink()
        ):
            return {rel_query}
        raise KeyError(f"path or symbol not found: {query}")

    def _affected_levels(
        self,
        roots: set[str],
        *,
        max_depth: int,
    ) -> tuple[list[list[str]], set[str]]:
        levels = self._python_reverse_levels(roots, max_depth=max_depth)
        if levels is not None:
            seen = set(roots)
            for level in levels:
                seen.update(level)
            return levels, seen

        reverse = self._reverse_file_graph()

        seen = set(roots)
        frontier = set(roots)
        resolved: list[list[str]] = []
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for path in frontier:
                next_frontier.update(reverse.get(path, ()))
            next_frontier -= seen
            if not next_frontier:
                break
            resolved.append(sorted(next_frontier))
            seen.update(next_frontier)
            frontier = next_frontier
        return resolved, seen

    @operation_response("affected")
    @decision_scoped
    def affected(self, query: str, *, max_depth: int = 12) -> dict[str, object]:
        self.reads.ready()
        roots = self._affected_roots(query)
        levels, seen = self._affected_levels(roots, max_depth=max_depth)
        affected = sorted(seen - roots)
        tests = [path for path in affected if is_test_path(path)]
        root_projects = {
            str(project["project_id"])
            for path in roots
            for project in self.native._fresh_projects_for_path(path)[:1]
        }
        impacted_projects = (
            self.native._fresh_project_dependents(root_projects, max_depth=max_depth)
            if root_projects
            else set()
        )
        return {
            "schema": operation_schema("affected"),
            "query": query,
            **self.reads.freshness_fields(),
            "roots": sorted(roots),
            "affected_files": affected,
            "tests": tests,
            "levels": levels,
            "root_projects": sorted(root_projects),
            "affected_projects": sorted(impacted_projects - root_projects),
            "evidence": "static import graph plus retained native/manifest project graph when available; advisory and conservative",
        }

    @operation_response("tests")
    @decision_scoped
    def tests(self, query: str, *, max_depth: int = 12) -> dict[str, object]:
        value = self.affected(query, max_depth=max_depth)
        return {
            "schema": operation_schema("tests"),
            "query": query,
            "generation": value["generation"],
            "identity_generation": value["identity_generation"],
            "stale": value["stale"],
            "roots": value["roots"],
            "tests": value["tests"],
            "affected_files": value["affected_files"],
            "evidence": value["evidence"],
        }
