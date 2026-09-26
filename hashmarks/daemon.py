from __future__ import annotations

import contextlib
import json
import os
import secrets
import socket
import socketserver
import threading
from typing import TYPE_CHECKING, Any

from .client import default_socket_path, prepare_default_state_dir
from .engine import IdentityEngine
from .inputs import InputManifest
from .ipc_boundary import dispatch_json_request
from .observation import ObservationState
from .paths import (
    canonical_host_path,
    has_glob,
    normalize_relative_path,
    normalize_relative_pattern,
)
from .schema import (
    DAEMON_CAPABILITIES,
    DAEMON_PROTOCOL_VERSION,
    DAEMON_SEMANTICS,
    IDENTITY_SCHEMA,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

_PROTOCOL_VERSION = DAEMON_PROTOCOL_VERSION
_MAX_REQUEST = 4 * 1024 * 1024
_MAX_PENDING_MANIFESTS = 8
_MAX_REGISTERED_MANIFEST_PATHS = 2_000_000
_MAX_TOTAL_REGISTERED_MANIFEST_PATHS = 4_000_000
_MAX_REGISTERED_MANIFESTS = 1024


_UNIX_STREAM_SERVER = getattr(socketserver, "UnixStreamServer", None)

if _UNIX_STREAM_SERVER is not None:

    class _UnixServer(socketserver.ThreadingMixIn, _UNIX_STREAM_SERVER):
        """Thread-per-request Unix socket owner with explicit state locking."""

        allow_reuse_address = False
        request_queue_size = 128
        daemon_threads = False
        block_on_close = True

else:

    class _UnixServer:
        """Import-safe placeholder when the platform has no Unix socket server."""


class _RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        daemon: IdentityDaemon = self.server.identity_daemon  # type: ignore[attr-defined]
        raw = self.rfile.readline(_MAX_REQUEST + 1)
        if len(raw) > _MAX_REQUEST:
            daemon._write_response(
                self.wfile, {"ok": False, "error": "request exceeded size limit"}
            )
            return
        response = dispatch_json_request(raw, daemon.dispatch)
        daemon._write_response(self.wfile, response)


class IdentityDaemon:
    """Long-lived identity owner with watcher-backed observation continuity.

    The daemon never turns watcher state into canonical identity. It only keeps
    already-proven Merkle/manifest state alive between CLI processes. A lost
    watcher/daemon continuity transitions ChangeTracker to UNKNOWN, forcing the
    next identity request through normal reconciliation before hot state is
    trusted again.
    """

    def __init__(
        self,
        workspace: str | Path,
        *,
        state_dir: str | Path | None = None,
        socket_path: str | Path | None = None,
        watcher_factory: Callable[[IdentityEngine], Any] | None = None,
    ) -> None:
        self.workspace = canonical_host_path(workspace)
        self.state_dir = (
            prepare_default_state_dir(self.workspace)
            if state_dir is None
            else canonical_host_path(state_dir)
        )
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.state_dir, 0o700)
        except OSError:
            # Some filesystems/platforms do not expose POSIX permission bits.
            pass
        self.socket_path = (
            default_socket_path(self.workspace)
            if socket_path is None
            else canonical_host_path(socket_path)
        )
        self.engine = IdentityEngine(self.workspace, state_dir=self.state_dir)
        self._watcher_factory = watcher_factory or (lambda engine: engine.watcher())
        self._watcher = None
        self._server: _UnixServer | None = None
        self._request_lock = threading.RLock()
        self._literal_manifests: dict[tuple[tuple[str, ...], bool], InputManifest] = {}
        self._registered_manifests: dict[str, tuple[InputManifest, int]] = {}
        self._registered_manifest_paths = 0
        self._pending_manifests: dict[str, list[str]] = {}
        self._request_count = 0

    @staticmethod
    def _write_response(stream, response: dict[str, Any]) -> None:
        stream.write(
            (json.dumps(response, separators=(",", ":"), sort_keys=True) + "\n").encode(
                "utf-8"
            )
        )
        stream.flush()

    def _manifest(
        self, patterns: Sequence[str], require_matches: bool
    ) -> InputManifest:
        normalized = tuple(normalize_relative_pattern(p) for p in patterns)
        # Exact file/directory declarations have stable membership semantics:
        # a directory node naturally absorbs new/deleted descendants. Glob
        # membership itself can change, so globs are deliberately re-resolved.
        if any(has_glob(pattern) for pattern in normalized):
            return self.engine.manifest(normalized, require_matches=require_matches)
        key = (normalized, require_matches)
        with self._request_lock:
            manifest = self._literal_manifests.get(key)
        if manifest is not None:
            return manifest

        # Manifest resolution can walk a large directory.  Do not hold the
        # daemon-state lock while that repository work executes.  Two callers
        # may deterministically resolve the same literal manifest in parallel;
        # only one immutable object is retained.
        resolved = self.engine.manifest(normalized, require_matches=require_matches)
        with self._request_lock:
            return self._literal_manifests.setdefault(key, resolved)

    def _manifest_from_request(self, request: dict[str, Any]) -> InputManifest:
        handle = request.get("manifest_handle")
        if handle is not None:
            if not isinstance(handle, str):
                raise ValueError("manifest_handle must be a string")
            with self._request_lock:
                try:
                    return self._registered_manifests[handle][0]
                except KeyError as exc:
                    raise KeyError(f"unknown registered manifest: {handle}") from exc
        patterns = request.get("patterns")
        if not isinstance(patterns, list) or not all(
            isinstance(p, str) for p in patterns
        ):
            raise ValueError("patterns must be a list of strings")
        return self._manifest(patterns, bool(request.get("require_matches", True)))

    def _manifest_begin(self) -> dict[str, Any]:
        if len(self._pending_manifests) >= _MAX_PENDING_MANIFESTS:
            raise RuntimeError("too many pending manifest registrations")
        token = secrets.token_hex(16)
        self._pending_manifests[token] = []
        return {"ok": True, "token": token}

    def _manifest_append(self, request: dict[str, Any]) -> dict[str, Any]:
        token = request.get("token")
        paths = request.get("paths")
        if not isinstance(token, str) or token not in self._pending_manifests:
            raise KeyError("unknown pending manifest token")
        if not isinstance(paths, list) or not all(
            isinstance(path, str) for path in paths
        ):
            raise ValueError("paths must be a list of strings")
        pending = self._pending_manifests[token]
        if len(pending) + len(paths) > _MAX_REGISTERED_MANIFEST_PATHS:
            self._pending_manifests.pop(token, None)
            raise ValueError("registered manifest exceeds path limit")
        pending.extend(
            normalize_relative_path(path, allow_root=False) for path in paths
        )
        return {"ok": True, "token": token, "received": len(pending)}

    def _manifest_commit(self, request: dict[str, Any]) -> dict[str, Any]:
        token = request.get("token")
        if not isinstance(token, str):
            raise ValueError("token must be a string")
        try:
            pending = self._pending_manifests.pop(token)
        except KeyError as exc:
            raise KeyError("unknown pending manifest token") from exc
        manifest = InputManifest(tuple(sorted(set(pending))))
        existing = self._registered_manifests.get(manifest.fingerprint)
        if existing is not None:
            self._registered_manifests[manifest.fingerprint] = (
                existing[0],
                existing[1] + 1,
            )
        else:
            if len(self._registered_manifests) >= _MAX_REGISTERED_MANIFESTS:
                raise RuntimeError(
                    "registered manifest handle limit reached; restart daemon or release handles"
                )
            if (
                self._registered_manifest_paths + len(manifest.paths)
                > _MAX_TOTAL_REGISTERED_MANIFEST_PATHS
            ):
                raise RuntimeError(
                    "registered manifest path budget exhausted; restart daemon or release handles"
                )
            self._registered_manifests[manifest.fingerprint] = (manifest, 1)
            self._registered_manifest_paths += len(manifest.paths)
        return {
            "ok": True,
            "manifest_handle": manifest.fingerprint,
            "manifest": manifest.fingerprint,
            "paths": len(manifest.paths),
            "references": self._registered_manifests[manifest.fingerprint][1],
        }

    def _synchronize_observer(self) -> None:
        watcher = self._watcher
        if watcher is None:
            self.engine.mark_observer_unknown("daemon watcher is not active")
            return
        synchronize = getattr(watcher, "synchronize", None)
        if synchronize is None or not bool(synchronize()):
            self.engine.mark_observer_unknown(
                "watcher backend has no request-time observation barrier"
            )

    def _status_response(self, _request: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            snapshot = self.engine.changes.snapshot()
            return {
                "ok": True,
                "schema": IDENTITY_SCHEMA,
                "protocol": _PROTOCOL_VERSION,
                "semantics": DAEMON_SEMANTICS,
                "capabilities": list(DAEMON_CAPABILITIES),
                "pid": os.getpid(),
                "workspace": str(self.workspace),
                "state_dir": str(self.state_dir),
                "socket": str(self.socket_path),
                "observation": snapshot.state.value,
                "generation": snapshot.generation,
                "dirty_paths": len(snapshot.paths),
                "watcher_backend": type(self._watcher).__name__
                if self._watcher is not None
                else None,
                "registered_manifests": len(self._registered_manifests),
                "registered_manifest_references": sum(
                    refs for _, refs in self._registered_manifests.values()
                ),
                "registered_manifest_paths": self._registered_manifest_paths,
                "requests": self._request_count,
            }

    def _observe_response(self, _request: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            self._synchronize_observer()
            snapshot = self.engine.changes.snapshot()
            # Derived consumers may reuse exact observer paths only when the
            # bounded payload is complete. Larger dirty sets fail closed to
            # generation-only evidence so consumers can reconcile fully.
            max_paths = 4096
            paths_complete = (
                snapshot.state is not ObservationState.UNKNOWN
                and len(snapshot.paths) <= max_paths
            )
            return {
                "ok": True,
                "schema": IDENTITY_SCHEMA,
                "protocol": _PROTOCOL_VERSION,
                "semantics": DAEMON_SEMANTICS,
                "observation": snapshot.state.value,
                "generation": snapshot.generation,
                "dirty_paths": len(snapshot.paths),
                "paths": list(snapshot.paths) if paths_complete else [],
                "paths_complete": paths_complete,
                "reason": snapshot.reason,
            }

    def _stats_response(self, _request: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            return {
                "ok": True,
                **self.engine.stats(),
                "daemon_requests": self._request_count,
            }

    def _manifest_begin_response(self, _request: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            return self._manifest_begin()

    def _manifest_append_response(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            return self._manifest_append(request)

    def _manifest_commit_response(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            return self._manifest_commit(request)

    def _manifest_drop_response(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            handle = request.get("manifest_handle")
            if not isinstance(handle, str):
                raise ValueError("manifest_handle must be a string")
            existing = self._registered_manifests.get(handle)
            if existing is None:
                return {"ok": True, "deleted": False, "references": 0}
            manifest, references = existing
            if references > 1:
                self._registered_manifests[handle] = (manifest, references - 1)
                return {"ok": True, "deleted": False, "references": references - 1}
            self._registered_manifests.pop(handle, None)
            self._registered_manifest_paths -= len(manifest.paths)
            return {"ok": True, "deleted": True, "references": 0}

    def _input_root_response(self, request: dict[str, Any]) -> dict[str, Any]:
        self._synchronize_observer()
        manifest = self._manifest_from_request(request)
        snap = self.engine.snapshot(manifest, verify=bool(request.get("verify", False)))
        payload = snap.as_dict()
        payload["mode"] = "daemon"
        return {"ok": True, **payload}

    def _stop_response(self, _request: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            server = self._server
        if server is not None:
            threading.Thread(target=server.shutdown, daemon=True).start()
        return {"ok": True, "stopping": True}

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("protocol") != _PROTOCOL_VERSION:
            raise ValueError("unsupported protocol version")
        with self._request_lock:
            self._request_count += 1
        handlers = {
            "status": self._status_response,
            "observe": self._observe_response,
            "stats": self._stats_response,
            "manifest_begin": self._manifest_begin_response,
            "manifest_append": self._manifest_append_response,
            "manifest_commit": self._manifest_commit_response,
            "manifest_drop": self._manifest_drop_response,
            "input_root": self._input_root_response,
            "stop": self._stop_response,
        }
        op = request.get("op")
        handler = handlers.get(op)
        if handler is None:
            raise ValueError(f"unknown operation: {op!r}")
        return handler(request)

    def _prepare_socket(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.socket_path.parent, 0o700)
        if self.socket_path.exists() or self.socket_path.is_socket():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(0.15)
                probe.connect(str(self.socket_path))
            except OSError:
                self.socket_path.unlink(missing_ok=True)
            else:
                raise RuntimeError(
                    f"identity daemon already running at {self.socket_path}"
                )
            finally:
                probe.close()

    def serve_forever(self) -> None:
        if _UNIX_STREAM_SERVER is None:
            raise RuntimeError(
                "Hashmarks identity daemon requires Unix-domain socket server support"
            )
        self._prepare_socket()
        watcher = self._watcher_factory(self.engine)
        # Watcher starts before the socket becomes available. The initial
        # ChangeTracker is UNKNOWN; the first identity request reconciles while
        # the observer is already live, closing the startup observation gap.
        watcher.start()
        self._watcher = watcher
        try:
            server = _UnixServer(str(self.socket_path), _RequestHandler)
            server.identity_daemon = self  # type: ignore[attr-defined]
            self._server = server
            os.chmod(self.socket_path, 0o600)
            server.serve_forever(poll_interval=0.1)
        finally:
            if self._server is not None:
                self._server.server_close()
            try:
                watcher.stop()
            finally:
                self.engine.close()
                self.socket_path.unlink(missing_ok=True)
