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
