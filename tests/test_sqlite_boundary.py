from __future__ import annotations

import sqlite3

import pytest

from hashmarks.sqlite_boundary import configure_sqlite_connection, sqlite_transaction


def test_configure_sqlite_connection_retries_only_wal_first_open_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FirstOpenRaceConnection:
        def __init__(self) -> None:
            self.wal_attempts = 0
            self.events: list[str] = []

        def execute(self, statement: str):
            self.events.append(statement)
            if statement == "PRAGMA journal_mode=WAL":
                self.wal_attempts += 1
                if self.wal_attempts == 1:
                    raise sqlite3.OperationalError("database is locked")
            return self

    monkeypatch.setattr("hashmarks.sqlite_boundary.time.sleep", lambda _seconds: None)
    db = FirstOpenRaceConnection()

    configure_sqlite_connection(db, busy_timeout_ms=100)  # type: ignore[arg-type]

    assert db.events == [
        "PRAGMA busy_timeout=100",
        "PRAGMA journal_mode=WAL",
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
    ]


def test_configure_sqlite_connection_does_not_hide_unrelated_sqlite_error() -> None:
    class BrokenConnection:
        def execute(self, statement: str):
            if statement == "PRAGMA journal_mode=WAL":
                raise sqlite3.OperationalError("disk I/O error")
            return self

    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        configure_sqlite_connection(BrokenConnection())  # type: ignore[arg-type]


def test_sqlite_transaction_commits_successful_work() -> None:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE item(value INTEGER NOT NULL)")

    with sqlite_transaction(db):
        db.execute("INSERT INTO item(value) VALUES (1)")

    assert db.in_transaction is False
    assert db.execute("SELECT value FROM item").fetchall() == [(1,)]


def test_sqlite_transaction_rolls_back_any_failed_operation() -> None:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE item(value INTEGER NOT NULL)")

    with pytest.raises(ValueError, match="abort"):
        with sqlite_transaction(db, begin="BEGIN IMMEDIATE"):
            db.execute("INSERT INTO item(value) VALUES (1)")
            raise ValueError("abort")

    assert db.in_transaction is False
    assert db.execute("SELECT value FROM item").fetchall() == []


def test_sqlite_transaction_rolls_back_failed_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingCommitConnection:
        def __init__(self) -> None:
            self.in_transaction = False
            self.events: list[str] = []

        def execute(self, statement: str):
            self.events.append(statement)
            if statement.startswith("BEGIN"):
                self.in_transaction = True
            elif statement == "COMMIT":
                raise sqlite3.OperationalError("commit failed")
            elif statement == "ROLLBACK":
                self.in_transaction = False
            return self

    db = FailingCommitConnection()
    with pytest.raises(sqlite3.OperationalError, match="commit failed"):
        with sqlite_transaction(db):  # type: ignore[arg-type]
            pass

    assert db.events == ["BEGIN", "COMMIT", "ROLLBACK"]
    assert db.in_transaction is False
