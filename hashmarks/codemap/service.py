from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import socketserver
from pathlib import Path
from typing import Any

from hashmarks.client import default_runtime_dir
from hashmarks.ipc_boundary import dispatch_json_request
from hashmarks.paths import canonical_host_path

from .change_impact import ChangeImpactOptions
from .engine import CodeMap

PROTOCOL = "hashmarks.codemap-service.v2"
MAX_REQUEST = 1024 * 1024
MAX_RESPONSE = 8 * 1024 * 1024


def default_codemap_socket(workspace: str | Path) -> Path:
    return default_runtime_dir(workspace) / "codemap.sock"


class _Server(socketserver.UnixStreamServer):
    allow_reuse_address = False
    request_queue_size = 128


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        service: CodeMapService = self.server.codemap_service  # type: ignore[attr-defined]
        raw = self.rfile.readline(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            service._write(
                self.wfile, {"ok": False, "error": "request exceeded size limit"}
            )
            return
        response = dispatch_json_request(raw, service.dispatch)
        service._write(self.wfile, response)


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
    def _write(stream, response: dict[str, Any]) -> None:
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
        result = self._map().sync()
        elapsed = (time.perf_counter() - started) * 1000.0
        self._syncs += 1
        return {"ok": True, "elapsed_ms": elapsed, "result": result.as_dict()}

    def _repository_findings_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "repository_findings": self._map().repository_findings(
                self._paths(request)
            ),
        }

    def _import_ownership_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "import_ownership": self._map().import_ownership_findings(
                self._paths(request)
            ),
        }

    def _cache_ownership_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "cache_ownership": self._map().cache_ownership_findings(
                self._paths(request)
            ),
        }

    def _cache_invalidation_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "cache_invalidation_ownership": self._map().cache_invalidation_ownership_graph(
                self._paths(request)
            ),
        }

    def _authority_ownership_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "authority_ownership": self._map().repository_ownership_graph(
                self._paths(request)
            ),
        }

    def _concurrency_risk_response(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "concurrency_risk": self._map().concurrency_risk_findings(
                self._paths(request)
            ),
        }

    def _verification_ownership_response(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        task = self._task(request)
        limit = self._bounded_int(request, "limit", 20, 1, 100)
        candidate_limit = self._bounded_int(request, "candidate_limit", 8, 1, 16)
        graph = self._map().verification_ownership_graph(
            task, limit=limit, candidate_limit=candidate_limit
        )
        return {"ok": True, "verification_ownership": graph}

    def _find_task_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task = self._task(request)
        limit = self._bounded_int(request, "limit", 20, 1, 100)
        return {
            "ok": True,
            "hits": [hit.as_dict() for hit in self._map().find_task(task, limit=limit)],
        }

    def _task_context(self, request: dict[str, Any]) -> tuple[str, int, int]:
        return (
            self._task(request),
            self._bounded_int(request, "limit", 20, 1, 100),
            int(request.get("per_role", 3)),
        )

    def _task_action_map_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, limit, per_role = self._task_context(request)
        result = self._map().task_action_map(task, limit=limit, per_role=per_role)
        return {"ok": True, "action_map": result}

    def _verification_relevance_response(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        task = self._task(request)
        limit = self._bounded_int(request, "limit", 20, 1, 100)
        candidate_limit = self._bounded_int(request, "candidate_limit", 8, 1, 16)
        result = self._map().verification_relevance(
            task, limit=limit, candidate_limit=candidate_limit
        )
        return {"ok": True, "verification_relevance": result}

    def _ownership_relation_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task = self._task(request)
        start_path = request.get("start_path")
        if not isinstance(start_path, str) or not start_path.strip():
            raise ValueError("start_path must be a non-empty string")
        max_depth = int(request.get("max_depth", 2))
        result = self._map().ownership_relation_graph(
            task, start_path, max_depth=max_depth
        )
        return {"ok": True, "ownership_relation_graph": result}

    def _task_evidence_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, limit, per_role = self._task_context(request)
        token_budget = self._bounded_int(request, "token_budget", 1536, 1, 100_000)
        result = self._map().task_evidence(
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )
        return {"ok": True, "task_evidence": result}

    def _changed_context(
        self, request: dict[str, Any]
    ) -> tuple[str, list[str], int, int, int]:
        task, limit, per_role = self._task_context(request)
        changed = self._string_list(request, "changed_paths", required=True)
        token_budget = self._bounded_int(request, "token_budget", 512, 1, 100_000)
        return task, changed, limit, per_role, token_budget

    def _change_impact_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, changed, limit, per_role, _budget = self._changed_context(request)
        impact_limit = self._bounded_int(request, "impact_limit_per_surface", 6, 1, 100)
        max_depth = self._bounded_int(request, "max_depth", 4, 1, 32)
        raw_limit = request.get("project_impact_limit")
        project_limit = None if raw_limit is None else int(raw_limit)
        if project_limit is not None and not 1 <= project_limit <= 100_000:
            raise ValueError("project_impact_limit must be between 1 and 100000")
        encoding = str(request.get("project_impact_encoding", "verbose"))
        if encoding not in {"verbose", "compact"}:
            raise ValueError("project_impact_encoding must be verbose or compact")
        result = self._map().task_change_impact(
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
        negative_members = self._string_list(
            request, "negative_members", required=False
        )
        previous_map = request.get("previous_map")
        if previous_map is not None and not isinstance(previous_map, dict):
            raise ValueError("previous_map must be an object or null")
        previous_snapshot = request.get("previous_snapshot")
        if previous_snapshot is not None and not isinstance(previous_snapshot, dict):
            raise ValueError("previous_snapshot must be an object or null")
        member_path = request.get("member_path")
        if member_path is not None and (
            not isinstance(member_path, str) or not member_path.strip()
        ):
            raise ValueError("member_path must be a non-empty string or null")
        result = self._map().repository_intelligence_query(
            surface,
            task,
            changed,
            member_path=member_path,
            profile=str(request.get("profile", "compact")),
            negative_members=negative_members,
            previous_map=previous_map,
            previous_snapshot=previous_snapshot,
            limit=self._bounded_int(request, "limit", 20, 1, 100),
            per_role=self._bounded_int(request, "per_role", 3, 1, 20),
            impact_limit_per_surface=self._bounded_int(
                request, "impact_limit_per_surface", 4, 1, 100
            ),
            max_depth=self._bounded_int(request, "max_depth", 3, 1, 32),
            project_impact_limit=self._bounded_int(
                request, "project_impact_limit", 12, 1, 100000
            ),
        )
        return {"ok": True, "repository_intelligence_query": result}

    def _post_change_delta_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, changed, limit, per_role, _budget = self._changed_context(request)
        previous_evidence = request.get("previous_evidence")
        if not isinstance(previous_evidence, dict):
            raise ValueError("previous_evidence must be an object")
        token_budget = self._bounded_int(request, "token_budget", 1536, 1, 100_000)
        result = self._map().task_post_change_delta(
            task,
            changed,
            previous_evidence=previous_evidence,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )
        return {"ok": True, "post_change_delta": result}

    def _refresh_delta_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, changed, limit, per_role, budget = self._changed_context(request)
        result = self._map().refresh_after_change_delta(
            task,
            changed,
            previous_edit_path=request.get("previous_edit_path"),
            previous_verify_path=request.get("previous_verify_path"),
            limit=limit,
            per_role=per_role,
            token_budget=budget,
        )
        return {"ok": True, "refresh_delta": result}

    def _refresh_brief_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, changed, limit, per_role, budget = self._changed_context(request)
        result = self._map().refresh_after_change_brief(
            task,
            changed,
            limit=limit,
            per_role=per_role,
            token_budget=budget,
        )
        return {"ok": True, "refresh_brief": result}

    def _refresh_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, changed, limit, per_role, budget = self._changed_context(request)
        result = self._map().refresh_after_change(
            task,
            changed,
            limit=limit,
            per_role=per_role,
            token_budget=budget,
        )
        return {"ok": True, "refresh": result}

    def _decision_brief_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, limit, per_role = self._task_context(request)
        budget = self._bounded_int(request, "token_budget", 512, 1, 100_000)
        result = self._map().task_decision_brief(
            task, limit=limit, per_role=per_role, token_budget=budget
        )
        return {"ok": True, "decision_brief": result}

    def _task_action_brief_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, limit, per_role = self._task_context(request)
        raw_budget = request.get("token_budget")
        budget = None if raw_budget is None else int(raw_budget)
        if budget is not None and not 1 <= budget <= 100_000:
            raise ValueError("token_budget must be between 1 and 100000")
        result = self._map().task_action_brief(
            task, limit=limit, per_role=per_role, token_budget=budget
        )
        return {"ok": True, "task_action_brief": result}

    def _budget_sweep_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, limit, per_role = self._task_context(request)
        budgets = request.get("budgets", [64, 128, 192, 256, 384, 512])
        if (
            not isinstance(budgets, list)
            or not budgets
            or not all(isinstance(value, int) for value in budgets)
        ):
            raise ValueError("budgets must be a non-empty list of integers")
        result = self._map().task_decision_brief_budget_sweep(
            task, budgets=budgets, limit=limit, per_role=per_role
        )
        return {"ok": True, "budget_sweep": result}

    def _decision_packet_response(self, request: dict[str, Any]) -> dict[str, Any]:
        task, limit, per_role = self._task_context(request)
        budget = self._bounded_int(request, "token_budget", 512, 1, 100_000)
        result = self._map().task_decision_packet(
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
        self._requests += 1
        handlers = {
            "status": self._status_response,
            "sync": self._sync_response,
            "repository_findings": self._repository_findings_response,
            "import_ownership": self._import_ownership_response,
            "cache_ownership": self._cache_ownership_response,
            "cache_invalidation_ownership": self._cache_invalidation_response,
            "authority_ownership": self._authority_ownership_response,
            "concurrency_risk": self._concurrency_risk_response,
            "verification_ownership": self._verification_ownership_response,
            "find_task": self._find_task_response,
            "task_action_map": self._task_action_map_response,
            "verification_relevance": self._verification_relevance_response,
            "ownership_relation_graph": self._ownership_relation_response,
            "task_evidence": self._task_evidence_response,
            "task_change_impact": self._change_impact_response,
            "repository_intelligence_query": self._repository_intelligence_query_response,
            "task_post_change_delta": self._post_change_delta_response,
            "refresh_after_change_delta": self._refresh_delta_response,
            "refresh_after_change_brief": self._refresh_brief_response,
            "refresh_after_change": self._refresh_response,
            "task_decision_brief": self._decision_brief_response,
            "task_action_brief": self._task_action_brief_response,
            "task_decision_brief_budget_sweep": self._budget_sweep_response,
            "task_decision_packet": self._decision_packet_response,
            "stop": self._stop_response,
        }
        op = request.get("op")
        handler = handlers.get(op)
        if handler is None:
            raise ValueError(f"unsupported operation: {op!r}")
        return handler(request)

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

        self._prepare_socket()
        with CodeMap(self.workspace) as codemap:
            self._codemap = codemap
            started = time.perf_counter()
            codemap.sync()
            self._initial_sync_ms = (time.perf_counter() - started) * 1000.0
            self._syncs = 1
            server = _Server(str(self.socket_path), _Handler)
            server.codemap_service = self  # type: ignore[attr-defined]
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

    def request(self, op: str, **payload: Any) -> dict[str, Any]:
        message = {"protocol": PROTOCOL, "op": op, **payload}
        raw = (
            json.dumps(message, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
        import time

        deadline = time.monotonic() + self.timeout
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            while True:
                try:
                    sock.connect(str(self.socket_path))
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "timed out waiting for CodeMap service admission"
                        ) from None
                    time.sleep(0.005)
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

    def status(self) -> dict[str, Any]:
        return self.request("status")

    def sync(self) -> dict[str, Any]:
        return self.request("sync")

    def repository_findings(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return dict(
            self.request("repository_findings", **payload)["repository_findings"]
        )

    def concurrency_risk_findings(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return dict(self.request("concurrency_risk", **payload)["concurrency_risk"])

    def verification_ownership_graph(
        self, task: str, *, limit: int = 20, candidate_limit: int = 8
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "verification_ownership",
                task=task,
                limit=limit,
                candidate_limit=candidate_limit,
            )["verification_ownership"]
        )

    def repository_ownership_graph(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        """Return repository ownership evidence over the stable v0.11 wire contract."""
        payload = {} if paths is None else {"paths": list(paths)}
        return dict(
            self.request("authority_ownership", **payload)["authority_ownership"]
        )

    def cache_ownership_findings(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return dict(self.request("cache_ownership", **payload)["cache_ownership"])

    def cache_invalidation_ownership_graph(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return dict(
            self.request("cache_invalidation_ownership", **payload)[
                "cache_invalidation_ownership"
            ]
        )

    def import_ownership_findings(
        self, paths: tuple[str, ...] | list[str] | None = None
    ) -> dict[str, Any]:
        payload = {} if paths is None else {"paths": list(paths)}
        return dict(self.request("import_ownership", **payload)["import_ownership"])

    def find_task(self, task: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return list(self.request("find_task", task=task, limit=limit)["hits"])

    def task_action_map(
        self, task: str, *, limit: int = 20, per_role: int = 3
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "task_action_map",
                task=task,
                limit=limit,
                per_role=per_role,
            )["action_map"]
        )

    def verification_relevance(
        self, task: str, *, limit: int = 20, candidate_limit: int = 8
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "verification_relevance",
                task=task,
                limit=limit,
                candidate_limit=candidate_limit,
            )["verification_relevance"]
        )

    def ownership_relation_graph(
        self, task: str, start_path: str, *, max_depth: int = 2
    ) -> dict[str, Any]:
        return dict(
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
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 512,
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "task_decision_packet",
                task=task,
                limit=limit,
                per_role=per_role,
                token_budget=token_budget,
            )["decision_packet"]
        )

    def task_decision_brief(
        self,
        task: str,
        *,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 512,
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "task_decision_brief",
                task=task,
                limit=limit,
                per_role=per_role,
                token_budget=token_budget,
            )["decision_brief"]
        )

    def task_action_brief(
        self,
        task: str,
        *,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"task": task, "limit": limit, "per_role": per_role}
        if token_budget is not None:
            payload["token_budget"] = token_budget
        return dict(self.request("task_action_brief", **payload)["task_action_brief"])

    def task_evidence(
        self,
        task: str,
        *,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 1536,
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "task_evidence",
                task=task,
                limit=limit,
                per_role=per_role,
                token_budget=token_budget,
            )["task_evidence"]
        )

    def task_decision_brief_budget_sweep(
        self,
        task: str,
        *,
        budgets: tuple[int, ...] | list[int] = (64, 128, 192, 256, 384, 512),
        limit: int = 20,
        per_role: int = 3,
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "task_decision_brief_budget_sweep",
                task=task,
                budgets=list(budgets),
                limit=limit,
                per_role=per_role,
            )["budget_sweep"]
        )

    def repository_intelligence_query(
        self,
        surface: str,
        task: str,
        changed_paths: tuple[str, ...] | list[str] = (),
        *,
        member_path: str | None = None,
        profile: str = "compact",
        negative_members: tuple[str, ...] | list[str] = (),
        previous_map: dict[str, Any] | None = None,
        previous_snapshot: dict[str, Any] | None = None,
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 4,
        max_depth: int = 3,
        project_impact_limit: int = 12,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "surface": surface,
            "task": task,
            "changed_paths": list(changed_paths),
            "profile": profile,
            "negative_members": list(negative_members),
            "limit": limit,
            "per_role": per_role,
            "impact_limit_per_surface": impact_limit_per_surface,
            "max_depth": max_depth,
            "project_impact_limit": project_impact_limit,
        }
        if member_path is not None:
            payload["member_path"] = member_path
        if previous_map is not None:
            payload["previous_map"] = previous_map
        if previous_snapshot is not None:
            payload["previous_snapshot"] = previous_snapshot
        return dict(
            self.request(
                "repository_intelligence_query",
                **payload,
            )["repository_intelligence_query"]
        )

    def task_change_impact(
        self,
        task: str,
        changed_paths: tuple[str, ...] | list[str],
        *,
        limit: int = 20,
        per_role: int = 3,
        options: ChangeImpactOptions = ChangeImpactOptions(),
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "task_change_impact",
                task=task,
                changed_paths=list(changed_paths),
                limit=limit,
                per_role=per_role,
                impact_limit_per_surface=options.impact_limit_per_surface,
                max_depth=options.max_depth,
                project_impact_limit=options.project_impact_limit,
                project_impact_encoding=options.project_impact_encoding,
            )["task_change_impact"]
        )

    def task_post_change_delta(
        self,
        task: str,
        changed_paths: tuple[str, ...] | list[str],
        *,
        previous_evidence: dict[str, Any],
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 1536,
    ) -> dict[str, Any]:
        return dict(
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
        previous_edit_path: str | None = None,
        previous_verify_path: str | None = None,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 512,
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "refresh_after_change_delta",
                task=task,
                changed_paths=list(changed_paths),
                previous_edit_path=previous_edit_path,
                previous_verify_path=previous_verify_path,
                limit=limit,
                per_role=per_role,
                token_budget=token_budget,
            )["refresh_delta"]
        )

    def refresh_after_change_brief(
        self,
        task: str,
        changed_paths: tuple[str, ...] | list[str],
        *,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 512,
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "refresh_after_change_brief",
                task=task,
                changed_paths=list(changed_paths),
                limit=limit,
                per_role=per_role,
                token_budget=token_budget,
            )["refresh_brief"]
        )

    def refresh_after_change(
        self,
        task: str,
        changed_paths: tuple[str, ...] | list[str],
        *,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 512,
    ) -> dict[str, Any]:
        return dict(
            self.request(
                "refresh_after_change",
                task=task,
                changed_paths=list(changed_paths),
                limit=limit,
                per_role=per_role,
                token_budget=token_budget,
            )["refresh"]
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
