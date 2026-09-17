from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from hashmarks.digest import Digest
from hashmarks.file_store import FileDigestStore


BIG = 2**63


def _oversized_metadata(*, field: int) -> tuple[int, int, int, int, int, int]:
    values = [1, 2, 5, 4, 5, 0]
    values[field] = BIG
    return tuple(values)  # type: ignore[return-value]


@pytest.mark.parametrize("field", range(5))
def test_single_digest_accepts_filesystem_metadata_beyond_sqlite_signed_64(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: int
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("same\n")
    store = FileDigestStore(tmp_path / "identity.sqlite3")
    metadata = _oversized_metadata(field=field)
    monkeypatch.setattr(store, "_metadata", lambda _path: metadata)
    monkeypatch.setattr(
        "hashmarks.file_store.hash_file",
        lambda _path: Digest(hash="a" * 64, size=metadata[2]),
    )

    first = store.digest(target, workspace=workspace, relative_path="a.txt")
    store.close()

    reopened = FileDigestStore(tmp_path / "identity.sqlite3")
    monkeypatch.setattr(reopened, "_metadata", lambda _path: metadata)
    reopened.reset_stats()
    second = reopened.digest(target, workspace=workspace, relative_path="a.txt")

    assert second == first
    assert reopened.stats()["content_hashes"] == 0
    assert reopened.stats()["digest_reuses"] == 1
    reopened.close()


def test_batch_digest_accepts_oversized_metadata_and_reuses_after_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    files = []
    for index in range(3):
        target = workspace / f"{index}.txt"
        target.write_text(f"{index}\n")
        files.append((target, target.name))

    metadata_by_name = {
        "0.txt": (BIG, 2, 2, 4, 5, 0),
        "1.txt": (1, BIG, 2, 4, 5, 0),
        "2.txt": (1, 2, 2, BIG, BIG + 1, 0),
    }
    store = FileDigestStore(tmp_path / "identity.sqlite3")
    monkeypatch.setattr(store, "_metadata", lambda path: metadata_by_name[path.name])
    monkeypatch.setattr(
        "hashmarks.file_store.hash_file",
        lambda path: Digest(hash=path.name.encode().hex().ljust(64, "0")[:64], size=metadata_by_name[path.name][2]),
    )
    first = store.digest_many_info(files, workspace=workspace)
    store.close()

    reopened = FileDigestStore(tmp_path / "identity.sqlite3")
    monkeypatch.setattr(reopened, "_metadata", lambda path: metadata_by_name[path.name])
    reopened.reset_stats()
    second = reopened.digest_many_info(files, workspace=workspace)

    assert second == first
    assert reopened.stats()["content_hashes"] == 0
    assert reopened.stats()["digest_reuses"] == 3
    reopened.close()


def test_fresh_schema_keeps_existing_integer_affinity_without_versioning(tmp_path: Path) -> None:
    db = tmp_path / "identity.sqlite3"
    store = FileDigestStore(db)
    store.close()

    connection = sqlite3.connect(db)
    columns = {
        row[1]: row[2]
        for row in connection.execute("PRAGMA table_info(file_digest)").fetchall()
    }
    assert columns == {
        "workspace": "TEXT",
        "path": "TEXT",
        "device": "INTEGER",
        "inode": "INTEGER",
        "size": "INTEGER",
        "mtime_ns": "INTEGER",
        "ctime_ns": "INTEGER",
        "executable": "INTEGER",
        "overflow_metadata": "BLOB",
        "digest": "TEXT",
    }
    connection.close()


def test_incompatible_file_digest_schema_is_rebuilt_as_disposable_cache(tmp_path: Path) -> None:
    db = tmp_path / "identity.sqlite3"
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE file_digest (workspace TEXT NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL)"
    )
    connection.execute("INSERT INTO file_digest VALUES ('/repo', 'a.txt', 'stale')")
    connection.commit()
    connection.close()

    store = FileDigestStore(db)
    assert store.count() == 0
    store.close()

    connection = sqlite3.connect(db)
    columns = {
        row[1]: row[2]
        for row in connection.execute("PRAGMA table_info(file_digest)").fetchall()
    }
    assert columns == FileDigestStore._expected_schema()
    connection.close()


@pytest.mark.parametrize("bad", ["", "+1", "01", "-0", "1.0", "not-an-int", "9" * 129])
def test_malformed_persisted_metadata_is_never_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("same\n")
    db = tmp_path / "identity.sqlite3"
    store = FileDigestStore(db)
    metadata = (1, BIG, 5, 4, 5, 0)
    monkeypatch.setattr(store, "_metadata", lambda _path: metadata)
    expected = store.digest(target, workspace=workspace, relative_path="a.txt")
    store.close()

    connection = sqlite3.connect(db)
    connection.execute(
        "UPDATE file_digest SET overflow_metadata = ? WHERE path = 'a.txt'",
        (bad.encode("ascii"),),
    )
    connection.commit()
    connection.close()

    reopened = FileDigestStore(db)
    monkeypatch.setattr(reopened, "_metadata", lambda _path: metadata)
    reopened.reset_stats()
    actual = reopened.digest(target, workspace=workspace, relative_path="a.txt")
    assert actual == expected
    assert reopened.stats()["content_hashes"] == 1
    assert reopened.stats()["digest_reuses"] == 0
    reopened.close()


def test_corrupt_persisted_row_is_evicted_in_batch_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    targets = []
    for index in range(2):
        target = workspace / f"{index}.txt"
        target.write_text(f"{index}\n")
        targets.append((target, target.name))

    db = tmp_path / "identity.sqlite3"
    store = FileDigestStore(db)
    store.digest_many_info(targets, workspace=workspace)
    store.close()

    connection = sqlite3.connect(db)
    connection.execute(
        "UPDATE file_digest SET overflow_metadata = ? WHERE path = '0.txt'",
        (b"not-an-int",),
    )
    connection.commit()
    connection.close()

    reopened = FileDigestStore(db)
    reopened.reset_stats()
    reopened.digest_many_info(targets, workspace=workspace)
    stats = reopened.stats()
    assert stats["content_hashes"] == 1
    assert stats["digest_reuses"] == 1
    reopened.close()



def test_signed64_metadata_stays_on_integer_fast_path_without_overflow_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("same\n")
    db = tmp_path / "identity.sqlite3"
    metadata = (1, 2, 5, -4, 5, 0)
    store = FileDigestStore(db)
    monkeypatch.setattr(store, "_metadata", lambda _path: metadata)
    store.digest(target, workspace=workspace, relative_path="a.txt")
    row = store._db.execute(
        "SELECT typeof(device), typeof(inode), typeof(size), typeof(mtime_ns), "
        "typeof(ctime_ns), overflow_metadata FROM file_digest WHERE path = 'a.txt'"
    ).fetchone()
    assert row == ("integer", "integer", "integer", "integer", "integer", None)
    store.close()

def test_overflow_metadata_uses_one_canonical_blob_and_bind_safe_integer_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("same\n")
    db = tmp_path / "identity.sqlite3"
    metadata = (1, BIG, 5, -(BIG + 1), 5, 0)
    store = FileDigestStore(db)
    monkeypatch.setattr(store, "_metadata", lambda _path: metadata)
    store.digest(target, workspace=workspace, relative_path="a.txt")
    store.close()

    connection = sqlite3.connect(db)
    row = connection.execute(
        """
        SELECT typeof(device), typeof(inode), typeof(size),
               typeof(mtime_ns), typeof(ctime_ns), inode, mtime_ns,
               typeof(overflow_metadata), overflow_metadata
        FROM file_digest WHERE path = 'a.txt'
        """
    ).fetchone()
    assert row == (
        "integer",
        "integer",
        "integer",
        "integer",
        "integer",
        0,
        0,
        "blob",
        f"1,{BIG},5,{-BIG - 1},5".encode("ascii"),
    )
    connection.close()


def test_distinct_oversized_metadata_never_collapses_through_sqlite_numeric_affinity(
    tmp_path: Path,
) -> None:
    from hashmarks.digest import Digest

    store = FileDigestStore(tmp_path / "identity.sqlite3")
    records = [
        (
            f"f{index}.txt",
            (1, BIG + index, 1, 1, 1, 0),
            Digest(hash=f"{index:064x}"[-64:], size=1),
        )
        for index in range(1000)
    ]
    store._store_many("/repo", records)
    rows = store._db.execute(
        "SELECT typeof(inode), inode, typeof(overflow_metadata), overflow_metadata "
        "FROM file_digest ORDER BY path"
    ).fetchall()
    assert {inode_kind for inode_kind, _inode, _overflow_kind, _overflow in rows} == {"integer"}
    assert {inode for _inode_kind, inode, _overflow_kind, _overflow in rows} == {0}
    assert {overflow_kind for _inode_kind, _inode, overflow_kind, _overflow in rows} == {"blob"}
    assert len({overflow for _inode_kind, _inode, _overflow_kind, overflow in rows}) == 1000
    store.close()
