from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path

from .decision_session import ReadScopeOwner, decision_scoped
from .import_resolution import (
    python_import_spelling,
    python_module_prefixes,
    unique_python_module_owner,
)
from .model import EvidenceVisibility
from .providers import source_grammar
from .repository_domains import is_test_path
from .signature_preview import signature_disclosure

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .decision_session import DecisionScope
    from .import_resolution import PythonImportSites, RepositoryImports
    from .native_evidence import RepositoryNativeEvidence


class RepositoryRelationships(ReadScopeOwner):
    """Own repository-only relationship queries and their generation-bound reuse."""

    def __init__(
        self,
        imports: RepositoryImports,
        native: RepositoryNativeEvidence,
    ) -> None:
        if imports.reads is not native.reads:
            raise ValueError(
                "Import and native evidence must share one repository read scope"
            )
        self.source = imports.source
        self._reads = imports.reads
        self.store = self.source.store
        self.imports = imports
        self.native = native
        self.workspace = self.source.workspace
        self._reverse_file_graph_cache: (
            tuple[int, bytes, dict[str, set[str]]] | None
        ) = None

    @property
    def reads(self) -> DecisionScope:
        return self._reads

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
        rows = {row["path"]: row for row in self.store.all_file_rows()}
        graph: dict[str, set[str]] = {path: set() for path in rows}
        module_paths: dict[str, list[str]] = {}
        for path, row in rows.items():
            if row["language"] == "python" and row["module_name"]:
                module_paths.setdefault(row["module_name"], []).append(path)
        known_paths = set(graph)

        for edge in self.store.all_edges("import"):
            source = str(edge["path"])
            target = str(edge["target"] or "").strip()
            if not target or source not in rows:
                continue
            language = rows[source]["language"]
            if language == "python":
                spelling = python_import_spelling(
                    source, rows[source]["module_name"] or "", target
                )
                owner = unique_python_module_owner(
                    python_module_prefixes(spelling), module_paths.get
                )
                targets = {owner} if owner is not None else set()
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

    def _python_import_dependents(
        self, imports: set[tuple[str, str]]
    ) -> dict[str, set[str]]:
        prefixes = {p for _, target in imports for p in python_module_prefixes(target)}
        resolved = self.store.module_paths_many(prefixes)
        reverse: dict[str, set[str]] = {}
        for source, target in imports:
            if owner := unique_python_module_owner(
                python_module_prefixes(target), resolved.get
            ):
                reverse.setdefault(owner, set()).add(source)
        return reverse

    def _python_reverse_frontier(
        self,
        frontier: set[str],
        seen: set[str],
        scanned_packages: set[str],
        relative: dict[str, set[str]],
    ) -> set[str] | None:
        rows = self.reads.file_rows(frontier)
        modules_by_path = {
            path: str(row.get("module_name") or "")
            for path, row in rows.items()
            if row.get("module_name")
        }
        if len(modules_by_path) != len(frontier):
            return None
        candidates = self.store.python_import_candidates_for_modules(
            modules_by_path.values()
        )
        absolute = self._python_import_dependents(
            {
                (row["path"], row["target"])
                for bucket in candidates.values()
                for row in bucket
            }
        )
        # A relative import cannot leave its top-level package. Qualify its
        # indexed spellings once when the traversal first enters that package.
        packages = {
            name.partition(".")[0] for name in modules_by_path.values()
        } - scanned_packages
        if packages:
            relative.update(
                self._python_import_dependents(
                    {
                        (
                            row["path"],
                            python_import_spelling(
                                row["path"], row["module_name"], row["target"]
                            ),
                        )
                        for row in self.store.relative_python_imports(packages)
                    }
                )
            )
            scanned_packages.update(packages)
        return {
            source
            for path in frontier
            for reverse in (absolute, relative)
            for source in reverse.get(path, ())
            if source not in seen
        }

    def _python_reverse_levels(
        self, roots: set[str], *, max_depth: int
    ) -> list[list[str]] | None:
        """Traverse Python reverse imports without materializing the repository graph.

        Returns ``None`` when the bounded fast path cannot prove semantic
        equivalence, causing callers to use the established full graph.
        """
        root_rows = self.reads.file_rows(roots)
        if len(root_rows) != len(roots) or any(
            str(row.get("language") or "") != "python"
            or not str(row.get("module_name") or "")
            for row in root_rows.values()
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
        scanned_packages: set[str] = set()
        relative: dict[str, set[str]] = {}
        for _ in range(max_depth):
            nxt = self._python_reverse_frontier(
                frontier, seen, scanned_packages, relative
            )
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
            for row in self.store.visible_symbol_candidates(query, limit=50)
        }

    def _resolve_edge(
        self, edge: dict, import_sites: dict[str, PythonImportSites]
    ) -> dict:
        value = dict(edge)
        path = str(value.get("path", ""))
        target = str(value.get("target", ""))
        resolved_paths = (
            self.imports._resolve_import_paths(path, target)
            if value.get("kind") == "import"
            else []
        )
        if value.get("kind") == "import" and source_grammar(path) == "python":
            if path not in import_sites:
                import_sites[path] = self.imports.python_import_sites(path)
            site = import_sites[path].get((value["line"], target))
            candidates, value["symbol_resolution"] = (
                self.imports.python_dependency_symbols(path, target, site)
            )
        else:
            short = target.rsplit(".", 1)[-1]
            candidates = self.store.symbols_named(short, limit=9, visible_only=True)
        resolved_symbols = [
            {
                "path": row["path"],
                "qualname": row["qualname"],
                **signature_disclosure(str(row["path"]), str(row["signature"])),
            }
            for row in candidates[:8]
        ]
        value["resolved_paths"] = resolved_paths
        value["resolved_symbols"] = resolved_symbols
        if len(candidates) > 8:
            value["resolved_symbols_truncated"] = True
        return value

    @decision_scoped
    def deps(self, query: str) -> dict[str, object]:
        self.reads.ready()
        import_sites: dict[str, PythonImportSites] = {}
        matches = self.store.visible_symbol_candidates(query, limit=51)
        if matches:
            visible_matches = matches[:50]
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
                "matches_truncated": len(matches) > len(visible_matches),
                **self.reads.freshness_fields(),
                "edges": [self._resolve_edge(row, import_sites) for row in rows],
                "native_edges": native_rows,
                "native_file_edges": [
                    row
                    for path in dict.fromkeys(
                        str(match["path"]) for match in visible_matches
                    )
                    for row in self.native._fresh_native_file_edges_from(path)
                ],
            }
        if self.store.has_symbol(query):
            raise PermissionError(f"symbol exists but agent context is denied: {query}")
        rel = normalize_relative_path(query, allow_root=False)
        self.source.ensure_current(rel)
        member = self.reads.file_row(rel)
        if member and member["evidence_visibility"] == EvidenceVisibility.DENY.value:
            raise PermissionError(
                f"repository evidence denied by context policy: {rel}"
            )
        return {
            "schema": "hashmarks.deps.v1",
            "query": query,
            **self.reads.freshness_fields(),
            "edges": [
                self._resolve_edge(row, import_sites)
                for row in self.store.edges_from(rel)
            ],
            "native_edges": self.native._fresh_native_edges_from(rel),
            "native_file_edges": self.native._fresh_native_file_edges_from(rel),
        }

    @decision_scoped
    def refs(self, query: str) -> dict[str, object]:
        self.reads.ready()
        rows = self.store.refs(query, limit=101, visible_only=True)
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
            "references": rows[:100],
            "references_truncated": len(rows) > 100,
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
