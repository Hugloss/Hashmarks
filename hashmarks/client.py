from __future__ import annotations

import hashlib
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .observation import ObservationState
from .paths import canonical_host_path
from .schema import DAEMON_CAPABILITIES, DAEMON_PROTOCOL_VERSION, DAEMON_SEMANTICS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .inputs import InputManifest

_PROTOCOL_VERSION = DAEMON_PROTOCOL_VERSION
_MAX_RESPONSE = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RepositoryObservation:
    """One request-barriered repository freshness observation.

    The generation, state, bounded dirty-path set, and completeness flag are
    one atomic client value. Consumers must not combine fields sampled by
    separate daemon requests into one freshness decision.
    """

    state: ObservationState
    generation: int
    dirty_paths: tuple[str, ...]
    paths_complete: bool
    dirty_path_count: int
    reason: str | None = None

    @property
    def can_incrementally_reconcile(self) -> bool:
        return (
            self.state is ObservationState.DIRTY
            and self.paths_complete
            and self.dirty_path_count == len(self.dirty_paths)
            and self.dirty_path_count > 0
        )


class DaemonUnavailableError(ConnectionError):
    pass


class DaemonProtocolError(RuntimeError):
    pass


class DaemonCompatibilityError(DaemonProtocolError):
    pass


def default_state_dir(workspace: str | Path) -> Path:
    return canonical_host_path(workspace) / ".hashmarks"


def _workspace_runtime_key(workspace: str | Path) -> str:
    canonical = canonical_host_path(workspace)
    # The key is only a collision-resistant namespace for ephemeral local IPC;
    # it is not a content or trust identity. Keep it short so AF_UNIX paths stay
    # comfortably below Linux's sockaddr_un limit even for very long repos.
    return hashlib.sha256(os.fsencode(str(canonical))).hexdigest()[:20]


def default_runtime_dir(workspace: str | Path) -> Path:
    """Return a local-filesystem directory for ephemeral daemon IPC.

    Persistent cache state may live inside a workspace (including WSL DrvFS),
    but Unix-domain sockets must not: some mounted filesystems cannot create
    socket inodes and long workspace/runtime paths can exceed ``sockaddr_un``.
    The chosen path is therefore also bounded for socket-path length.
    """
    key = _workspace_runtime_key(workspace)

    if os.name == "posix":
        uid = os.getuid()
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
        if xdg_runtime:
            preferred = canonical_host_path(xdg_runtime) / "hashmarks" / key
            preferred_socket = preferred / "identity.sock"
            # Stay comfortably below Linux's common 108-byte sun_path limit.
            if len(os.fsencode(str(preferred_socket))) < 96:
                return canonical_host_path(preferred)

        run_user = Path(f"/run/user/{uid}")
        if run_user.is_dir():
            preferred = canonical_host_path(run_user) / "hashmarks" / key
            preferred_socket = preferred / "identity.sock"
            if len(os.fsencode(str(preferred_socket))) < 96:
                return canonical_host_path(preferred)

        # Short, socket-capable Linux fallback. This is especially important
        # on WSL where the source workspace may live on /mnt/c (DrvFS).
        return canonical_host_path(Path("/tmp") / f"hm-{uid}" / key)

    # The current daemon transport is Unix-domain sockets, but keep a
    # deterministic fallback for callers inspecting the path on non-POSIX.
    return canonical_host_path(default_state_dir(workspace) / "runtime" / key)


def default_socket_path(workspace: str | Path) -> Path:
    return default_runtime_dir(workspace) / "identity.sock"


class IdentityClient:
    """Thin local IPC client for a long-lived IdentityDaemon."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        state_dir: str | Path | None = None,
        socket_path: str | Path | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.workspace = canonical_host_path(workspace)
        self.state_dir = (
            default_state_dir(self.workspace)
            if state_dir is None
            else canonical_host_path(state_dir)
        )
        self.socket_path = (
            default_socket_path(self.workspace)
            if socket_path is None
            else canonical_host_path(socket_path)
        )
        self.timeout = timeout
        self._compatibility_validated = False

    def request(self, op: str, **payload: Any) -> dict[str, Any]:
        message = {"protocol": _PROTOCOL_VERSION, "op": op, **payload}
        raw = (
            json.dumps(message, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
        return self._decode_response(self._read_response(raw))

    def _read_response(self, raw: bytes) -> bytes:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(str(self.socket_path))
            sock.sendall(raw)
            chunks = bytearray()
            while len(chunks) <= _MAX_RESPONSE:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.extend(chunk)
                if b"\n" in chunk:
                    break
        except (
            TimeoutError,
            FileNotFoundError,
            ConnectionRefusedError,
            OSError,
        ) as exc:
            raise DaemonUnavailableError(
                f"identity daemon unavailable at {self.socket_path}: {exc}"
            ) from exc
        finally:
            sock.close()
        return bytes(chunks)

    @staticmethod
    def _decode_response(chunks: bytes) -> dict[str, Any]:
        if len(chunks) > _MAX_RESPONSE:
            raise DaemonProtocolError("daemon response exceeded size limit")
        line = chunks.split(b"\n", 1)[0]
        if not line:
            raise DaemonProtocolError("daemon returned an empty response")
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DaemonProtocolError("daemon returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise DaemonProtocolError("daemon response must be an object")
        if not response.get("ok", False):
            raise DaemonProtocolError(
                str(response.get("error", "daemon request failed"))
            )
        return response

    def status(self) -> dict[str, Any]:
        try:
            response = self.request("status")
        except DaemonProtocolError as exc:
            raise DaemonCompatibilityError(
                f"identity daemon is not compatible with client protocol {_PROTOCOL_VERSION}: {exc}"
            ) from exc
        protocol = response.get("protocol")
        semantics = response.get("semantics")
        capabilities = response.get("capabilities")
        if protocol != _PROTOCOL_VERSION:
            raise DaemonCompatibilityError(
                f"identity daemon protocol mismatch: expected {_PROTOCOL_VERSION}, got {protocol!r}"
            )
        if semantics != DAEMON_SEMANTICS:
            raise DaemonCompatibilityError(
                f"identity daemon semantics mismatch: expected {DAEMON_SEMANTICS!r}, got {semantics!r}"
            )
        if not isinstance(capabilities, list) or not all(
            isinstance(v, str) for v in capabilities
        ):
            raise DaemonCompatibilityError(
                "identity daemon did not advertise a valid capability set"
            )
        missing = sorted(set(DAEMON_CAPABILITIES) - set(capabilities))
        if missing:
            raise DaemonCompatibilityError(
                "identity daemon is missing required capabilities: "
                + ", ".join(missing)
            )
        self._compatibility_validated = True
        return response

    def _ensure_compatible(self) -> None:
        if not self._compatibility_validated:
            self.status()

    def repository_observation(self) -> RepositoryObservation:
        """Return one atomic, request-barriered repository observation.

        Protocol v3 intentionally exposes a typed snapshot rather than a raw
        mapping. Invalid observation payloads fail closed as protocol errors.
        """
        self._ensure_compatible()
        response = self.request("observe")
        try:
            state = ObservationState(str(response["observation"]))
            generation = int(response["generation"])
            dirty_path_count = int(response["dirty_paths"])
            paths_complete = response["paths_complete"]
            raw_paths = response["paths"]
        except (KeyError, TypeError, ValueError) as exc:
            raise DaemonProtocolError(
                "daemon returned an invalid repository observation"
            ) from exc
        paths = self._validated_observation_paths(
            state, dirty_path_count, paths_complete, raw_paths
        )
        reason = response.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise DaemonProtocolError(
                "repository observation reason must be a string or null"
            )
        return RepositoryObservation(
            state=state,
            generation=generation,
            dirty_paths=paths,
            paths_complete=paths_complete,
            dirty_path_count=dirty_path_count,
            reason=reason,
        )

    @staticmethod
    def _validated_observation_paths(
        state: ObservationState,
        dirty_path_count: int,
        paths_complete: object,
        raw_paths: object,
    ) -> tuple[str, ...]:
        if not isinstance(paths_complete, bool):
            raise DaemonProtocolError(
                "repository observation paths_complete must be boolean"
            )
        if not isinstance(raw_paths, list) or not all(
            isinstance(path, str) for path in raw_paths
        ):
            raise DaemonProtocolError(
                "repository observation paths must be a list of strings"
            )
        paths = tuple(raw_paths)
        if paths_complete and dirty_path_count != len(paths):
            raise DaemonProtocolError(
                "complete repository observation path count mismatch"
            )
        if not paths_complete and paths:
            raise DaemonProtocolError(
                "incomplete repository observation must not expose partial paths"
            )
        if state is ObservationState.CLEAN and (dirty_path_count != 0 or paths):
            raise DaemonProtocolError(
                "clean repository observation cannot contain dirty paths"
            )
        if state is ObservationState.UNKNOWN and paths:
            raise DaemonProtocolError(
                "unknown repository observation cannot authorize dirty paths"
            )
        return paths

    def stats(self) -> dict[str, Any]:
        self._ensure_compatible()
        return self.request("stats")

    def stop(self) -> dict[str, Any]:
        self._ensure_compatible()
        return self.request("stop")

    def register_manifest(
        self,
        manifest: InputManifest,
        *,
        chunk_size: int = 10_000,
        max_chunk_bytes: int = 1_000_000,
    ) -> str:
        self._ensure_compatible()
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if max_chunk_bytes < 1024:
            raise ValueError("max_chunk_bytes must be >= 1024")
        begin = self.request("manifest_begin")
        token = str(begin["token"])
        chunk: list[str] = []
        encoded_bytes = 128
        for path in manifest.paths:
            path_bytes = len(json.dumps(path, ensure_ascii=False).encode("utf-8")) + 1
            if path_bytes + 128 > max_chunk_bytes:
                raise ValueError(f"manifest path exceeds chunk byte budget: {path!r}")
            if chunk and (
                len(chunk) >= chunk_size or encoded_bytes + path_bytes > max_chunk_bytes
            ):
                self.request("manifest_append", token=token, paths=chunk)
                chunk = []
                encoded_bytes = 128
            chunk.append(path)
            encoded_bytes += path_bytes
        if chunk:
            self.request("manifest_append", token=token, paths=chunk)
        committed = self.request("manifest_commit", token=token)
        handle = str(committed["manifest_handle"])
        if handle != manifest.fingerprint:
            raise DaemonProtocolError(
                "daemon registered a different manifest fingerprint"
            )
        return handle

    def drop_manifest(self, manifest_handle: str) -> bool:
        self._ensure_compatible()
        response = self.request("manifest_drop", manifest_handle=manifest_handle)
        return bool(response.get("deleted", False))

    def input_root_manifest(
        self,
        manifest_handle: str,
        *,
        verify: bool = False,
    ) -> dict[str, Any]:
        self._ensure_compatible()
        return self.request(
            "input_root",
            manifest_handle=manifest_handle,
            verify=verify,
        )

    def input_root(
        self,
        patterns: Sequence[str],
        *,
        require_matches: bool = True,
        verify: bool = False,
    ) -> dict[str, Any]:
        self._ensure_compatible()
        return self.request(
            "input_root",
            patterns=list(patterns),
            require_matches=require_matches,
            verify=verify,
        )
