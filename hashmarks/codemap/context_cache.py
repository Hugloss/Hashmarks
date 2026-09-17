from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hashmarks.cas import CAS
from hashmarks.digest import Digest, hash_bytes
from hashmarks.paths import canonical_host_path
from hashmarks.sqlite_boundary import configure_sqlite_connection

if TYPE_CHECKING:
    from pathlib import Path

_CONTEXT_ACTION_DOMAIN = b"hashmarks.context-action.v1\0"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def context_action_hash(action: dict[str, Any]) -> str:
    return hash_bytes(canonical_json_bytes(action), domain=_CONTEXT_ACTION_DOMAIN).hash


@dataclass(frozen=True, slots=True)
class CachedContext:
    action_hash: str
    result_digest: Digest
    payload: dict[str, Any]


class ContextCache:
    """Action-key -> content-addressed context payload mapping.

    The SQLite row is only an index. Payload bytes live in the ordinary local
    CAS and are rehashed on read. Cache state is derived and disposable.
    """

    def __init__(self, state_dir: str | Path) -> None:
        root = canonical_host_path(state_dir)
        root.mkdir(parents=True, exist_ok=True)
        self.cas = CAS(root / "context-cas")
        self.db_path = root / "context-cache.sqlite3"
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            self.db_path, check_same_thread=False, isolation_level=None
        )
        configure_sqlite_connection(self._db)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS context_cache (
                action_hash TEXT PRIMARY KEY,
                blob_hash TEXT NOT NULL,
                blob_size INTEGER NOT NULL
            )
            """
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def put(self, action: dict[str, Any], payload: dict[str, Any]) -> CachedContext:
        action_hash = context_action_hash(action)
        data = canonical_json_bytes(payload)
        digest = self.cas.put_bytes(data)
        with self._lock:
            self._db.execute(
                """
                INSERT INTO context_cache(action_hash, blob_hash, blob_size)
                VALUES (?, ?, ?)
                ON CONFLICT(action_hash) DO UPDATE SET
                    blob_hash=excluded.blob_hash,
                    blob_size=excluded.blob_size
                """,
                (action_hash, digest.hash, digest.size),
            )
        return CachedContext(
            action_hash=action_hash, result_digest=digest, payload=payload
        )

    def get(self, action: dict[str, Any]) -> CachedContext | None:
        action_hash = context_action_hash(action)
        with self._lock:
            row = self._db.execute(
                "SELECT blob_hash, blob_size FROM context_cache WHERE action_hash=?",
                (action_hash,),
            ).fetchone()
        if row is None:
            return None
        digest = Digest(hash=str(row[0]), size=int(row[1]))
        try:
            data = self.cas.get_bytes(digest)
            payload = json.loads(data)
        except (OSError, FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            with self._lock:
                self._db.execute(
                    "DELETE FROM context_cache WHERE action_hash=?", (action_hash,)
                )
            return None
        if not isinstance(payload, dict):
            return None
        return CachedContext(
            action_hash=action_hash, result_digest=digest, payload=payload
        )

    def count(self) -> int:
        with self._lock:
            return int(
                self._db.execute("SELECT COUNT(*) FROM context_cache").fetchone()[0]
            )
