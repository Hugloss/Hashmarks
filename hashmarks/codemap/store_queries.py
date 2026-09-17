from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .repository_index_store import WorkspaceMapStore


class WorkspaceMapQueryMixin:
    def has_derived_nodes(self, path: str) -> bool:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM derived_node WHERE path=? LIMIT 1", (path,)
            ).fetchone()
        return row is not None

    def derived_paths(self, paths) -> set[str]:
        """Return paths with derived evidence using bounded SQLite batches."""
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted({str(path) for path in paths if path})
        result: set[str] = set()
        with self._lock:
            for start in range(0, len(unique), 500):
                chunk = unique[start : start + 500]
                if not chunk:
                    continue
                placeholders = ",".join("?" for _ in chunk)
                rows = self._db.execute(
                    f"SELECT DISTINCT path FROM derived_node WHERE path IN ({placeholders})",
                    tuple(chunk),
                ).fetchall()
                result.update(str(row[0]) for row in rows)
        return result

    def file_reuse_rows(self, paths) -> dict[str, tuple[str, str, str, str, bool]]:
        """Load only warm-reuse authority fields in bounded SQLite batches."""
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted({str(path) for path in paths if path})
        result: dict[str, tuple[str, str, str, str, bool]] = {}
        with self._lock:
            for start in range(0, len(unique), 500):
                chunk = unique[start : start + 500]
                if not chunk:
                    continue
                placeholders = ",".join("?" for _ in chunk)
                rows = self._db.execute(
                    f"""SELECT f.path,f.file_digest,f.artifact_key,f.evidence_visibility,f.module_name,
                    EXISTS(SELECT 1 FROM derived_node d WHERE d.path=f.path)
                    FROM file_map f WHERE f.path IN ({placeholders})""",
                    tuple(chunk),
                ).fetchall()
                for row in rows:
                    result[str(row[0])] = (
                        str(row[1]),
                        str(row[2]),
                        str(row[3]),
                        str(row[4] or ""),
                        bool(row[5]),
                    )
        return result

    def derived_nodes(self, path: str | None = None) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            if path is None:
                rows = self._db.execute(
                    "SELECT * FROM derived_node ORDER BY path,kind"
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM derived_node WHERE path=? ORDER BY kind", (path,)
                ).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["dependencies"] = json.loads(value["dependencies"])
            value["input_identities"] = json.loads(value["input_identities"])
            result.append(value)
        return result

    def outline(self, path: str) -> dict | None:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        row = self.file_row(path)
        if row is None:
            return None
        return dict(row)

    def symbols_for_path(self, path: str) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        self._count_read("symbols_for_path")
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM symbol WHERE path=? ORDER BY start_line", (path,)
            ).fetchall()
        return [dict(row) for row in rows]

    def symbol(self, query: str) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            rows = self._db.execute(
                """SELECT s.*, f.evidence_visibility FROM symbol s JOIN file_map f ON f.path=s.path
                WHERE s.qualname=? OR s.name=? ORDER BY CASE WHEN s.qualname=? THEN 0 ELSE 1 END, s.path LIMIT 50""",
                (query, query, query),
            ).fetchall()
        return [dict(row) for row in rows]

    def edges_from(self, path: str, source: str | None = None) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            if source is None:
                rows = self._db.execute(
                    "SELECT * FROM edge WHERE path=? ORDER BY line", (path,)
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM edge WHERE path=? AND (source=? OR source LIKE ?) ORDER BY line",
                    (path, source, source + ".%"),
                ).fetchall()
        return [dict(row) for row in rows]

    def refs(self, target: str, *, limit: int = 100) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        if limit < 1:
            raise ValueError("limit must be >= 1")
        limit = min(int(limit), 1024)
        short = target.rsplit(".", 1)[-1]
        self._count_read("refs")
        with self._lock:
            rows = self._db.execute(
                """SELECT e.*, f.evidence_visibility FROM edge e JOIN file_map f ON f.path=e.path
                WHERE e.target_short=? ORDER BY e.path,e.line LIMIT ?""",
                (short, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def refs_many(
        self, targets: Iterable[str], *, limit_per_target: int = 100
    ) -> dict[str, list[dict]]:
        """Read bounded reverse-reference prefixes without scanning every same-name edge.

        High-frequency symbols can have tens of thousands of edges.  A windowed
        multi-target query must rank the complete matching set before applying the
        per-target bound.  Resolve each distinct short identity through the ordered
        covering index instead, so SQLite can stop at ``limit_per_target`` while
        preserving the established deterministic ``path,line`` prefix semantics.
        """
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique_targets = list(
            dict.fromkeys(str(target) for target in targets if target)
        )
        if not unique_targets:
            return {}
        if limit_per_target < 1:
            raise ValueError("limit_per_target must be >= 1")
        limit_per_target = min(int(limit_per_target), 1024)
        target_short = {target: target.rsplit(".", 1)[-1] for target in unique_targets}
        unique_shorts = list(dict.fromkeys(target_short.values()))
        self._count_read("refs_many")
        by_short: dict[str, list[dict]] = {}
        with self._lock:
            for short in unique_shorts:
                rows = self._db.execute(
                    """SELECT e.*,f.evidence_visibility
                    FROM edge e JOIN file_map f ON f.path=e.path
                    WHERE e.target_short=?
                    ORDER BY e.path,e.line LIMIT ?""",
                    (short, limit_per_target),
                ).fetchall()
                by_short[short] = [dict(row) for row in rows]
        return {
            target: [dict(row) for row in by_short[target_short[target]]]
            for target in unique_targets
        }

    def refs_matching_target_suffix(
        self, target_short: str, target_suffix: str, *, limit: int = 1024
    ) -> list[dict]:
        """Return bounded same-name refs whose qualified target ends at a known owner.

        This is a candidate read only.  Callers must still resolve import identity
        against the repository before treating a row as direct evidence.
        """
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        if limit < 1:
            raise ValueError("limit must be >= 1")
        short = str(target_short).strip()
        suffix = str(target_suffix).strip(".")
        if not short or not suffix:
            return []
        limit = min(int(limit), 1024)
        self._count_read("refs_matching_target_suffix")
        with self._lock:
            rows = self._db.execute(
                """SELECT e.*,f.evidence_visibility
                FROM edge e JOIN file_map f ON f.path=e.path
                WHERE e.target_short=? AND (e.target=? OR e.target LIKE ?)
                ORDER BY e.path,e.line LIMIT ?""",
                (short, suffix, "%" + suffix, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def edges_from_many(
        self, seeds: Iterable[tuple[str, str]], *, limit_per_seed: int = 100
    ) -> dict[tuple[str, str], list[dict]]:
        """Read bounded path+source edge neighborhoods without N+1 or N×row Python scans."""
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = list(
            dict.fromkeys(
                (str(path), str(source)) for path, source in seeds if path and source
            )
        )
        if not unique:
            return {}
        if limit_per_seed < 1:
            raise ValueError("limit_per_seed must be >= 1")
        limit_per_seed = min(int(limit_per_seed), 1024)
        self._count_read("edges_from_many")
        values_sql = ",".join("(?,?,?)" for _ in unique)
        params: list[object] = []
        for path, source in unique:
            params.extend((path, source, source + ".%"))
        params.append(limit_per_seed)
        with self._lock:
            rows = self._db.execute(
                f"""WITH wanted(seed_path,seed_source,seed_prefix) AS (VALUES {values_sql}),
                matched AS (
                  SELECT wanted.seed_path AS query_path,wanted.seed_source AS query_source,e.*,
                         ROW_NUMBER() OVER (
                           PARTITION BY wanted.seed_path,wanted.seed_source ORDER BY e.line,e.target,e.kind
                         ) AS rn
                  FROM wanted JOIN edge e
                    ON e.path=wanted.seed_path
                   AND (e.source=wanted.seed_source OR e.source LIKE wanted.seed_prefix)
                )
                SELECT * FROM matched WHERE rn<=? ORDER BY query_path,query_source,line""",
                tuple(params),
            ).fetchall()
        result: dict[tuple[str, str], list[dict]] = {seed: [] for seed in unique}
        for raw in rows:
            row = dict(raw)
            key = (str(row.pop("query_path")), str(row.pop("query_source")))
            row.pop("rn", None)
            result[key].append(row)
        return result

    def edges_for_paths_many(
        self, paths: Iterable[str], *, limit_per_path: int = 100
    ) -> dict[str, list[dict]]:
        """Read bounded edge neighborhoods for known paths in one SQL read.

        This is the path-level companion to ``edges_from_many`` for callers that
        already know the file identities but do not need source-qualname filtering.
        """
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = list(dict.fromkeys(str(path) for path in paths if path))
        if not unique:
            return {}
        if limit_per_path < 1:
            raise ValueError("limit_per_path must be >= 1")
        limit_per_path = min(int(limit_per_path), 1024)
        self._count_read("edges_for_paths_many")
        values_sql = ",".join("(?)" for _ in unique)
        params: list[object] = [*unique, limit_per_path]
        with self._lock:
            rows = self._db.execute(
                f"""WITH wanted(seed_path) AS (VALUES {values_sql}),
                matched AS (
                  SELECT wanted.seed_path AS query_path,e.*,
                         ROW_NUMBER() OVER (PARTITION BY wanted.seed_path ORDER BY e.line,e.target,e.kind) AS rn
                  FROM wanted JOIN edge e ON e.path=wanted.seed_path
                )
                SELECT * FROM matched WHERE rn<=? ORDER BY query_path,line,target,kind""",
                tuple(params),
            ).fetchall()
        result: dict[str, list[dict]] = {path: [] for path in unique}
        for raw in rows:
            row = dict(raw)
            path = str(row.pop("query_path"))
            row.pop("rn", None)
            result[path].append(row)
        return result

    def search_candidates(self, query: str, limit: int = 200) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        q = f"%{query.lower()}%"
        with self._lock:
            symbols = self._db.execute(
                """SELECT s.*, f.evidence_visibility FROM symbol s JOIN file_map f ON f.path=s.path
                WHERE lower(s.name) LIKE ? OR lower(s.qualname) LIKE ? OR lower(s.signature) LIKE ? OR lower(s.path) LIKE ?
                ORDER BY s.path,s.start_line,s.qualname
                LIMIT ?""",
                (q, q, q, q, limit),
            ).fetchall()
            files = self._db.execute(
                """SELECT path,language,evidence_visibility,full_tokens,outline FROM file_map
                WHERE lower(path) LIKE ? ORDER BY path LIMIT ?""",
                (q, limit),
            ).fetchall()
        out = [{"row_type": "symbol", **dict(row)} for row in symbols]
        out.extend({"row_type": "file", **dict(row)} for row in files)
        return out

    def exact_symbol_candidates(self, terms: list[str], limit: int = 500) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted({term.lower() for term in terms if term})
        if not unique:
            return []
        self._count_read("exact_symbol_candidates")
        placeholders = ",".join("?" for _ in unique)
        with self._lock:
            rows = self._db.execute(
                f"""SELECT s.*, f.evidence_visibility FROM symbol s JOIN file_map f ON f.path=s.path
                WHERE lower(s.name) IN ({placeholders}) OR lower(s.qualname) IN ({placeholders})
                ORDER BY s.path,s.start_line LIMIT ?""",
                (*unique, *unique, limit),
            ).fetchall()
        return [{"row_type": "symbol", **dict(row)} for row in rows]

    def lexical_document_frequencies(
        self, tokens: list[str]
    ) -> tuple[int, dict[str, int]]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted({token.lower() for token in tokens if token})
        self._count_read("lexical_document_frequencies")
        with self._lock:
            total = int(self._db.execute("SELECT COUNT(*) FROM file_map").fetchone()[0])
            if not unique:
                return total, {}
            placeholders = ",".join("?" for _ in unique)
            rows = self._db.execute(
                f"""SELECT token,COUNT(DISTINCT path) AS documents FROM lexical
                WHERE token IN ({placeholders}) GROUP BY token""",
                tuple(unique),
            ).fetchall()
        return total, {str(row["token"]): int(row["documents"]) for row in rows}

    def lexical_file_candidates(
        self, tokens: list[str], limit: int = 100
    ) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted({token.lower() for token in tokens if token})
        if not unique:
            return []
        self._count_read("lexical_file_candidates")
        placeholders = ",".join("?" for _ in unique)
        with self._lock:
            rows = self._db.execute(
                f"""WITH matched AS (
                    SELECT token,path FROM lexical
                    WHERE token IN ({placeholders})
                    GROUP BY token,path
                ), ranked AS (
                    SELECT path,COUNT(*) AS matches FROM matched
                    GROUP BY path
                    ORDER BY matches DESC,path
                    LIMIT ?
                )
                SELECT ranked.path,f.language,f.evidence_visibility,f.full_tokens,f.outline,ranked.matches
                FROM ranked JOIN file_map f ON f.path=ranked.path
                ORDER BY ranked.matches DESC,ranked.path""",
                (*unique, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def symbols_for_paths(self, paths: list[str], limit: int = 5000) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted({path for path in paths if path})
        if not unique:
            return []
        self._count_read("symbols_for_paths")
        placeholders = ",".join("?" for _ in unique)
        with self._lock:
            rows = self._db.execute(
                f"""SELECT s.*, f.evidence_visibility FROM symbol s JOIN file_map f ON f.path=s.path
                WHERE s.path IN ({placeholders}) ORDER BY s.path,s.start_line LIMIT ?""",
                (*unique, limit),
            ).fetchall()
        return [{"row_type": "symbol", **dict(row)} for row in rows]

    def symbols_for_paths_complete(self, paths: Iterable[str]) -> list[dict]:
        """Return the complete symbol rows for a bounded, already-known path set.

        Decision-session preloading must never publish a globally truncated
        multi-path query as if each path cache were complete.  Callers are
        expected to pass a small candidate path set that has already been
        bounded by repository retrieval/action logic.
        """
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted({str(path) for path in paths if path})
        if not unique:
            return []
        self._count_read("symbols_for_paths_complete")
        placeholders = ",".join("?" for _ in unique)
        with self._lock:
            rows = self._db.execute(
                f"""SELECT s.*, f.evidence_visibility FROM symbol s JOIN file_map f ON f.path=s.path
                WHERE s.path IN ({placeholders}) ORDER BY s.path,s.start_line""",
                tuple(unique),
            ).fetchall()
        return [{"row_type": "symbol", **dict(row)} for row in rows]

    def symbols_for_paths_many(
        self,
        paths: Iterable[str],
        *,
        limit_per_path: int = 64,
    ) -> dict[str, list[dict]]:
        """Read a bounded symbol prefix for each already-known path in one query.

        Unlike ``symbols_for_paths`` this preserves an independent bound per
        path, so a symbol-dense file cannot starve later paths. It is intended
        for callers that previously performed ``symbols_for_path(path)[:N]`` in
        a loop and therefore has exact row-at-a-time replacement semantics.
        """
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = list(dict.fromkeys(str(path) for path in paths if path))
        if not unique:
            return {}
        if limit_per_path < 1:
            raise ValueError("limit_per_path must be >= 1")
        limit_per_path = min(int(limit_per_path), 1024)
        values_sql = ",".join("(?)" for _ in unique)
        self._count_read("symbols_for_paths_many")
        with self._lock:
            rows = self._db.execute(
                f"""WITH wanted(path) AS (VALUES {values_sql}),
                ranked AS (
                  SELECT s.*,ROW_NUMBER() OVER (
                    PARTITION BY s.path ORDER BY s.start_line
                  ) AS rn
                  FROM wanted JOIN symbol s ON s.path=wanted.path
                )
                SELECT * FROM ranked WHERE rn<=? ORDER BY path,start_line""",
                (*unique, limit_per_path),
            ).fetchall()
        result: dict[str, list[dict]] = {path: [] for path in unique}
        for raw in rows:
            row = dict(raw)
            row.pop("rn", None)
            result[str(row["path"])].append(row)
        return result

    def path_candidates(self, terms: list[str], limit: int = 100) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted({term.lower() for term in terms if len(term) >= 2})
        if not unique:
            return []
        clauses = " OR ".join("lower(path) LIKE ?" for _ in unique)
        params = tuple(f"%{term}%" for term in unique)
        with self._lock:
            rows = self._db.execute(
                f"""SELECT path,language,evidence_visibility,full_tokens,outline FROM file_map
                WHERE {clauses} ORDER BY path LIMIT ?""",
                (*params, limit),
            ).fetchall()
        return [{"row_type": "file", **dict(row)} for row in rows]

    def all_symbols(self, limit: int = 100000) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            rows = self._db.execute(
                """SELECT s.*, f.evidence_visibility FROM symbol s JOIN file_map f ON f.path=s.path
                ORDER BY s.path,s.start_line LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def lexical_candidates(self, tokens: list[str], limit: int = 500) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted({token.lower() for token in tokens if token})
        if not unique:
            return []
        placeholders = ",".join("?" for _ in unique)
        with self._lock:
            rows = self._db.execute(
                f"""SELECT l.path,l.line,f.evidence_visibility,COUNT(DISTINCT l.token) matches
                FROM lexical l JOIN file_map f ON f.path=l.path
                WHERE l.token IN ({placeholders})
                GROUP BY l.path,l.line
                HAVING matches=?
                ORDER BY l.path,l.line
                LIMIT ?""",
                (*unique, len(unique), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def module_paths(self, module: str) -> list[str]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        candidate = module.strip(".")
        self._count_read("module_paths")
        with self._lock:
            rows = self._db.execute(
                "SELECT path FROM file_map WHERE module_name=? ORDER BY path LIMIT 20",
                (candidate,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def module_paths_many(self, modules: Iterable[str]) -> dict[str, list[str]]:
        """Resolve many exact module identities in one indexed read.

        Results preserve ``module_paths`` ordering and its per-module 20-path
        bound.  The caller supplies already-known module identities; this is a
        bulk primary-key-style lookup, not broader repository discovery.
        """
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted(
            {str(module).strip(".") for module in modules if str(module).strip(".")}
        )
        if not unique:
            return {}
        self._count_read("module_paths_many")
        placeholders = ",".join("?" for _ in unique)
        with self._lock:
            rows = self._db.execute(
                f"SELECT module_name,path FROM file_map WHERE module_name IN ({placeholders}) ORDER BY module_name,path",
                tuple(unique),
            ).fetchall()
        grouped: dict[str, list[str]] = {module: [] for module in unique}
        for row in rows:
            module = str(row[0])
            bucket = grouped.setdefault(module, [])
            if len(bucket) < 20:
                bucket.append(str(row[1]))
        return grouped

    def symbols_named(self, name: str, limit: int = 20) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            rows = self._db.execute(
                """SELECT s.*, f.evidence_visibility FROM symbol s JOIN file_map f ON f.path=s.path
                WHERE s.name=? ORDER BY s.path,s.start_line LIMIT ?""",
                (name, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def all_file_rows(self) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            rows = self._db.execute(
                "SELECT path,language,module_name,evidence_visibility,file_digest FROM file_map ORDER BY path"
            ).fetchall()
        return [dict(row) for row in rows]

    def repository_instruction_file_rows(self) -> list[dict]:
        """Return only mechanically scoped repository authority surfaces."""
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            rows = self._db.execute(
                """SELECT path,language,module_name,evidence_visibility,file_digest FROM file_map
                   WHERE path='AGENTS.md' OR path='AGENTS.override.md'
                      OR path LIKE '%/AGENTS.md' OR path LIKE '%/AGENTS.override.md'
                   ORDER BY path"""
            ).fetchall()
        return [dict(row) for row in rows]

    def python_import_candidates_for_modules(
        self, modules: Iterable[str]
    ) -> dict[str, list[dict]]:
        """Return indexed Python import rows that may resolve through modules.

        This is a reverse-lookup primitive for bounded impact traversal.  It
        deliberately returns candidates rather than claiming resolution: the
        caller still applies the existing longest-module-prefix rule.
        """
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        unique = sorted(
            {str(module).strip(".") for module in modules if str(module).strip(".")}
        )
        if not unique:
            return {}
        self._count_read("python_import_candidates_for_modules")
        clauses: list[str] = []
        params: list[object] = []
        for module in unique:
            prefix = module + "."
            clauses.append("(e.target=? OR (e.target>=? AND e.target<?))")
            params.extend((module, prefix, prefix + "\uffff"))
        sql = f"""SELECT e.path,e.target,e.line FROM edge e
                  JOIN file_map f ON f.path=e.path
                  WHERE e.kind='import' AND f.language='python'
                    AND ({" OR ".join(clauses)})
                  ORDER BY e.path,e.line,e.target"""
        with self._lock:
            rows = self._db.execute(sql, tuple(params)).fetchall()
        out: dict[str, list[dict]] = {module: [] for module in unique}
        for raw in rows:
            row = dict(raw)
            target = str(row.get("target") or "")
            for module in unique:
                if target == module or target.startswith(module + "."):
                    out[module].append(row)
        return out

    def all_edges(self, kind: str | None = None) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            if kind is None:
                rows = self._db.execute(
                    "SELECT * FROM edge ORDER BY path,line"
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM edge WHERE kind=? ORDER BY path,line",
                    (kind,),
                ).fetchall()
        return [dict(row) for row in rows]

    def top_edge_targets(self, limit: int = 12) -> list[tuple[str, int]]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            rows = self._db.execute(
                "SELECT target,COUNT(*) n FROM edge GROUP BY target ORDER BY n DESC,target LIMIT ?",
                (limit,),
            ).fetchall()
        return [(str(row[0]), int(row[1])) for row in rows]

    def file_digests(self) -> list[tuple[str, str]]:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            rows = self._db.execute(
                "SELECT path,file_digest FROM file_map ORDER BY path"
            ).fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]

    def symbol_at(self, path: str, qualname: str) -> dict | None:
        if TYPE_CHECKING:
            self = cast("WorkspaceMapStore", self)
        with self._lock:
            row = self._db.execute(
                """SELECT s.*, f.evidence_visibility FROM symbol s JOIN file_map f ON f.path=s.path
                WHERE s.path=? AND s.qualname=?""",
                (path, qualname),
            ).fetchone()
        return None if row is None else dict(row)
