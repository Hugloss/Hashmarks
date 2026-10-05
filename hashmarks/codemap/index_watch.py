from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from hashmarks.observation import ChangeTracker, ObservationState
from hashmarks.watcher import create_default_watcher

from .watch_continuity import (
    WATCH_CONTINUITY_META,
    WatchContinuityRecord,
    watch_record_from_snapshot,
)

if TYPE_CHECKING:
    from .engine import CodeMap


class WatchLeaseHeldError(RuntimeError):
    """Raised when another live watcher already owns continuity authority."""


class WatchLeaseLostError(RuntimeError):
    """Raised when a watcher tries to publish after losing its fence."""


@dataclass(slots=True)
class _IndexWatchSession:
    """Mutable reconciliation state shared by watcher callbacks and the loop."""

    codemap: CodeMap
    on_update: Callable[[object, list[str]], None] | None
    tracker: ChangeTracker = field(default_factory=ChangeTracker)
    update_lock: threading.RLock = field(default_factory=threading.RLock)
    owner: str = field(default_factory=lambda: uuid.uuid4().hex)
    fence: int | None = None

    def _record(self, *, fence: int, active: bool) -> WatchContinuityRecord:
        return watch_record_from_snapshot(
            self.tracker.snapshot(),
            owner=self.owner,
            fence=fence,
            heartbeat_unix=time.time(),
            active=active,
            codemap_generation=self.codemap.store.generation(),
        )

    def acquire(self) -> None:
        with self.update_lock:
            for _ in range(8):
                raw = self.codemap.store.meta(WATCH_CONTINUITY_META)
                current = WatchContinuityRecord.from_json(raw)
                if current is not None and current.lease_live():
                    raise WatchLeaseHeldError(
                        "CodeMap watch continuity is already owned by "
                        f"{current.owner} (fence {current.fence})"
                    )
                fence = 1 if current is None else current.fence + 1
                record = self._record(fence=fence, active=True)
                if self.codemap.store.compare_and_set_meta(
                    WATCH_CONTINUITY_META,
                    expected=raw,
                    value=record.to_json(),
                ):
                    self.fence = fence
                    return
            raise RuntimeError("CodeMap watch continuity authority changed repeatedly")

    def publish(self, *, active: bool = True) -> None:
        with self.update_lock:
            if self.fence is None:
                raise RuntimeError("CodeMap watch continuity lease is not acquired")
            raw = self.codemap.store.meta(WATCH_CONTINUITY_META)
            current = WatchContinuityRecord.from_json(raw)
            if (
                current is None
                or current.owner != self.owner
                or current.fence != self.fence
                or (active and not current.active)
            ):
                raise WatchLeaseLostError(
                    "CodeMap watch continuity lease was replaced by another owner"
                )
            record = self._record(fence=self.fence, active=active)
            if not self.codemap.store.compare_and_set_meta(
                WATCH_CONTINUITY_META,
                expected=raw,
                value=record.to_json(),
            ):
                raise WatchLeaseLostError(
                    "CodeMap watch continuity changed while publishing"
                )

    def release(self) -> None:
        if self.fence is None:
            return
        try:
            self.publish(active=False)
        except WatchLeaseLostError:
            pass

    def reconcile(self, paths: list[str]) -> None:
        with self.update_lock:
            before = self.tracker.snapshot()
            result = self.codemap.sync(
                None if before.state is ObservationState.UNKNOWN else paths
            )
            self.tracker.mark_reconciled(expected_generation=before.generation)
            self.publish()
            if self.on_update is not None:
                self.on_update(result, paths)

    def refresh_state(self) -> None:
        snapshot = self.tracker.snapshot()
        if snapshot.state is ObservationState.UNKNOWN:
            with self.update_lock:
                snapshot = self.tracker.snapshot()
                if snapshot.state is ObservationState.UNKNOWN:
                    self.publish()
                    self.reconcile([])
                    return
        self.publish()


class IndexWatchMixin:
    """Foreground CodeMap watch orchestration over repository sync authority."""

    def watch_forever(self, *, debounce_seconds: float = 0.05, on_update=None) -> None:
        """Maintain CodeMap incrementally in a separate foreground process.

        Watcher loss/overflow is fail-safe: the control loop observes UNKNOWN
        and performs a full reconciliation. Parser work stays outside the
        identity daemon and therefore outside identity's latency-critical path.
        """

        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        session = _IndexWatchSession(self, on_update)
        session.acquire()
        watcher = None
        try:
            exclude = []
            try:
                state_rel = self.state_dir.relative_to(self.workspace).as_posix()
            except ValueError:
                pass
            else:
                exclude.append(state_rel)
            exclude.append(".git")
            watcher = create_default_watcher(
                self.workspace,
                session.reconcile,
                debounce_seconds=debounce_seconds,
                change_tracker=session.tracker,
                exclude_relative_paths=exclude,
            )
            watcher.start()
            # Observer starts first so the cold scan has no uncovered gap.
            initial = self.sync()
            watcher.synchronize()
            session.tracker.mark_reconciled(
                expected_generation=session.tracker.snapshot().generation
            )
            session.publish()
            if on_update is not None:
                on_update(initial, [])

            while True:
                time.sleep(0.5)
                session.refresh_state()
        except KeyboardInterrupt:
            return
        finally:
            if watcher is not None:
                watcher.stop()
            session.tracker.mark_unknown("watcher stopped")
            session.release()
