from __future__ import annotations

import time
from typing import Callable, TypeVar

from .file_store import UnstableFileError

_TRANSIENT_RETRY_DELAYS = (0.0, 0.005, 0.01, 0.02, 0.04, 0.08, 0.16, 0.25)
_TRANSIENT_RUNTIME_MESSAGES = (
    "CodeMap generation is incomplete (BUILDING)",
    "CodeMap generation changed before nested decision session",
    "CodeMap generation changed during decision session",
)

_T = TypeVar("_T")


def is_transient_repository_race(exc: BaseException) -> bool:
    """Return whether *exc* is a known recomputable repository race."""

    if isinstance(exc, UnstableFileError):
        return True
    if not isinstance(exc, RuntimeError):
        return False
    message = str(exc)
    return any(marker in message for marker in _TRANSIENT_RUNTIME_MESSAGES)


def retry_transient_repository_race(operation: Callable[[], _T]) -> _T:
    """Retry only bounded repository races that are safe to recompute from scratch.

    Each attempt reruns the complete operation against current durable state. This
    is not a stale-result fallback and does not create a second freshness authority.
    Validation errors and unrelated runtime failures propagate immediately.
    """

    last_error: BaseException | None = None
    for delay in _TRANSIENT_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            return operation()
        except (RuntimeError, UnstableFileError) as exc:
            if not is_transient_repository_race(exc):
                raise
            last_error = exc
    assert last_error is not None
    raise last_error
