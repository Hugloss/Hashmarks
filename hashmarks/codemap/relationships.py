from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility, SearchHit
from .python_ast import identifier_terms
from .query_primitives import _query_terms
from .repository_domains import classify_repository_path

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .engine import CodeMap


@dataclass
class _TaskAdjacencyState:
    primary_paths: set[str]
    tokens: list[str]
    raw_query: str
    relation_weight: dict[str, float]
    symbolic_targets: dict[str, list[tuple[int, str, str, str]]]
    pending_admissions: list[tuple[str, int, str, str, str]]
    candidates: dict[str, dict[str, object]]


class RelationshipsMixin:
    """Bounded task adjacency and relationship projections."""

    @staticmethod
    def _validate_adjacency_bounds(
        seed_limit: int,
        limit: int,
        per_seed_edge_limit: int,
        per_seed_result_limit: int,
    ) -> None:
        if seed_limit < 1:
            raise ValueError("seed_limit must be >= 1")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if per_seed_edge_limit < 1:
            raise ValueError("per_seed_edge_limit must be >= 1")
        if per_seed_result_limit < 1:
            raise ValueError("per_seed_result_limit must be >= 1")

    @staticmethod
    def _adjacency_relation_weights() -> dict[str, float]:
        return {
            "imports": 42.0,
            "native-import": 44.0,
            "call": 38.0,
            "return-type": 36.0,
            "parameter-type": 34.0,
            "inherits": 40.0,
            "attribute-type": 32.0,
        }

    @staticmethod
    def _adjacency_symbolic_kinds() -> set[str]:
        return {"call", "return-type", "parameter-type", "inherits", "attribute-type"}

    @staticmethod
    def _adjacency_admit(
        state: _TaskAdjacencyState,
        path: str,
        seed_rank: int,
        seed_path: str,
        relation: str,
        confidence: str,
    ) -> None:
        if path and path not in state.primary_paths:
            state.pending_admissions.append(
                (path, seed_rank, seed_path, relation, confidence)
            )

    def _adjacency_import_edge(
        self,
        state: _TaskAdjacencyState,
        target: str,
        seed_rank: int,
        seed_path: str,
        confidence: str,
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for path in self._resolve_import_paths(seed_path, target)[:4]:
            self._adjacency_admit(
                state, path, seed_rank, seed_path, "imports", confidence
            )

    @staticmethod
    def _adjacency_symbol_short(target: str, tokens: list[str]) -> str | None:
        short = target.rsplit(".", 1)[-1].strip()
        if not short:
            return None
        return short if set(identifier_terms(short)).intersection(tokens) else None

    def _adjacency_static_edge(
        self, state: _TaskAdjacencyState, edge: dict, seed_rank: int, seed_path: str
    ) -> None:
        kind = str(edge.get("kind") or "")
        confidence = str(edge.get("confidence") or "static")
        target = str(edge.get("target") or "")
        if kind == "import":
            self._adjacency_import_edge(state, target, seed_rank, seed_path, confidence)
            return
        if kind not in self._adjacency_symbolic_kinds() or not target:
            return
        short = self._adjacency_symbol_short(target, state.tokens)
        if short is not None:
            state.symbolic_targets.setdefault(short.lower(), []).append(
                (seed_rank, seed_path, kind, confidence)
            )

    def _collect_adjacency_seeds(
        self, state: _TaskAdjacencyState, primary, per_seed_edge_limit: int
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        edge_map = self._session_edges_for_paths_many(
            [seed.path for seed in primary], limit_per_path=per_seed_edge_limit
        )
        for seed_rank, seed in enumerate(primary, 1):
            for edge in edge_map.get(seed.path, ()):
                self._adjacency_static_edge(state, edge, seed_rank, seed.path)
            for edge in self._fresh_native_file_edges_from(seed.path)[
                :per_seed_edge_limit
            ]:
                target = str(edge.get("target") or "")
                if target:
                    confidence = str(edge.get("confidence") or "native")
                    self._adjacency_admit(
                        state, target, seed_rank, seed.path, "native-import", confidence
                    )

    @staticmethod
    def _adjacency_symbol_rows(resolved, symbolic_targets) -> dict[str, list[dict]]:
        rows_by_alias: dict[str, list[dict]] = {}
        for row in resolved:
            aliases = {
                str(row.get("name") or "").lower(),
                str(row.get("qualname") or "").lower(),
                str(row.get("qualname") or "").rsplit(".", 1)[-1].lower(),
            }
            for alias in aliases.intersection(symbolic_targets):
                rows_by_alias.setdefault(alias, []).append(row)
        return rows_by_alias

    def _admit_resolved_adjacency_alias(
        self, state: _TaskAdjacencyState, alias: str, target_rows: list[dict]
    ) -> None:
        if len({str(row.get("path") or "") for row in target_rows}) > 4:
            return
        matched = state.symbolic_targets.get(alias, ())
        for row in target_rows:
            path = str(row.get("path") or "")
            for seed_rank, seed_path, relation, confidence in matched[:8]:
                self._adjacency_admit(
                    state, path, seed_rank, seed_path, relation, confidence
                )

    def _resolve_adjacency_symbols(self, state: _TaskAdjacencyState) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not state.symbolic_targets:
            return
        resolved = self._session_exact_symbol_candidates(
            sorted(state.symbolic_targets),
            limit=max(160, min(5000, len(state.symbolic_targets) * 32)),
        )
        rows_by_alias = self._adjacency_symbol_rows(resolved, state.symbolic_targets)
        for alias, target_rows in rows_by_alias.items():
            self._admit_resolved_adjacency_alias(state, alias, target_rows)

    def _score_adjacency_row(
        self,
        task: str,
        state: _TaskAdjacencyState,
        candidate: tuple[str, int, str, str, str],
        file_row: Mapping[str, object],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        path, seed_rank, seed_path, relation, confidence = candidate
        row = dict(file_row)
        if (
            EvidenceVisibility(str(row["evidence_visibility"]))
            is EvidenceVisibility.DENY
        ):
            return
        base_score = self._score(
            task,
            {"row_type": "file", **row},
            tokens=state.tokens,
            raw_query=state.raw_query,
        )
        score = (
            base_score
            + state.relation_weight.get(relation, 20.0)
            + (28.0 / (1.0 + seed_rank))
        )
        provenance = {
            "seed_path": seed_path,
            "seed_rank": seed_rank,
            "relation": relation,
            "confidence": confidence,
        }
        current = state.candidates.get(path)
        if current is None or score > float(current["score"]):
            state.candidates[path] = {
                "path": path,
                "score": score,
                "domains": [domain.value for domain in classify_repository_path(path)],
                "provenance": [provenance],
            }
            return
        existing = current.get("provenance")
        if (
            isinstance(existing, list)
            and provenance not in existing
            and len(existing) < 4
        ):
            existing.append(provenance)

    def _score_adjacency_admissions(
        self, task: str, state: _TaskAdjacencyState
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rows = self._session_file_rows(path for path, *_ in state.pending_admissions)
        for candidate in state.pending_admissions:
            file_row = rows.get(candidate[0])
            if file_row is not None:
                self._score_adjacency_row(task, state, candidate, file_row)

    @staticmethod
    def _candidate_matches_seed(candidate: dict[str, object], seed_rank: int) -> bool:
        provenance = candidate.get("provenance")
        if not isinstance(provenance, list):
            return False
        return any(
            isinstance(item, dict) and int(item.get("seed_rank", -1)) == seed_rank
            for item in provenance
        )

    @classmethod
    def _seed_adjacency_rows(
        cls, primary, ordered, per_seed_result_limit: int
    ) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for seed_rank, seed in enumerate(primary, 1):
            local = [
                candidate
                for candidate in ordered
                if cls._candidate_matches_seed(candidate, seed_rank)
            ]
            if local:
                result.append(
                    {
                        "seed_path": seed.path,
                        "seed_rank": seed_rank,
                        "adjacent": local[:per_seed_result_limit],
                    }
                )
        return result

    def _path_graph_adjacency(
        self,
        task: str,
        paths: set[str],
        *,
        limit: int = 12,
        per_seed_edge_limit: int = 96,
        per_seed_result_limit: int = 3,
    ) -> dict[str, object]:
        """Return one-hop adjacency seeded by already-proven exact paths.

        This avoids reinterpreting a repository path as free-text task input.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        primary: list[SearchHit] = []
        for path in sorted(paths):
            row = self._session_file_row(path)
            if row is None:
                continue
            visibility = EvidenceVisibility(str(row["evidence_visibility"]))
            if visibility is EvidenceVisibility.DENY:
                continue
            primary.append(
                SearchHit(
                    path=path, score=100.0, kind="file", evidence_visibility=visibility
                )
            )
        state = _TaskAdjacencyState(
            {hit.path for hit in primary},
            _query_terms(task),
            task.strip().lower(),
            self._adjacency_relation_weights(),
            {},
            [],
            {},
        )
        self._collect_adjacency_seeds(state, primary, per_seed_edge_limit)
        self._resolve_adjacency_symbols(state)
        self._score_adjacency_admissions(task, state)
        ordered = sorted(
            state.candidates.values(),
            key=lambda row: (-float(row["score"]), str(row["path"])),
        )
        return {
            "schema": "hashmarks.task-graph-adjacency.v1",
            "task": task,
            "generation": self.store.generation(),
            "bounds": {
                "seed_limit": len(primary),
                "limit": limit,
                "per_seed_edge_limit": per_seed_edge_limit,
                "per_seed_result_limit": per_seed_result_limit,
                "max_hops": 1,
            },
            "primary": [hit.as_dict() for hit in primary],
            "adjacent": ordered[:limit],
            "seed_adjacency": self._seed_adjacency_rows(
                primary, ordered, per_seed_result_limit
            ),
        }

    def task_graph_adjacency(
        self,
        task: str,
        *,
        seed_limit: int = 20,
        limit: int = 12,
        per_seed_edge_limit: int = 96,
        per_seed_result_limit: int = 3,
    ) -> dict[str, object]:
        """Return bounded one-hop graph evidence adjacent to canonical task hits."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_adjacency_bounds(
            seed_limit, limit, per_seed_edge_limit, per_seed_result_limit
        )
        primary = self.find_task(task, limit=seed_limit)
        state = _TaskAdjacencyState(
            {hit.path for hit in primary},
            _query_terms(task),
            task.strip().lower(),
            self._adjacency_relation_weights(),
            {},
            [],
            {},
        )
        self._collect_adjacency_seeds(state, primary, per_seed_edge_limit)
        self._resolve_adjacency_symbols(state)
        self._score_adjacency_admissions(task, state)
        ordered = sorted(
            state.candidates.values(),
            key=lambda row: (-float(row["score"]), str(row["path"])),
        )
        return {
            "schema": "hashmarks.task-graph-adjacency.v1",
            "task": task,
            "generation": self.store.generation(),
            "bounds": {
                "seed_limit": seed_limit,
                "limit": limit,
                "per_seed_edge_limit": per_seed_edge_limit,
                "per_seed_result_limit": per_seed_result_limit,
                "max_hops": 1,
            },
            "primary": [hit.as_dict() for hit in primary],
            "adjacent": ordered[:limit],
            "seed_adjacency": self._seed_adjacency_rows(
                primary, ordered, per_seed_result_limit
            ),
        }

    @staticmethod
    def _validate_relationship_bounds(
        seed_limit: int, adjacency_limit: int, impact_limit_per_surface: int
    ) -> None:
        if seed_limit < 1:
            raise ValueError("seed_limit must be >= 1")
        if adjacency_limit < 1:
            raise ValueError("adjacency_limit must be >= 1")
        if impact_limit_per_surface < 1:
            raise ValueError("impact_limit_per_surface must be >= 1")

    def _relationship_impact_surfaces(
        self, task: str, impact_limit_per_surface: int
    ) -> tuple[dict[str, list[dict[str, object]]], str | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        try:
            impact = self.change_impact(
                task, max_depth=2, limit_per_surface=impact_limit_per_surface
            )
        except KeyError:
            return {}, "no-proven-impact-root"
        return impact["surfaces"], None  # type: ignore[return-value]

    @staticmethod
    def _append_relationship(
        relationships,
        seen,
        source: str,
        target: str,
        relation: str,
        metadata: dict[str, object],
    ) -> None:
        if not source or not target or source == target:
            return
        key = (source, target, relation)
        if key in seen:
            return
        seen.add(key)
        relationships.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "layer": metadata["layer"],
                "provenance": metadata["provenance"],
            }
        )

    @classmethod
    def _append_adjacency_provenance(
        cls, relationships, seen, target: str, item: object
    ) -> None:
        if not isinstance(item, dict):
            return
        cls._append_relationship(
            relationships,
            seen,
            str(item.get("seed_path") or ""),
            target,
            str(item.get("relation") or "related"),
            {"layer": "code-graph", "provenance": item},
        )

    @classmethod
    def _relationship_adjacency_edges(cls, adjacency, relationships, seen) -> None:
        for row in adjacency.get("adjacent", []):
            if not isinstance(row, dict):
                continue
            provenance = row.get("provenance")
            if not isinstance(provenance, list):
                continue
            target = str(row.get("path") or "")
            for item in provenance:
                cls._append_adjacency_provenance(relationships, seen, target, item)

    @classmethod
    def _relationship_impact_edges(
        cls, surfaces, primary_paths, relationships, seen
    ) -> None:
        for surface, rows in surfaces.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                target = str(row.get("path") or "")
                provenance = {
                    "surface": surface,
                    "depth": row.get("depth"),
                    "source": row.get("provenance"),
                    "relation": row.get("relation"),
                }
                for source in primary_paths[:4]:
                    cls._append_relationship(
                        relationships,
                        seen,
                        source,
                        target,
                        f"affects-{surface}",
                        {"layer": "change-impact", "provenance": provenance},
                    )

    def _relationship_authority_edges(
        self, primary_paths, relationships, seen
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        authority_rows: list[dict[str, object]] = []
        for path in primary_paths[:4]:
            value = self.repository_instruction_scope(path)
            for row in value["authority"]:
                if not isinstance(row, dict):
                    continue
                authority_path = str(row.get("path") or "")
                authority_rows.append(
                    {
                        "target_path": path,
                        "authority_path": authority_path,
                        "kind": row.get("kind"),
                        "specificity": row.get("specificity"),
                    }
                )
                self._append_relationship(
                    relationships,
                    seen,
                    authority_path,
                    path,
                    "governs",
                    {
                        "layer": "authority",
                        "provenance": {
                            "kind": row.get("kind"),
                            "specificity": row.get("specificity"),
                            "scope": row.get("scope"),
                        },
                    },
                )
        return authority_rows

    @staticmethod
    def _relationship_layer_counts(relationships) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in relationships:
            layer = str(row["layer"])
            counts[layer] = counts.get(layer, 0) + 1
        return counts

    def task_relationships(
        self,
        task: str,
        *,
        seed_limit: int = 12,
        adjacency_limit: int = 18,
        impact_limit_per_surface: int = 12,
    ) -> dict[str, object]:
        """Return bounded cross-layer repository relationships for one task."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_relationship_bounds(
            seed_limit, adjacency_limit, impact_limit_per_surface
        )
        primary = self.find_task(task, limit=seed_limit)
        primary_paths = [hit.path for hit in primary]
        adjacency = self.task_graph_adjacency(
            task, seed_limit=seed_limit, limit=adjacency_limit
        )
        impact_surfaces, impact_error = self._relationship_impact_surfaces(
            task, impact_limit_per_surface
        )
        relationships: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        self._relationship_adjacency_edges(adjacency, relationships, seen)
        self._relationship_impact_edges(
            impact_surfaces, primary_paths, relationships, seen
        )
        authority_rows = self._relationship_authority_edges(
            primary_paths, relationships, seen
        )
        return {
            "schema": "hashmarks.task-relationships.v1",
            "task": task,
            "generation": self.store.generation(),
            "primary": [hit.as_dict() for hit in primary],
            "relationships": relationships,
            "authority": authority_rows,
            "layer_counts": self._relationship_layer_counts(relationships),
            "impact_status": "available" if impact_error is None else impact_error,
            "bounds": {
                "seed_limit": seed_limit,
                "adjacency_limit": adjacency_limit,
                "impact_limit_per_surface": impact_limit_per_surface,
                "impact_max_depth": 2,
                "adjacency_max_hops": 1,
                "authority_seed_limit": 4,
            },
            "ranking_effect": "none",
            "authority_effect": "advisory-navigation-only",
        }
