from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from hashmarks.codemap import service as service_module


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
