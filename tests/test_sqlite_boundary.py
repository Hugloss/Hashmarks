from __future__ import annotations

import sqlite3

import pytest

from hashmarks.sqlite_boundary import sqlite_transaction


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
