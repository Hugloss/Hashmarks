from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Iterable

from .digest import Digest, hash_file
from .file_metadata_codec import MetadataCodecError, decode_overflow_metadata, encode_metadata_fields
from .paths import canonical_host_path, sqlite_identity_exclusions
from .sqlite_boundary import configure_sqlite_connection, sqlite_transaction

_Metadata = tuple[int, int, int, int, int, int]
_CachedRow = tuple[int, int, int, int, int, int, str]



class UnstableFileError(RuntimeError):
    """Raised when a file keeps changing while its bytes are being hashed."""


class FileDigestStore:
    """Persistent file-content digest cache.

    Canonical identity is always the content digest. Filesystem metadata is
    only an accelerator. Warm reads use a process-local row cache plus batched
    SQLite lookups; cold/changed rows are written transactionally in batches.
    """

    _SQLITE_BATCH = 500

    def __init__(self, db_path: str | Path):
        self.db_path = canonical_host_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,
        )
        configure_sqlite_connection(self._db)
        self._ensure_schema()
        self._rows: dict[tuple[str, str], _CachedRow] = {}
        self._stats = {
            "metadata_checks": 0,
            "content_hashes": 0,
            "digest_reuses": 0,
            "sqlite_batches": 0,
            "rows_written": 0,
        }


    @staticmethod
    def _schema_sql() -> str:
        return """
            CREATE TABLE file_digest (
                workspace TEXT NOT NULL,
                path TEXT NOT NULL,
                device INTEGER NOT NULL CHECK(typeof(device) = 'integer' AND device >= 0),
                inode INTEGER NOT NULL CHECK(typeof(inode) = 'integer' AND inode >= 0),
                size INTEGER NOT NULL CHECK(typeof(size) = 'integer' AND size >= 0),
                mtime_ns INTEGER NOT NULL CHECK(typeof(mtime_ns) = 'integer'),
                ctime_ns INTEGER NOT NULL CHECK(typeof(ctime_ns) = 'integer'),
                executable INTEGER NOT NULL CHECK(typeof(executable) = 'integer' AND executable IN (0, 1)),
                overflow_metadata BLOB CHECK(overflow_metadata IS NULL OR typeof(overflow_metadata) = 'blob'),
                digest TEXT NOT NULL CHECK(typeof(digest) = 'text'),
                PRIMARY KEY (workspace, path)
            )
        """

    @staticmethod
    def _expected_schema() -> dict[str, str]:
        return {
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

    def _ensure_schema(self) -> None:
        """Ensure only the current local cache shape; incompatible cache state is disposable."""
        with sqlite_transaction(self._db, begin="BEGIN IMMEDIATE"):
            rows = self._db.execute("PRAGMA table_info(file_digest)").fetchall()
            if rows:
                actual = {str(row[1]): str(row[2]).upper() for row in rows}
                if actual != self._expected_schema():
                    self._db.execute("DROP TABLE file_digest")
                    rows = []
            if not rows:
                self._db.execute(self._schema_sql())

    @staticmethod
    def _encode_metadata(metadata: _Metadata) -> tuple[int, int, int, int, int, int, bytes | None]:
        device, inode, size, mtime_ns, ctime_ns, executable = metadata
        if device < 0 or inode < 0 or size < 0:
            raise MetadataCodecError("device, inode, and size must be non-negative")
        if executable not in (0, 1):
            raise MetadataCodecError("executable metadata must be 0 or 1")
        stored, overflow = encode_metadata_fields((device, inode, size, mtime_ns, ctime_ns))
        return (*stored, executable, overflow)

    @staticmethod
    def _decode_row(row: tuple[object, ...]) -> _CachedRow:
        if len(row) != 8:
            raise MetadataCodecError("invalid persisted file-digest row shape")
        device, inode, size, mtime_ns, ctime_ns, executable, overflow, digest = row
        if overflow is None:
            return (device, inode, size, mtime_ns, ctime_ns, executable, digest)  # type: ignore[return-value]
        metadata = decode_overflow_metadata(overflow)
        device, inode, size, mtime_ns, ctime_ns = metadata
        if device < 0 or inode < 0 or size < 0:
            raise MetadataCodecError("persisted device, inode, and size must be non-negative")
        return (device, inode, size, mtime_ns, ctime_ns, executable, digest)  # type: ignore[return-value]

    def _discard_corrupt_row(self, workspace: str, relpath: str) -> None:
        self._db.execute(
            "DELETE FROM file_digest WHERE workspace = ? AND path = ?",
            (workspace, relpath),
        )
        self._rows.pop((workspace, relpath), None)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def identity_exclusions(self) -> tuple[Path, ...]:
        """Host paths owned by this store that must never enter source identity."""
        return sqlite_identity_exclusions(self.db_path)

    def _metadata(self, path: Path) -> _Metadata:
        with self._lock:
            self._stats["metadata_checks"] += 1
        st = path.stat()
        return (
            int(st.st_dev),
            int(st.st_ino),
            int(st.st_size),
            int(st.st_mtime_ns),
            int(st.st_ctime_ns),
            int(bool(st.st_mode & 0o111)),
        )

    def _hash_stable(
        self,
        path: Path,
        initial_metadata: _Metadata,
        *,
        max_attempts: int = 3,
    ) -> tuple[Digest, _Metadata]:
        before = initial_metadata
        for _ in range(max_attempts):
            with self._lock:
                self._stats["content_hashes"] += 1
            digest = hash_file(path)
            after = self._metadata(path)
            if after == before:
                return digest, after
            before = after
        raise UnstableFileError(f"file changed while hashing: {path}")

    def _row(self, workspace: str, relpath: str) -> _CachedRow | None:
        key = (workspace, relpath)
        with self._lock:
            cached = self._rows.get(key)
            if cached is not None:
                return cached
            row = self._db.execute(
                """
                SELECT device, inode, size, mtime_ns, ctime_ns, executable, overflow_metadata, digest
                FROM file_digest
                WHERE workspace = ? AND path = ?
                """,
                key,
            ).fetchone()
            if row is None:
                return None
            try:
                typed = self._decode_row(tuple(row))
            except MetadataCodecError:
                self._discard_corrupt_row(workspace, relpath)
                return None
            self._rows[key] = typed
            return typed

    def _rows_many(self, workspace: str, relpaths: list[str]) -> dict[str, _CachedRow]:
        result: dict[str, _CachedRow] = {}
        missing: list[str] = []
        with self._lock:
            for rel in relpaths:
                row = self._rows.get((workspace, rel))
                if row is None:
                    missing.append(rel)
                else:
                    result[rel] = row

            for start in range(0, len(missing), self._SQLITE_BATCH):
                chunk = missing[start : start + self._SQLITE_BATCH]
                if not chunk:
                    continue
                placeholders = ",".join("?" for _ in chunk)
                self._stats["sqlite_batches"] += 1
                rows = self._db.execute(
                    f"""
                    SELECT path, device, inode, size, mtime_ns, ctime_ns, executable, overflow_metadata, digest
                    FROM file_digest
                    WHERE workspace = ? AND path IN ({placeholders})
                    """,
                    (workspace, *chunk),
                ).fetchall()
                for row in rows:
                    rel = str(row[0])
                    try:
                        typed = self._decode_row(tuple(row[1:]))
                    except MetadataCodecError:
                        self._discard_corrupt_row(workspace, rel)
                        continue
                    result[rel] = typed
                    self._rows[(workspace, rel)] = typed
        return result

    def _store_many(
        self,
        workspace: str,
        records: list[tuple[str, _Metadata, Digest]],
    ) -> None:
        if not records:
            return
        sql = """
            INSERT INTO file_digest (
                workspace, path, device, inode, size,
                mtime_ns, ctime_ns, executable, overflow_metadata, digest
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace, path) DO UPDATE SET
                device = excluded.device,
                inode = excluded.inode,
                size = excluded.size,
                mtime_ns = excluded.mtime_ns,
                ctime_ns = excluded.ctime_ns,
                executable = excluded.executable,
                overflow_metadata = excluded.overflow_metadata,
                digest = excluded.digest
        """
        rows = [
            (workspace, rel, *self._encode_metadata(metadata), digest.hash)
            for rel, metadata, digest in records
        ]
        with self._lock:
            self._stats["rows_written"] += len(records)
            with sqlite_transaction(self._db):
                self._db.executemany(sql, rows)
            for rel, metadata, digest in records:
                self._rows[(workspace, rel)] = (*metadata, digest.hash)

    def _store(self, workspace: str, relative_path: str, metadata: _Metadata, digest: Digest) -> None:
        self._store_many(workspace, [(relative_path, metadata, digest)])

    def digest(
        self,
        path: str | Path,
        *,
        workspace: str | Path,
        relative_path: str,
        force: bool = False,
    ) -> Digest:
        path = Path(path)
        workspace_key = str(canonical_host_path(workspace))
        metadata = self._metadata(path)

        if not force:
            row = self._row(workspace_key, relative_path)
            if row is not None and tuple(row[:6]) == metadata:
                with self._lock:
                    self._stats["digest_reuses"] += 1
                return Digest(hash=row[6], size=metadata[2])

        digest, metadata = self._hash_stable(path, metadata)
        self._store(workspace_key, relative_path, metadata, digest)
        return digest

    def digest_many_info(
        self,
        files: Iterable[tuple[str | Path, str]],
        *,
        workspace: str | Path,
        force: bool = False,
    ) -> dict[str, tuple[Digest, bool]]:
        """Digest files with one stat each and batched persistent-cache lookup."""
        workspace_key = str(canonical_host_path(workspace))
        items = [(Path(path), rel) for path, rel in files]
        rows = {} if force else self._rows_many(workspace_key, [rel for _, rel in items])
        result: dict[str, tuple[Digest, bool]] = {}
        changed: list[tuple[str, _Metadata, Digest]] = []

        for path, rel in items:
            metadata = self._metadata(path)
            row = rows.get(rel)
            if row is not None and tuple(row[:6]) == metadata:
                with self._lock:
                    self._stats["digest_reuses"] += 1
                digest = Digest(hash=row[6], size=metadata[2])
            else:
                digest, metadata = self._hash_stable(path, metadata)
                changed.append((rel, metadata, digest))
            result[rel] = (digest, bool(metadata[5]))

        self._store_many(workspace_key, changed)
        return result

    def digest_many(
        self,
        files: Iterable[tuple[str | Path, str]],
        *,
        workspace: str | Path,
        force: bool = False,
    ) -> dict[str, Digest]:
        return {
            rel: digest
            for rel, (digest, _executable) in self.digest_many_info(
                files,
                workspace=workspace,
                force=force,
            ).items()
        }


    def stats(self) -> dict[str, int]:
        with self._lock:
            return dict(self._stats)

    def reset_stats(self) -> None:
        with self._lock:
            for key in self._stats:
                self._stats[key] = 0

    def forget(self, *, workspace: str | Path, relative_path: str) -> None:
        workspace_key = str(canonical_host_path(workspace))
        with self._lock:
            self._db.execute(
                "DELETE FROM file_digest WHERE workspace = ? AND path = ?",
                (workspace_key, relative_path),
            )
            self._rows.pop((workspace_key, relative_path), None)

    def clear_workspace(self, workspace: str | Path) -> None:
        workspace_key = str(canonical_host_path(workspace))
        with self._lock:
            self._db.execute(
                "DELETE FROM file_digest WHERE workspace = ?",
                (workspace_key,),
            )
            for key in [key for key in self._rows if key[0] == workspace_key]:
                self._rows.pop(key, None)

    def count(self, workspace: str | Path | None = None) -> int:
        with self._lock:
            if workspace is None:
                return int(self._db.execute("SELECT COUNT(*) FROM file_digest").fetchone()[0])
            workspace_key = str(canonical_host_path(workspace))
            return int(
                self._db.execute(
                    "SELECT COUNT(*) FROM file_digest WHERE workspace = ?",
                    (workspace_key,),
                ).fetchone()[0]
            )

    def prune_missing_files(self, workspace: str | Path) -> int:
        workspace_path = canonical_host_path(workspace)
        workspace_key = str(workspace_path)
        with self._lock:
            rows = self._db.execute(
                "SELECT path FROM file_digest WHERE workspace = ?",
                (workspace_key,),
            ).fetchall()
            missing = [rel for (rel,) in rows if not os.path.lexists(workspace_path / rel)]
            self._db.executemany(
                "DELETE FROM file_digest WHERE workspace = ? AND path = ?",
                ((workspace_key, rel) for rel in missing),
            )
            for rel in missing:
                self._rows.pop((workspace_key, rel), None)
        return len(missing)
