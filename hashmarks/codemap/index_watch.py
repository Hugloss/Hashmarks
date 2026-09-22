from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from hashmarks.observation import ChangeTracker, ObservationState
from hashmarks.watcher import create_default_watcher

if TYPE_CHECKING:
    from .engine import CodeMap


@dataclass(slots=True)
class _IndexWatchSession:
    """Mutable reconciliation state shared by watcher callbacks and the loop."""

    codemap: CodeMap
    on_update: Callable[[object, list[str]], None] | None
    tracker: ChangeTracker = field(default_factory=ChangeTracker)
    update_lock: threading.RLock = field(default_factory=threading.RLock)

    def publish(self, state: str) -> None:
        self.codemap.store.set_meta("watcher_pid", str(os.getpid()))
        self.codemap.store.set_meta("watcher_state", state)
        self.codemap.store.set_meta("watcher_heartbeat_unix", str(time.time()))

    def reconcile(self, paths: list[str]) -> None:
        with self.update_lock:
            before = self.tracker.snapshot()
            result = self.codemap.sync(
                None if before.state is ObservationState.UNKNOWN else paths
            )
            clean = self.tracker.mark_reconciled(expected_generation=before.generation)
            self.publish("clean" if clean else "dirty")
            if self.on_update is not None:
                self.on_update(result, paths)

    def refresh_state(self) -> None:
        snapshot = self.tracker.snapshot()
        if snapshot.state is ObservationState.UNKNOWN:
            with self.update_lock:
                snapshot = self.tracker.snapshot()
                if snapshot.state is ObservationState.UNKNOWN:
                    self.publish("reconciling")
                    self.reconcile([])
                    return
        self.publish(snapshot.state.value)


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

        exclude = []
        try:
            state_rel = self.state_dir.relative_to(self.workspace).as_posix()
        except ValueError:
            pass
        else:
            exclude.append(state_rel)
        exclude.extend([".git", ".fastidentity"])
        watcher = create_default_watcher(
            self.workspace,
            session.reconcile,
            debounce_seconds=debounce_seconds,
            change_tracker=session.tracker,
            exclude_relative_paths=exclude,
        )
        watcher.start()
        session.publish("reconciling")
        try:
            # Observer starts first so the cold scan has no uncovered gap.
            initial = self.sync()
            watcher.synchronize()
            session.tracker.mark_reconciled(
                expected_generation=session.tracker.snapshot().generation
            )
            session.publish("clean")
            if on_update is not None:
                on_update(initial, [])

            while True:
                time.sleep(0.5)
                session.refresh_state()
        except KeyboardInterrupt:
            return
        finally:
            watcher.stop()
            self.store.set_meta("watcher_state", "stopped")
            self.store.set_meta("watcher_heartbeat_unix", str(time.time()))
            self.store.set_meta("watcher_pid", "")
