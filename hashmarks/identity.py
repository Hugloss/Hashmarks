from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

from .client import DaemonCompatibilityError, DaemonUnavailableError, IdentityClient
from .digest import Digest
from .engine import IdentityEngine
from .inputs import InputManifest
from .schema import IDENTITY_SCHEMA
from .snapshot import Snapshot
from .specs import InputValue, validate_input_values


class RepositoryIdentityMode(str, Enum):
    AUTO = "auto"
    LOCAL = "local"
    DAEMON = "daemon"


class RepositoryIdentity:
    """Small, safe public façade over local or daemon-maintained identity.

    ``auto`` prefers an already-running daemon and falls back to the exact same
    canonical local implementation. Falling back changes performance, never
    identity semantics.
    """

    def __init__(
        self,
        workspace: str | Path = ".",
        *,
        mode: str | RepositoryIdentityMode = RepositoryIdentityMode.AUTO,
        state_dir: str | Path | None = None,
        timeout: float = 30.0,
        socket_path: str | Path | None = None,
        local_observer: str = "reconcile",
    ) -> None:
        self.mode = RepositoryIdentityMode(mode)
        self.client = IdentityClient(
            workspace,
            state_dir=state_dir,
            socket_path=socket_path,
            timeout=timeout,
        )
        self.workspace = self.client.workspace
        self.state_dir = self.client.state_dir
        if local_observer not in {"reconcile", "watcher", "manual"}:
            raise ValueError("local_observer must be reconcile, watcher, or manual")
        self.local_observer = local_observer
        self._engine: IdentityEngine | None = None
        self._local_watcher = None
        self._manifest_handles: dict[str, str] = {}
        self._daemon_confirmed = False
        self._codemap = None

        if self.mode is RepositoryIdentityMode.DAEMON:
            # Fail immediately for an explicitly required daemon.
            self.client.status()
            self._daemon_confirmed = True

    def __enter__(self) -> "RepositoryIdentity":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._manifest_handles and self._daemon_confirmed:
            for handle in tuple(self._manifest_handles.values()):
                try:
                    self.client.drop_manifest(handle)
                except (DaemonUnavailableError, DaemonCompatibilityError):
                    break
            self._manifest_handles.clear()
        if self._codemap is not None:
            self._codemap.close()
            self._codemap = None
        if self._local_watcher is not None:
            self._local_watcher.stop()
            self._local_watcher = None
        if self._engine is not None:
            self._engine.close()
            self._engine = None

    def _local(self) -> IdentityEngine:
        if self._engine is None:
            self._engine = IdentityEngine(self.workspace, state_dir=self.state_dir)
            if self.local_observer == "watcher":
                watcher = self._engine.watcher()
                watcher.start()
                self._local_watcher = watcher
        return self._engine

    def _prepare_local_read(self) -> IdentityEngine:
        engine = self._local()
        if self.local_observer == "reconcile":
            engine.mark_observer_unknown("local facade configured for per-read reconciliation")
        elif self.local_observer == "watcher":
            watcher = self._local_watcher
            synchronize = None if watcher is None else getattr(watcher, "synchronize", None)
            if synchronize is None or not bool(synchronize()):
                engine.mark_observer_unknown("local watcher has no request-time observation barrier")
        # manual is an explicit expert mode: the caller owns record_changes().
        return engine

    def record_changes(self, paths: Iterable[str | Path]) -> None:
        if self.local_observer != "manual":
            raise RuntimeError("record_changes is only valid with local_observer='manual'")
        self._local().record_changes(paths)


    def _daemon_available(self) -> bool:
        if self.mode is RepositoryIdentityMode.LOCAL:
            return False
        if self._daemon_confirmed:
            return True
        try:
            self.client.status()
        except (DaemonUnavailableError, DaemonCompatibilityError):
            if self.mode is RepositoryIdentityMode.DAEMON:
                raise
            return False
        self._daemon_confirmed = True
        return True

    @property
    def active_mode(self) -> str:
        return "daemon" if self._daemon_available() else "local"

    @staticmethod
    def _snapshot_from_response(response: Mapping[str, object]) -> Snapshot:
        return Snapshot(
            digest=Digest(hash=str(response["hash"]), size=int(response["size"])),
            manifest_fingerprint=str(response["manifest"]),
            generation=None if response.get("generation") is None else int(response["generation"]),
            observed_paths=tuple(str(path) for path in response.get("observed_paths", [])),
            mode=str(response.get("mode", "daemon")),
        )

    def manifest(
        self,
        inputs: Iterable[InputValue],
        *,
        require_matches: bool = True,
    ) -> InputManifest:
        patterns = validate_input_values(
            self.workspace, inputs, require_matches=require_matches
        )
        return InputManifest.resolve(
            self.workspace, patterns, require_matches=require_matches
        )

    def snapshot(
        self,
        *inputs: InputValue,
        require_matches: bool = True,
        verify: bool = False,
    ) -> Snapshot:
        patterns = validate_input_values(
            self.workspace, inputs, require_matches=require_matches
        )
        if self._daemon_available():
            try:
                response = self.client.input_root(
                    patterns,
                    require_matches=require_matches,
                    verify=verify,
                )
                return self._snapshot_from_response(response)
            except (DaemonUnavailableError, DaemonCompatibilityError):
                if self.mode is RepositoryIdentityMode.DAEMON:
                    raise
                self._daemon_confirmed = False
        engine = self._prepare_local_read()
        manifest = engine.manifest(patterns, require_matches=require_matches)
        return engine.snapshot(manifest, verify=verify)

    def snapshot_manifest(self, manifest: InputManifest, *, verify: bool = False) -> Snapshot:
        if self._daemon_available():
            try:
                handle = self._manifest_handles.get(manifest.fingerprint)
                if handle is None:
                    handle = self.client.register_manifest(manifest)
                    self._manifest_handles[manifest.fingerprint] = handle
                response = self.client.input_root_manifest(handle, verify=verify)
                return self._snapshot_from_response(response)
            except (DaemonUnavailableError, DaemonCompatibilityError):
                if self.mode is RepositoryIdentityMode.DAEMON:
                    raise
                self._daemon_confirmed = False
        return self._prepare_local_read().snapshot(manifest, verify=verify)


    def code_map(self):
        """Return the lazily-created derived CodeMap for repository-intelligence queries.

        Importing or using Identity never loads CodeMap unless this method is called,
        preserving the latency-sensitive identity module graph.
        """
        if self._codemap is None:
            from .codemap import CodeMap

            self._codemap = CodeMap(self.workspace, state_dir=self.state_dir)
        return self._codemap

    def stats(self) -> dict[str, object]:
        if self._daemon_available():
            try:
                response = self.client.stats()
                return {key: value for key, value in response.items() if key != "ok"}
            except (DaemonUnavailableError, DaemonCompatibilityError):
                if self.mode is RepositoryIdentityMode.DAEMON:
                    raise
                self._daemon_confirmed = False
        return self._local().stats()

    def doctor(self) -> dict[str, object]:
        daemon_status: dict[str, object] | None = None
        daemon_error: str | None = None
        try:
            daemon_status = self.client.status()
        except (DaemonUnavailableError, DaemonCompatibilityError) as exc:
            daemon_error = str(exc)
        return {
            "schema": IDENTITY_SCHEMA,
            "workspace": str(self.workspace),
            "state_dir": str(self.state_dir),
            "requested_mode": self.mode.value,
            "active_mode": "daemon" if daemon_status is not None and self.mode is not RepositoryIdentityMode.LOCAL else "local",
            "daemon": daemon_status,
            "daemon_error": daemon_error,
        }
