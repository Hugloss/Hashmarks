from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Generic, Hashable, TypeVar

T = TypeVar("T")


@dataclass
class _Flight(Generic[T]):
    event: threading.Event
    result: T | None = None
    error: BaseException | None = None


class SingleFlight(Generic[T]):
    """Share one in-process computation for an exact immutable key.

    Entries exist only while work is in flight. Results are not retained here;
    persistent reuse belongs to the context CAS. Followers receive only the
    leader's immutable result or exception, never leader-local session state.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flights: dict[Hashable, _Flight[T]] = {}

    def run(self, key: Hashable, fn: Callable[[], T]) -> tuple[T, bool]:
        with self._lock:
            flight = self._flights.get(key)
            if flight is None:
                flight = _Flight(event=threading.Event())
                self._flights[key] = flight
                leader = True
            else:
                leader = False

        if leader:
            try:
                flight.result = fn()
            except BaseException as exc:
                flight.error = exc
            finally:
                with self._lock:
                    self._flights.pop(key, None)
                flight.event.set()
        else:
            flight.event.wait()

        if flight.error is not None:
            raise flight.error
        return flight.result, not leader  # type: ignore[return-value]

    def in_flight(self) -> int:
        with self._lock:
            return len(self._flights)
