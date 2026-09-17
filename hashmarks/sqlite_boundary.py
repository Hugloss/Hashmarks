from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


def _enable_wal_with_bounded_retry(
    db: sqlite3.Connection,
    *,
    busy_timeout_ms: int,
) -> None:
    """Enable WAL across concurrent first-open callers.

    SQLite's busy handler does not reliably wait while ``journal_mode`` itself is
    being changed. Retry only that known lock/busy race, bounded by the same timeout
    used for ordinary database lock contention.
    """

    timeout_seconds = max(0, int(busy_timeout_ms)) / 1_000
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            db.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if (
                "database is locked" not in message
                and "database is busy" not in message
            ):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.01, remaining))


def configure_sqlite_connection(
    db: sqlite3.Connection,
    *,
    busy_timeout_ms: int = 5_000,
) -> None:
    """Apply one shared SQLite concurrency policy to a new connection.

    ``busy_timeout`` owns ordinary lock contention. WAL negotiation has one additional
    bounded retry because SQLite can return ``database is locked`` immediately when
    multiple callers first-open the same database and change journal mode concurrently.
    """

    db.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    _enable_wal_with_bounded_retry(db, busy_timeout_ms=busy_timeout_ms)
    db.execute("PRAGMA synchronous=NORMAL")


@contextmanager
def sqlite_transaction(
    db: sqlite3.Connection,
    *,
    begin: str = "BEGIN",
) -> Iterator[None]:
    """Own BEGIN/COMMIT/ROLLBACK for one simple SQLite transaction."""

    db.execute(begin)
    try:
        yield
        db.execute("COMMIT")
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
