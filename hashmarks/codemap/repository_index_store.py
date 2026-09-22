from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from hashmarks.paths import canonical_host_path
from hashmarks.sqlite_boundary import configure_sqlite_connection, sqlite_transaction

from .derived import derive_file_nodes
from .model import (
    EdgeRecord,
    EvidenceVisibility,
    LexicalRecord,
    ParsedArtifact,
    SymbolRecord,
)
from .store_queries import WorkspaceMapQueryMixin

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


class WorkspaceStateMismatchError(ValueError):
    """Raised when durable CodeMap state belongs to a different workspace."""


def _shared_root() -> Path:
    if os.name == "posix":
        base = os.environ.get("XDG_CACHE_HOME")
        if base:
            return canonical_host_path(base) / "hashmarks" / "codemap"
        return canonical_host_path(Path.home() / ".cache" / "hashmarks" / "codemap")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return canonical_host_path(local) / "Hashmarks" / "codemap"
    return canonical_host_path(Path.home() / ".cache" / "hashmarks" / "codemap")


def repository_cache_key(workspace: Path) -> str:
    anchor = workspace
    try:
        completed = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--git-common-dir"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    if completed is not None and completed.returncode == 0 and completed.stdout.strip():
        value = Path(completed.stdout.strip())
        if not value.is_absolute():
            value = workspace / value
        anchor = canonical_host_path(value)
    return hashlib.sha256(os.fsencode(str(anchor))).hexdigest()[:24]


def default_artifact_db(workspace: Path) -> Path:
    return _shared_root() / repository_cache_key(workspace) / "artifacts.sqlite3"


def git_base_identity(workspace: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "HEAD^{tree}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip() if completed.returncode == 0 else ""
    return value or None


def default_base_snapshot(workspace: Path, base_identity: str) -> Path:
    return (
        _shared_root()
        / repository_cache_key(workspace)
        / "bases"
        / f"{base_identity}.json"
    )


def _parse_git_overlay_paths(output: bytes) -> set[str] | None:
    out: set[str] = set()
    records = output.split(b"\0")
    i = 0
    while i < len(records):
        record = records[i]
        i += 1
        if not record:
            continue
        if len(record) < 4:
            return None
        status = record[:2]
        raw = record[3:]
        # Rename/copy porcelain -z uses an additional NUL-delimited origin path.
        if b"R" in status or b"C" in status:
            if i >= len(records):
                return None
            origin = records[i]
            i += 1
            if origin:
                out.add(os.fsdecode(origin).replace("\\", "/"))
        out.add(os.fsdecode(raw).replace("\\", "/"))
    return {
        path
        for path in out
        if path not in {".hashmarks", ".fastidentity"}
        and not path.startswith((".hashmarks/", ".fastidentity/"))
    }


def git_overlay_paths(workspace: Path) -> set[str] | None:
    """Return paths that differ from HEAD, including staged/untracked/deleted paths.

    None means Git could not prove the overlay, so callers must fall back to
    ordinary filesystem hashing rather than trust a base snapshot.
    """
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(workspace),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return _parse_git_overlay_paths(completed.stdout)


def _symbol_from(value: dict) -> SymbolRecord:
    lines = value.get("lines") or [1, 1]
    return SymbolRecord(
        name=str(value["name"]),
        qualname=str(value["qualname"]),
        kind=str(value["kind"]),
        signature=str(value["signature"]),
        start_line=int(lines[0]),
        end_line=int(lines[1]),
        signature_tokens=int(value.get("signature_tokens", 0)),
        body_tokens=int(value.get("body_tokens", 0)),
        parent=None if value.get("parent") is None else str(value["parent"]),
    )


def _edge_from(value: dict) -> EdgeRecord:
    return EdgeRecord(
        source=None if value.get("source") is None else str(value["source"]),
        kind=str(value["kind"]),
        target=str(value["target"]),
        line=None if value.get("line") is None else int(value["line"]),
        confidence=str(value.get("confidence", "static")),
    )


class ArtifactStore:
    """Content-addressed parsed artifacts shared by worktrees of one repository."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = canonical_host_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        configure_sqlite_connection(self._db)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS artifact (artifact_key TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL)"
        )
        self._db.commit()
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def get(self, key: str) -> ParsedArtifact | None:
        with self._lock:
            row = self._db.execute(
                "SELECT payload FROM artifact WHERE artifact_key=?", (key,)
            ).fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
        return ParsedArtifact(
            artifact_key=str(value["artifact_key"]),
            file_digest=str(value["file_digest"]),
            language=str(value["language"]),
            parser=str(value["parser"]),
            full_tokens=int(value["full_tokens"]),
            outline=str(value.get("outline", "")),
            symbols=tuple(_symbol_from(item) for item in value.get("symbols", [])),
            edges=tuple(_edge_from(item) for item in value.get("edges", [])),
            lexical=tuple(
                LexicalRecord(token=str(item["token"]), line=int(item["line"]))
                for item in value.get("lexical", [])
            ),
            parse_error=None
            if value.get("parse_error") is None
            else str(value["parse_error"]),
        )

    def put(self, artifact: ParsedArtifact) -> None:
        payload = json.dumps(artifact.as_dict(), separators=(",", ":"), sort_keys=True)
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO artifact (artifact_key,payload,created) VALUES (?,?,?)",
                (artifact.artifact_key, payload, time.time()),
            )
            self._db.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM artifact WHERE artifact_key=?", (key,))
            self._db.commit()

    def clear(self) -> int:
        with self._lock:
            count = int(self._db.execute("SELECT COUNT(*) FROM artifact").fetchone()[0])
            self._db.execute("DELETE FROM artifact")
            self._db.commit()
        return count

    def count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM artifact").fetchone()[0])


class WorkspaceMapStore(WorkspaceMapQueryMixin):
    def __init__(self, db_path: Path) -> None:
        self.db_path = canonical_host_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        configure_sqlite_connection(self._db)
        # Schema inspection, disposal, and creation are one cross-connection
        # initialization authority. Without the writer lock, two first-open
        # callers can observe each other's partial CREATE script and one can
        # discard tables while the other is still creating indexes.
        self._db.execute("BEGIN IMMEDIATE")
        if not self._schema_is_current():
            self._discard_incompatible_schema_locked()
        # executescript() commits an active transaction before running.
        # Put BEGIN IMMEDIATE inside the script so schema publication stays
        # serialized until its final COMMIT.
        self._db.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS file_map (
              path TEXT PRIMARY KEY,
              file_digest TEXT NOT NULL,
              artifact_key TEXT NOT NULL,
              language TEXT NOT NULL,
              module_name TEXT,
              evidence_visibility TEXT NOT NULL,
              full_tokens INTEGER NOT NULL,
              outline TEXT NOT NULL,
              parse_error TEXT,
              index_surface TEXT NOT NULL DEFAULT 'other',
              lexical_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS symbol (
              path TEXT NOT NULL,
              name TEXT NOT NULL,
              qualname TEXT NOT NULL,
              kind TEXT NOT NULL,
              signature TEXT NOT NULL,
              start_line INTEGER NOT NULL,
              end_line INTEGER NOT NULL,
              signature_tokens INTEGER NOT NULL,
              body_tokens INTEGER NOT NULL,
              parent TEXT,
              PRIMARY KEY(path, qualname)
            );
            CREATE INDEX IF NOT EXISTS symbol_name_idx ON symbol(name);
            CREATE INDEX IF NOT EXISTS symbol_qualname_idx ON symbol(qualname);
            CREATE INDEX IF NOT EXISTS symbol_name_lower_idx ON symbol(lower(name));
            CREATE INDEX IF NOT EXISTS symbol_qualname_lower_idx ON symbol(lower(qualname));
            CREATE TABLE IF NOT EXISTS edge (
              path TEXT NOT NULL,
              source TEXT,
              kind TEXT NOT NULL,
              target TEXT NOT NULL,
              target_short TEXT,
              line INTEGER,
              confidence TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS edge_target_idx ON edge(target);
            CREATE INDEX IF NOT EXISTS edge_source_idx ON edge(source);
            CREATE INDEX IF NOT EXISTS edge_path_line_idx ON edge(path,line);
            CREATE INDEX IF NOT EXISTS edge_path_source_line_idx ON edge(path,source,line);
            CREATE TABLE IF NOT EXISTS lexical (
              path TEXT NOT NULL,
              token TEXT NOT NULL,
              line INTEGER NOT NULL,
              PRIMARY KEY(token,path,line)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS project_node (
              project_id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              root TEXT NOT NULL,
              manifest TEXT NOT NULL,
              producer TEXT NOT NULL,
              metadata TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS project_node_root_idx ON project_node(root);
            CREATE TABLE IF NOT EXISTS project_edge (
              source TEXT NOT NULL,
              target TEXT NOT NULL,
              kind TEXT NOT NULL,
              confidence TEXT NOT NULL,
              producer TEXT NOT NULL,
              PRIMARY KEY(source,target,kind,producer)
            );
            CREATE INDEX IF NOT EXISTS project_edge_target_idx ON project_edge(target);
            CREATE TABLE IF NOT EXISTS native_definition (
              path TEXT NOT NULL,
              symbol TEXT NOT NULL,
              display_name TEXT NOT NULL,
              line INTEGER NOT NULL,
              end_line INTEGER NOT NULL,
              producer TEXT NOT NULL,
              PRIMARY KEY(path,symbol,line,producer)
            );
            CREATE INDEX IF NOT EXISTS native_definition_name_idx ON native_definition(display_name);
            CREATE TABLE IF NOT EXISTS native_edge (
              path TEXT NOT NULL,
              source TEXT,
              target_symbol TEXT NOT NULL,
              target_name TEXT NOT NULL,
              line INTEGER NOT NULL,
              producer TEXT NOT NULL,
              PRIMARY KEY(path,target_symbol,line,producer)
            );
            CREATE INDEX IF NOT EXISTS native_edge_target_idx ON native_edge(target_name);
            CREATE TABLE IF NOT EXISTS native_file_edge (
              source TEXT NOT NULL,
              target TEXT NOT NULL,
              kind TEXT NOT NULL,
              confidence TEXT NOT NULL,
              producer TEXT NOT NULL,
              specifier TEXT,
              PRIMARY KEY(source,target,kind,producer)
            );
            CREATE INDEX IF NOT EXISTS native_file_edge_target_idx ON native_file_edge(target);
            CREATE TABLE IF NOT EXISTS derived_node (
              node_id TEXT PRIMARY KEY,
              path TEXT NOT NULL,
              kind TEXT NOT NULL,
              identity TEXT NOT NULL,
              dependencies TEXT NOT NULL,
              input_identities TEXT NOT NULL,
              producer TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS derived_node_path_idx ON derived_node(path);
            CREATE INDEX IF NOT EXISTS derived_node_kind_idx ON derived_node(kind);
            CREATE INDEX IF NOT EXISTS derived_node_identity_idx ON derived_node(identity);
            COMMIT;
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS edge_target_short_idx ON edge(target_short)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS edge_target_short_path_line_idx "
            "ON edge(target_short,path,line)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS lexical_path_idx ON lexical(path)")
        self._lock = threading.RLock()
        # Process-local diagnostics for repository-read amplification. These
        # counters are observational only and are never persisted as authority.
        self._read_counters: dict[str, int] = {}
        self._bulk_file_write_batch_size = 0
        self._bulk_file_write_count = 0
        self._bulk_file_write_committed = 0
        self._bulk_file_write_on_commit: Callable[[int], None] | None = None

    def _count_read(self, name: str) -> None:
        self._read_counters[name] = self._read_counters.get(name, 0) + 1

    def reset_read_counters(self) -> None:
        self._read_counters.clear()

    def read_counters(self) -> dict[str, int]:
        return dict(self._read_counters)

    def _begin_bulk_file_writes(
        self, batch_size: int, on_commit: Callable[[int], None] | None
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        with self._lock:
            if self._bulk_file_write_batch_size:
                raise RuntimeError("nested bulk file writes are not supported")
            if self._db.in_transaction:
                raise RuntimeError("cannot start bulk file writes inside a transaction")
            self._bulk_file_write_batch_size = batch_size
            self._bulk_file_write_count = 0
            self._bulk_file_write_committed = 0
            self._bulk_file_write_on_commit = on_commit

    def _clear_bulk_file_write_state(self) -> None:
        self._bulk_file_write_batch_size = 0
        self._bulk_file_write_count = 0
        self._bulk_file_write_on_commit = None

    def _rollback_bulk_file_writes(self) -> None:
        with self._lock:
            try:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
            finally:
                self._clear_bulk_file_write_state()

    def _commit_bulk_file_writes(self) -> None:
        with self._lock:
            try:
                if self._db.in_transaction:
                    pending = self._bulk_file_write_count
                    self._db.execute("COMMIT")
                    self._bulk_file_write_committed += pending
                    callback = self._bulk_file_write_on_commit
                    if callback is not None and pending:
                        callback(self._bulk_file_write_committed)
            finally:
                self._clear_bulk_file_write_state()

    @contextmanager
    def bulk_file_writes(
        self, *, batch_size: int = 32, on_commit: Callable[[int], None] | None = None
    ):
        """Bound cold-sync write amplification without changing file semantics.

        Each completed chunk is committed independently, so an interruption can
        lose at most the current bounded chunk rather than the entire sync.  The
        ordinary ``set_file`` contract remains one-file/one-transaction outside
        this explicit context.
        """
        self._begin_bulk_file_writes(batch_size, on_commit)
        try:
            yield
        except Exception:
            self._rollback_bulk_file_writes()
            raise
        else:
            self._commit_bulk_file_writes()

    _CURRENT_TABLES = frozenset(
        {
            "meta",
            "file_map",
            "symbol",
            "edge",
            "lexical",
            "project_node",
            "project_edge",
            "native_definition",
            "native_edge",
            "native_file_edge",
            "derived_node",
        }
    )

    @staticmethod
    def _column_names(db: sqlite3.Connection, table: str) -> tuple[str, ...]:
        return tuple(
            str(row[1]) for row in db.execute(f"PRAGMA table_info({table})").fetchall()
        )

    def _schema_is_current(self) -> bool:
        """Accept only the current generated CodeMap schema; old cache shapes are disposable."""
        tables = {
            str(row[0])
            for row in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        if not tables:
            return True
        if tables != self._CURRENT_TABLES:
            return False
        if self._column_names(self._db, "edge") != (
            "path",
            "source",
            "kind",
            "target",
            "target_short",
            "line",
            "confidence",
        ):
            return False
        if self._column_names(self._db, "file_map") != (
            "path",
            "file_digest",
            "artifact_key",
            "language",
            "module_name",
            "evidence_visibility",
            "full_tokens",
            "outline",
            "parse_error",
            "index_surface",
            "lexical_count",
        ):
            return False
        row = self._db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='lexical'"
        ).fetchone()
        shape = "" if row is None else "".join(str(row[0] or "").lower().split())
        return "withoutrowid" in shape and "primarykey(token,path,line)" in shape

    def _discard_incompatible_schema_locked(self) -> None:
        """Discard generated state while the caller owns SQLite writer authority."""
        if self._schema_is_current():
            return
        rows = self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for row in rows:
            name = str(row[0]).replace('"', '""')
            self._db.execute(f'DROP TABLE "{name}"')

    def _discard_incompatible_schema(self) -> None:
        """Discard generated CodeMap state instead of migrating historical local schemas."""
        with sqlite_transaction(self._db, begin="BEGIN IMMEDIATE"):
            self._discard_incompatible_schema_locked()

    def bind_workspace(
        self,
        workspace: str | Path,
        *,
        allow_unbound_existing: bool = False,
    ) -> None:
        """Bind this durable CodeMap state to exactly one canonical workspace.

        A fresh state directory may be claimed once. Existing unbound state is
        only adoptable when the caller can prove ownership structurally (for
        example because the state directory lives inside that workspace).
        """

        canonical = str(canonical_host_path(workspace))
        key = "state.workspace"
        with self._lock:
            if self._db.in_transaction:
                raise RuntimeError("cannot bind workspace inside an active transaction")
            with sqlite_transaction(self._db, begin="BEGIN IMMEDIATE"):
                row = self._db.execute(
                    "SELECT value FROM meta WHERE key=?", (key,)
                ).fetchone()
                if row is not None:
                    bound = str(row[0])
                    if bound != canonical:
                        raise WorkspaceStateMismatchError(
                            "CodeMap state directory is already bound to a different workspace: "
                            f"{bound!r} != {canonical!r}"
                        )
                    return

                existing = (
                    self._db.execute("SELECT 1 FROM file_map LIMIT 1").fetchone()
                    is not None
                    or self._db.execute("SELECT 1 FROM meta LIMIT 1").fetchone()
                    is not None
                )
                if existing and not allow_unbound_existing:
                    raise WorkspaceStateMismatchError(
                        "existing external CodeMap state is not workspace-bound; "
                        "remove or clean that state directory before reusing it"
                    )
                self._db.execute(
                    "INSERT INTO meta(key,value) VALUES (?,?)",
                    (key, canonical),
                )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def meta(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT value FROM meta WHERE key=?", (key,)
            ).fetchone()
        return default if row is None else str(row[0])

    def meta_items(self, *, prefix: str = "") -> list[tuple[str, str]]:
        with self._lock:
            if prefix:
                rows = self._db.execute(
                    "SELECT key,value FROM meta WHERE key LIKE ? ORDER BY key",
                    (prefix + "%",),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT key,value FROM meta ORDER BY key"
                ).fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._db.commit()

    def set_meta_many(self, values: dict[str, str]) -> None:
        if not values:
            return
        with self._lock:
            if self._db.in_transaction:
                raise RuntimeError(
                    "cannot publish sync metadata inside an active transaction"
                )
            self._db.executemany(
                "INSERT INTO meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                list(values.items()),
            )
            self._db.commit()

    def generation(self) -> int:
        return int(self.meta("generation", "0") or 0)

    def bump_generation(self) -> int:
        """Atomically advance the durable CodeMap generation.

        Generation is shared durable state.  Keep the read-modify-write inside
        one store lock/transaction so concurrent sync callers cannot both sample
        the same revision and publish the same successor.
        """
        with self._lock:
            if self._db.in_transaction:
                raise RuntimeError(
                    "cannot bump generation inside an active transaction"
                )
            # The Python lock owns one connection; BEGIN IMMEDIATE additionally
            # serializes other WorkspaceMapStore instances/processes using the
            # same durable database so the read-modify-write cannot lose a bump.
            with sqlite_transaction(self._db, begin="BEGIN IMMEDIATE"):
                row = self._db.execute(
                    "SELECT value FROM meta WHERE key='generation'"
                ).fetchone()
                value = int(row[0]) + 1 if row is not None else 1
                self._db.execute(
                    "INSERT INTO meta(key,value) VALUES ('generation',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(value),),
                )
            return value

    def file_row(self, path: str):
        self._count_read("file_row")
        with self._lock:
            return self._db.execute(
                "SELECT * FROM file_map WHERE path=?", (path,)
            ).fetchone()

    def has_files(self) -> bool:
        """Cheap readiness probe; avoids full-table COUNTs on query hot paths."""
        with self._lock:
            return (
                self._db.execute("SELECT 1 FROM file_map LIMIT 1").fetchone()
                is not None
            )

    def file_rows(self, paths: Iterable[str]) -> dict[str, dict]:
        unique = sorted({str(path) for path in paths if path})
        if not unique:
            return {}
        self._count_read("file_rows")
        result: dict[str, dict] = {}
        with self._lock:
            for start in range(0, len(unique), 500):
                chunk = unique[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = self._db.execute(
                    f"SELECT * FROM file_map WHERE path IN ({placeholders})",
                    tuple(chunk),
                ).fetchall()
                result.update({str(row["path"]): dict(row) for row in rows})
        return result

    def paths(self) -> set[str]:
        with self._lock:
            return {
                str(row[0]) for row in self._db.execute("SELECT path FROM file_map")
            }

    def set_file(
        self,
        path: str,
        artifact: ParsedArtifact,
        *,
        module_name: str | None,
        visibility: EvidenceVisibility,
        index_surface: str = "other",
    ) -> dict[str, object]:
        new_nodes = derive_file_nodes(path, artifact)
        old_nodes = {row["kind"]: row for row in self.derived_nodes(path)}
        changed_kinds = tuple(
            node.kind
            for node in new_nodes
            if old_nodes.get(node.kind, {}).get("identity") != node.identity
        )
        preserved_kinds = tuple(
            node.kind
            for node in new_nodes
            if old_nodes.get(node.kind, {}).get("identity") == node.identity
        )
        shielded_kinds = tuple(
            node.kind
            for node in new_nodes
            if old_nodes.get(node.kind, {}).get("identity") == node.identity
            and tuple(old_nodes[node.kind].get("input_identities", ()))
            != node.input_identities
        )
        with self._lock:
            bulk_write = self._bulk_file_write_batch_size > 0
            if not self._db.in_transaction:
                self._db.execute("BEGIN")
            try:
                self._db.execute("DELETE FROM symbol WHERE path=?", (path,))
                self._db.execute("DELETE FROM edge WHERE path=?", (path,))
                self._db.execute("DELETE FROM lexical WHERE path=?", (path,))
                self._db.execute("DELETE FROM derived_node WHERE path=?", (path,))
                self._db.execute(
                    """INSERT INTO file_map(path,file_digest,artifact_key,language,module_name,evidence_visibility,full_tokens,outline,parse_error,index_surface,lexical_count)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(path) DO UPDATE SET
                      file_digest=excluded.file_digest, artifact_key=excluded.artifact_key,
                      language=excluded.language, module_name=excluded.module_name,
                      evidence_visibility=excluded.evidence_visibility, full_tokens=excluded.full_tokens,
                      outline=excluded.outline, parse_error=excluded.parse_error,
                      index_surface=excluded.index_surface, lexical_count=excluded.lexical_count""",
                    (
                        path,
                        artifact.file_digest,
                        artifact.artifact_key,
                        artifact.language,
                        module_name,
                        visibility.value,
                        artifact.full_tokens,
                        artifact.outline,
                        artifact.parse_error,
                        index_surface,
                        len(artifact.lexical),
                    ),
                )
                self._db.executemany(
                    """INSERT INTO symbol(path,name,qualname,kind,signature,start_line,end_line,signature_tokens,body_tokens,parent)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [
                        (
                            path,
                            s.name,
                            s.qualname,
                            s.kind,
                            s.signature,
                            s.start_line,
                            s.end_line,
                            s.signature_tokens,
                            s.body_tokens,
                            s.parent,
                        )
                        for s in artifact.symbols
                    ],
                )
                self._db.executemany(
                    "INSERT INTO edge(path,source,kind,target,target_short,line,confidence) VALUES (?,?,?,?,?,?,?)",
                    [
                        (
                            path,
                            e.source,
                            e.kind,
                            e.target,
                            e.target.rsplit(".", 1)[-1],
                            e.line,
                            e.confidence,
                        )
                        for e in artifact.edges
                    ],
                )
                self._db.executemany(
                    "INSERT INTO lexical(path,token,line) VALUES (?,?,?)",
                    [(path, item.token, item.line) for item in artifact.lexical],
                )
                nodes = new_nodes
                self._db.executemany(
                    "INSERT INTO derived_node(node_id,path,kind,identity,dependencies,input_identities,producer) VALUES (?,?,?,?,?,?,?)",
                    [
                        (
                            node.node_id,
                            node.path,
                            node.kind,
                            node.identity,
                            json.dumps(list(node.dependencies), separators=(",", ":")),
                            json.dumps(
                                list(node.input_identities), separators=(",", ":")
                            ),
                            node.producer,
                        )
                        for node in nodes
                    ],
                )
                if bulk_write:
                    self._bulk_file_write_count += 1
                    if self._bulk_file_write_count >= self._bulk_file_write_batch_size:
                        committed = self._bulk_file_write_count
                        self._db.execute("COMMIT")
                        self._bulk_file_write_committed += committed
                        self._bulk_file_write_count = 0
                        callback = self._bulk_file_write_on_commit
                        if callback is not None:
                            callback(self._bulk_file_write_committed)
                else:
                    self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                self._bulk_file_write_count = 0
                raise
        return {
            "changed_kinds": changed_kinds,
            "preserved_kinds": preserved_kinds,
            "shielded_kinds": shielded_kinds,
        }

    def paths_under(self, prefix: str) -> set[str]:
        clean = prefix.strip("/")
        if not clean:
            return self.paths()
        # Repository paths use '/' as the normalized segment separator. Under
        # SQLite's BINARY ordering every descendant therefore lies in the
        # contiguous range [clean + "/", clean + "0"). Keeping the exact path
        # as a separate equality term preserves file-prefix queries while
        # letting the file_map primary-key index bound descendant reads instead
        # of rescanning it through LIKE for every requested prefix.
        lower = clean + "/"
        upper = clean + "0"
        with self._lock:
            rows = self._db.execute(
                "SELECT path FROM file_map WHERE path=? OR (path>=? AND path<?)",
                (clean, lower, upper),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def delete_paths(self, paths: Iterable[str]) -> int:
        values = list(paths)
        if not values:
            return 0
        with self._lock, sqlite_transaction(self._db):
            for path in values:
                self._db.execute("DELETE FROM symbol WHERE path=?", (path,))
                self._db.execute("DELETE FROM edge WHERE path=?", (path,))
                self._db.execute("DELETE FROM lexical WHERE path=?", (path,))
                self._db.execute("DELETE FROM derived_node WHERE path=?", (path,))
                self._db.execute("DELETE FROM file_map WHERE path=?", (path,))
        return len(values)

    def replace_native_file_edges(self, producer_prefix: str, edges) -> None:
        with self._lock:
            with sqlite_transaction(self._db):
                self._db.execute(
                    "DELETE FROM native_file_edge WHERE producer LIKE ?",
                    (producer_prefix + "%",),
                )
                self._db.executemany(
                    "INSERT OR REPLACE INTO native_file_edge(source,target,kind,confidence,producer,specifier) VALUES (?,?,?,?,?,?)",
                    [
                        (
                            edge.source,
                            edge.target,
                            edge.kind,
                            edge.confidence,
                            edge.producer,
                            edge.specifier,
                        )
                        for edge in edges
                    ],
                )

    def native_file_edges(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT source,target,kind,confidence,producer,specifier FROM native_file_edge ORDER BY source,target"
            ).fetchall()
        return [dict(row) for row in rows]

    def native_file_edges_from(self, path: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT source,target,kind,confidence,producer,specifier FROM native_file_edge WHERE source=? ORDER BY target",
                (path,),
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_native_occurrences(self, producer: str, definitions, edges) -> None:
        with self._lock:
            with sqlite_transaction(self._db):
                self._db.execute(
                    "DELETE FROM native_definition WHERE producer=?", (producer,)
                )
                self._db.execute(
                    "DELETE FROM native_edge WHERE producer=?", (producer,)
                )
                self._db.executemany(
                    "INSERT OR REPLACE INTO native_definition(path,symbol,display_name,line,end_line,producer) VALUES (?,?,?,?,?,?)",
                    [
                        (
                            row["path"],
                            row["symbol"],
                            row["display_name"],
                            int(row["line"]),
                            int(row["end_line"]),
                            producer,
                        )
                        for row in definitions
                    ],
                )
                self._db.executemany(
                    "INSERT OR REPLACE INTO native_edge(path,source,target_symbol,target_name,line,producer) VALUES (?,?,?,?,?,?)",
                    [
                        (
                            row["path"],
                            row.get("source"),
                            row["target_symbol"],
                            row["target_name"],
                            int(row["line"]),
                            producer,
                        )
                        for row in edges
                    ],
                )

    def native_definitions(self, query: str, limit: int = 100) -> list[dict]:
        q = f"%{query.lower()}%"
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM native_definition WHERE lower(display_name) LIKE ? OR lower(symbol) LIKE ? ORDER BY path,line LIMIT ?",
                (q, q, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def native_refs(self, query: str, limit: int = 200) -> list[dict]:
        q = f"%{query.lower()}%"
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM native_edge WHERE lower(target_name) LIKE ? OR lower(target_symbol) LIKE ? ORDER BY path,line LIMIT ?",
                (q, q, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def native_edges_from(
        self, path: str, source: str | None = None, limit: int = 200
    ) -> list[dict]:
        with self._lock:
            if source is None:
                rows = self._db.execute(
                    "SELECT * FROM native_edge WHERE path=? ORDER BY line LIMIT ?",
                    (path, limit),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM native_edge WHERE path=? AND source=? ORDER BY line LIMIT ?",
                    (path, source, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def replace_project_graph(self, producer: str, nodes, edges) -> None:
        with self._lock:
            with sqlite_transaction(self._db):
                self._db.execute(
                    "DELETE FROM project_edge WHERE producer=?", (producer,)
                )
                self._db.execute(
                    "DELETE FROM project_node WHERE producer=?", (producer,)
                )
                self._db.executemany(
                    "INSERT INTO project_node(project_id,kind,root,manifest,producer,metadata) VALUES (?,?,?,?,?,?)",
                    [
                        (
                            node.project_id,
                            node.kind,
                            node.root,
                            node.manifest,
                            node.producer,
                            json.dumps(
                                node.metadata, sort_keys=True, separators=(",", ":")
                            ),
                        )
                        for node in nodes
                    ],
                )
                self._db.executemany(
                    "INSERT OR REPLACE INTO project_edge(source,target,kind,confidence,producer) VALUES (?,?,?,?,?)",
                    [
                        (
                            edge.source,
                            edge.target,
                            edge.kind,
                            edge.confidence,
                            edge.producer,
                        )
                        for edge in edges
                    ],
                )

    def project_nodes(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT project_id,kind,root,manifest,producer,metadata FROM project_node ORDER BY root,project_id"
            ).fetchall()
        out = []
        for row in rows:
            value = dict(row)
            try:
                value["metadata"] = json.loads(value["metadata"])
            except (TypeError, json.JSONDecodeError):
                value["metadata"] = {}
            out.append(value)
        return out

    def project_edges(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT source,target,kind,confidence,producer FROM project_edge ORDER BY source,target,kind"
            ).fetchall()
        return [dict(row) for row in rows]

    def projects_for_path(self, path: str) -> list[dict]:
        clean = path.strip("/")
        rows = self.project_nodes()
        matches = []
        for row in rows:
            root = str(row["root"]).strip("/")
            if root in {"", "."} or clean == root or clean.startswith(root + "/"):
                matches.append(row)
        matches.sort(key=lambda row: len(str(row["root"])), reverse=True)
        return matches

    def project_dependents(
        self, project_ids: set[str], max_depth: int = 12
    ) -> set[str]:
        reverse: dict[str, set[str]] = {}
        for edge in self.project_edges():
            reverse.setdefault(str(edge["target"]), set()).add(str(edge["source"]))
        seen = set(project_ids)
        frontier = set(project_ids)
        for _ in range(max_depth):
            nxt: set[str] = set()
            for project_id in frontier:
                nxt.update(reverse.get(project_id, ()))
            nxt -= seen
            if not nxt:
                break
            seen.update(nxt)
            frontier = nxt
        return seen

    def clear(self) -> dict[str, int]:
        before = self.stats()
        tables = (
            "native_file_edge",
            "native_edge",
            "native_definition",
            "project_edge",
            "project_node",
            "lexical",
            "edge",
            "symbol",
            "file_map",
        )
        with self._lock, sqlite_transaction(self._db, begin="BEGIN IMMEDIATE"):
            for table in tables:
                self._db.execute(f"DELETE FROM {table}")
            self._db.execute("DELETE FROM meta WHERE key != 'state.workspace'")
        return before

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "files": int(
                    self._db.execute("SELECT COUNT(*) FROM file_map").fetchone()[0]
                ),
                "symbols": int(
                    self._db.execute("SELECT COUNT(*) FROM symbol").fetchone()[0]
                ),
                "edges": int(
                    self._db.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
                ),
                "lexical_occurrences": int(
                    self._db.execute("SELECT COUNT(*) FROM lexical").fetchone()[0]
                ),
                "parse_errors": int(
                    self._db.execute(
                        "SELECT COUNT(*) FROM file_map WHERE parse_error IS NOT NULL"
                    ).fetchone()[0]
                ),
                "projects": int(
                    self._db.execute("SELECT COUNT(*) FROM project_node").fetchone()[0]
                ),
                "project_edges": int(
                    self._db.execute("SELECT COUNT(*) FROM project_edge").fetchone()[0]
                ),
                "native_definitions": int(
                    self._db.execute(
                        "SELECT COUNT(*) FROM native_definition"
                    ).fetchone()[0]
                ),
                "native_edges": int(
                    self._db.execute("SELECT COUNT(*) FROM native_edge").fetchone()[0]
                ),
                "native_file_edges": int(
                    self._db.execute(
                        "SELECT COUNT(*) FROM native_file_edge"
                    ).fetchone()[0]
                ),
            }

    def economics_counts_by_surface(self) -> dict[str, object]:
        """Return exact economics from compact per-file facts, not lexical scans."""
        with self._lock:
            rows = self._db.execute(
                """SELECT index_surface,COUNT(*) files,SUM(lexical_count) lexical_occurrences,
                          SUM(CASE WHEN parse_error IS NOT NULL THEN 1 ELSE 0 END) parse_errors
                   FROM file_map GROUP BY index_surface ORDER BY index_surface"""
            ).fetchall()
        surfaces: dict[str, dict[str, int]] = {}
        files = lexical = parse_errors = 0
        for row in rows:
            count = int(row["files"] or 0)
            occurrences = int(row["lexical_occurrences"] or 0)
            errors = int(row["parse_errors"] or 0)
            files += count
            lexical += occurrences
            parse_errors += errors
            if occurrences:
                surfaces[str(row["index_surface"])] = {
                    "files_with_lexical_evidence": count,
                    "lexical_occurrences": occurrences,
                }
        return {
            "files": files,
            "lexical_occurrences": lexical,
            "parse_errors": parse_errors,
            "surfaces": surfaces,
        }

    def lexical_counts_by_path(self) -> dict[str, int]:
        """Return measured lexical occurrence counts keyed by indexed path."""
        with self._lock:
            rows = self._db.execute(
                "SELECT path,COUNT(*) n FROM lexical GROUP BY path"
            ).fetchall()
        return {str(row["path"]): int(row["n"]) for row in rows}

    def language_counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._db.execute(
                "SELECT language,COUNT(*) n FROM file_map GROUP BY language ORDER BY n DESC"
            ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def top_level_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for path in self.paths():
            top = path.split("/", 1)[0]
            counts[top] = counts.get(top, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
