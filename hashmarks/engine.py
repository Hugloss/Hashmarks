from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .client import prepare_default_state_dir
from .directory_store import DirectoryDigestStore
from .file_store import FileDigestStore
from .freshness import freshness_state
from .input_observation import CapturedInputs, DirectoryCapture
from .inputs import InputManifest, ResolvedInputScope
from .merkle import MerklePathScope, MerkleTree
from .observation import ChangeTracker, ObservationState
from .paths import canonical_host_path
from .schema import IDENTITY_SCHEMA
from .snapshot import DirectoryObservation, InputObservation, Snapshot
from .specs import InputValue, validate_input_values

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .digest import Digest
    from .watcher import NativeLinuxBatchWatcher, WatchdogBatchWatcher


class IdentityEngine:
    """Single ownership boundary for canonical repository content identity.

    Derived caches and filesystem observation accelerate repository identity,
    but never become stronger authority than current repository bytes.
    """

    def __init__(
        self,
        workspace: str | Path,
        *,
        state_dir: str | Path | None = None,
        persist_directory_digests: bool = False,
    ):
        self.workspace = canonical_host_path(workspace)
        if state_dir is None:
            self.state_dir = prepare_default_state_dir(self.workspace)
        else:
            state = Path(state_dir)
            if not state.is_absolute():
                state = self.workspace / state
            self.state_dir = canonical_host_path(state)
            self.state_dir.mkdir(parents=True, exist_ok=True)

        self.changes = ChangeTracker()
        self.file_store = FileDigestStore(self.state_dir / "identity.sqlite3")
        # Persisted directory nodes have no safe freshness read-side yet. Keep
        # the feature available for experiments/direct use, but do not pay the
        # write cost in the default engine until it provides measured value.
        self.directory_store = (
            DirectoryDigestStore(self.state_dir / "directories.sqlite3")
            if persist_directory_digests
            else None
        )
        self.merkle = MerkleTree(
            self.workspace,
            self.file_store,
            directory_store=self.directory_store,
            change_tracker=self.changes,
            path_scope=MerklePathScope(exclude_paths=(self.state_dir,)),
        )

    def close(self) -> None:
        if self.directory_store is not None:
            self.directory_store.close()
        self.file_store.close()

    def manifest(
        self,
        patterns: Iterable[str],
        *,
        require_matches: bool = True,
    ) -> InputManifest:
        return InputManifest.resolve(
            self.workspace,
            patterns,
            require_matches=require_matches,
        )

    def manifest_specs(
        self,
        inputs: Iterable[InputValue],
        *,
        require_matches: bool = True,
    ) -> InputManifest:
        return self.manifest(
            validate_input_values(
                self.workspace, inputs, require_matches=require_matches
            ),
            require_matches=require_matches,
        )

    def snapshot(self, manifest: InputManifest, *, verify: bool = False) -> Snapshot:
        before = self.changes.snapshot()
        digest = self.input_root(manifest, verify=verify)
        after = self.changes.snapshot()
        return Snapshot(
            digest=digest,
            manifest_fingerprint=manifest.fingerprint,
            generation=after.generation,
            observed_paths=before.paths,
            mode="local",
        )

    def observe_inputs(
        self,
        inputs: tuple[InputValue, ...],
        *,
        exclude: tuple[InputValue, ...],
        require_matches: bool,
        verify: bool,
        max_members: int,
    ) -> InputObservation:
        if type(max_members) is not int or max_members < 1:
            raise ValueError("max_members must be a positive integer")
        before = self.changes.snapshot()
        captured = self.merkle.observe_inputs(
            lambda: self._input_scope(inputs, exclude, require_matches=require_matches),
            verify=verify,
            max_members=max_members,
        )
        return self._input_observation(before.paths, captured)

    def observe_directory(
        self,
        *,
        exclude: tuple[str, ...],
        verify: bool,
        max_members: int,
        capture: DirectoryCapture,
    ) -> DirectoryObservation:
        before = self.changes.snapshot()
        captured = self.merkle.observe_inputs(
            lambda: ResolvedInputScope.directory_contents(
                self.workspace,
                tuple(sorted(set(exclude) | (self.merkle._excluded_paths - {""}))),
                max_members=max_members,
                checkpoint=capture.check,
            ),
            verify=verify,
            max_members=max_members,
            directory_capture=capture,
        )
        return DirectoryObservation(
            self._input_observation(before.paths, captured),
            captured.materialization_counts,
        )

    def _input_observation(
        self, observed_paths: tuple[str, ...], captured: CapturedInputs
    ) -> InputObservation:
        after = self.changes.snapshot()
        scope = captured.scope
        stale = {
            ObservationState.CLEAN: False,
            ObservationState.DIRTY: True,
            ObservationState.UNKNOWN: None,
        }[after.state]
        return InputObservation(
            snapshot=Snapshot(
                digest=captured.digest,
                manifest_fingerprint=scope.manifest.fingerprint,
                generation=after.generation,
                observed_paths=observed_paths,
                mode="local",
            ),
            manifest=scope.manifest,
            excluded_paths=scope.excluded_paths,
            members=captured.members,
            counts=captured.counts,
            freshness=freshness_state(stale),
            walk_ignore_names=tuple(sorted(self.merkle.walk_ignore_names)),
            mandatory_exclude_names=tuple(sorted(self.merkle.mandatory_exclude_names)),
            internal_excluded_paths=tuple(sorted(self.merkle._excluded_paths)),
        )

    def _input_scope(
        self,
        inputs: tuple[InputValue, ...],
        exclude: tuple[InputValue, ...],
        *,
        require_matches: bool,
    ) -> ResolvedInputScope:
        patterns = validate_input_values(
            self.workspace, inputs, require_matches=require_matches
        )
        exclusions = validate_input_values(
            self.workspace, exclude, require_matches=False
        )
        return ResolvedInputScope.resolve(
            self.workspace, patterns, exclusions, require_matches=require_matches
        )

    def stats(self) -> dict[str, object]:
        observation = self.changes.snapshot()
        return {
            "schema": IDENTITY_SCHEMA,
            "workspace": str(self.workspace),
            "observation": {
                "state": observation.state.value,
                "generation": observation.generation,
                "dirty_paths": len(observation.paths),
                "reason": observation.reason,
            },
            "file_store": self.file_store.stats(),
            "merkle": self.merkle.stats(),
            "last_reconciliation": self.merkle.last_reconciliation(),
            "cache": {
                "file_digest_rows": self.file_store.count(self.workspace),
            },
        }

    def record_changes(self, paths: Iterable[str | Path]) -> None:
        # Do not recompute here. The next identity read consumes this exact
        # dirty set lazily and invalidates only affected Merkle ancestors.
        self.changes.mark_dirty(paths)

    def mark_observer_unknown(self, reason: str = "observer continuity lost") -> None:
        self.changes.mark_unknown(reason)
        self.merkle.drop_hot_cache()

    def input_root(self, manifest: InputManifest, *, verify: bool = False) -> Digest:
        return self.merkle.digest_manifest(manifest, verify=verify)

    def workspace_root(self, *, verify: bool = False) -> Digest:
        return self.merkle.directory_digest("", verify=verify)

    def watcher(
        self, *, debounce_seconds: float = 0.05
    ) -> NativeLinuxBatchWatcher | WatchdogBatchWatcher:
        """Create the optional watcher wired to this engine's safety state."""
        from .watcher import create_default_watcher

        exclude_relative: tuple[str, ...] = ()
        try:
            state_rel = self.state_dir.relative_to(self.workspace).as_posix()
        except ValueError:
            pass
        else:
            exclude_relative = (state_rel,)

        return create_default_watcher(
            self.workspace,
            # The watcher thread only records changed paths in ChangeTracker.
            # Merkle invalidation stays lazy on the foreground identity read.
            callback=lambda _paths: None,
            debounce_seconds=debounce_seconds,
            change_tracker=self.changes,
            exclude_relative_paths=exclude_relative,
        )
