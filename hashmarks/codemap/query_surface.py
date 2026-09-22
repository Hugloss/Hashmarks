from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .model import EvidenceVisibility
from .python_ast import estimate_tokens
from .query_primitives import _WORD_RE
from .repository_domains import RepositoryDomain, classify_repository_path

if TYPE_CHECKING:
    from .engine import CodeMap


_CHANGE_IMPACT_SURFACES = (
    "implementation",
    "contract",
    "verification",
    "build_config",
    "orientation",
    "other",
)


def _instruction_scope(authority: str) -> str:
    parent = Path(authority).parent.as_posix()
    return "." if parent in {"", "."} else parent


def _instruction_applies(authority: str, target: str) -> bool:
    scope = _instruction_scope(authority)
    return scope == "." or target == scope or target.startswith(scope + "/")


def _instruction_specificity(authority: str) -> int:
    scope = _instruction_scope(authority)
    return 0 if scope == "." else len(Path(scope).parts)


def _change_impact_roles(path: str) -> tuple[str, ...]:
    domains = set(classify_repository_path(path))
    roles: list[str] = []
    if RepositoryDomain.TEST in domains:
        roles.append("verification")
    if domains & {RepositoryDomain.CONTRACT, RepositoryDomain.OWNERSHIP}:
        roles.append("contract")
    if domains & {
        RepositoryDomain.BUILD,
        RepositoryDomain.CONFIG,
        RepositoryDomain.PLAN,
        RepositoryDomain.SCRIPT,
    }:
        roles.append("build_config")
    if domains & {RepositoryDomain.ARCHITECTURE, RepositoryDomain.DOC}:
        roles.append("orientation")
    if RepositoryDomain.SOURCE in domains and RepositoryDomain.TEST not in domains:
        roles.append("implementation")
    return tuple(dict.fromkeys(roles)) or ("other",)


@dataclass
class _ChangeImpactAccumulator:
    roots: set[str]
    limit_per_surface: int
    surfaces: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: {key: [] for key in _CHANGE_IMPACT_SURFACES}
    )
    seen: set[tuple[str, str]] = field(default_factory=set)

    def add(
        self,
        path: str,
        *,
        depth: int,
        provenance: str,
        relation: str | None = None,
    ) -> None:
        if path in self.roots:
            return
        domains = [domain.value for domain in classify_repository_path(path)]
        for role in _change_impact_roles(path):
            key = (role, path)
            if key in self.seen or len(self.surfaces[role]) >= self.limit_per_surface:
                continue
            row: dict[str, object] = {
                "path": path,
                "depth": depth,
                "domains": domains,
                "provenance": provenance,
            }
            if relation is not None:
                row["relation"] = relation
            self.surfaces[role].append(row)
            self.seen.add(key)


class QuerySurfaceMixin:
    def _grep_candidate_match(
        self,
        candidate: dict[str, object],
        *,
        lowered: str,
        tokens: list[str],
        context_lines: int,
    ) -> dict[str, object] | None:
        path = str(candidate["path"])
        visibility = EvidenceVisibility(str(candidate["evidence_visibility"]))
        if visibility is not EvidenceVisibility.SOURCE:
            return None
        self._ensure_path_current(path)
        try:
            lines = (
                (self.workspace / path)
                .read_text(encoding="utf-8", errors="replace")
                .splitlines()
            )
        except OSError:
            return None
        line_no = int(candidate["line"])
        if line_no < 1 or line_no > len(lines):
            return None
        line = lines[line_no - 1]
        if lowered not in line.lower() and not all(
            token in line.lower() for token in tokens
        ):
            return None
        start = max(1, line_no - max(0, context_lines))
        end = min(len(lines), line_no + max(0, context_lines))
        return {
            "path": path,
            "line": line_no,
            "range": [start, end],
            "content": "\n".join(lines[start - 1 : end]),
            "evidence_visibility": visibility.value,
        }

    def grep(
        self, query: str, *, limit: int = 50, context_lines: int = 0
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        raw = query.strip()
        if not raw:
            raise ValueError("query must not be empty")
        tokens = [token.lower() for token in _WORD_RE.findall(raw) if len(token) >= 2]
        candidates = self.store.lexical_candidates(tokens, limit=max(limit * 10, 100))
        matches: list[dict[str, object]] = []
        lowered = raw.lower()
        for candidate in candidates:
            match = self._grep_candidate_match(
                dict(candidate),
                lowered=lowered,
                tokens=tokens,
                context_lines=context_lines,
            )
            if match is None:
                continue
            matches.append(match)
            if len(matches) >= limit:
                break
        generation, identity_generation, stale = self._generation_status()
        return {
            "schema": "hashmarks.grep.v1",
            "query": query,
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "matches": matches,
        }

    def symbol(self, query: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        matches = self.store.symbol(query)
        if not matches:
            raise KeyError(f"symbol not found: {query}")
        visible = [
            row
            for row in matches
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        if not visible:
            raise PermissionError(f"symbol exists but agent context is denied: {query}")
        return {
            "schema": "hashmarks.symbol.v1",
            "query": query,
            **self._query_freshness_fields(),
            "matches": visible,
        }

    def _source_visible_matches(
        self,
        query: str,
    ) -> list[dict[str, object]]:
        if "::" in query:
            raw_path, qualname = query.split("::", 1)
            path = normalize_relative_path(raw_path, allow_root=False)
            self._ensure_path_current(path)
            match = self.store.symbol_at(path, qualname)
            matches = [] if match is None else [match]
        else:
            matches = self.store.symbol(query)
        visible = [
            dict(row)
            for row in matches
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        if not visible:
            raise KeyError(f"symbol not found: {query}")
        return visible

    def _source_current_content(
        self,
        query: str,
        row: dict[str, object],
    ) -> tuple[str, str, dict[str, object], str]:
        path = str(row["path"])
        qualname = str(row["qualname"])
        self._ensure_path_current(path)
        current_row = self.store.symbol_at(path, qualname)
        if current_row is None:
            raise KeyError(f"symbol changed or disappeared during refresh: {query}")
        current = dict(current_row)
        visibility = EvidenceVisibility(str(current["evidence_visibility"]))
        if visibility is not EvidenceVisibility.SOURCE:
            raise PermissionError(f"source body is not agent-visible: {path}")
        content = self._source_slice(
            path,
            int(current["start_line"]),
            int(current["end_line"]),
            qualname=qualname,
        )
        return path, qualname, current, content

    def source(self, query: str, *, token_budget: int = 4000) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        if token_budget < 16:
            raise ValueError("token budget must be at least 16")
        visible = self._source_visible_matches(query)
        if len(visible) > 1 and "::" not in query:
            return {
                "schema": "hashmarks.source.v1",
                "query": query,
                "ambiguous": True,
                "matches": [
                    {
                        "symbol_id": f"{row['path']}::{row['qualname']}",
                        "path": row["path"],
                        "qualname": row["qualname"],
                        "signature": row["signature"],
                    }
                    for row in visible[:20]
                ],
            }

        path, qualname, current, body = self._source_current_content(query, visible[0])
        tokens = estimate_tokens(body)
        if tokens > token_budget:
            return {
                "schema": "hashmarks.source.v1",
                "query": query,
                "symbol_id": f"{path}::{qualname}",
                "path": path,
                "qualname": qualname,
                "signature": current["signature"],
                "lines": [current["start_line"], current["end_line"]],
                "estimated_tokens": tokens,
                "budget": token_budget,
                "too_large": True,
                "guidance": "Use outline/deps or raise the explicit source budget.",
            }
        return {
            "schema": "hashmarks.source.v1",
            "query": query,
            "symbol_id": f"{path}::{qualname}",
            "path": path,
            "qualname": qualname,
            "signature": current["signature"],
            "lines": [current["start_line"], current["end_line"]],
            "estimated_tokens": tokens,
            "budget": token_budget,
            "too_large": False,
            "content": body,
        }

    def projects(self) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        return {
            "schema": "hashmarks.codemap-projects.v1",
            **self._query_freshness_fields(),
            "projects": self._fresh_project_nodes(),
            "edges": self._fresh_project_edges(),
            "native_file_edges": self._fresh_native_file_edges(),
            "last_enriched_unix": None
            if self.store.meta("project_graph_last_sync_unix") is None
            else float(self.store.meta("project_graph_last_sync_unix") or 0),
        }

    def structural(
        self, pattern: str, *, language: str | None = None, limit: int = 100
    ) -> dict[str, object]:
        """Syntax-aware search through an optional local ast-grep authority."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        raw, warnings = self.structural_search_provider.search(
            self.workspace, pattern, language=language, limit=max(limit * 4, limit)
        )
        matches: list[dict[str, object]] = []
        for row in raw:
            raw_path = row.get("file")
            if not raw_path:
                continue
            try:
                rel = normalize_relative_path(
                    str(raw_path).replace("\\", "/"), allow_root=False
                )
            except ValueError:
                continue
            mapped = self._session_file_row(rel)
            if mapped is None:
                continue
            visibility = EvidenceVisibility(str(mapped["evidence_visibility"]))
            # ast-grep's match text is implementation content, so outline-only
            # files are intentionally not disclosed by this operation.
            if visibility is not EvidenceVisibility.SOURCE:
                continue
            range_value = row.get("range") if isinstance(row.get("range"), dict) else {}
            start_value = (
                range_value.get("start") if isinstance(range_value, dict) else {}
            )
            end_value = range_value.get("end") if isinstance(range_value, dict) else {}
            matches.append(
                {
                    "path": rel,
                    "text": str(row.get("text") or ""),
                    "language": row.get("language"),
                    "range": [
                        int((start_value or {}).get("line", 0)) + 1,
                        int((end_value or {}).get("line", 0)) + 1,
                    ],
                    "producer": "ast-grep",
                }
            )
            if len(matches) >= limit:
                break
        return {
            "schema": "hashmarks.structural-search.v1",
            **self._query_freshness_fields(),
            "pattern": pattern,
            "available": self.structural_search_provider.available,
            "provider": self.structural_search_provider.status().as_dict(),
            "matches": matches,
            "warnings": list(warnings),
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

    def affected(self, query: str, *, max_depth: int = 12) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        roots = self._affected_roots(query)
        levels, seen = self._affected_levels(roots, max_depth=max_depth)
        affected = sorted(seen - roots)
        tests = [path for path in affected if self._is_test_path(path)]
        root_projects = {
            str(project["project_id"])
            for path in roots
            for project in self._fresh_projects_for_path(path)[:1]
        }
        impacted_projects = (
            self._fresh_project_dependents(root_projects, max_depth=max_depth)
            if root_projects
            else set()
        )
        return {
            "schema": "hashmarks.codemap-affected.v1",
            "query": query,
            **self._query_freshness_fields(),
            "roots": sorted(roots),
            "affected_files": affected,
            "tests": tests,
            "levels": levels,
            "root_projects": sorted(root_projects),
            "affected_projects": sorted(impacted_projects - root_projects),
            "evidence": "static import graph plus retained native/manifest project graph when available; advisory and conservative",
        }

    def tests(self, query: str, *, max_depth: int = 12) -> dict[str, object]:
        value = self.affected(query, max_depth=max_depth)
        return {
            "schema": "hashmarks.codemap-tests.v1",
            "query": query,
            "generation": value["generation"],
            "identity_generation": value["identity_generation"],
            "stale": value["stale"],
            "roots": value["roots"],
            "tests": value["tests"],
            "affected_files": value["affected_files"],
            "evidence": value["evidence"],
        }

    def _instruction_seed_paths(
        self,
        query: str,
        *,
        seed_limit: int,
    ) -> tuple[list[str], str]:
        try:
            rel = normalize_relative_path(query, allow_root=False)
        except ValueError:
            rel = None
        candidate = None if rel is None else self.workspace / rel
        if rel is not None and candidate is not None and candidate.exists():
            return [rel], "explicit-path"

        seed_paths: list[str] = []
        for hit in self.find_task(query, limit=seed_limit):
            if hit.path not in seed_paths:
                seed_paths.append(hit.path)
        return seed_paths, "task-retrieval"

    @staticmethod
    def _instruction_authority_projection(
        seed_paths: list[str],
        indexed_authority: dict[str, dict[str, object]],
        authority_paths: set[str],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        chains: list[dict[str, object]] = []
        merged: dict[str, dict[str, object]] = {}
        for seed in seed_paths:
            applicable = [
                path for path in authority_paths if _instruction_applies(path, seed)
            ]
            applicable.sort(
                key=lambda path: (
                    _instruction_specificity(path),
                    0 if Path(path).name == "AGENTS.md" else 1,
                    path,
                )
            )
            chain: list[dict[str, object]] = []
            for order, path in enumerate(applicable):
                row = indexed_authority[path]
                entry = {
                    "path": path,
                    "scope": _instruction_scope(path),
                    "specificity": _instruction_specificity(path),
                    "kind": (
                        "override"
                        if Path(path).name == "AGENTS.override.md"
                        else "agents"
                    ),
                    "precedence": order,
                    "evidence_visibility": str(row.get("evidence_visibility") or ""),
                }
                chain.append(entry)
                previous = merged.get(path)
                if previous is None:
                    merged[path] = {**entry, "applies_to": [seed]}
                    continue
                applies_to = previous["applies_to"]
                if isinstance(applies_to, list) and seed not in applies_to:
                    applies_to.append(seed)
            chains.append({"path": seed, "authority": chain})

        ordered = sorted(
            merged.values(),
            key=lambda row: (
                int(row["specificity"]),
                0 if row["kind"] == "agents" else 1,
                str(row["path"]),
            ),
        )
        return chains, ordered

    def repository_instruction_scope(
        self, query: str, *, seed_limit: int = 8
    ) -> dict[str, object]:
        """Resolve mechanically applicable repository instruction files for task scopes.

        Authority discovery is deliberately narrower than retrieval: only
        ``AGENTS.md`` and ``AGENTS.override.md`` files already indexed by
        CodeMap participate. Root authority applies repository-wide; nested
        authority applies only beneath its directory. A local override wins
        over ``AGENTS.md`` at the same scope and deeper scopes are more
        specific. The API reports paths and precedence only; it never parses
        instructions or changes ``find``/``find_task`` ranking.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if seed_limit < 1:
            raise ValueError("seed_limit must be >= 1")
        self._ensure_map_ready()
        rows = self.store.repository_instruction_file_rows()
        indexed_authority = {str(row["path"]): dict(row) for row in rows}
        authority_paths = {
            path
            for path in indexed_authority
            if Path(path).name in {"AGENTS.md", "AGENTS.override.md"}
        }
        seed_paths, source = self._instruction_seed_paths(
            query,
            seed_limit=seed_limit,
        )
        chains, ordered = self._instruction_authority_projection(
            seed_paths,
            indexed_authority,
            authority_paths,
        )
        return {
            "schema": "hashmarks.codemap-scoped-authority.v1",
            "query": query,
            **self._query_freshness_fields(),
            "scope_source": source,
            "seed_paths": seed_paths,
            "authority": ordered,
            "chains": chains,
            "precedence": "deeper scope wins; AGENTS.override.md wins over AGENTS.md at the same scope",
            "evidence": "indexed repository path hierarchy only; no semantic authority inference",
            "ranking_effect": "none",
        }

    @staticmethod
    def _change_impact_depths(
        roots: set[str],
        levels: list[list[str]],
    ) -> dict[str, int]:
        depth_by_path: dict[str, int] = dict.fromkeys(roots, 0)
        for depth, level in enumerate(levels, start=1):
            for path in level:
                depth_by_path.setdefault(path, depth)
        return depth_by_path

    def _change_impact_adjacency(
        self,
        query: str,
        roots: set[str],
        *,
        limit_per_surface: int,
    ) -> dict[str, object]:
        adjacency_limit = max(12, limit_per_surface * 2)
        exact_path_roots = self._query_paths(query)
        if len(exact_path_roots) == 1 and exact_path_roots == roots:
            try:
                normalized_query = normalize_relative_path(query, allow_root=False)
            except ValueError:
                normalized_query = ""
            if normalized_query in roots:
                return self._path_graph_adjacency(
                    query,
                    roots,
                    limit=adjacency_limit,
                )
        return self.task_graph_adjacency(
            query,
            seed_limit=min(12, max(4, limit_per_surface)),
            limit=adjacency_limit,
        )

    @staticmethod
    def _change_impact_relation(row: dict[str, object]) -> str | None:
        provenance_rows = row.get("provenance")
        if (
            isinstance(provenance_rows, list)
            and provenance_rows
            and isinstance(provenance_rows[0], dict)
        ):
            return str(provenance_rows[0].get("relation") or "") or None
        return None

    def change_impact(
        self, query: str, *, max_depth: int = 4, limit_per_surface: int = 20
    ) -> dict[str, object]:
        """Project proven change relationships into bounded repository surfaces.

        Reverse dependency reachability and the existing one-hop task graph are
        combined as separate provenance lanes. The API is additive navigation
        only: it does not alter ``find``/``find_task`` ranking or infer fuzzy
        relationships.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if limit_per_surface < 1:
            raise ValueError("limit_per_surface must be >= 1")
        value = self.affected(query, max_depth=max_depth)
        roots = {str(path) for path in value["roots"]}
        levels = [list(map(str, level)) for level in value["levels"]]
        depth_by_path = self._change_impact_depths(roots, levels)
        accumulator = _ChangeImpactAccumulator(roots, limit_per_surface)

        for path in sorted(
            depth_by_path,
            key=lambda item: (depth_by_path[item], item),
        ):
            accumulator.add(
                path,
                depth=depth_by_path[path],
                provenance="reverse-file-graph",
            )

        adjacency = self._change_impact_adjacency(
            query,
            roots,
            limit_per_surface=limit_per_surface,
        )
        for row in adjacency["adjacent"]:
            if not isinstance(row, dict):
                continue
            accumulator.add(
                str(row.get("path") or ""),
                depth=1,
                provenance="task-graph-adjacency",
                relation=self._change_impact_relation(row),
            )

        return {
            "schema": "hashmarks.codemap-change-impact.v1",
            "query": query,
            "generation": value["generation"],
            "identity_generation": value["identity_generation"],
            "stale": value["stale"],
            "roots": sorted(roots),
            "surfaces": accumulator.surfaces,
            "affected_projects": value["affected_projects"],
            "root_projects": value["root_projects"],
            "bounds": {
                "max_depth": max_depth,
                "limit_per_surface": limit_per_surface,
                "adjacency_max_hops": 1,
            },
            "evidence": value["evidence"] + "; plus bounded task graph adjacency",
            "authority": "advisory-navigation-only",
        }
