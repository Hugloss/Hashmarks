from __future__ import annotations

import argparse
from typing import Literal

from .errors import UserFacingError

McpTransport = Literal["stdio", "streamable-http"]

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000
DEFAULT_HTTP_PATH = "/mcp"

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


def add_transport_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help=(
            "stdio is the local subprocess transport; streamable-http serves the "
            "same read-only MCP surface on loopback for a secure tunnel or local client"
        ),
    )
    parser.add_argument("--host", default=DEFAULT_HTTP_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT)
    parser.add_argument("--path", default=DEFAULT_HTTP_PATH)


def validate_streamable_http(
    *, host: str, port: int, path: str
) -> tuple[str, int, str]:
    if host not in _LOOPBACK_HOSTS:
        raise UserFacingError(
            "Hashmarks streamable HTTP is loopback-only; use 127.0.0.1 or ::1 and "
            "place an authenticated/tunneled boundary in front "
            "of Hashmarks when remote access is required"
        )
    if not 1 <= port <= 65535:
        raise UserFacingError("MCP HTTP port must be between 1 and 65535")
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "?" in path
        or "#" in path
        or any(character.isspace() for character in path)
    ):
        raise UserFacingError(
            "MCP HTTP path must be one absolute URL path without query, fragment, "
            "whitespace, or a leading //"
        )
    return host, port, path
