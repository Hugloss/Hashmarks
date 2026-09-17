from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .digest import Digest
from .paths import canonical_host_path, sqlite_identity_exclusions
from .sqlite_boundary import configure_sqlite_connection, sqlite_transaction


class DirectoryDigestStore:
    """Persistent latest-known canonical Merkle node per directory.

    This store is deliberately *not* an authority for filesystem freshness.
    Writes are buffered and flushed as one transaction after a successful
    reconciliation, avoiding an autocommit per directory on large trees.
    """

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
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS directory_digest_latest (
                workspace TEXT NOT NULL,
                path TEXT NOT NULL,
                digest TEXT NOT NULL,
                size INTEGER NOT NULL,
                PRIMARY KEY (workspace, path)
            )
            """
        )
        self._pending: dict[tuple[str, str], Digest] = {}

    def close(self) -> None:
        # Pending entries are intentionally not flushed implicitly: only a
        # successfully reconciled identity operation may make them persistent.
        with self._lock:
            self._pending.clear()
            self._db.close()

    def identity_exclusions(self) -> tuple[Path, ...]:
        """Host paths owned by this store that must never enter source identity."""
        return sqlite_identity_exclusions(self.db_path)

    def get(self, *, workspace: str | Path, relative_path: str) -> Digest | None:
        workspace_key = str(canonical_host_path(workspace))
        key = (workspace_key, relative_path)
        with self._lock:
            pending = self._pending.get(key)
            if pending is not None:
                return pending
            row = self._db.execute(
                """
                SELECT digest, size
                FROM directory_digest_latest
                WHERE workspace = ? AND path = ?
                """,
                key,
            ).fetchone()
        if row is None:
            return None
        return Digest(hash=row[0], size=int(row[1]))

    def put(
        self,
        *,
        workspace: str | Path,
        relative_path: str,
        digest: Digest,
    ) -> None:
        workspace_key = str(canonical_host_path(workspace))
        with self._lock:
            self._pending[(workspace_key, relative_path)] = digest

    def flush(self) -> int:
        with self._lock:
            if not self._pending:
                return 0
            items = list(self._pending.items())
            rows = [
                (workspace, path, digest.hash, digest.size)
                for (workspace, path), digest in items
            ]
            with sqlite_transaction(self._db):
                self._db.executemany(
                    """
                    INSERT INTO directory_digest_latest(workspace, path, digest, size)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(workspace, path) DO UPDATE SET
                        digest = excluded.digest,
                        size = excluded.size
                    """,
                    rows,
                )
            for key, _digest in items:
                self._pending.pop(key, None)
            return len(items)

    def discard_pending(self) -> None:
        with self._lock:
            self._pending.clear()

    def clear_workspace(self, workspace: str | Path) -> None:
        workspace_key = str(canonical_host_path(workspace))
        with self._lock:
            self._db.execute(
                "DELETE FROM directory_digest_latest WHERE workspace = ?",
                (workspace_key,),
            )
            for key in [key for key in self._pending if key[0] == workspace_key]:
                self._pending.pop(key, None)

    def count(self, workspace: str | Path | None = None) -> int:
        with self._lock:
            if workspace is None:
                return int(self._db.execute("SELECT COUNT(*) FROM directory_digest_latest").fetchone()[0])
            workspace_key = str(canonical_host_path(workspace))
            return int(
                self._db.execute(
                    "SELECT COUNT(*) FROM directory_digest_latest WHERE workspace = ?",
                    (workspace_key,),
                ).fetchone()[0]
            )
