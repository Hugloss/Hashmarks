from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.client import (
    _PROTOCOL_VERSION,
    DAEMON_CAPABILITIES,
    DAEMON_SEMANTICS,
    DaemonCompatibilityError,
    IdentityClient,
)


class _FakeSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = iter(chunks)
        self.closed = False
        self.sent = b""

    def settimeout(self, _timeout: float) -> None:
        pass

    def connect(self, _path: str) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent = data

    def recv(self, _size: int) -> bytes:
        try:
            return next(self.chunks)
        except StopIteration:
            return b""

    def close(self) -> None:
        self.closed = True


def _client_with_socket(
    tmp_path: Path, monkeypatch, chunks: list[bytes]
) -> IdentityClient:
    sock = _FakeSocket(chunks)
    monkeypatch.setattr("hashmarks.client.socket.socket", lambda *_args: sock)
    return IdentityClient(tmp_path, socket_path=tmp_path / "identity.sock")


def test_compatibility_success(tmp_path: Path, monkeypatch) -> None:
    import json

    response = {
        "ok": True,
        "protocol": _PROTOCOL_VERSION,
        "semantics": DAEMON_SEMANTICS,
        "capabilities": list(DAEMON_CAPABILITIES),
    }
    chunks = [json.dumps(response).encode() + b"\n"]
    client = _client_with_socket(tmp_path, monkeypatch, chunks)

    assert client.status() == response
    assert client._compatibility_validated is True


def test_compatibility_protocol_mismatch(tmp_path: Path, monkeypatch) -> None:
    import json

    response = {
        "ok": True,
        "protocol": "wrong-version",
        "semantics": DAEMON_SEMANTICS,
        "capabilities": DAEMON_CAPABILITIES,
    }
    client = _client_with_socket(
        tmp_path, monkeypatch, [json.dumps(response).encode() + b"\n"]
    )

    with pytest.raises(DaemonCompatibilityError, match="protocol mismatch"):
        client.status()


def test_compatibility_semantics_mismatch(tmp_path: Path, monkeypatch) -> None:
    import json

    response = {
        "ok": True,
        "protocol": _PROTOCOL_VERSION,
        "semantics": "wrong-semantics",
        "capabilities": DAEMON_CAPABILITIES,
    }
    client = _client_with_socket(
        tmp_path, monkeypatch, [json.dumps(response).encode() + b"\n"]
    )

    with pytest.raises(DaemonCompatibilityError, match="semantics mismatch"):
        client.status()


def test_compatibility_invalid_capabilities_type(tmp_path: Path, monkeypatch) -> None:
    import json

    response = {
        "ok": True,
        "protocol": _PROTOCOL_VERSION,
        "semantics": DAEMON_SEMANTICS,
        "capabilities": "not-a-list",
    }
    client = _client_with_socket(
        tmp_path, monkeypatch, [json.dumps(response).encode() + b"\n"]
    )

    with pytest.raises(DaemonCompatibilityError, match="valid capability set"):
        client.status()


def test_compatibility_missing_capabilities(tmp_path: Path, monkeypatch) -> None:
    import json

    # Remove one required capability
    caps = list(DAEMON_CAPABILITIES)
    if caps:
        caps.pop()

    response = {
        "ok": True,
        "protocol": _PROTOCOL_VERSION,
        "semantics": DAEMON_SEMANTICS,
        "capabilities": caps,
    }
    client = _client_with_socket(
        tmp_path, monkeypatch, [json.dumps(response).encode() + b"\n"]
    )

    with pytest.raises(DaemonCompatibilityError, match="missing required capabilities"):
        client.status()
