from __future__ import annotations

import time
from typing import TYPE_CHECKING, TypeVar

from .file_store import UnstableFileError

if TYPE_CHECKING:
    from collections.abc import Callable

_TRANSIENT_RETRY_BUDGET_SECONDS = 5.0
_TRANSIENT_RETRY_INITIAL_DELAY_SECONDS = 0.005
_TRANSIENT_RETRY_MAX_DELAY_SECONDS = 0.25
_TRANSIENT_RUNTIME_MESSAGES = (
    "CodeMap generation is incomplete (BUILDING)",
    "CodeMap generation changed before expected decision session",
    "CodeMap generation changed before nested decision session",
    "CodeMap generation changed before expected decision session",
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
    return message.startswith(_TRANSIENT_RUNTIME_MESSAGES)


def retry_transient_repository_race(operation: Callable[[], _T]) -> _T:
    """Retry only bounded repository races that are safe to recompute from scratch.

    Each attempt reruns the complete operation against current durable state. This
    is not a stale-result fallback and does not create a second freshness authority.
    Validation errors and unrelated runtime failures propagate immediately.
    """

    deadline: float | None = None
    delay = 0.0
    while True:
        try:
            return operation()
        except (RuntimeError, UnstableFileError) as exc:
            if not is_transient_repository_race(exc):
                raise

            now = time.monotonic()
            if deadline is None:
                deadline = now + _TRANSIENT_RETRY_BUDGET_SECONDS
            remaining = deadline - now
            if remaining <= 0:
                raise

            if delay:
                time.sleep(min(delay, remaining))
            delay = (
                _TRANSIENT_RETRY_INITIAL_DELAY_SECONDS
                if delay == 0.0
                else min(delay * 2, _TRANSIENT_RETRY_MAX_DELAY_SECONDS)
            )
