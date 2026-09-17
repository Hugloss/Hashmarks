from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .paths import normalize_relative_path

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class UnstableObservationError(RuntimeError):
    """Raised when the filesystem keeps changing through reconciliation."""


class ObservationState(str, Enum):
    """Confidence in the change-observation stream.

    CLEAN means all known filesystem events since the last reconciliation have
    been accounted for. DIRTY means exact changed paths are known. UNKNOWN
    means the observer may have missed changes and cached directory identities
    must not be trusted until a reconciliation scan succeeds.
    """

    CLEAN = "clean"
    DIRTY = "dirty"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ChangeSnapshot:
    state: ObservationState
    generation: int
    paths: tuple[str, ...]
    reason: str | None = None


class ChangeTracker:
    """Thread-safe watcher/change-journal state.

    A new tracker starts UNKNOWN on purpose: no process may assume that a
    previous observer covered the gap before this process started.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = ObservationState.UNKNOWN
        self._generation = 0
        self._paths: set[str] = set()
        self._reason: str | None = "observer not yet reconciled"

    def mark_dirty(self, paths: Iterable[str | Path]) -> None:
        normalized = {normalize_relative_path(path) for path in paths}
        with self._lock:
            self._paths.update(normalized)
            if self._state is not ObservationState.UNKNOWN:
                self._state = ObservationState.DIRTY
            self._generation += 1

    def mark_unknown(self, reason: str = "observer continuity lost") -> None:
        with self._lock:
            self._state = ObservationState.UNKNOWN
            self._reason = reason
            self._paths.clear()
            self._generation += 1

    def mark_reconciled(self, *, expected_generation: int | None = None) -> bool:
        """Mark CLEAN only if no newer observation arrived during reconciliation.

        Returns True when the transition was committed. A generation mismatch
        leaves the newer DIRTY/UNKNOWN state untouched.
        """
        with self._lock:
            if (
                expected_generation is not None
                and self._generation != expected_generation
            ):
                return False
            if (
                self._state is ObservationState.CLEAN
                and not self._paths
                and self._reason is None
            ):
                # Re-reading an already reconciled world does not create a new
                # observation generation. This keeps hot daemon reads truly
                # read-only while generation changes still represent actual
                # observation transitions.
                return True
            self._state = ObservationState.CLEAN
            self._reason = None
            self._paths.clear()
            self._generation += 1
            return True

    def snapshot(self) -> ChangeSnapshot:
        with self._lock:
            return ChangeSnapshot(
                state=self._state,
                generation=self._generation,
                paths=tuple(sorted(self._paths)),
                reason=self._reason,
            )
