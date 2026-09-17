from __future__ import annotations

import ast
import contextlib
import json
import os
import queue
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from urllib.parse import unquote, urlparse

from hashmarks.paths import canonical_host_path, normalize_relative_path
from hashmarks.python_ast_cache import read_python_ast

from .typescript_resolver import NativeFileEdge

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

_SUPPORTED_TSP_MINOR = "0.4"


@dataclass(frozen=True)
class PythonImportSpec:
    source: str
    leading_dots: int
    name_parts: tuple[str, ...]

    @property
    def display(self) -> str:
        return "." * self.leading_dots + ".".join(self.name_parts)


@dataclass(frozen=True)
class PyrightTypeServerResolution:
    producer: str
    edges: tuple[NativeFileEdge, ...]
    warnings: tuple[str, ...] = ()
    protocol_version: str | None = None
    package_version: str | None = None


@dataclass
class _EdgeCollectState:
    workspace: Path
    snapshot: int
    producer: str
    warnings: list[str]


class _TypeServerClientProtocol(Protocol):
    protocol_version: str

    def initialize(self) -> None: ...
    def snapshot(self) -> int: ...
    def resolve_import(
        self,
        source_uri: str,
        leading_dots: int,
        name_parts: tuple[str, ...],
        snapshot: int,
    ) -> str | None: ...
    def close(self) -> None: ...


class _JsonRpcError(RuntimeError):
    def __init__(self, code: int | None, message: str) -> None:
        self.code = code
        super().__init__(message)


class _JsonRpcProcess:
    """Small synchronous JSON-RPC/LSP-framing client for an explicit CodeMap probe."""

    def __init__(self, command: list[str], *, cwd: Path, timeout: float) -> None:
        self.timeout = float(timeout)
        self._next_id = 1
        self._responses: queue.Queue[dict] = queue.Queue()
        self._stderr_lines: list[str] = []
        self._proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),
        )
        self._reader = threading.Thread(
            target=self._read_loop, name="hashmarks-pyright-tsp-reader", daemon=True
        )
        self._reader.start()
        self._stderr_reader = threading.Thread(
            target=self._read_stderr, name="hashmarks-pyright-tsp-stderr", daemon=True
        )
        self._stderr_reader.start()

    def _read_stderr(self) -> None:
        stream = self._proc.stderr
        if stream is None:
            return
        try:
            for raw in iter(stream.readline, b""):
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self._stderr_lines.append(line)
                    if len(self._stderr_lines) > 40:
                        del self._stderr_lines[:-40]
        except (OSError, ValueError):
            return

    @staticmethod
    def _message_length(stream) -> int | None:
        length: int | None = None
        while True:
            raw = stream.readline()
            if not raw:
                return None
            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                return length
            key, sep, value = line.partition(":")
            if sep and key.lower() == "content-length":
                length = int(value.strip())

    @staticmethod
    def _read_message(stream, length: int) -> dict | None:
        payload = stream.read(length)
        if len(payload) != length:
            return None
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return message if isinstance(message, dict) else {}

    def _read_loop(self) -> None:
        stream = self._proc.stdout
        if stream is None:
            return
        try:
            while True:
                length = self._message_length(stream)
                if length is None:
                    return
                if length < 0:
                    continue
                message = self._read_message(stream, length)
                if message is None:
                    return
                if message:
                    self._responses.put(message)
        except (OSError, ValueError):
            return

    def _send(self, message: dict) -> None:
        stream = self._proc.stdin
        if stream is None or self._proc.poll() is not None:
            detail = (
                self._stderr_lines[-1] if self._stderr_lines else "type server exited"
            )
            raise RuntimeError(detail)
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        frame = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload
        stream.write(frame)
        stream.flush()

    def notify(self, method: str, params: object | None = None) -> None:
        message: dict[str, object] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    @staticmethod
    def _server_reply_result(method: str, params: object) -> object:
        if method == "workspace/configuration":
            items = params.get("items") if isinstance(params, dict) else None
            count = len(items) if isinstance(items, list) else 0
            return [None] * count
        if method == "workspace/applyEdit":
            return {
                "applied": False,
                "failureReason": "Hashmarks analysis client is read-only",
            }
        return None

    def _reply_to_server_request(self, message: dict) -> None:
        request_id = message.get("id")
        if request_id is None:
            return
        method = str(message.get("method") or "")
        supported = {
            "workspace/configuration",
            "client/registerCapability",
            "client/unregisterCapability",
            "window/workDoneProgress/create",
            "window/showMessageRequest",
            "workspace/workspaceFolders",
            "workspace/applyEdit",
        }
        if method in supported:
            reply = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": self._server_reply_result(method, message.get("params")),
            }
        else:
            reply = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"client method not supported: {method}",
                },
            }
        self._send(reply)

    @staticmethod
    def _rpc_error(response: dict) -> _JsonRpcError:
        error = response.get("error") or {}
        if not isinstance(error, dict):
            return _JsonRpcError(None, str(error))
        code = error.get("code")
        try:
            parsed_code = None if code is None else int(code)
        except (TypeError, ValueError):
            parsed_code = None
        return _JsonRpcError(parsed_code, str(error.get("message") or "JSON-RPC error"))

    def _wait_response(self, request_id: int, method: str) -> object:
        while True:
            try:
                response = self._responses.get(timeout=self.timeout)
            except queue.Empty as exc:
                detail = (
                    self._stderr_lines[-1]
                    if self._stderr_lines
                    else f"timeout waiting for {method}"
                )
                raise TimeoutError(detail) from exc
            if "method" in response:
                if response.get("id") is not None:
                    self._reply_to_server_request(response)
                continue
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise self._rpc_error(response)
            return response.get("result")

    def request(self, method: str, params: object | None = None) -> object:
        request_id = self._next_id
        self._next_id += 1
        message: dict[str, object] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self._send(message)
        return self._wait_response(request_id, method)

    def close(self) -> None:
        try:
            if self._proc.poll() is None:
                with contextlib.suppress(OSError, RuntimeError):
                    self.request("shutdown")
                with contextlib.suppress(OSError, RuntimeError):
                    self.notify("exit")
        finally:
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=min(1.0, self.timeout))
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=1.0)


class _PyrightTypeServerClient:
    def __init__(
        self, executable: Path | str, *, workspace: Path, timeout: float
    ) -> None:
        self.workspace = workspace
        self._rpc = _JsonRpcProcess(
            [str(executable), "--stdio"], cwd=workspace, timeout=timeout
        )
        self.protocol_version = ""

    def initialize(self) -> None:
        root_uri = self.workspace.as_uri()
        self._rpc.request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": root_uri,
                "capabilities": {},
                "workspaceFolders": [
                    {"uri": root_uri, "name": self.workspace.name or "workspace"}
                ],
            },
        )
        self._rpc.notify("initialized", {})
        version = self._rpc.request("typeServer/getSupportedProtocolVersion")
        if not isinstance(version, str):
            raise RuntimeError(
                "Pyright Type Server returned an invalid protocol version"
            )
        if not version.startswith(_SUPPORTED_TSP_MINOR + "."):
            raise RuntimeError(
                f"unsupported Type Server Protocol {version}; Hashmarks currently supports {_SUPPORTED_TSP_MINOR}.x"
            )
        self.protocol_version = version

    def snapshot(self) -> int:
        value = self._rpc.request("typeServer/getSnapshot")
        if not isinstance(value, int) or value < 0:
            raise RuntimeError("Pyright Type Server returned an invalid snapshot")
        return value

    def resolve_import(
        self,
        source_uri: str,
        leading_dots: int,
        name_parts: tuple[str, ...],
        snapshot: int,
    ) -> str | None:
        try:
            value = self._rpc.request(
                "typeServer/resolveImport",
                {
                    "sourceUri": source_uri,
                    "moduleDescriptor": {
                        "leadingDots": leading_dots,
                        "nameParts": list(name_parts),
                    },
                    "snapshot": snapshot,
                },
            )
        except _JsonRpcError as exc:
            if exc.code == -32802:
                raise
            raise
        if value is None:
            return None
        if not isinstance(value, str):
            raise RuntimeError("Pyright Type Server returned an invalid import URI")
        return value

    def close(self) -> None:
        self._rpc.close()


def _plain_import_specs(node: ast.Import, rel: str) -> list[PythonImportSpec]:
    result: list[PythonImportSpec] = []
    for alias in node.names:
        parts = tuple(part for part in alias.name.split(".") if part)
        if parts:
            result.append(PythonImportSpec(rel, 0, parts))
    return result


def _relative_alias_specs(
    node: ast.ImportFrom, rel: str, leading: int
) -> list[PythonImportSpec]:
    result: list[PythonImportSpec] = []
    for alias in node.names:
        if alias.name == "*":
            continue
        parts = tuple(part for part in alias.name.split(".") if part)
        if parts:
            result.append(PythonImportSpec(rel, leading, parts))
    return result


def _from_import_specs(node: ast.ImportFrom, rel: str) -> list[PythonImportSpec]:
    leading = int(node.level or 0)
    if not node.module:
        return _relative_alias_specs(node, rel, leading)
    parts = tuple(part for part in node.module.split(".") if part)
    return [PythonImportSpec(rel, leading, parts)] if parts else []


def _import_specs(node: ast.AST, rel: str) -> list[PythonImportSpec]:
    if isinstance(node, ast.Import):
        return _plain_import_specs(node, rel)
    if isinstance(node, ast.ImportFrom):
        return _from_import_specs(node, rel)
    return []


def _dedupe_import_specs(rows: list[PythonImportSpec]) -> tuple[PythonImportSpec, ...]:
    seen: set[tuple[int, tuple[str, ...]]] = set()
    unique: list[PythonImportSpec] = []
    for row in rows:
        key = (row.leading_dots, row.name_parts)
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return tuple(unique)


def _imports_for_file(path: Path, rel: str) -> tuple[PythonImportSpec, ...]:
    try:
        tree = read_python_ast(path).tree
    except (OSError, UnicodeError, SyntaxError, ValueError):
        return ()
    result = [spec for node in ast.walk(tree) for spec in _import_specs(node, rel)]
    return _dedupe_import_specs(result)


def _file_uri_path(uri: str) -> str | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    raw_path = unquote(parsed.path)
    windows_drive = (
        os.name == "nt"
        and raw_path.startswith("/")
        and len(raw_path) >= 3
        and raw_path[2] == ":"
    )
    return raw_path[1:] if windows_drive else raw_path


def _uri_to_workspace_path(uri: str, workspace: Path) -> str | None:
    raw_path = _file_uri_path(uri)
    if raw_path is None:
        return None
    try:
        target = canonical_host_path(raw_path)
        rel = normalize_relative_path(
            target.relative_to(workspace).as_posix(), allow_root=False
        )
    except (ValueError, OSError):
        return None
    return rel if target.is_file() and not target.is_symlink() else None


class PyrightTypeServerProvider:
    """Optional native Python import resolver using the published TSP boundary.

    This provider is explicit CodeMap enrichment only. It does not provide
    symbol/reference authority (SCIP remains the preferred generic source for
    that), and it is never imported from Hashmarks' Identity hot path.
    """

    name = "pyright-typeserver"

    def __init__(
        self,
        executable: str | Path | None = None,
        *,
        client_factory: Callable[[Path | str, Path, float], _TypeServerClientProtocol]
        | None = None,
    ) -> None:
        self._explicit_executable = None if executable is None else Path(executable)
        self._client_factory = client_factory

    def _executable(self, workspace: Path) -> Path | None:
        if self._explicit_executable is not None:
            return self._explicit_executable
        suffixes = (
            ("pyright-typeserver.cmd", "pyright-typeserver.exe")
            if os.name == "nt"
            else ("pyright-typeserver",)
        )
        for suffix in suffixes:
            candidate = workspace / "node_modules" / ".bin" / suffix
            if candidate.is_file():
                return candidate
        found = shutil.which("pyright-typeserver")
        return None if found is None else Path(found)

    def detect(self, workspace: Path) -> bool:
        return self._executable(workspace) is not None

    @staticmethod
    def _package_version(workspace: Path) -> str | None:
        package_json = (
            workspace / "node_modules" / "pyright-typeserver" / "package.json"
        )
        try:
            value = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        version = value.get("version") if isinstance(value, dict) else None
        return None if version is None else str(version)

    def _client(
        self, executable: Path | str, workspace: Path, timeout: float
    ) -> _TypeServerClientProtocol:
        if self._client_factory is not None:
            return self._client_factory(executable, workspace, timeout)
        return _PyrightTypeServerClient(
            executable, workspace=workspace, timeout=timeout
        )

    @staticmethod
    def _source_specs(
        workspace: Path, sources: Iterable[str]
    ) -> list[PythonImportSpec]:
        specs: list[PythonImportSpec] = []
        for raw in sources:
            try:
                rel = normalize_relative_path(
                    str(raw).replace("\\", "/"), allow_root=False
                )
            except ValueError:
                continue
            if not rel.endswith((".py", ".pyi")):
                continue
            path = workspace / rel
            if path.is_file() and not path.is_symlink():
                specs.extend(_imports_for_file(path, rel))
        return specs

    @staticmethod
    def _producer(package_version: str | None, protocol_version: str | None) -> str:
        if protocol_version is None:
            return "pyright-typeserver"
        return (
            f"pyright-typeserver:{package_version or 'unknown'}:tsp-{protocol_version}"
        )

    @staticmethod
    def _resolve_spec(
        client: _TypeServerClientProtocol,
        spec: PythonImportSpec,
        source_uri: str,
        snapshot: int,
    ) -> tuple[str | None, int, str | None]:
        try:
            return (
                client.resolve_import(
                    source_uri, spec.leading_dots, spec.name_parts, snapshot
                ),
                snapshot,
                None,
            )
        except _JsonRpcError as exc:
            if exc.code != -32802:
                return None, snapshot, str(exc)
        refreshed = client.snapshot()
        try:
            result = client.resolve_import(
                source_uri, spec.leading_dots, spec.name_parts, refreshed
            )
            return result, refreshed, None
        except (OSError, RuntimeError) as exc:
            return None, refreshed, str(exc)

    def _collect_edges(
        self,
        client: _TypeServerClientProtocol,
        specs: list[PythonImportSpec],
        state: _EdgeCollectState,
    ) -> list[NativeFileEdge]:
        edges: list[NativeFileEdge] = []
        seen: set[tuple[str, str, str]] = set()
        for spec in specs:
            source_uri = (state.workspace / spec.source).as_uri()
            result_uri, state.snapshot, error = self._resolve_spec(
                client, spec, source_uri, state.snapshot
            )
            if error is not None:
                state.warnings.append(f"{spec.source}: {spec.display}: {error}")
                continue
            target = (
                None
                if result_uri is None
                else _uri_to_workspace_path(result_uri, state.workspace)
            )
            if target is None or target == spec.source:
                continue
            key = (spec.source, target, spec.display)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                NativeFileEdge(
                    source=spec.source,
                    target=target,
                    kind="python-import-resolution",
                    confidence="native",
                    producer=state.producer,
                    specifier=spec.display,
                )
            )
        return edges

    @staticmethod
    def _close_client(client: _TypeServerClientProtocol | None) -> None:
        if client is None:
            return
        with contextlib.suppress(OSError, RuntimeError):
            client.close()

    def collect(
        self,
        workspace: Path,
        sources: Iterable[str],
        *,
        timeout: float = 20.0,
    ) -> PyrightTypeServerResolution:
        executable = self._executable(workspace)
        if executable is None:
            return PyrightTypeServerResolution(
                self.name, (), ("pyright-typeserver executable unavailable",)
            )
        canonical_workspace = canonical_host_path(workspace)
        specs = self._source_specs(canonical_workspace, sources)
        package_version = self._package_version(canonical_workspace)
        warnings: list[str] = []
        edges: list[NativeFileEdge] = []
        client: _TypeServerClientProtocol | None = None
        protocol_version: str | None = None
        try:
            client = self._client(executable, canonical_workspace, timeout)
            client.initialize()
            protocol_version = client.protocol_version
            producer = self._producer(package_version, protocol_version)
            state = _EdgeCollectState(
                canonical_workspace, client.snapshot(), producer, warnings
            )
            edges = self._collect_edges(client, specs, state)
        except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
            warnings.append(f"Pyright Type Server unavailable: {exc}")
        finally:
            self._close_client(client)
        return PyrightTypeServerResolution(
            producer=self._producer(package_version, protocol_version),
            edges=tuple(edges),
            warnings=tuple(dict.fromkeys(warnings)),
            protocol_version=protocol_version,
            package_version=package_version,
        )
