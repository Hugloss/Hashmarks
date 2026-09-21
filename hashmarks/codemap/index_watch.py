from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING, cast

from hashmarks.observation import ChangeTracker, ObservationState
from hashmarks.watcher import create_default_watcher

if TYPE_CHECKING:
    from .engine import CodeMap


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
        tracker = ChangeTracker()
        update_lock = threading.RLock()

        def publish_state(state: str) -> None:
            self.store.set_meta("watcher_pid", str(os.getpid()))
            self.store.set_meta("watcher_state", state)
            self.store.set_meta("watcher_heartbeat_unix", str(time.time()))

        def update(paths: list[str]) -> None:
            with update_lock:
                before = tracker.snapshot()
                result = self.sync(
                    None if before.state is ObservationState.UNKNOWN else paths
                )
                clean = tracker.mark_reconciled(expected_generation=before.generation)
                publish_state("clean" if clean else "dirty")
                if on_update is not None:
                    on_update(result, paths)

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
            update,
            debounce_seconds=debounce_seconds,
            change_tracker=tracker,
            exclude_relative_paths=exclude,
        )
        watcher.start()
        publish_state("reconciling")
        try:
            # Observer starts first so the cold scan has no uncovered gap.
            initial = self.sync()
            watcher.synchronize()
            tracker.mark_reconciled(expected_generation=tracker.snapshot().generation)
            publish_state("clean")
            if on_update is not None:
                on_update(initial, [])

            while True:
                time.sleep(0.5)
                snapshot = tracker.snapshot()
                if snapshot.state is ObservationState.UNKNOWN:
                    with update_lock:
                        snapshot = tracker.snapshot()
                        if snapshot.state is ObservationState.UNKNOWN:
                            publish_state("reconciling")
                            result = self.sync()
                            clean = tracker.mark_reconciled(
                                expected_generation=snapshot.generation
                            )
                            publish_state("clean" if clean else "dirty")
                            if on_update is not None:
                                on_update(result, [])
                            continue
                publish_state(snapshot.state.value)
        except KeyboardInterrupt:
            return
        finally:
            watcher.stop()
            self.store.set_meta("watcher_state", "stopped")
            self.store.set_meta("watcher_heartbeat_unix", str(time.time()))
            self.store.set_meta("watcher_pid", "")

