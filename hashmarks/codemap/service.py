from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import socketserver
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeGuard

from hashmarks.client import default_runtime_dir
from hashmarks.evidence_presentation import validate_presentation
from hashmarks.ipc_boundary import dispatch_json_request
from hashmarks.operation_contract import (
    operation_default_mode,
    require_operation_mode,
    require_registered_operation,
    validate_operation_response,
)
from hashmarks.paths import canonical_host_path

from .change_impact import (
    CHANGE_IMPACT_DEFAULT_REQUEST,
    ChangeImpactOptions,
)
from .engine import CodeMap
from .evidence_decision_packet import TASK_DECISION_DEFAULT_OPTIONS
from .evidence_packet import (
    TASK_ACTION_BRIEF_BUDGET_DEFAULT_OPTIONS,
    TASK_DECISION_BRIEF_BUDGET_SWEEP_DEFAULTS,
    TASK_EVIDENCE_DEFAULT_OPTIONS,
)
from .ownership_relation_defaults import OWNERSHIP_RELATION_DEFAULT_OPTIONS
from .ownership_relation_types import OwnershipRelationGraph
from .post_change import POST_CHANGE_DEFAULT_OPTIONS, PostChangeOptions
from .repository_declaration_selection import source_declaration_providers
from .repository_intelligence_query import (
    REPOSITORY_INTELLIGENCE_QUERY_DEFAULT_OPTIONS,
    RepositoryIntelligenceQueryOptions,
)
from .task_action_projection import TASK_ACTION_DEFAULT_OPTIONS
from .task_evidence_contract import (
    read_ownership_relation_graph,
    read_post_change_delta,
    read_task_action_map,
    read_task_evidence,
)
from .task_evidence_types import (
    PreviousTaskEvidence,
    TaskActionMap,
    TaskEvidencePacket,
    TaskPostChangeDelta,
)
from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS

PROTOCOL = "hashmarks.codemap-service.v2"
MAX_REQUEST = 1024 * 1024
MAX_RESPONSE = 8 * 1024 * 1024


def _request_result_mode(operation: str, request: dict[str, object]) -> str:
    """Select the operation-owned mode without coercing malformed wire values."""
    mode = request.get("result_mode")
    if mode is not None and not isinstance(mode, str):
        raise ValueError("result_mode must be a string")
    return require_operation_mode(operation, mode)


def _source_request(
    request: dict[str, Any], option_names: tuple[str, ...]
) -> tuple[str, dict[str, Any]]:
    unexpected = set(request) - {"protocol", "op", "result_mode", "path", *option_names}
    if unexpected:
        raise ValueError(f"unsupported source request fields: {sorted(unexpected)}")
    path = request.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a non-empty string")
    return path, {name: request[name] for name in option_names if name in request}


_ServiceRouteClassification = Literal["canonical-semantic", "internal-service"]


@dataclass(frozen=True, slots=True)
class _ServiceRoute:
    handler_name: str
    classification: _ServiceRouteClassification
    operation: str | None = None
    response_key: str | None = None

    def __post_init__(self) -> None:
        if not self.handler_name.strip():
            raise ValueError("service route handler_name must not be empty")
        if self.classification == "canonical-semantic":
            if not self.operation or not self.response_key:
                raise ValueError(
                    "canonical-semantic service routes require operation and response_key"
                )
            self.admit()
            return
        if self.classification != "internal-service":
            raise ValueError(
                f"unsupported service route classification: {self.classification!r}"
            )
        if self.operation is not None or self.response_key is not None:
            raise ValueError(
                "internal-service routes must not carry semantic operation metadata"
            )

    def admit(self) -> None:
        if self.classification == "canonical-semantic":
            assert self.operation is not None
            require_registered_operation(self.operation)

    def validate_response(
        self, response: dict[str, Any], *, result_mode: str | None = None
    ) -> None:
        if self.classification != "canonical-semantic":
            return
        assert self.operation is not None
        assert self.response_key is not None
        validate_operation_response(
            self.operation,
            response.get(self.response_key),
            mode=result_mode,
        )


def _internal_service_route(handler_name: str) -> _ServiceRoute:
    return _ServiceRoute(
        handler_name=handler_name,
        classification="internal-service",
    )


def _canonical_service_route(
    handler_name: str,
    *,
    operation: str,
    response_key: str,
) -> _ServiceRoute:
    return _ServiceRoute(
        handler_name=handler_name,
        classification="canonical-semantic",
        operation=operation,
        response_key=response_key,
    )


_SERVICE_ROUTES = {
    "status": _internal_service_route("_status_response"),
    "sync": _internal_service_route("_sync_response"),
    "repository_declarations": _canonical_service_route(
        "_repository_declarations_response",
        operation="repository_declarations",
        response_key="repository_declarations",
    ),
    "source_range_receipt": _canonical_service_route(
        "_source_range_receipt_response",
        operation="source_range_receipt",
        response_key="source_range_receipt",
    ),
    "source_ecmascript": _canonical_service_route(
        "_source_ecmascript_response",
        operation="source_ecmascript",
        response_key="source_ecmascript",
    ),
    "verification_membership": _canonical_service_route(
        "_verification_membership_response",
        operation="verification_membership",
        response_key="verification_membership",
    ),
    "repository_findings": _canonical_service_route(
        "_repository_findings_response",
        operation="repository_findings",
        response_key="repository_findings",
    ),
    "import_ownership": _canonical_service_route(
        "_import_ownership_response",
        operation="import_ownership",
        response_key="import_ownership",
    ),
    "cache_ownership": _canonical_service_route(
        "_cache_ownership_response",
        operation="cache_ownership",
        response_key="cache_ownership",
    ),
    "cache_invalidation_ownership": _canonical_service_route(
        "_cache_invalidation_response",
        operation="cache_invalidation_ownership",
        response_key="cache_invalidation_ownership",
    ),
    "authority_ownership": _canonical_service_route(
        "_authority_ownership_response",
        operation="repository_ownership",
        response_key="authority_ownership",
    ),
    "concurrency_risk": _canonical_service_route(
        "_concurrency_risk_response",
        operation="concurrency_risk",
        response_key="concurrency_risk",
    ),
    "verification_ownership": _canonical_service_route(
        "_verification_ownership_response",
        operation="verification_ownership",
        response_key="verification_ownership",
    ),
    "find_task": _internal_service_route("_find_task_response"),
    "task_action_map": _canonical_service_route(
        "_task_action_map_response",
        operation="task_action_map",
        response_key="action_map",
    ),
    "verification_relevance": _canonical_service_route(
        "_verification_relevance_response",
        operation="verification_relevance",
        response_key="verification_relevance",
    ),
    "ownership_relation_graph": _canonical_service_route(
        "_ownership_relation_response",
        operation="ownership_relation_graph",
        response_key="ownership_relation_graph",
    ),
    "task_evidence": _canonical_service_route(
        "_task_evidence_response",
        operation="task_evidence",
        response_key="task_evidence",
    ),
    "task_change_impact": _canonical_service_route(
        "_change_impact_response",
        operation="change_impact",
        response_key="task_change_impact",
    ),
    "repository_intelligence_query": _canonical_service_route(
        "_repository_intelligence_query_response",
        operation="repository_intelligence_query",
        response_key="repository_intelligence_query",
    ),
    "task_post_change_delta": _canonical_service_route(
        "_post_change_delta_response",
        operation="post_change",
        response_key="post_change_delta",
    ),
    "refresh_after_change_delta": _canonical_service_route(
        "_refresh_delta_response",
        operation="refresh_after_change_delta",
        response_key="refresh_delta",
    ),
    "refresh_after_change_brief": _canonical_service_route(
        "_refresh_brief_response",
        operation="refresh_after_change_brief",
        response_key="refresh_brief",
    ),
    "refresh_after_change": _canonical_service_route(
        "_refresh_response",
        operation="refresh_after_change",
        response_key="refresh",
    ),
    "task_decision_brief": _canonical_service_route(
        "_decision_brief_response",
        operation="task_decision_brief",
        response_key="decision_brief",
    ),
    "task_action_brief": _canonical_service_route(
        "_task_action_brief_response",
        operation="task_action_brief",
        response_key="task_action_brief",
    ),
    "task_decision_brief_budget_sweep": _canonical_service_route(
        "_budget_sweep_response",
        operation="task_decision_brief_budget_sweep",
        response_key="budget_sweep",
    ),
    "task_decision_packet": _canonical_service_route(
        "_decision_packet_response",
        operation="task_decision_packet",
        response_key="decision_packet",
    ),
    "stop": _internal_service_route("_stop_response"),
}


def default_codemap_socket(workspace: str | Path) -> Path:
    return default_runtime_dir(workspace) / "codemap.sock"


_UNIX_STREAM_SERVER = getattr(socketserver, "UnixStreamServer", None)

if TYPE_CHECKING or _UNIX_STREAM_SERVER is not None:

    class _Server(socketserver.UnixStreamServer):
        allow_reuse_address = False
        request_queue_size = 128
        codemap_service: CodeMapService

else:

    class _Server:
        """Import-safe placeholder when the platform has no Unix socket server."""


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server = self.server
        if not isinstance(server, _Server):
            raise RuntimeError("CodeMap handler requires its service server")
        service = server.codemap_service
        raw = self.rfile.readline(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            service._write(
                self.wfile, {"ok": False, "error": "request exceeded size limit"}
            )
            return
        response = dispatch_json_request(raw, service.dispatch)
        service._write(self.wfile, response)


class _ResponseWriter(Protocol):
    def write(self, data: bytes, /) -> object: ...

    def flush(self) -> None: ...


def _is_wire_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


class CodeMapService:
    """Single-owner warm CodeMap service for many stateless agent clients.

    The Unix server is intentionally single-threaded: one thread owns the
    CodeMap/SQLite state for its entire lifetime. Concurrent clients queue in the
    local socket backlog instead of creating multiple repository authorities.
    """

    def __init__(
        self, workspace: str | Path, *, socket_path: str | Path | None = None
    ) -> None:
        self.workspace = canonical_host_path(workspace)
        self.socket_path = (
            default_codemap_socket(self.workspace)
            if socket_path is None
            else canonical_host_path(socket_path)
        )
        self._codemap: CodeMap | None = None
        self._server: _Server | None = None
        self._requests = 0
        self._syncs = 0
        self._initial_sync_ms = 0.0

    @staticmethod
    def _write(stream: _ResponseWriter, response: dict[str, object]) -> None:
        payload = (
            json.dumps(response, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
        if len(payload) > MAX_RESPONSE:
            payload = b'{"ok":false,"error":"response exceeded size limit"}\n'
        stream.write(payload)
        stream.flush()

    def _map(self) -> CodeMap:
        if self._codemap is None:
            raise RuntimeError("CodeMap service is not running")
        return self._codemap

    @staticmethod
    def _paths(request: dict[str, Any], *, required: bool = False) -> list[str] | None:
        paths = request.get("paths")
        if paths is None and not required:
            return None
        if (
            not isinstance(paths, list)
            or (required and not paths)
            or not all(isinstance(path, str) for path in paths)
        ):
            message = (
                "paths must be a non-empty list of strings"
                if required
                else "paths must be a list of strings"
            )
            raise ValueError(message)
        return paths

    @staticmethod
    def _task(request: dict[str, Any]) -> str:
        task = request.get("task")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        return task

    @staticmethod
    def _bounded_int(
        request: dict[str, Any], key: str, default: int, minimum: int, maximum: int
    ) -> int:
        value = int(request.get(key, default))
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _string_list(
        request: dict[str, Any], key: str, *, required: bool = False
    ) -> list[str]:
        value = request.get(key, [])
        if (
            not isinstance(value, list)
            or (required and not value)
            or not all(isinstance(item, str) for item in value)
        ):
            qualifier = "a non-empty list" if required else "a list"
            raise ValueError(f"{key} must be {qualifier} of strings")
        return value

    def _status_response(self, _request: dict[str, Any]) -> dict[str, Any]:
        codemap = self._map()
        return {
            "ok": True,
            "protocol": PROTOCOL,
            "pid": os.getpid(),
            "workspace": str(self.workspace),
            "socket": str(self.socket_path),
            "generation": codemap.store.generation(),
            "requests": self._requests,
            "syncs": self._syncs,
            "initial_sync_ms": self._initial_sync_ms,
            "ownership": "single-warm-codemap",
        }

    def _sync_response(self, _request: dict[str, Any]) -> dict[str, Any]:
        import time

        started = time.perf_counter()
        result = self._map().index.sync()
        elapsed = (time.perf_counter() - started) * 1000.0
        self._syncs += 1
        return {"ok": True, "elapsed_ms": elapsed, "result": result.as_dict()}

    def _repository_findings_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "repository_findings": self._map().ownership.findings(self._paths(request)),
        }

    def _repository_declarations_response(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        unexpected = set(request) - {
            "protocol",
            "op",
            "groups",
            "result_mode",
            "source_selection",
            "previous_observation",
        }
        if unexpected:
            raise ValueError(
                f"unsupported declaration request fields: {sorted(unexpected)}"
            )
        groups = request.get("groups", [])
        if not isinstance(groups, list):
            raise ValueError("groups must be an array")
        previous = request.get("previous_observation")
        if previous is not None and not isinstance(previous, dict):
            raise ValueError("previous_observation must be an object")
        mode = _request_result_mode("repository_declarations", request)
        providers = source_declaration_providers(mode, request.get("source_selection"))
        result = self._map().declarations.operation(
            groups,
            previous_observation=previous,
            result_mode=mode,
            providers=providers,
        )
        return {"ok": True, "repository_declarations": result}

    def _source_range_receipt_response(self, request: dict[str, Any]) -> dict[str, Any]:
        path, options = _source_request(
            request, ("start_byte", "end_byte", "max_bytes")
        )
        if not {"start_byte", "end_byte"} <= set(options):
            raise ValueError("source range requires start_byte and end_byte")
        return {
            "ok": True,
            "source_range_receipt": self._map().source.range_receipt(path, **options),
        }

    def _source_ecmascript_response(self, request: dict[str, Any]) -> dict[str, Any]:
        path, options = _source_request(request, ("limit", "max_bytes"))
        return {
            "ok": True,
            "source_ecmascript": self._map().source.ecmascript(path, **options),
        }

    def _verification_membership_response(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        if set(request) - {"protocol", "op", "result_mode", "report"}:
            raise ValueError("verification membership accepts only a supplied report")
        return {
            "ok": True,
            "verification_membership": self._map().verification.observe_membership(
                request.get("report")
            ),
        }

    def _import_ownership_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "import_ownership": self._map().ownership.import_findings(
                self._paths(request)
            ),
        }

    def _cache_ownership_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "cache_ownership": self._map().ownership.cache_findings(
                self._paths(request)
            ),
        }

    def _cache_invalidation_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "cache_invalidation_ownership": self._map().ownership.cache_invalidation_graph(
                self._paths(request)
            ),
        }

    def _authority_ownership_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "authority_ownership": self._map().ownership.repository_graph(
                self._paths(request)
            ),
        }

    def _concurrency_risk_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "concurrency_risk": self._map().ownership.concurrency_findings(
                self._paths(request)
            ),
        }

    def _verification_ownership_response(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        defaults = VERIFICATION_RELEVANCE_DEFAULTS
        task = self._task(request)
        limit = self._bounded_int(request, "limit", defaults.limit, 1, 100)
        candidate_limit = self._bounded_int(
            request, "candidate_limit", defaults.candidate_limit, 1, 16
        )
        graph = self._map().tasks.verification_ownership_graph(
            task, limit=limit, candidate_limit=candidate_limit
        )
        return {"ok": True, "verification_ownership": graph}

    def _find_task_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task = self._task(request)
        limit = self._bounded_int(request, "limit", 20, 1, 100)
        return {
            "ok": True,
            "hits": [
                hit.as_dict() for hit in self._map().search.find_task(task, limit=limit)
            ],
        }

    def _task_context(self, request: dict[str, Any]) -> tuple[str, int, int]:
        return (
            self._task(request),
            self._bounded_int(request, "limit", 20, 1, 100),
            int(request.get("per_role", 3)),
        )

    def _task_action_context(self, request: dict[str, Any]) -> tuple[str, int, int]:
        defaults = TASK_ACTION_DEFAULT_OPTIONS
        return (
            self._task(request),
            self._bounded_int(request, "limit", defaults.limit, 1, 100),
            self._bounded_int(request, "per_role", defaults.per_role, 1, 20),
        )

    def _task_action_map_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, limit, per_role = self._task_action_context(request)
        result = self._map().tasks.action_map(task, limit=limit, per_role=per_role)
        return {"ok": True, "action_map": result}

    def _verification_relevance_response(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        defaults = VERIFICATION_RELEVANCE_DEFAULTS
        task = self._task(request)
        limit = self._bounded_int(request, "limit", defaults.limit, 1, 100)
        candidate_limit = self._bounded_int(
            request, "candidate_limit", defaults.candidate_limit, 1, 16
        )
        result = self._map().tasks.verification_relevance(
            task, limit=limit, candidate_limit=candidate_limit
        )
        return {"ok": True, "verification_relevance": result}

    def _ownership_relation_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task = self._task(request)
        start_path = request.get("start_path")
        if not isinstance(start_path, str) or not start_path.strip():
            raise ValueError("start_path must be a non-empty string")
        max_depth = int(
            request.get("max_depth", OWNERSHIP_RELATION_DEFAULT_OPTIONS.max_depth)
        )
        result = self._map().ownership.relations(task, start_path, max_depth=max_depth)
        return {"ok": True, "ownership_relation_graph": result}

    def _task_evidence_response(self, request: dict[str, Any]) -> dict[str, Any]:
        defaults = TASK_EVIDENCE_DEFAULT_OPTIONS
        task = self._task(request)
        limit = self._bounded_int(request, "limit", defaults.limit, 1, 100)
        per_role = int(request.get("per_role", defaults.per_role))
        token_budget = self._bounded_int(
            request, "token_budget", defaults.token_budget, 1, 100_000
        )
        result = self._map().tasks.evidence(
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
            supplied_observations=request.get("supplied_observations"),
        )
        return {"ok": True, "task_evidence": result}

    def _changed_context(
        self, request: dict[str, Any]
    ) -> tuple[str, list[str], int, int, int]:
        task, limit, per_role = self._task_context(request)
        changed = self._string_list(request, "changed_paths", required=True)
        token_budget = self._bounded_int(request, "token_budget", 512, 1, 100_000)
        return task, changed, limit, per_role, token_budget

    def _refresh_context(
        self, request: dict[str, Any]
    ) -> tuple[str, list[str], int, int, int]:
        defaults = POST_CHANGE_DEFAULT_OPTIONS
        return (
            self._task(request),
            self._string_list(request, "changed_paths", required=True),
            self._bounded_int(request, "limit", defaults.limit, 1, 100),
            self._bounded_int(request, "per_role", defaults.per_role, 1, 20),
            self._bounded_int(
                request, "token_budget", defaults.token_budget, 1, 100_000
            ),
        )

    def _change_impact_response(self, request: dict[str, Any]) -> dict[str, Any]:
        defaults = CHANGE_IMPACT_DEFAULT_REQUEST
        options = defaults.options
        task = self._task(request)
        changed = self._string_list(request, "changed_paths", required=True)
        limit = self._bounded_int(request, "limit", defaults.limit, 1, 100)
        per_role = self._bounded_int(request, "per_role", defaults.per_role, 1, 20)
        impact_limit = self._bounded_int(
            request,
            "impact_limit_per_surface",
            options.impact_limit_per_surface,
            1,
            100,
        )
        max_depth = self._bounded_int(request, "max_depth", options.max_depth, 1, 32)
        raw_limit = request.get("project_impact_limit", options.project_impact_limit)
        project_limit = None if raw_limit is None else int(raw_limit)
        if project_limit is not None and not 1 <= project_limit <= 100_000:
            raise ValueError("project_impact_limit must be between 1 and 100000")
        encoding = str(
            request.get("project_impact_encoding", options.project_impact_encoding)
        )
        if encoding not in {"verbose", "compact"}:
            raise ValueError("project_impact_encoding must be verbose or compact")
        result = self._map().changes.task_impact(
            task,
            changed,
            limit=limit,
            per_role=per_role,
            options=ChangeImpactOptions(
                impact_limit_per_surface=impact_limit,
                max_depth=max_depth,
                project_impact_limit=project_limit,
                project_impact_encoding=encoding,
            ),
        )
        return {"ok": True, "task_change_impact": result}

    def _repository_intelligence_query_response(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        task = self._task(request)
        surface = request.get("surface")
        if not isinstance(surface, str) or not surface.strip():
            raise ValueError("surface must be a non-empty string")
        changed = self._string_list(request, "changed_paths", required=False)
        defaults = REPOSITORY_INTELLIGENCE_QUERY_DEFAULT_OPTIONS
        negative_members = request.get("negative_members", defaults.negative_members)
        if "negative_members" in request and (
            not isinstance(negative_members, list)
            or not all(isinstance(item, str) for item in negative_members)
        ):
            raise ValueError("negative_members must be a list of strings")
        previous_map = request.get("previous_map", defaults.previous_map)
        if previous_map is not None and not isinstance(previous_map, dict):
            raise ValueError("previous_map must be an object or null")
        previous_snapshot = request.get("previous_snapshot", defaults.previous_snapshot)
        if previous_snapshot is not None and not isinstance(previous_snapshot, dict):
            raise ValueError("previous_snapshot must be an object or null")
        member_path = request.get("member_path", defaults.member_path)
        if member_path is not None and (
            not isinstance(member_path, str) or not member_path.strip()
        ):
            raise ValueError("member_path must be a non-empty string or null")
        result = self._map().views.query(
            surface,
            task,
            changed,
            options=RepositoryIntelligenceQueryOptions(
                member_path=member_path,
                profile=str(request.get("profile", defaults.profile)),
                presentation=validate_presentation(
                    request.get("presentation", defaults.presentation)
                ),
                negative_members=negative_members,
                previous_map=previous_map,
                previous_snapshot=previous_snapshot,
                limit=self._bounded_int(request, "limit", defaults.limit, 1, 100),
                per_role=self._bounded_int(
                    request, "per_role", defaults.per_role, 1, 20
                ),
                impact_limit_per_surface=self._bounded_int(
                    request,
                    "impact_limit_per_surface",
                    defaults.impact_limit_per_surface,
                    1,
                    100,
                ),
                max_depth=self._bounded_int(
                    request, "max_depth", defaults.max_depth, 1, 32
                ),
                project_impact_limit=self._bounded_int(
                    request,
                    "project_impact_limit",
                    defaults.project_impact_limit,
                    1,
                    100_000,
                ),
            ),
        )
        return {"ok": True, "repository_intelligence_query": result}

    def _post_change_delta_response(self, request: dict[str, Any]) -> dict[str, Any]:
        defaults = TASK_EVIDENCE_DEFAULT_OPTIONS
        task = self._task(request)
        changed = self._string_list(request, "changed_paths", required=True)
        limit = self._bounded_int(request, "limit", defaults.limit, 1, 100)
        per_role = self._bounded_int(request, "per_role", defaults.per_role, 1, 20)
        previous_evidence = request.get("previous_evidence")
        if not isinstance(previous_evidence, dict):
            raise ValueError("previous_evidence must be an object")
        token_budget = self._bounded_int(
            request, "token_budget", defaults.token_budget, 1, 100_000
        )
        result = self._map().changes.task_delta(
            task,
            changed,
            previous_evidence=previous_evidence,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )
        return {"ok": True, "post_change_delta": result}

    def _refresh_delta_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, changed, limit, per_role, budget = self._refresh_context(request)
        defaults = POST_CHANGE_DEFAULT_OPTIONS
        result = self._map().changes.refresh_delta(
            task,
            changed,
            options=PostChangeOptions(
                previous_edit_path=request.get(
                    "previous_edit_path", defaults.previous_edit_path
                ),
                previous_verify_path=request.get(
                    "previous_verify_path", defaults.previous_verify_path
                ),
                limit=limit,
                per_role=per_role,
                token_budget=budget,
            ),
        )
        return {"ok": True, "refresh_delta": result}

    def _refresh_brief_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, changed, limit, per_role, budget = self._refresh_context(request)
        result = self._map().changes.refresh_brief(
            task,
            changed,
            limit=limit,
            per_role=per_role,
            token_budget=budget,
        )
        return {"ok": True, "refresh_brief": result}

    def _refresh_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, changed, limit, per_role, budget = self._refresh_context(request)
        result = self._map().changes.refresh(
            task,
            changed,
            limit=limit,
            per_role=per_role,
            token_budget=budget,
        )
        return {"ok": True, "refresh": result}

    def _decision_brief_response(self, request: dict[str, Any]) -> dict[str, Any]:
        defaults = TASK_DECISION_DEFAULT_OPTIONS
        task = self._task(request)
        limit = self._bounded_int(request, "limit", defaults.limit, 1, 100)
        per_role = int(request.get("per_role", defaults.per_role))
        budget = self._bounded_int(
            request, "token_budget", defaults.token_budget, 1, 100_000
        )
        result = self._map().tasks.decision_brief(
            task, limit=limit, per_role=per_role, token_budget=budget
        )
        return {"ok": True, "decision_brief": result}

    def _task_action_brief_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, limit, per_role = self._task_action_context(request)
        raw_budget = request.get(
            "token_budget", TASK_ACTION_BRIEF_BUDGET_DEFAULT_OPTIONS.token_budget
        )
        budget = None if raw_budget is None else int(raw_budget)
        if budget is not None and not 1 <= budget <= 100_000:
            raise ValueError("token_budget must be between 1 and 100000")
        result = self._map().tasks.action_brief(
            task, limit=limit, per_role=per_role, token_budget=budget
        )
        return {"ok": True, "task_action_brief": result}

    def _budget_sweep_response(self, request: dict[str, Any]) -> dict[str, Any]:
        defaults = TASK_DECISION_DEFAULT_OPTIONS
        task = self._task(request)
        limit = self._bounded_int(request, "limit", defaults.limit, 1, 100)
        per_role = int(request.get("per_role", defaults.per_role))
        budgets = request.get(
            "budgets", list(TASK_DECISION_BRIEF_BUDGET_SWEEP_DEFAULTS)
        )
        if (
            not isinstance(budgets, list)
            or not budgets
            or not all(isinstance(value, int) for value in budgets)
        ):
            raise ValueError("budgets must be a non-empty list of integers")
        result = self._map().tasks.decision_brief_budget_sweep(
            task, budgets=budgets, limit=limit, per_role=per_role
        )
        return {"ok": True, "budget_sweep": result}

    def _decision_packet_response(self, request: dict[str, Any]) -> dict[str, Any]:
        defaults = TASK_DECISION_DEFAULT_OPTIONS
        task = self._task(request)
        limit = self._bounded_int(request, "limit", defaults.limit, 1, 100)
        per_role = int(request.get("per_role", defaults.per_role))
        budget = self._bounded_int(
            request, "token_budget", defaults.token_budget, 1, 100_000
        )
        result = self._map().tasks.decision_packet(
            task, limit=limit, per_role=per_role, token_budget=budget
        )
        return {"ok": True, "decision_packet": result}

    def _stop_response(self, _request: dict[str, Any]) -> dict[str, Any]:
        if self._server is not None:
            import threading

            threading.Thread(target=self._server.shutdown, daemon=True).start()
        return {"ok": True}

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("protocol") != PROTOCOL:
            raise ValueError("unsupported protocol version")
        op = request.get("op")
        route = _SERVICE_ROUTES.get(op) if isinstance(op, str) else None
        if route is None:
            raise ValueError(f"unsupported operation: {op!r}")

        route.admit()
        result_mode = (
            _request_result_mode(route.operation, request)
            if route.operation is not None
            else None
        )
        handler = getattr(self, route.handler_name, None)
        if not callable(handler):
            raise RuntimeError(
                f"CodeMap service route handler is unavailable: {route.handler_name}"
            )

        self._requests += 1
        response = handler(request)
        if not _is_wire_object(response):
            raise RuntimeError("CodeMap service handler must return a JSON object")
        route.validate_response(response, result_mode=result_mode)
        return response

    def _prepare_socket(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.socket_path.parent, 0o700)
        if self.socket_path.exists() or self.socket_path.is_socket():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(0.2)
                probe.connect(str(self.socket_path))
            except OSError:
                self.socket_path.unlink(missing_ok=True)
            else:
                raise RuntimeError(
                    f"CodeMap service already running at {self.socket_path}"
                )
            finally:
                probe.close()

    def serve_forever(self) -> None:
        import time

        if _UNIX_STREAM_SERVER is None:
            raise RuntimeError(
                "Hashmarks CodeMap service requires Unix-domain socket server support"
            )
        self._prepare_socket()
        with CodeMap(self.workspace) as codemap:
            self._codemap = codemap
            started = time.perf_counter()
            codemap.index.sync()
            self._initial_sync_ms = (time.perf_counter() - started) * 1000.0
            self._syncs = 1
            server = _Server(str(self.socket_path), _Handler)
            server.codemap_service = self
            self._server = server
            try:
                with contextlib.suppress(OSError):
                    os.chmod(self.socket_path, 0o600)
                server.serve_forever(poll_interval=0.05)
            finally:
                server.server_close()
                self._server = None
                self._codemap = None
                self.socket_path.unlink(missing_ok=True)


class CodeMapServiceClient:
    def __init__(
        self,
        workspace: str | Path,
        *,
        socket_path: str | Path | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.workspace = canonical_host_path(workspace)
        self.socket_path = (
            default_codemap_socket(self.workspace)
            if socket_path is None
            else canonical_host_path(socket_path)
        )
        self.timeout = timeout

    def _connect_to_service(self, sock: socket.socket) -> None:
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                sock.connect(str(self.socket_path))
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "timed out waiting for CodeMap service admission"
                    ) from None
                time.sleep(0.005)

    def request(self, op: str, **payload: object) -> dict[str, object]:
        message = {"protocol": PROTOCOL, "op": op, **payload}
        raw = (
            json.dumps(message, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            self._connect_to_service(sock)
            sock.sendall(raw)
            chunks = bytearray()
            while len(chunks) <= MAX_RESPONSE:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.extend(chunk)
                if b"\n" in chunk:
                    break
        finally:
            sock.close()
        if len(chunks) > MAX_RESPONSE:
            raise RuntimeError("CodeMap service response exceeded size limit")
        line = bytes(chunks).split(b"\n", 1)[0]
        response = json.loads(line)
        if not isinstance(response, dict) or not response.get("ok"):
            raise RuntimeError(
                str(response.get("error", "CodeMap service request failed"))
                if isinstance(response, dict)
                else "invalid CodeMap service response"
            )
        return response

    def _canonical_payload(self, op: str, **payload: object) -> dict[str, object]:
        """Qualify a semantic reply using the existing route/schema authority."""
        route = _SERVICE_ROUTES[op]
        if route.operation is None or route.response_key is None:
            raise RuntimeError(f"CodeMap service route {op} is not semantic")
        result_mode = _request_result_mode(route.operation, payload)
        response = self.request(op, **payload)
        return dict(
            validate_operation_response(
                route.operation, response.get(route.response_key), mode=result_mode
            )
        )

    def status(self) -> dict[str, Any]:
        return self.request("status")

    def sync(self) -> dict[str, Any]:
        return self.request("sync")

    def repository_declarations(
        self,
        groups: list[dict[str, object]],
        *,
        previous_observation: dict[str, object] | None = None,
        result_mode: str = operation_default_mode("repository_declarations"),
        source_selection: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Project declarations or select registered source providers over IPC."""
        return self._canonical_payload(
            "repository_declarations",
            groups=groups,
            previous_observation=previous_observation,
            result_mode=result_mode,
            source_selection=source_selection,
        )

    def source_range_receipt(
        self,
        path: str,
        *,
        start_byte: int,
        end_byte: int,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        """Read an exact range; omitted bounds retain the Source owner's defaults."""
        options = {} if max_bytes is None else {"max_bytes": max_bytes}
        return self._canonical_payload(
            "source_range_receipt",
            path=path,
            start_byte=start_byte,
            end_byte=end_byte,
            **options,
        )

    def source_ecmascript(
        self,
        path: str,
        *,
        limit: int | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        """Transport bounded ECMAScript source facts from their existing owner."""
        options = {
            name: value
            for name, value in {"limit": limit, "max_bytes": max_bytes}.items()
            if value is not None
        }
        return self._canonical_payload("source_ecmascript", path=path, **options)

    def verification_membership(self, report: object) -> dict[str, object]:
        """Bind a supplied collection report without running its producer."""
        return self._canonical_payload("verification_membership", report=report)

    def repository_findings(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return self._canonical_payload("repository_findings", **payload)

    def concurrency_risk_findings(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return self._canonical_payload("concurrency_risk", **payload)

    def verification_ownership_graph(
        self,
        task: str,
        *,
        limit: int = VERIFICATION_RELEVANCE_DEFAULTS.limit,
        candidate_limit: int = VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit,
    ) -> dict[str, Any]:
        return self._canonical_payload(
            "verification_ownership",
            task=task,
            limit=limit,
            candidate_limit=candidate_limit,
        )

    def repository_ownership_graph(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        """Return repository ownership evidence over the stable v0.11 wire contract."""
        payload = {} if paths is None else {"paths": list(paths)}
        return self._canonical_payload("authority_ownership", **payload)

    def cache_ownership_findings(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return self._canonical_payload("cache_ownership", **payload)

    def cache_invalidation_ownership_graph(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return self._canonical_payload("cache_invalidation_ownership", **payload)

    def import_ownership_findings(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return self._canonical_payload("import_ownership", **payload)

    def find_task(self, task: str, *, limit: int = 20) -> list[dict[str, Any]]:
        hits = self.request("find_task", task=task, limit=limit).get("hits")
        if not isinstance(hits, list):
            raise RuntimeError("invalid find_task service response: expected an array")
        rows: list[dict[str, object]] = []
        for hit in hits:
            if not _is_wire_object(hit):
                raise RuntimeError(
                    "invalid find_task service response: expected objects"
                )
            rows.append(hit)
        return rows

    def task_action_map(
        self,
        task: str,
        *,
        limit: int = TASK_ACTION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_ACTION_DEFAULT_OPTIONS.per_role,
    ) -> TaskActionMap:
        return read_task_action_map(
            self.request(
                "task_action_map",
                task=task,
                limit=limit,
                per_role=per_role,
            )["action_map"]
        )

    def verification_relevance(
        self,
        task: str,
        *,
        limit: int = VERIFICATION_RELEVANCE_DEFAULTS.limit,
        candidate_limit: int = VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit,
    ) -> dict[str, Any]:
        return self._canonical_payload(
            "verification_relevance",
            task=task,
            limit=limit,
            candidate_limit=candidate_limit,
        )

    def ownership_relation_graph(
        self,
        task: str,
        start_path: str,
        *,
        max_depth: int = OWNERSHIP_RELATION_DEFAULT_OPTIONS.max_depth,
    ) -> OwnershipRelationGraph:
        return read_ownership_relation_graph(
            self.request(
                "ownership_relation_graph",
                task=task,
                start_path=start_path,
                max_depth=max_depth,
            )["ownership_relation_graph"]
        )

    def task_decision_packet(
        self,
        task: str,
        *,
        limit: int = TASK_DECISION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_DECISION_DEFAULT_OPTIONS.per_role,
        token_budget: int = TASK_DECISION_DEFAULT_OPTIONS.token_budget,
    ) -> dict[str, Any]:
        return self._canonical_payload(
            "task_decision_packet",
            task=task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )

    def task_decision_brief(
        self,
        task: str,
        *,
        limit: int = TASK_DECISION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_DECISION_DEFAULT_OPTIONS.per_role,
        token_budget: int = TASK_DECISION_DEFAULT_OPTIONS.token_budget,
    ) -> dict[str, Any]:
        return self._canonical_payload(
            "task_decision_brief",
            task=task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )

    def task_action_brief(
        self,
        task: str,
        *,
        limit: int = TASK_ACTION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_ACTION_DEFAULT_OPTIONS.per_role,
        token_budget: int | None = (
            TASK_ACTION_BRIEF_BUDGET_DEFAULT_OPTIONS.token_budget
        ),
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"task": task, "limit": limit, "per_role": per_role}
        if token_budget is not None:
            payload["token_budget"] = token_budget
        return self._canonical_payload("task_action_brief", **payload)

    def task_evidence(
        self,
        task: str,
        *,
        limit: int = TASK_EVIDENCE_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_EVIDENCE_DEFAULT_OPTIONS.per_role,
        token_budget: int = TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
        supplied_observations: list[dict[str, Any]] | None = None,
    ) -> TaskEvidencePacket:
        return read_task_evidence(
            self.request(
                "task_evidence",
                task=task,
                limit=limit,
                per_role=per_role,
                token_budget=token_budget,
                supplied_observations=supplied_observations,
            )["task_evidence"]
        )

    def task_decision_brief_budget_sweep(
        self,
        task: str,
        *,
        budgets: tuple[int, ...] | list[int] = (
            TASK_DECISION_BRIEF_BUDGET_SWEEP_DEFAULTS
        ),
        limit: int = TASK_DECISION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_DECISION_DEFAULT_OPTIONS.per_role,
    ) -> dict[str, Any]:
        return self._canonical_payload(
            "task_decision_brief_budget_sweep",
            task=task,
            budgets=list(budgets),
            limit=limit,
            per_role=per_role,
        )

    def repository_intelligence_query(
        self,
        surface: str,
        task: str,
        changed_paths: tuple[str, ...] | list[str] = (),
        *,
        options: RepositoryIntelligenceQueryOptions = (
            REPOSITORY_INTELLIGENCE_QUERY_DEFAULT_OPTIONS
        ),
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "surface": surface,
            "task": task,
            "changed_paths": list(changed_paths),
            "profile": options.profile,
            "presentation": validate_presentation(options.presentation),
            "negative_members": list(options.negative_members),
            "limit": options.limit,
            "per_role": options.per_role,
            "impact_limit_per_surface": options.impact_limit_per_surface,
            "max_depth": options.max_depth,
            "project_impact_limit": options.project_impact_limit,
        }
        if options.member_path is not None:
            payload["member_path"] = options.member_path
        if options.previous_map is not None:
            payload["previous_map"] = options.previous_map
        if options.previous_snapshot is not None:
            payload["previous_snapshot"] = options.previous_snapshot
        result = self._canonical_payload("repository_intelligence_query", **payload)
        if options.presentation != "none":
            projection = result.get("presentation")
            if (
                not isinstance(projection, dict)
                or projection.get("format") != options.presentation
            ):
                raise ValueError(
                    "unsupported presentation: service did not honor requested format"
                )
        return result

    def task_change_impact(
        self,
        task: str,
        changed_paths: tuple[str, ...] | list[str],
        *,
        limit: int = CHANGE_IMPACT_DEFAULT_REQUEST.limit,
        per_role: int = CHANGE_IMPACT_DEFAULT_REQUEST.per_role,
        options: ChangeImpactOptions = CHANGE_IMPACT_DEFAULT_REQUEST.options,
    ) -> dict[str, Any]:
        return self._canonical_payload(
            "task_change_impact",
            task=task,
            changed_paths=list(changed_paths),
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=options.impact_limit_per_surface,
            max_depth=options.max_depth,
            project_impact_limit=options.project_impact_limit,
            project_impact_encoding=options.project_impact_encoding,
        )

    def task_post_change_delta(
        self,
        task: str,
        changed_paths: tuple[str, ...] | list[str],
        *,
        previous_evidence: PreviousTaskEvidence,
        limit: int = TASK_EVIDENCE_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_EVIDENCE_DEFAULT_OPTIONS.per_role,
        token_budget: int = TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
    ) -> TaskPostChangeDelta:
        return read_post_change_delta(
            self.request(
                "task_post_change_delta",
                task=task,
                changed_paths=list(changed_paths),
                previous_evidence=previous_evidence,
                limit=limit,
                per_role=per_role,
                token_budget=token_budget,
            )["post_change_delta"]
        )

    def refresh_after_change_delta(
        self,
        task: str,
        changed_paths: tuple[str, ...] | list[str],
        *,
        options: PostChangeOptions = POST_CHANGE_DEFAULT_OPTIONS,
    ) -> dict[str, Any]:
        return self._canonical_payload(
            "refresh_after_change_delta",
            task=task,
            changed_paths=list(changed_paths),
            previous_edit_path=options.previous_edit_path,
            previous_verify_path=options.previous_verify_path,
            limit=options.limit,
            per_role=options.per_role,
            token_budget=options.token_budget,
        )

    def refresh_after_change_brief(
        self,
        task: str,
        changed_paths: tuple[str, ...] | list[str],
        *,
        limit: int = POST_CHANGE_DEFAULT_OPTIONS.limit,
        per_role: int = POST_CHANGE_DEFAULT_OPTIONS.per_role,
        token_budget: int = POST_CHANGE_DEFAULT_OPTIONS.token_budget,
    ) -> dict[str, Any]:
        return self._canonical_payload(
            "refresh_after_change_brief",
            task=task,
            changed_paths=list(changed_paths),
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )

    def refresh_after_change(
        self,
        task: str,
        changed_paths: tuple[str, ...] | list[str],
        *,
        limit: int = POST_CHANGE_DEFAULT_OPTIONS.limit,
        per_role: int = POST_CHANGE_DEFAULT_OPTIONS.per_role,
        token_budget: int = POST_CHANGE_DEFAULT_OPTIONS.token_budget,
    ) -> dict[str, Any]:
        return self._canonical_payload(
            "refresh_after_change",
            task=task,
            changed_paths=list(changed_paths),
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )

    def stop(self) -> None:
        self.request("stop")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve one warm Hashmarks CodeMap to many local consumers"
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--socket", type=Path)
    args = parser.parse_args()
    CodeMapService(args.workspace, socket_path=args.socket).serve_forever()


if __name__ == "__main__":
    main()
