from __future__ import annotations

import json
from threading import RLock
from typing import TYPE_CHECKING, Any, TypeVar

from .codemap import ChangeImpactOptions, CodeMap
from .codemap.evidence_correlation import (
    CORRELATION_PACKET_MAX_BYTES,
    CORRELATION_REQUEST_MAX_BYTES,
)
from .codemap.repository_declaration_contract import MAX_PACKET_BYTES
from .codemap.repository_declaration_contract import MAX_REQUEST_BYTES
from .repository_retry import retry_transient_repository_race

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX_QUERY_CHARS = 8_192
_MAX_TASK_CHARS = 16_384
_MAX_CHANGED_PATHS = 256
_MAX_LIMIT = 50
_MAX_TOKEN_BUDGET = 8_192
_MAX_PREVIOUS_EVIDENCE_BYTES = 262_144
_MAX_DEPENDENCY_CODEMAP_BYTES = 1_048_576
_MAX_DEPENDENCY_QUERIES = 32

_T = TypeVar("_T")


class McpSurfaceError(ValueError):
    """Invalid consumer input at the Hashmarks MCP boundary."""


def _bounded_text(
    value: str, *, name: str, maximum: int, allow_empty: bool = False
) -> str:
    if not isinstance(value, str):
        raise McpSurfaceError(f"{name} must be a string")
    text = value.strip()
    if not text and not allow_empty:
        raise McpSurfaceError(f"{name} must not be empty")
    if len(text) > maximum:
        raise McpSurfaceError(f"{name} exceeds {maximum} characters")
    return text


def _bounded_int(value: int, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise McpSurfaceError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise McpSurfaceError(f"{name} must be between {minimum} and {maximum}")
    return value


def _previous_evidence(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise McpSurfaceError("previous_evidence must be an object")
    try:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise McpSurfaceError(
            "previous_evidence must contain JSON-compatible values"
        ) from exc
    if len(encoded) > _MAX_PREVIOUS_EVIDENCE_BYTES:
        raise McpSurfaceError(
            f"previous_evidence exceeds {_MAX_PREVIOUS_EVIDENCE_BYTES} encoded bytes"
        )
    return value


def _bounded_json(value: Any, *, name: str, maximum: int, expected_type: type) -> Any:
    if not isinstance(value, expected_type):
        kind = "an object" if expected_type is dict else "a list"
        raise McpSurfaceError(f"{name} must be {kind}")
    try:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise McpSurfaceError(f"{name} must contain JSON-compatible values") from exc
    if len(encoded) > maximum:
        raise McpSurfaceError(f"{name} exceeds {maximum} encoded bytes")
    return value


def _changed_paths(values: list[str]) -> list[str]:
    if not isinstance(values, list) or not values:
        raise McpSurfaceError(
            "changed_paths must contain at least one repository-relative path"
        )
    if len(values) > _MAX_CHANGED_PATHS:
        raise McpSurfaceError(f"changed_paths exceeds {_MAX_CHANGED_PATHS} entries")
    return [
        _bounded_text(str(value), name="changed path", maximum=4_096)
        for value in values
    ]


class HashmarksMcpSurface:
    """Small read-only MCP projection over one workspace-bound CodeMap.

    The gate serializes repository refresh and evidence reads so MCP consumers
    never observe the CodeMap's transient BUILDING generation. It does not add
    another freshness authority: CodeMap remains the owner of reconciliation.
    """

    def __init__(self, workspace: str = ".", *, state_dir: str | None = None) -> None:
        self._map = CodeMap(workspace, state_dir=state_dir)
        self._gate = RLock()

    def close(self) -> None:
        self._map.close()

    def _read(self, operation: Callable[[], _T]) -> _T:
        with self._gate:
            return retry_transient_repository_race(operation)

    def repository_context(self, *, max_areas: int = 12) -> dict[str, object]:
        max_areas = _bounded_int(max_areas, name="max_areas", minimum=1, maximum=32)
        return self._read(lambda: self._map.orient(max_areas=max_areas))

    def find(self, query: str, *, limit: int = 20) -> dict[str, object]:
        query = _bounded_text(query, name="query", maximum=_MAX_QUERY_CHARS)
        limit = _bounded_int(limit, name="limit", minimum=1, maximum=_MAX_LIMIT)
        hits = self._read(lambda: self._map.find(query, limit=limit + 1))
        visible = hits[:limit]
        return {
            "schema": "hashmarks.mcp-find.v1",
            "query": query,
            "results": [hit.as_dict() for hit in visible],
            "truncated": len(hits) > limit,
        }

    def task_evidence(
        self,
        task: str,
        *,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 1536,
    ) -> dict[str, object]:
        task = _bounded_text(task, name="task", maximum=_MAX_TASK_CHARS)
        limit = _bounded_int(limit, name="limit", minimum=1, maximum=_MAX_LIMIT)
        per_role = _bounded_int(per_role, name="per_role", minimum=1, maximum=8)
        token_budget = _bounded_int(
            token_budget, name="token_budget", minimum=1, maximum=_MAX_TOKEN_BUDGET
        )
        return self._read(
            lambda: self._map.task_evidence(
                task, limit=limit, per_role=per_role, token_budget=token_budget
            )
        )

    def change_impact(
        self, task: str, changed_paths: list[str], *, max_depth: int = 4
    ) -> dict[str, object]:
        task = _bounded_text(task, name="task", maximum=_MAX_TASK_CHARS)
        paths = _changed_paths(changed_paths)
        max_depth = _bounded_int(max_depth, name="max_depth", minimum=1, maximum=12)
        return self._read(
            lambda: self._map.task_change_impact(
                task,
                paths,
                limit=20,
                per_role=3,
                options=ChangeImpactOptions(
                    impact_limit_per_surface=6,
                    max_depth=max_depth,
                    project_impact_encoding="compact",
                ),
            )
        )

    def correlate_evidence(
        self,
        bundles: list[dict[str, Any]],
        *,
        path_mappings: list[dict[str, Any]] | None = None,
        previous_correlation: dict[str, Any] | None = None,
        include_relationships: bool = True,
        relationship_limit_per_path: int = 100,
    ) -> dict[str, object]:
        bundles = _bounded_json(
            bundles,
            name="bundles",
            maximum=CORRELATION_REQUEST_MAX_BYTES,
            expected_type=list,
        )
        mappings = (
            None
            if path_mappings is None
            else _bounded_json(
                path_mappings,
                name="path_mappings",
                maximum=CORRELATION_REQUEST_MAX_BYTES,
                expected_type=list,
            )
        )
        previous = (
            None
            if previous_correlation is None
            else _bounded_json(
                previous_correlation,
                name="previous_correlation",
                maximum=CORRELATION_PACKET_MAX_BYTES,
                expected_type=dict,
            )
        )
        if not isinstance(include_relationships, bool):
            raise McpSurfaceError("include_relationships must be a boolean")
        relationship_limit_per_path = _bounded_int(
            relationship_limit_per_path,
            name="relationship_limit_per_path",
            minimum=1,
            maximum=1000,
        )

        def correlate() -> dict[str, object]:
            try:
                return self._map.correlate_evidence(
                    bundles,
                    path_mappings=mappings,
                    previous_correlation=previous,
                    include_relationships=include_relationships,
                    relationship_limit_per_path=relationship_limit_per_path,
                )
            except ValueError as exc:
                raise McpSurfaceError(str(exc)) from exc

        return self._read(correlate)

    def dependency_codemap(
        self,
        snapshot: dict[str, Any],
        queries: list[dict[str, Any]] | None = None,
    ) -> dict[str, object]:
        """Qualify and query one request-scoped dependency-resolution observation."""
        raw_snapshot = _bounded_json(
            snapshot,
            name="snapshot",
            maximum=_MAX_DEPENDENCY_CODEMAP_BYTES,
            expected_type=dict,
        )
        raw_queries = [] if queries is None else queries
        if not isinstance(raw_queries, list):
            raise McpSurfaceError("queries must be a list")
        if len(raw_queries) > _MAX_DEPENDENCY_QUERIES:
            raise McpSurfaceError(f"queries exceeds {_MAX_DEPENDENCY_QUERIES} entries")
        bounded_queries = _bounded_json(
            raw_queries,
            name="queries",
            maximum=_MAX_DEPENDENCY_CODEMAP_BYTES,
            expected_type=list,
        )

        def project() -> dict[str, object]:
            try:
                observation = self._map.dependency_resolution_evidence(raw_snapshot)
                result: dict[str, object] = {
                    "schema": "hashmarks.mcp-dependency-codemap.v1",
                    "observation": observation,
                    "authority": "repository-intelligence-only",
                    "producer_authority": "caller-claimed",
                    "interpretation_authority": "consumer-owned",
                    "causation": "not-inferred",
                }
                if bounded_queries:
                    result["queries"] = self._map.dependency_resolution_queries(
                        observation, bounded_queries
                    )
                return result
            except ValueError as exc:
                raise McpSurfaceError(str(exc)) from exc

        return self._read(project)

    def repository_declarations(
        self,
        groups: list[dict[str, Any]],
        *,
        previous_observation: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        """Qualify request-scoped cross-artifact repository declarations."""
        bounded_groups = _bounded_json(
            groups,
            name="groups",
            maximum=MAX_REQUEST_BYTES,
            expected_type=list,
        )
        previous = (
            None
            if previous_observation is None
            else _bounded_json(
                previous_observation,
                name="previous_observation",
                maximum=MAX_PACKET_BYTES,
                expected_type=dict,
            )
        )

        def project() -> dict[str, object]:
            try:
                return self._map.repository_declarations(
                    bounded_groups,
                    previous_observation=previous,
                )
            except ValueError as exc:
                raise McpSurfaceError(str(exc)) from exc

        return self._read(project)

    def post_change(
        self,
        task: str,
        changed_paths: list[str],
        previous_evidence: dict[str, Any],
        *,
        token_budget: int = 1536,
    ) -> dict[str, object]:
        task = _bounded_text(task, name="task", maximum=_MAX_TASK_CHARS)
        paths = _changed_paths(changed_paths)
        previous_evidence = _previous_evidence(previous_evidence)
        token_budget = _bounded_int(
            token_budget, name="token_budget", minimum=1, maximum=_MAX_TOKEN_BUDGET
        )
        return self._read(
            lambda: self._map.task_post_change_delta(
                task,
                paths,
                previous_evidence=previous_evidence,
                limit=20,
                per_role=3,
                token_budget=token_budget,
            )
        )
