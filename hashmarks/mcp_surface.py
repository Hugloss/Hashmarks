from __future__ import annotations

import json
from threading import RLock
from typing import TYPE_CHECKING, Any, TypeVar

from . import repository_retry
from .codemap import ChangeImpactOptions, CodeMap
from .codemap.change_impact import CHANGE_IMPACT_DEFAULT_REQUEST
from .codemap.evidence_correlation import (
    CORRELATION_PACKET_MAX_BYTES,
    CORRELATION_REQUEST_MAX_BYTES,
)
from .codemap.evidence_packet import TASK_EVIDENCE_DEFAULT_OPTIONS
from .codemap.find_engine import FIND_DEFAULT_OPTIONS
from .codemap.repository_declaration_contract import (
    MAX_PACKET_BYTES,
    MAX_REQUEST_BYTES,
)
from .codemap.repository_intelligence_query import RepositoryIntelligenceQueryOptions
from .file_store import UnstableFileError
from .mcp_contract import (
    MCP_ERROR_REASONS,
    MCP_ERROR_RECOVERY_AUTHORITY,
    MCP_ERROR_SCHEMA,
)
from .operation_contract import operation_default_mode
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
    """Caller-visible Hashmarks MCP failure with one stable reason code."""

    def __init__(self, message: str, *, reason: str = "invalid-request") -> None:
        if reason not in MCP_ERROR_REASONS:
            raise RuntimeError(f"unknown Hashmarks MCP error reason: {reason}")
        super().__init__(message)
        self.reason = reason

    def as_dict(self) -> dict[str, str]:
        return {
            "schema": MCP_ERROR_SCHEMA,
            "reason": self.reason,
            "message": str(self),
            "recovery_authority": MCP_ERROR_RECOVERY_AUTHORITY,
        }

    def transport_message(self) -> str:
        return json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def _value_error_reason(message: str) -> str:
    lowered = message.lower()
    if "repository-mismatch" in lowered or "repository binding mismatch" in lowered:
        return "stale-or-foreign-evidence"
    if "codemap-generation-mismatch" in lowered:
        return "stale-or-foreign-evidence"
    if "unsupported " in lowered:
        return "unsupported-semantic"
    if "continuity mismatch" in lowered:
        return "continuity-mismatch"
    if "mismatch" in lowered and (
        lowered.startswith("previous ") or lowered.startswith("before ")
    ):
        return "continuity-mismatch"
    return "invalid-request"


def _surface_value_error(exc: ValueError) -> McpSurfaceError:
    message = str(exc)
    return McpSurfaceError(message, reason=_value_error_reason(message))


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


def _dependency_codemap_request(
    snapshot: dict[str, Any],
    queries: list[dict[str, Any]] | None,
    previous_observation: dict[str, Any] | None,
    result_mode: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None, str]:
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
    previous = (
        None
        if previous_observation is None
        else _bounded_json(
            previous_observation,
            name="previous_observation",
            maximum=_MAX_DEPENDENCY_CODEMAP_BYTES,
            expected_type=dict,
        )
    )
    mode = _bounded_text(result_mode, name="result_mode", maximum=32)
    return raw_snapshot, bounded_queries, previous, mode


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
            try:
                return retry_transient_repository_race(operation)
            except (RuntimeError, UnstableFileError) as exc:
                if repository_retry.is_transient_repository_race(exc):
                    raise McpSurfaceError(
                        "repository state did not stabilize within the bounded MCP read window",
                        reason="transient-race-exhausted",
                    ) from exc
                raise

    def repository_context(self, *, max_areas: int = 12) -> dict[str, object]:
        max_areas = _bounded_int(max_areas, name="max_areas", minimum=1, maximum=32)
        return self._read(lambda: self._map.orient(max_areas=max_areas))

    def find(
        self,
        query: str,
        *,
        limit: int = FIND_DEFAULT_OPTIONS.limit,
    ) -> dict[str, object]:
        query = _bounded_text(query, name="query", maximum=_MAX_QUERY_CHARS)
        limit = _bounded_int(limit, name="limit", minimum=1, maximum=_MAX_LIMIT)
        return self._read(lambda: self._map.find_packet(query, limit=limit))

    def task_evidence(
        self,
        task: str,
        *,
        limit: int = TASK_EVIDENCE_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_EVIDENCE_DEFAULT_OPTIONS.per_role,
        token_budget: int = TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
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
        self,
        task: str,
        changed_paths: list[str],
        *,
        max_depth: int = CHANGE_IMPACT_DEFAULT_REQUEST.options.max_depth,
    ) -> dict[str, object]:
        task = _bounded_text(task, name="task", maximum=_MAX_TASK_CHARS)
        paths = _changed_paths(changed_paths)
        max_depth = _bounded_int(max_depth, name="max_depth", minimum=1, maximum=12)
        defaults = CHANGE_IMPACT_DEFAULT_REQUEST
        options = defaults.options
        return self._read(
            lambda: self._map.task_change_impact(
                task,
                paths,
                limit=defaults.limit,
                per_role=defaults.per_role,
                options=ChangeImpactOptions(
                    impact_limit_per_surface=options.impact_limit_per_surface,
                    max_depth=max_depth,
                    project_impact_limit=options.project_impact_limit,
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
                raise _surface_value_error(exc) from exc

        return self._read(correlate)

    def dependency_codemap(
        self,
        snapshot: dict[str, Any],
        queries: list[dict[str, Any]] | None = None,
        *,
        previous_observation: dict[str, Any] | None = None,
        result_mode: str = operation_default_mode("dependency_codemap"),
    ) -> dict[str, object]:
        """Project one core-owned dependency operation without changing semantics."""
        raw_snapshot, bounded_queries, previous, mode = _dependency_codemap_request(
            snapshot,
            queries,
            previous_observation,
            result_mode,
        )

        def project() -> dict[str, object]:
            try:
                return self._map.dependency_codemap(
                    raw_snapshot,
                    bounded_queries,
                    previous_observation=previous,
                    result_mode=mode,
                )
            except ValueError as exc:
                raise _surface_value_error(exc) from exc

        return self._read(project)

    def repository_declarations(
        self,
        groups: list[dict[str, Any]],
        *,
        previous_observation: dict[str, Any] | None = None,
        result_mode: str = operation_default_mode("repository_declarations"),
    ) -> dict[str, object]:
        """Project one core-owned declaration operation without changing semantics."""
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
        mode = _bounded_text(result_mode, name="result_mode", maximum=32)

        def project() -> dict[str, object]:
            try:
                return self._map.repository_declarations_operation(
                    bounded_groups,
                    previous_observation=previous,
                    result_mode=mode,
                )
            except ValueError as exc:
                raise _surface_value_error(exc) from exc

        return self._read(project)

    def repository_intelligence_query(  # noqa: PLR0913 - explicit MCP query dimensions
        self,
        surface: str,
        task: str,
        changed_paths: list[str] | None = None,
        *,
        profile: str = "compact",
        presentation: str = "compact",
        member_path: str | None = None,
        previous_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        surface = _bounded_text(surface, name="surface", maximum=48)
        task = _bounded_text(task, name="task", maximum=_MAX_TASK_CHARS)
        paths = _changed_paths(changed_paths) if changed_paths else []
        if previous_snapshot is not None:
            previous_snapshot = _bounded_json(
                previous_snapshot,
                name="previous_snapshot",
                maximum=1_048_576,
                expected_type=dict,
            )
        if member_path is not None:
            member_path = _bounded_text(member_path, name="member_path", maximum=2_048)
        profile = _bounded_text(profile, name="profile", maximum=16)
        presentation = _bounded_text(presentation, name="presentation", maximum=16)

        def project() -> dict[str, object]:
            try:
                return self._map.repository_intelligence_query(
                    surface,
                    task,
                    paths,
                    options=RepositoryIntelligenceQueryOptions(
                        member_path=member_path,
                        profile=profile,
                        previous_snapshot=previous_snapshot,
                        presentation=presentation,
                    ),
                )
            except ValueError as exc:
                raise _surface_value_error(exc) from exc

        return self._read(project)

    @staticmethod
    def _validate_source_request(
        paths: list[str], literal: str | None, result_mode: str
    ) -> None:
        if not isinstance(paths, list) or not 1 <= len(paths) <= 32:
            raise McpSurfaceError(
                "paths must contain between 1 and 32 explicit members"
            )
        if not all(isinstance(path, str) and path for path in paths):
            raise McpSurfaceError("paths must contain nonblank strings")
        if result_mode not in ("member", "scope"):
            raise McpSurfaceError("result_mode must be one of: member, scope")
        if result_mode == "member" and len(paths) != 1:
            raise McpSurfaceError("member mode requires exactly one path")
        if result_mode == "scope" and literal is None:
            raise McpSurfaceError("scope mode requires a literal")

    def source_observation(
        self,
        paths: list[str],
        *,
        literal: str | None = None,
        result_mode: str = operation_default_mode("source_observation"),
        limit: int = 50,
    ) -> dict[str, object]:
        self._validate_source_request(paths, literal, result_mode)
        if literal is not None:
            literal = _bounded_text(literal, name="literal", maximum=_MAX_QUERY_CHARS)
        limit = _bounded_int(limit, name="limit", minimum=1, maximum=50)

        def project() -> dict[str, object]:
            try:
                self._map.sync(paths)
                if result_mode == "member":
                    return self._map.source_observation(
                        paths[0], literal=literal, limit=limit
                    )
                assert literal is not None
                return self._map.scoped_source_occurrences(paths, literal, limit=limit)
            except ValueError as exc:
                raise _surface_value_error(exc) from exc

        return self._read(project)

    def _repository_binding_observation(
        self, request: dict[str, Any]
    ) -> dict[str, object]:
        fields = {"bindings", "dependency_paths", "include_relationships"}
        if set(request) - fields:
            raise ValueError("unsupported evidence observation request fields")
        bindings = request.get("bindings")
        if not isinstance(bindings, list):
            raise ValueError("bindings must be a list")
        return self._map.repository_evidence_bindings(
            bindings,
            dependency_paths=request.get("dependency_paths"),
            include_relationships=request.get("include_relationships", True),
        )

    def _repository_binding_coverage(
        self, request: dict[str, Any]
    ) -> dict[str, object]:
        fields = {"bindings_packet", "changed_paths", "change_set_complete"}
        if set(request) - fields:
            raise ValueError("unsupported evidence coverage request fields")
        packet = request.get("bindings_packet")
        if not isinstance(packet, dict):
            raise ValueError("bindings_packet must be an object")
        return self._map.repository_evidence_coverage(
            packet,
            changed_paths=request.get("changed_paths"),
            change_set_complete=request.get("change_set_complete"),
        )

    def repository_evidence(
        self,
        request: dict[str, Any],
        *,
        result_mode: str = operation_default_mode("repository_evidence"),
    ) -> dict[str, object]:
        request = _bounded_json(
            request, name="request", maximum=1_048_576, expected_type=dict
        )
        if result_mode not in ("observation", "coverage"):
            raise McpSurfaceError("result_mode must be one of: observation, coverage")

        def project() -> dict[str, object]:
            try:
                self._map.sync()
                producers = {
                    "observation": self._repository_binding_observation,
                    "coverage": self._repository_binding_coverage,
                }
                return producers[result_mode](request)
            except ValueError as exc:
                raise _surface_value_error(exc) from exc

        return self._read(project)

    def repository_findings(self, paths: list[str] | None = None) -> dict[str, object]:
        bounded = _changed_paths(paths) if paths else None

        def project() -> dict[str, object]:
            self._map.sync()
            return self._map.repository_findings(bounded)

        return self._read(project)

    def structural_locality(
        self, target: str, *, max_depth: int = 2
    ) -> dict[str, object]:
        target = _bounded_text(target, name="target", maximum=_MAX_QUERY_CHARS)
        max_depth = _bounded_int(max_depth, name="max_depth", minimum=1, maximum=6)

        def project() -> dict[str, object]:
            try:
                return self._map.structural_locality(target, max_depth=max_depth)
            except ValueError as exc:
                raise _surface_value_error(exc) from exc

        return self._read(project)

    def post_change(
        self,
        task: str,
        changed_paths: list[str],
        previous_evidence: dict[str, Any],
        *,
        token_budget: int = TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
    ) -> dict[str, object]:
        task = _bounded_text(task, name="task", maximum=_MAX_TASK_CHARS)
        paths = _changed_paths(changed_paths)
        previous_evidence = _previous_evidence(previous_evidence)
        token_budget = _bounded_int(
            token_budget, name="token_budget", minimum=1, maximum=_MAX_TOKEN_BUDGET
        )

        def project() -> dict[str, object]:
            try:
                return self._map.task_post_change_delta(
                    task,
                    paths,
                    previous_evidence=previous_evidence,
                    limit=TASK_EVIDENCE_DEFAULT_OPTIONS.limit,
                    per_role=TASK_EVIDENCE_DEFAULT_OPTIONS.per_role,
                    token_budget=token_budget,
                )
            except ValueError as exc:
                raise _surface_value_error(exc) from exc

        return self._read(project)
