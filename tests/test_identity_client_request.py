from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks.client import (
    _MAX_RESPONSE,
    DaemonProtocolError,
    DaemonUnavailableError,
    IdentityClient,
)

if TYPE_CHECKING:
    from pathlib import Path


class _FakeSocket:
    def __init__(self, chunks: list[bytes], *, connect_error: OSError | None = None):
        self.chunks = iter(chunks)
        self.connect_error = connect_error
        self.closed = False
        self.sent = b""

    def settimeout(self, _timeout: float) -> None:
        pass

    def connect(self, _path: str) -> None:
        if self.connect_error is not None:
            raise self.connect_error

    def sendall(self, payload: bytes) -> None:
        self.sent = payload

    def recv(self, _size: int) -> bytes:
        return next(self.chunks, b"")

    def close(self) -> None:
        self.closed = True


def _client_with_socket(
    tmp_path: Path, monkeypatch, sock: _FakeSocket
) -> IdentityClient:
    monkeypatch.setattr("hashmarks.client.socket.socket", lambda *_args: sock)
    return IdentityClient(tmp_path, socket_path=tmp_path / "identity.sock")


def test_request_reads_first_complete_response_and_closes_socket(
    tmp_path: Path, monkeypatch
) -> None:
    sock = _FakeSocket([b'{"ok":tr', b'ue,"value":3}\nignored'])
    client = _client_with_socket(tmp_path, monkeypatch, sock)

    assert client.request("status", sample=4) == {"ok": True, "value": 3}
    assert b'"op":"status"' in sock.sent
    assert b'"sample":4' in sock.sent
    assert sock.closed


@pytest.mark.parametrize(
    ("chunks", "message"),
    [
        ([], "empty response"),
        ([b"not-json\n"], "invalid JSON"),
        ([b"[]\n"], "must be an object"),
        ([b'{"ok":false,"error":"bad request"}\n'], "bad request"),
    ],
)
def test_request_rejects_invalid_responses_and_closes_socket(
    tmp_path: Path, monkeypatch, chunks: list[bytes], message: str
) -> None:
    sock = _FakeSocket(chunks)
    client = _client_with_socket(tmp_path, monkeypatch, sock)

    with pytest.raises(DaemonProtocolError, match=message):
        client.request("status")
    assert sock.closed


def test_request_translates_connection_failure_and_closes_socket(
    tmp_path: Path, monkeypatch
) -> None:
    sock = _FakeSocket([], connect_error=ConnectionRefusedError("refused"))
    client = _client_with_socket(tmp_path, monkeypatch, sock)

    with pytest.raises(DaemonUnavailableError, match="refused"):
        client.request("status")
    assert sock.closed


def test_request_rejects_response_above_size_limit(tmp_path: Path, monkeypatch) -> None:
    sock = _FakeSocket([b"x" * (_MAX_RESPONSE + 1)])
    client = _client_with_socket(tmp_path, monkeypatch, sock)

    with pytest.raises(DaemonProtocolError, match="exceeded size limit"):
        client.request("status")
    assert sock.closed
