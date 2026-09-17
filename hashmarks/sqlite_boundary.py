from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator


def configure_sqlite_connection(
    db: sqlite3.Connection,
    *,
    busy_timeout_ms: int = 5_000,
) -> None:
    """Apply one shared SQLite concurrency policy to a new connection.

    ``busy_timeout`` is installed before WAL negotiation so concurrent first-open
    callers wait for the schema/journal owner instead of failing immediately.
    """

    db.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    db.execute("PRAGMA journal_mode=WAL")
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
