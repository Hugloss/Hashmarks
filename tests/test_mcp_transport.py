from __future__ import annotations

from unittest import mock

import pytest

from hashmarks.errors import UserFacingError
from hashmarks.mcp_server import run_server
from hashmarks.mcp_transport import validate_streamable_http


class _Surface:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Server:
    def __init__(self) -> None:
        self._hashmarks_surface = _Surface()
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def run(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


def test_stdio_remains_default_transport_and_closes_surface(tmp_path) -> None:
    server = _Server()
    with mock.patch(
        "hashmarks.mcp_server.build_server",
        return_value=server,
    ) as build:
        run_server(tmp_path)

    build.assert_called_once_with(tmp_path, state_dir=None)
    assert server.calls == [((), {"transport": "stdio"})]
    assert server._hashmarks_surface.closed is True


def test_transport_validation_owner_accepts_only_local_authority() -> None:
    assert validate_streamable_http(
        host="127.0.0.1",
        port=8000,
        path="/mcp",
    ) == ("127.0.0.1", 8000, "/mcp")
    assert validate_streamable_http(
        host="localhost",
        port=9123,
        path="/hashmarks/mcp",
    ) == ("localhost", 9123, "/hashmarks/mcp")


def test_streamable_http_uses_loopback_stateless_json_transport(tmp_path) -> None:
    server = _Server()
    with mock.patch(
        "hashmarks.mcp_server.build_server",
        return_value=server,
    ) as build:
        run_server(
            tmp_path,
            state_dir=tmp_path / "state",
            transport="streamable-http",
            host="127.0.0.1",
            port=8765,
            path="/hashmarks/mcp",
        )

    build.assert_called_once_with(tmp_path, state_dir=tmp_path / "state")
    assert server.calls == [
        (
            (),
            {
                "transport": "streamable-http",
                "host": "127.0.0.1",
                "port": 8765,
                "streamable_http_path": "/hashmarks/mcp",
                "json_response": True,
                "stateless_http": True,
            },
        )
    ]
    assert server._hashmarks_surface.closed is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("host", "0.0.0.0", "loopback-only"),
        ("host", "192.0.2.10", "loopback-only"),
        ("port", 0, "between 1 and 65535"),
        ("port", 65536, "between 1 and 65535"),
        ("path", "mcp", "absolute URL path"),
        ("path", "//mcp", "absolute URL path"),
        ("path", "/mcp?debug=1", "absolute URL path"),
        ("path", "/mcp#fragment", "absolute URL path"),
        ("path", "/mcp path", "absolute URL path"),
    ],
)
def test_invalid_http_authority_fails_before_server_construction(
    tmp_path,
    field: str,
    value: object,
    message: str,
) -> None:
    options: dict[str, object] = {
        "transport": "streamable-http",
        "host": "127.0.0.1",
        "port": 8000,
        "path": "/mcp",
    }
    options[field] = value

    with mock.patch("hashmarks.mcp_server.build_server") as build:
        with pytest.raises(UserFacingError, match=message):
            run_server(tmp_path, **options)

    build.assert_not_called()


def test_top_level_cli_delegates_transport_once(tmp_path, monkeypatch) -> None:
    import hashmarks.cli as cli
    import hashmarks.mcp_server as mcp_server

    seen: dict[str, object] = {}

    def fake_run_server(workspace, **kwargs) -> None:
        seen["workspace"] = workspace
        seen.update(kwargs)

    monkeypatch.setattr(mcp_server, "run_server", fake_run_server)

    assert (
        cli.main(
            [
                "--workspace",
                str(tmp_path),
                "mcp",
                "--transport",
                "streamable-http",
                "--host",
                "localhost",
                "--port",
                "9123",
                "--path",
                "/mcp",
            ]
        )
        == 0
    )
    assert seen == {
        "workspace": tmp_path.resolve(),
        "state_dir": None,
        "transport": "streamable-http",
        "host": "localhost",
        "port": 9123,
        "path": "/mcp",
    }
