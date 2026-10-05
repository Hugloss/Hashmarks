from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from hashmarks.codemap import service as service_module
from hashmarks.codemap.post_change import PostChangeOptions
from hashmarks.codemap.repository_intelligence_query import (
    RepositoryIntelligenceQueryOptions,
)


class _FakeSocket:
    def __init__(self, chunks: list[bytes], *, blocked_connects: int = 0) -> None:
        self.chunks = iter(chunks)
        self.blocked_connects = blocked_connects
        self.sent = b""
        self.closed = False
        self.connects = 0

    def settimeout(self, _timeout: float) -> None:
        pass

    def connect(self, _path: str) -> None:
        self.connects += 1
        if self.connects <= self.blocked_connects:
            raise BlockingIOError

    def sendall(self, data: bytes) -> None:
        self.sent = data

    def recv(self, _size: int) -> bytes:
        return next(self.chunks, b"")

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_socket(monkeypatch: pytest.MonkeyPatch) -> Iterator[_FakeSocket]:
    sock = _FakeSocket([b'{"ok":true,"value":3}\n'])
    monkeypatch.setattr(service_module.socket, "socket", lambda *_args: sock)
    yield sock
    assert sock.closed


def test_client_request_sends_protocol_and_reads_success(
    tmp_path: Path, fake_socket: _FakeSocket
) -> None:
    client = service_module.CodeMapServiceClient(tmp_path)

    assert client.request("example", task="inspect") == {"ok": True, "value": 3}
    assert json.loads(fake_socket.sent) == {
        "protocol": service_module.PROTOCOL,
        "op": "example",
        "task": "inspect",
    }


@pytest.mark.parametrize(
    ("chunks", "message"),
    [
        ([b'{"ok":false,"error":"bad request"}\n'], "bad request"),
        ([b"[]\n"], "invalid CodeMap service response"),
    ],
)
def test_client_request_rejects_error_responses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    chunks: list[bytes],
    message: str,
) -> None:
    sock = _FakeSocket(chunks)
    monkeypatch.setattr(service_module.socket, "socket", lambda *_args: sock)

    with pytest.raises(RuntimeError, match=message):
        service_module.CodeMapServiceClient(tmp_path).request("example")
    assert sock.closed


def test_client_request_retries_blocked_local_connect(
    tmp_path: Path, fake_socket: _FakeSocket
) -> None:
    fake_socket.blocked_connects = 1

    assert service_module.CodeMapServiceClient(tmp_path).request("example")["ok"]
    assert fake_socket.connects == 2


def test_client_serializes_typed_query_and_refresh_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = service_module.CodeMapServiceClient(tmp_path)
    requests: list[tuple[str, dict[str, object]]] = []

    def request(operation: str, **payload: object) -> dict[str, object]:
        requests.append((operation, payload))
        key = (
            "repository_intelligence_query"
            if operation == "repository_intelligence_query"
            else "refresh_delta"
        )
        return {key: {"schema": "test"}}

    monkeypatch.setattr(client, "request", request)
    client.repository_intelligence_query(
        "profile",
        "inspect widget",
        ["src/widget.py"],
        options=RepositoryIntelligenceQueryOptions(profile="audit", limit=7),
    )
    client.refresh_after_change_delta(
        "inspect widget",
        ["src/widget.py"],
        options=PostChangeOptions(
            previous_edit_path="src/widget.py",
            previous_verify_path="tests/test_widget.py",
            token_budget=256,
        ),
    )

    assert requests[0][0] == "repository_intelligence_query"
    assert requests[0][1]["profile"] == "audit"
    assert requests[0][1]["limit"] == 7
    assert requests[1] == (
        "refresh_after_change_delta",
        {
            "task": "inspect widget",
            "changed_paths": ["src/widget.py"],
            "previous_edit_path": "src/widget.py",
            "previous_verify_path": "tests/test_widget.py",
            "limit": 20,
            "per_role": 3,
            "token_budget": 256,
        },
    )


def test_service_routes_are_exhaustively_classified() -> None:
    routes = service_module._SERVICE_ROUTES
    assert set(routes) == {
        "status",
        "sync",
        "repository_findings",
        "import_ownership",
        "cache_ownership",
        "cache_invalidation_ownership",
        "authority_ownership",
        "concurrency_risk",
        "verification_ownership",
        "find_task",
        "task_action_map",
        "verification_relevance",
        "ownership_relation_graph",
        "task_evidence",
        "task_change_impact",
        "repository_intelligence_query",
        "task_post_change_delta",
        "refresh_after_change_delta",
        "refresh_after_change_brief",
        "refresh_after_change",
        "task_decision_brief",
        "task_action_brief",
        "task_decision_brief_budget_sweep",
        "task_decision_packet",
        "stop",
    }

    semantic = {
        route: (entry.operation, entry.response_key)
        for route, entry in routes.items()
        if entry.classification == "canonical-semantic"
    }
    assert semantic == {
        "repository_findings": ("repository_findings", "repository_findings"),
        "import_ownership": ("import_ownership", "import_ownership"),
        "cache_ownership": ("cache_ownership", "cache_ownership"),
        "cache_invalidation_ownership": (
            "cache_invalidation_ownership",
            "cache_invalidation_ownership",
        ),
        "authority_ownership": ("repository_ownership", "authority_ownership"),
        "concurrency_risk": ("concurrency_risk", "concurrency_risk"),
        "verification_ownership": (
            "verification_ownership",
            "verification_ownership",
        ),
        "task_action_map": ("task_action_map", "action_map"),
        "verification_relevance": (
            "verification_relevance",
            "verification_relevance",
        ),
        "ownership_relation_graph": (
            "ownership_relation_graph",
            "ownership_relation_graph",
        ),
        "task_evidence": ("task_evidence", "task_evidence"),
        "task_change_impact": ("change_impact", "task_change_impact"),
        "repository_intelligence_query": (
            "repository_intelligence_query",
            "repository_intelligence_query",
        ),
        "task_post_change_delta": ("post_change", "post_change_delta"),
        "refresh_after_change_delta": (
            "refresh_after_change_delta",
            "refresh_delta",
        ),
        "refresh_after_change_brief": (
            "refresh_after_change_brief",
            "refresh_brief",
        ),
        "refresh_after_change": ("refresh_after_change", "refresh"),
        "task_decision_brief": ("task_decision_brief", "decision_brief"),
        "task_action_brief": ("task_action_brief", "task_action_brief"),
        "task_decision_brief_budget_sweep": (
            "task_decision_brief_budget_sweep",
            "budget_sweep",
        ),
        "task_decision_packet": ("task_decision_packet", "decision_packet"),
    }
    assert all(
        entry.classification in {"canonical-semantic", "internal-service"}
        for entry in routes.values()
    )
    assert all(
        (entry.operation is None and entry.response_key is None)
        for entry in routes.values()
        if entry.classification == "internal-service"
    )


def test_service_route_classification_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        service_module._ServiceRoute(
            handler_name="_fixture",
            classification="canonical-semantic",
            operation="unregistered_operation",
            response_key="payload",
        )
    with pytest.raises(
        ValueError,
        match="canonical-semantic service routes require operation and response_key",
    ):
        service_module._ServiceRoute(
            handler_name="_fixture",
            classification="canonical-semantic",
            operation="find",
        )
    with pytest.raises(
        ValueError,
        match="internal-service routes must not carry semantic operation metadata",
    ):
        service_module._ServiceRoute(
            handler_name="_fixture",
            classification="internal-service",
            operation="find",
            response_key="payload",
        )
    with pytest.raises(ValueError, match="unsupported service route classification"):
        service_module._ServiceRoute(
            handler_name="_fixture",
            classification="implicit",  # type: ignore[arg-type]
        )


def test_service_registry_owns_handler_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = service_module.CodeMapService(tmp_path)
    seen: list[dict[str, object]] = []

    def project(request: dict[str, object]) -> dict[str, object]:
        seen.append(request)
        return {
            "ok": True,
            "task_evidence": {"schema": "hashmarks.task-evidence.v2"},
        }

    monkeypatch.setattr(service, "_task_evidence_response", project)
    service.dispatch(
        {
            "protocol": service_module.PROTOCOL,
            "op": "task_evidence",
            "task": "inspect",
        }
    )

    assert seen == [
        {
            "protocol": service_module.PROTOCOL,
            "op": "task_evidence",
            "task": "inspect",
        }
    ]
    assert service._requests == 1


def test_service_route_missing_handler_fails_before_request_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = service_module.CodeMapService(tmp_path)
    monkeypatch.setitem(
        service_module._SERVICE_ROUTES,
        "fixture",
        service_module._ServiceRoute(
            handler_name="_missing_handler",
            classification="internal-service",
        ),
    )

    with pytest.raises(RuntimeError, match="route handler is unavailable"):
        service.dispatch(
            {
                "protocol": service_module.PROTOCOL,
                "op": "fixture",
            }
        )

    assert service._requests == 0


def test_canonical_service_admission_fails_before_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = service_module.CodeMapService(tmp_path)
    projected: list[dict[str, object]] = []

    def reject(operation: str) -> None:
        assert operation == "task_evidence"
        raise ValueError("unknown Hashmarks operation: task_evidence")

    def project(request: dict[str, object]) -> dict[str, object]:
        projected.append(request)
        return {
            "ok": True,
            "task_evidence": {"schema": "hashmarks.task-evidence.v2"},
        }

    monkeypatch.setattr(service_module, "require_registered_operation", reject)
    monkeypatch.setattr(service, "_task_evidence_response", project)

    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        service.dispatch(
            {
                "protocol": service_module.PROTOCOL,
                "op": "task_evidence",
                "task": "inspect",
            }
        )

    assert projected == []
    assert service._requests == 0


@pytest.mark.parametrize(
    ("route", "handler_name", "response_key"),
    [
        ("repository_findings", "_repository_findings_response", "repository_findings"),
        ("import_ownership", "_import_ownership_response", "import_ownership"),
        ("cache_ownership", "_cache_ownership_response", "cache_ownership"),
        (
            "cache_invalidation_ownership",
            "_cache_invalidation_response",
            "cache_invalidation_ownership",
        ),
        ("authority_ownership", "_authority_ownership_response", "authority_ownership"),
        ("concurrency_risk", "_concurrency_risk_response", "concurrency_risk"),
        (
            "verification_ownership",
            "_verification_ownership_response",
            "verification_ownership",
        ),
        ("task_action_map", "_task_action_map_response", "action_map"),
        (
            "verification_relevance",
            "_verification_relevance_response",
            "verification_relevance",
        ),
        (
            "ownership_relation_graph",
            "_ownership_relation_response",
            "ownership_relation_graph",
        ),
        ("task_evidence", "_task_evidence_response", "task_evidence"),
        ("task_change_impact", "_change_impact_response", "task_change_impact"),
        (
            "repository_intelligence_query",
            "_repository_intelligence_query_response",
            "repository_intelligence_query",
        ),
        ("task_post_change_delta", "_post_change_delta_response", "post_change_delta"),
        ("refresh_after_change_delta", "_refresh_delta_response", "refresh_delta"),
        ("refresh_after_change_brief", "_refresh_brief_response", "refresh_brief"),
        ("refresh_after_change", "_refresh_response", "refresh"),
        ("task_decision_brief", "_decision_brief_response", "decision_brief"),
        ("task_action_brief", "_task_action_brief_response", "task_action_brief"),
        (
            "task_decision_brief_budget_sweep",
            "_budget_sweep_response",
            "budget_sweep",
        ),
        ("task_decision_packet", "_decision_packet_response", "decision_packet"),
    ],
)
def test_canonical_service_projection_rejects_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    handler_name: str,
    response_key: str,
) -> None:
    service = service_module.CodeMapService(tmp_path)

    def project(_request: dict[str, object]) -> dict[str, object]:
        return {
            "ok": True,
            response_key: {"schema": "hashmarks.wrong.v1"},
        }

    monkeypatch.setattr(service, handler_name, project)

    with pytest.raises(RuntimeError, match="operation response schema drift"):
        service.dispatch(
            {
                "protocol": service_module.PROTOCOL,
                "op": route,
            }
        )
