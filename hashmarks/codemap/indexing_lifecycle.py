from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import json
import os
import sqlite3
import time
import tomllib
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.digest import Digest
from hashmarks.file_store import FileDigestStore, UnstableFileError
from hashmarks.paths import normalize_relative_path

from . import repository_file_discovery
from .index_surfaces import index_surface_for_path
from .index_watch import IndexWatchMixin
from .model import EvidenceVisibility, ParsedArtifact, SyncResult
from .parsers import artifact_key_for, parse_source
from .repository_file_discovery import _AdmittedRepositoryFile
from .repository_index_store import (
    ArtifactStore,
    WorkspaceMapStore,
    default_base_snapshot,
    git_base_identity,
    git_overlay_paths,
)
from .source_languages import SOURCE_LANGUAGES
from .watch_continuity import (
    WATCH_CONTINUITY_META,
    WatchContinuityRecord,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from hashmarks.client import RepositoryObservation

    from .providers import SourceRangeProvider
    from .repository_file_discovery import RepositoryFiles
    from .repository_observation import RepositoryObservationSource

_SOURCE_EXTENSIONS = SOURCE_LANGUAGES

_TEXT_EXTENSIONS = {
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".md",
    ".rst",
    ".txt",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".cmd",
    ".bat",
}
_TEXT_NAMES = {
    "Makefile",
    "Dockerfile",
    "Justfile",
    "go.mod",
    "go.sum",
    "gradlew",
    "mvnw",
    "README.md",
    "AGENTS.md",
    "AGENTS.override.md",
}
_NOISY_TEXT_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "Cargo.lock",
    "poetry.lock",
    ".hashmarks-context.toml",
    ".hashmarks-project-links.toml",
}
_ANALYSIS_SCOPE_CONFORMANCE_SCHEMA = "hashmarks.analysis-scope-conformance.v1"
_MAX_INDEX_BYTES = 2 * 1024 * 1024


def _language_for_path(path: Path) -> str | None:
    if path.name in _NOISY_TEXT_NAMES:
        return None
    language = _SOURCE_EXTENSIONS.get(path.suffix.lower())
    if language is not None:
        return language
    if path.name in _TEXT_NAMES or path.suffix.lower() in _TEXT_EXTENSIONS:
        return "text"
    return None


def _uv_workspace_member(
    pyproject: Path,
    workspace: Path,
    members: Sequence[str],
    excludes: Sequence[str],
) -> bool:
    """Apply one admitted workspace declaration to a candidate manifest."""
    if pyproject == workspace / "pyproject.toml":
        return True
    try:
        project = pyproject.parent.relative_to(workspace).as_posix()
    except ValueError:
        return False
    return any(
        fnmatch.fnmatchcase(project, pattern) for pattern in members
    ) and not any(fnmatch.fnmatchcase(project, pattern) for pattern in excludes)


def _uv_workspace_pyprojects(
    workspace: Path, pyprojects: Sequence[Path]
) -> tuple[Path, ...]:
    """Restrict nested project metadata to declared uv workspace members when configured."""
    root_manifest = workspace / "pyproject.toml"
    if root_manifest not in pyprojects:
        return tuple(pyprojects)
    try:
        data = tomllib.loads(root_manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return tuple(pyprojects)
    tool = data.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    workspace_cfg = uv.get("workspace") if isinstance(uv, dict) else None
    if not isinstance(workspace_cfg, dict):
        return tuple(pyprojects)
    members = workspace_cfg.get("members")
    if not isinstance(members, list):
        return tuple(pyprojects)
    member_patterns = tuple(
        value.strip().strip("/")
        for value in members
        if isinstance(value, str) and value.strip()
    )
    excludes = workspace_cfg.get("exclude")
    exclude_patterns = (
        tuple(
            value.strip().strip("/")
            for value in excludes
            if isinstance(value, str) and value.strip()
        )
        if isinstance(excludes, list)
        else ()
    )

    return tuple(
        pyproject
        for pyproject in pyprojects
        if _uv_workspace_member(pyproject, workspace, member_patterns, exclude_patterns)
    )


def _setuptools_source_roots(tool: dict[str, object]) -> set[str]:
    configured: set[str] = set()
    setuptools = tool.get("setuptools")
    if not isinstance(setuptools, dict):
        return configured
    package_dir = setuptools.get("package-dir")
    if not isinstance(package_dir, dict):
        return configured
    root = package_dir.get("")
    if isinstance(root, str) and root.strip():
        configured.add(root.strip().strip("/"))
    return configured


def _hatch_source_roots(tool: dict[str, object]) -> set[str]:
    configured: set[str] = set()
    hatch = tool.get("hatch")
    if not isinstance(hatch, dict):
        return configured
    build = hatch.get("build")
    targets = build.get("targets") if isinstance(build, dict) else None
    wheel = targets.get("wheel") if isinstance(targets, dict) else None
    packages = wheel.get("packages") if isinstance(wheel, dict) else None
    if not isinstance(packages, list):
        return configured
    for package in packages:
        if isinstance(package, str) and "/" in package.strip("/"):
            configured.add(package.strip("/").split("/", 1)[0])
    return configured


def _poetry_source_roots(tool: dict[str, object]) -> set[str]:
    configured: set[str] = set()
    poetry = tool.get("poetry")
    packages = poetry.get("packages") if isinstance(poetry, dict) else None
    if not isinstance(packages, list):
        return configured
    for package in packages:
        if not isinstance(package, dict):
            continue
        root = package.get("from")
        if isinstance(root, str) and root.strip():
            configured.add(root.strip().strip("/"))
    return configured


def _project_source_roots(data: object) -> set[str]:
    tool = data.get("tool") if isinstance(data, dict) else None
    tool = tool if isinstance(tool, dict) else {}
    return {
        *_setuptools_source_roots(tool),
        *_hatch_source_roots(tool),
        *_poetry_source_roots(tool),
    }


def _python_source_roots_from_pyprojects(
    workspace: Path, pyprojects: Sequence[Path]
) -> tuple[str, ...]:
    """Return workspace-relative import roots from explicit project metadata."""
    roots: set[str] = set()
    for pyproject in _uv_workspace_pyprojects(workspace, pyprojects):
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project_prefix = pyproject.parent.relative_to(workspace).as_posix()
        except (OSError, ValueError, tomllib.TOMLDecodeError):
            continue
        for root in _project_source_roots(data):
            combined = "/".join(
                part for part in (project_prefix, root) if part and part != "."
            )
            if combined:
                roots.add(combined)
    return tuple(sorted(roots))


def _module_name(relpath: str, source_roots: Sequence[str] = ()) -> str | None:
    if not relpath.endswith((".py", ".pyi")):
        return None
    module_path = relpath.rsplit(".", 1)[0]
    for root in sorted(source_roots, key=len, reverse=True):
        prefix = root.rstrip("/") + "/"
        if module_path.startswith(prefix):
            module_path = module_path[len(prefix) :]
            break
    parts = module_path.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or None


@dataclass(frozen=True)
class _DiscoveredFile:
    rel: str
    path: Path
    language: str
    visibility: EvidenceVisibility
    size: int


@dataclass
class _SyncIndexState:
    indexed: int = 0
    reused: int = 0
    parsed: int = 0
    skipped: int = 0
    parse_errors: int = 0
    persisted_file_writes: int = 0
    derived_changed: int = 0
    derived_preserved: int = 0
    semantic_shields: int = 0
    base_snapshot_reused: int = 0
    changed: bool = False
    present: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class _SyncDiscovery:
    files: list[_DiscoveredFile]
    full: bool
    requested_paths: tuple[str, ...]


@dataclass(frozen=True)
class _SyncBaseSnapshot:
    identity: str | None
    overlay_paths: set[str] | None
    payload: dict[str, object] | None


@dataclass(frozen=True)
class _SyncIdentity:
    generation: int
    fingerprint: str
    identity_generation: int | None


@dataclass(frozen=True)
class _AnalysisScopeConformance:
    """One scope observation and its canonical encoding and identity."""

    payload: dict[str, object]
    encoded: str
    identity: str


@dataclass(frozen=True)
class _FileReuseState:
    digest: str | None
    artifact: str | None
    visibility: str | None
    module: str | None
    has_derived: bool


def _minimal_path_prefixes(paths: Sequence[str]) -> tuple[str, ...]:
    """Return the smallest segment-aware prefix cover for normalized paths."""
    selected: list[str] = []
    for rel in sorted(set(paths)):
        if selected:
            parent = selected[-1]
            if rel == parent or rel.startswith(parent.rstrip("/") + "/"):
                continue
        selected.append(rel)
    return tuple(selected)


def _sorted_paths_under(sorted_paths: Sequence[str], rel: str) -> set[str]:
    """Return exact/descendant members without rescanning unrelated paths."""
    start = bisect_left(sorted_paths, rel)
    prefix = rel.rstrip("/") + "/"
    current: set[str] = set()
    for path in sorted_paths[start:]:
        if path == rel or path.startswith(prefix):
            current.add(path)
            continue
        break
    return current


class RepositoryIndex(IndexWatchMixin):
    """Own stable ingestion, reconciliation and atomic derived-index publication.

    Storage and producers are borrowed narrow dependencies. No read scope,
    source observer, relationship cache or CodeMap is required to construct it.
    """

    def __init__(  # noqa: PLR0913 - explicit ingestion capabilities replace a facade dependency
        self,
        files: RepositoryFiles,
        store: WorkspaceMapStore,
        file_store: FileDigestStore,
        artifacts: ArtifactStore,
        *,
        range_provider: SourceRangeProvider,
        observation_source: RepositoryObservationSource,
        max_index_bytes: int = _MAX_INDEX_BYTES,
    ) -> None:
        self.files = files
        self.workspace = files.workspace
        self.state_dir = store.db_path.parent
        self.store = store
        self.file_store = file_store
        self.artifacts = artifacts
        self.range_provider = range_provider
        self._observation_source = observation_source
        self._max_index_bytes = int(max_index_bytes)
        root_manifest = files.visible_file("pyproject.toml")
        self._python_import_roots = _python_source_roots_from_pyprojects(
            self.workspace, () if root_manifest is None else (root_manifest.path,)
        )

    @property
    def max_index_bytes(self) -> int:
        return self._max_index_bytes

    @property
    def python_import_roots(self) -> tuple[str, ...]:
        return self._python_import_roots

    def _reconcile_context_policy_for_query(self) -> None:
        """Converge a semantic live-policy change before query evidence returns."""
        if self.files.refresh_policy():
            self.sync()

    def _analysis_scope_conformance_payload(self) -> dict[str, object]:
        return {
            "schema": _ANALYSIS_SCOPE_CONFORMANCE_SCHEMA,
            "pruned_segments": sorted(repository_file_discovery._PRUNE_DIRS),
            "policy_fingerprint": self.files.policy_fingerprint(),
            "internal_state_path": self.files.internal_state_path or "",
        }

    def _analysis_scope_conformance(self) -> _AnalysisScopeConformance:
        """Bind the inputs that decide whether persisted repository rows are admissible."""
        payload = self._analysis_scope_conformance_payload()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return _AnalysisScopeConformance(
            payload=payload,
            encoded=encoded,
            identity="sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        )

    def _persisted_analysis_scope_requires_full_discovery(
        self,
        conformance: _AnalysisScopeConformance,
    ) -> bool:
        persisted = self.store.meta("analysis_scope_conformance_identity", "")
        if not persisted or persisted == conformance.identity:
            return False
        try:
            previous = json.loads(
                self.store.meta("analysis_scope_conformance_payload", "") or ""
            )
        except (TypeError, ValueError):
            return True
        current = dict(conformance.payload)
        if not isinstance(previous, dict):
            return True
        previous_encoded = json.dumps(
            previous, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if persisted != "sha256:" + hashlib.sha256(previous_encoded).hexdigest():
            return True
        previous_pruned = previous.pop("pruned_segments", None)
        current_pruned = cast("list[str]", current.pop("pruned_segments"))
        return not (
            previous == current
            and isinstance(previous_pruned, list)
            and all(isinstance(part, str) for part in previous_pruned)
            and set(previous_pruned).issubset(set(current_pruned))
        )

    def _workspace_fingerprint_from_store(self) -> str:
        fingerprint_blob = json.dumps(
            self.store.file_digests(), separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(
            b"hashmarks.codemap-workspace.v1\0" + fingerprint_blob
        ).hexdigest()

    def _reconcile_persisted_analysis_scope(
        self,
        conformance: _AnalysisScopeConformance,
    ) -> int:
        """Retire persisted rows admitted under an older analysis-scope contract.

        Reconciliation is paid only when the scope contract or repository context
        policy changes.  Stable queries reuse the persisted conformance identity
        and do not rescan the repository map.
        """
        if (
            self.store.meta("analysis_scope_conformance_identity", "")
            == conformance.identity
        ):
            return 0
        rejected = tuple(
            sorted(rel for rel in self.store.paths() if not self.files.is_admitted(rel))
        )
        rejected_rows = self.store.file_rows(rejected)
        for row in rejected_rows.values():
            self.artifacts.delete(str(row["artifact_key"]))
        removed = self.store.delete_paths(rejected) if rejected else 0
        if removed:
            self.store.bump_generation()
            self.store.set_meta(
                "workspace_fingerprint", self._workspace_fingerprint_from_store()
            )
        self.store.set_meta("analysis_scope_conformance_identity", conformance.identity)
        self.store.set_meta(
            "analysis_scope_conformance_payload",
            conformance.encoded,
        )
        return removed

    def _indexable_discovered_file(
        self,
        admitted: _AdmittedRepositoryFile,
        *,
        warnings: list[str] | None = None,
    ) -> _DiscoveredFile | None:
        language = _language_for_path(admitted.path)
        if language is None:
            return None
        try:
            size = int(admitted.path.stat().st_size)
        except OSError as exc:
            if warnings is not None:
                warnings.append(f"cannot stat {admitted.rel}: {exc}")
            return None
        if size > self.max_index_bytes:
            if warnings is not None:
                warnings.append(
                    f"skipped oversized source {admitted.rel} ({size} bytes)"
                )
            return None
        return _DiscoveredFile(
            admitted.rel,
            admitted.path,
            language,
            admitted.visibility,
            size,
        )

    def _discover(self) -> tuple[list[_DiscoveredFile], list[str]]:
        result: list[_DiscoveredFile] = []
        warnings: list[str] = []
        for admitted in self.files.iter_files():
            item = self._indexable_discovered_file(admitted, warnings=warnings)
            if item is not None:
                result.append(item)
        return result, warnings

    def _parse_or_reuse(
        self, rel: str, path: Path, language: str, digest_hash: str
    ) -> tuple[ParsedArtifact, bool]:
        key = artifact_key_for(
            digest_hash, language, range_provider=self.range_provider
        )
        cached = self.artifacts.get(key)
        if cached is not None:
            return cached, True
        raw, observed = self.file_store.read_bytes_stable(path)
        if observed.hash != digest_hash:
            key = artifact_key_for(
                observed.hash, language, range_provider=self.range_provider
            )
            cached = self.artifacts.get(key)
            if cached is not None:
                return cached, True
        artifact = parse_source(
            raw.decode("utf-8", errors="replace"),
            file_digest=observed.hash,
            language=language,
            range_provider=self.range_provider,
        )
        self.artifacts.put(artifact)
        return artifact, False

    def _discover_subtree(self, rel: str) -> list[_DiscoveredFile]:
        result: list[_DiscoveredFile] = []
        for admitted in self.files.iter_files(rel):
            item = self._indexable_discovered_file(admitted)
            if item is not None:
                result.append(item)
        return result

    @staticmethod
    def _index_surface_for_path(path: str) -> str:
        return index_surface_for_path(path)

    def _preflight_from_discovered(
        self, discovered: Sequence[_DiscoveredFile]
    ) -> dict[str, object]:
        language_files: dict[str, int] = {}
        language_bytes: dict[str, int] = {}
        surface_files: dict[str, int] = {}
        surface_bytes: dict[str, int] = {}
        source_bytes = 0
        measurable_files = 0
        for item in discovered:
            _rel, language, size = item.rel, item.language, item.size
            measurable_files += 1
            source_bytes += size
            language_files[language] = language_files.get(language, 0) + 1
            language_bytes[language] = language_bytes.get(language, 0) + size
            surface = self._index_surface_for_path(_rel)
            surface_files[surface] = surface_files.get(surface, 0) + 1
            surface_bytes[surface] = surface_bytes.get(surface, 0) + size
        count = len(discovered)
        if count <= 250 and source_bytes <= 8 * 1024 * 1024:
            work_class = "small"
        elif count <= 1000 and source_bytes <= 32 * 1024 * 1024:
            work_class = "medium"
        elif count <= 2500 and source_bytes <= 128 * 1024 * 1024:
            work_class = "large"
        else:
            work_class = "very-large"
        return {
            "schema": "hashmarks.codemap-index-preflight.v1",
            "indexable_files": count,
            "measured_files": measurable_files,
            "source_bytes": source_bytes,
            "languages": {
                language: {
                    "files": language_files[language],
                    "bytes": language_bytes.get(language, 0),
                }
                for language in sorted(language_files)
            },
            "surfaces": {
                surface: {
                    "files": surface_files[surface],
                    "bytes": surface_bytes.get(surface, 0),
                }
                for surface in sorted(surface_files)
            },
            "work_class": work_class,
            "work_class_basis": {
                "small": "<=250 files and <=8 MiB",
                "medium": "<=1000 files and <=32 MiB",
                "large": "<=2500 files and <=128 MiB",
                "very-large": "above the large threshold",
            },
            "estimated_lexical_rows": None,
            "estimated_lexical_rows_reason": "not guessed before parsing",
            "observation_coverage": self.files.discovery_coverage(count),
        }

    def preflight(self) -> dict[str, object]:
        """Cheap, read-only repository indexing cost evidence.

        This reports directly measurable repository shape.  It does not choose a
        deadline, retry, worker count, or execution policy.
        """
        discovered, warnings = self._discover()
        result = self._preflight_from_discovered(discovered)
        result["warnings"] = list(warnings)
        return result

    def _codemap_build_state(self) -> dict[str, object]:
        state = self.store.meta("sync.build_state") or "NEVER_SYNCED"
        return {
            "state": state,
            "complete": state == "COMPLETE",
            "build_id": self.store.meta("sync.build_id"),
            "started_unix": None
            if not self.store.meta("sync.started_unix")
            else float(self.store.meta("sync.started_unix") or 0),
            "completed_unix": None
            if not self.store.meta("sync.completed_unix")
            else float(self.store.meta("sync.completed_unix") or 0),
            "discovered": int(self.store.meta("sync.discovered", "0") or 0),
            "persisted_file_writes": int(
                self.store.meta("sync.persisted_file_writes", "0") or 0
            ),
        }

    def _workspace_map_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal"):
            path = Path(str(self.store.db_path) + suffix)
            with contextlib.suppress(OSError):
                total += int(path.stat().st_size)
        return total

    def _sync_remove_stale_paths(
        self,
        *,
        full: bool,
        present: set[str],
        discovered: Sequence[_DiscoveredFile],
        requested_paths: Sequence[str],
    ) -> int:
        """Remove rows no longer admitted by the current repository discovery."""
        if full:
            to_remove = self.store.paths() - present
            for rel in to_remove:
                if (self.workspace / rel).exists() and not self.files.decide(rel).index:
                    row = self.store.file_row(rel)
                    if row is not None:
                        self.artifacts.delete(str(row["artifact_key"]))
            return self.store.delete_paths(to_remove)
        discovered_paths = tuple(sorted({item.rel for item in discovered}))
        stale_rows: set[str] = set()
        for rel in _minimal_path_prefixes(requested_paths):
            current_under = _sorted_paths_under(discovered_paths, rel)
            stale_rows.update(self.store.paths_under(rel) - current_under)
        return self.store.delete_paths(stale_rows)

    def _sync_write_base_snapshot(
        self,
        *,
        full: bool,
        base_identity: str | None,
        overlay_paths: set[str] | None,
        skipped: int,
    ) -> None:
        """Persist reusable base evidence only for a complete clean-base sync."""
        if not (
            full
            and base_identity is not None
            and overlay_paths == set()
            and skipped == 0
        ):
            return
        snapshot_path = default_base_snapshot(self.workspace, base_identity)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        files_payload: dict[str, dict[str, str]] = {}
        for row in self.store.all_file_rows():
            current = self.store.file_row(str(row["path"]))
            if current is None:
                continue
            cur = current
            files_payload[str(row["path"])] = {
                "file_digest": str(cur["file_digest"]),
                "artifact_key": str(cur["artifact_key"]),
                "language": str(cur["language"]),
                "evidence_visibility": str(cur["evidence_visibility"]),
            }
        payload = {
            "schema": "hashmarks.codemap-base-snapshot.v1",
            "base_identity": base_identity,
            "files": files_payload,
        }
        temp = snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, snapshot_path)

    def _sync_economics(
        self,
        *,
        cache_state: str,
        elapsed: float,
        discovered_count: int,
        source_bytes: int,
        persisted_file_writes: int,
    ) -> dict[str, object]:
        """Describe measured indexing economics without choosing execution policy."""
        store_stats = self.store.economics_counts_by_surface()
        workspace_map_bytes = self._workspace_map_bytes()
        surface_economics = store_stats["surfaces"]
        return {
            "schema": "hashmarks.codemap-index-economics.v1",
            "cache_state": cache_state,
            "seconds": elapsed,
            "files_per_second": (discovered_count / elapsed) if elapsed > 0 else None,
            "source_bytes_per_second": (source_bytes / elapsed)
            if elapsed > 0
            else None,
            "source_bytes": source_bytes,
            "workspace_map_bytes": workspace_map_bytes,
            "workspace_map_to_source_ratio": (workspace_map_bytes / source_bytes)
            if source_bytes
            else None,
            "lexical_occurrences": store_stats["lexical_occurrences"],
            "files": store_stats["files"],
            "parse_errors": store_stats["parse_errors"],
            "persistence_batch_files": 32,
            "persisted_file_writes": persisted_file_writes,
            "surfaces": {
                key: surface_economics[key] for key in sorted(surface_economics)
            },
            "deadline_policy": None,
            "retry_policy": None,
        }

    def _sync_discovery(
        self,
        paths: Iterable[str | Path] | None,
        warnings: list[str],
    ) -> _SyncDiscovery:
        """Resolve the exact repository surface admitted to this indexing pass."""
        if paths is None:
            discovered, discovered_warnings = self._discover()
            warnings.extend(discovered_warnings)
            return _SyncDiscovery(discovered, True, ())
        requested_paths = tuple(
            normalize_relative_path(raw, allow_root=False) for raw in paths
        )
        discovered: list[_DiscoveredFile] = []
        seen: set[str] = set()
        for rel in requested_paths:
            for item in self._discover_subtree(rel):
                if item.rel in seen:
                    continue
                discovered.append(item)
                seen.add(item.rel)
        return _SyncDiscovery(discovered, False, requested_paths)

    def _sync_begin_build(
        self,
        *,
        discovered: Sequence[_DiscoveredFile],
        full: bool,
        requested_paths: Sequence[str],
        preflight: dict[str, object],
    ) -> str:
        """Publish build-in-progress evidence before repository rows can change."""
        has_existing_files = self.store.has_files()
        cache_state = (
            "incremental" if not full else ("warm" if has_existing_files else "cold")
        )
        build_started_unix = time.time()
        build_id = hashlib.sha256(
            f"{build_started_unix:.9f}:{self.store.generation()}:{len(discovered)}".encode()
        ).hexdigest()[:24]
        self.store.set_meta_many(
            {
                "sync.build_state": "BUILDING",
                "sync.build_id": build_id,
                "sync.started_unix": str(build_started_unix),
                "sync.completed_unix": "",
                "sync.discovered": str(len(discovered)),
                "sync.persisted_file_writes": "0",
                "sync.preflight": json.dumps(
                    preflight, sort_keys=True, separators=(",", ":")
                ),
                "sync.cache_state": cache_state,
            }
        )
        recent = [] if full else list(requested_paths)[:1000]
        self.store.set_meta(
            "recent_changed_paths", json.dumps(recent, separators=(",", ":"))
        )
        return cache_state

    def _sync_base_snapshot(self, *, full: bool) -> _SyncBaseSnapshot:
        """Load reusable clean-base evidence without changing repository state."""
        base_identity = git_base_identity(self.workspace) if full else None
        overlay_paths = (
            git_overlay_paths(self.workspace, state_rel=self.files.internal_state_path)
            if full and base_identity is not None
            else None
        )
        if not (full and base_identity is not None and overlay_paths is not None):
            return _SyncBaseSnapshot(base_identity, overlay_paths, None)
        snapshot_path = default_base_snapshot(self.workspace, base_identity)
        try:
            candidate = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return _SyncBaseSnapshot(base_identity, overlay_paths, None)
        if not isinstance(candidate, dict):
            return _SyncBaseSnapshot(base_identity, overlay_paths, None)
        if candidate.get("schema") != "hashmarks.codemap-base-snapshot.v1":
            return _SyncBaseSnapshot(base_identity, overlay_paths, None)
        if candidate.get("base_identity") != base_identity:
            return _SyncBaseSnapshot(base_identity, overlay_paths, None)
        return _SyncBaseSnapshot(base_identity, overlay_paths, candidate)

    def _sync_base_artifact(
        self,
        item: _DiscoveredFile,
        *,
        overlay_paths: set[str] | None,
        base_snapshot_payload: dict[str, object] | None,
    ) -> ParsedArtifact | None:
        """Qualify one Git-nominated snapshot artifact against current bytes."""
        if (
            base_snapshot_payload is None
            or overlay_paths is None
            or item.rel in overlay_paths
        ):
            return None
        entries = base_snapshot_payload.get("files")
        entry = entries.get(item.rel) if isinstance(entries, dict) else None
        if not isinstance(entry, dict):
            return None
        snap_digest = entry.get("file_digest")
        snap_artifact_key = entry.get("artifact_key")
        if not isinstance(snap_digest, str) or not isinstance(snap_artifact_key, str):
            return None
        try:
            current_digest = self.file_store.digest(
                item.path,
                workspace=self.workspace,
                relative_path=item.rel,
            )
        except (OSError, UnstableFileError):
            return None
        expected_artifact = artifact_key_for(
            current_digest.hash, item.language, range_provider=self.range_provider
        )
        if current_digest.hash != snap_digest or snap_artifact_key != expected_artifact:
            return None
        artifact = self.artifacts.get(expected_artifact)
        return (
            artifact
            if artifact is not None
            and artifact.file_digest == snap_digest
            and entry.get("language") == item.language
            and entry.get("evidence_visibility") == item.visibility.value
            else None
        )

    def _sync_base_entry(
        self,
        item: _DiscoveredFile,
        *,
        overlay_paths: set[str] | None,
        base_snapshot_payload: dict[str, object] | None,
        state: _SyncIndexState,
        module_name: str,
    ) -> bool:
        """Reuse a base artifact only when every current semantic authority matches."""
        artifact = self._sync_base_artifact(
            item,
            overlay_paths=overlay_paths,
            base_snapshot_payload=base_snapshot_payload,
        )
        if artifact is None:
            return False
        rel = item.rel
        row = self.store.file_row(rel)
        if row is not None and self._sync_file_reusable(
            self._sync_reuse_state(rel, row),
            digest_hash=artifact.file_digest,
            expected_artifact=artifact.artifact_key,
            visibility=item.visibility,
            module_name=module_name,
        ):
            state.indexed += 1
            state.reused += 1
            state.base_snapshot_reused += 1
            return True
        derived_update = self.store.set_file(
            rel,
            artifact,
            module_name=module_name,
            visibility=item.visibility,
            index_surface=self._index_surface_for_path(rel),
        )
        state.persisted_file_writes += 1
        state.derived_changed += len(derived_update["changed_kinds"])
        state.derived_preserved += len(derived_update["preserved_kinds"])
        state.semantic_shields += len(derived_update["shielded_kinds"])
        state.indexed += 1
        state.reused += 1
        state.base_snapshot_reused += 1
        state.changed = True
        return True

    def _sync_file_digest(
        self,
        *,
        item: _DiscoveredFile,
        warnings: list[str],
        state: _SyncIndexState,
        digest: Digest | None = None,
    ) -> Digest | None:
        if digest is not None:
            return digest
        try:
            return self.file_store.digest(
                item.path,
                workspace=self.workspace,
                relative_path=item.rel,
            )
        except (OSError, UnstableFileError) as exc:
            warnings.append(f"cannot index {item.rel}: {exc}")
            state.skipped += 1
            return None

    def _sync_reuse_state(
        self, rel: str, row: sqlite3.Row | tuple[str, str, str, str, bool] | None
    ) -> _FileReuseState:
        if isinstance(row, tuple):
            digest, artifact, visibility, module, has_derived = row
            return _FileReuseState(
                str(digest) if digest is not None else None,
                str(artifact) if artifact is not None else None,
                str(visibility) if visibility is not None else None,
                str(module) if module is not None else None,
                bool(has_derived),
            )
        if row is None:
            return _FileReuseState(None, None, None, None, False)
        return _FileReuseState(
            str(row["file_digest"]),
            str(row["artifact_key"]),
            str(row["evidence_visibility"]),
            str(row["module_name"] or ""),
            self.store.has_derived_nodes(rel),
        )

    @staticmethod
    def _sync_file_reusable(
        reuse: _FileReuseState,
        *,
        digest_hash: str,
        expected_artifact: str,
        visibility: EvidenceVisibility,
        module_name: str,
    ) -> bool:
        return (
            reuse.digest == digest_hash
            and reuse.artifact == expected_artifact
            and reuse.visibility == visibility.value
            and reuse.module == module_name
            and reuse.has_derived
        )

    @staticmethod
    def _record_persisted_artifact(
        state: _SyncIndexState,
        derived_update: dict[str, tuple[str, ...]],
        *,
        was_reused: bool,
        parse_error: bool,
    ) -> None:
        state.persisted_file_writes += 1
        state.derived_changed += len(derived_update["changed_kinds"])
        state.derived_preserved += len(derived_update["preserved_kinds"])
        state.semantic_shields += len(derived_update["shielded_kinds"])
        state.indexed += 1
        state.reused += int(was_reused)
        state.parsed += int(not was_reused)
        state.parse_errors += int(parse_error)
        state.changed = True

    def _sync_index_file(
        self,
        *,
        item: _DiscoveredFile,
        warnings: list[str],
        state: _SyncIndexState,
        digest: Digest | None = None,
        row: sqlite3.Row | tuple[str, str, str, str, bool] | None = None,
        module_name: str,
    ) -> None:
        """Reuse or parse one already-discovered repository file and persist its evidence."""
        digest = self._sync_file_digest(
            item=item,
            warnings=warnings,
            state=state,
            digest=digest,
        )
        if digest is None:
            return
        row = self.store.file_row(item.rel) if row is None else row
        expected_artifact = artifact_key_for(
            digest.hash,
            item.language,
            range_provider=self.range_provider,
        )
        if row is not None and self._sync_file_reusable(
            self._sync_reuse_state(item.rel, row),
            digest_hash=digest.hash,
            expected_artifact=expected_artifact,
            visibility=item.visibility,
            module_name=module_name,
        ):
            state.indexed += 1
            state.reused += 1
            return
        try:
            artifact, was_reused = self._parse_or_reuse(
                item.rel,
                item.path,
                item.language,
                digest.hash,
            )
        except (OSError, UnstableFileError) as exc:
            warnings.append(f"cannot read {item.rel}: {exc}")
            state.skipped += 1
            return
        derived_update = self.store.set_file(
            item.rel,
            artifact,
            module_name=module_name,
            visibility=item.visibility,
            index_surface=self._index_surface_for_path(item.rel),
        )
        self._record_persisted_artifact(
            state,
            derived_update,
            was_reused=was_reused,
            parse_error=artifact.parse_error is not None,
        )

    def _sync_index_discovered(
        self,
        *,
        discovered: Sequence[_DiscoveredFile],
        overlay_paths: set[str] | None,
        base_snapshot_payload: dict[str, object] | None,
        warnings: list[str],
    ) -> _SyncIndexState:
        """Persist repository evidence for the discovered surface in bounded batches."""
        state = _SyncIndexState()

        def publish_persisted(committed: int) -> None:
            self.store.set_meta_many(
                {
                    "sync.persisted_file_writes": str(committed),
                    "sync.progress_unix": str(time.time()),
                }
            )

        candidates: list[tuple[_DiscoveredFile, str]] = []
        for item in discovered:
            state.present.add(item.rel)
            module_name = _module_name(item.rel, self._python_import_roots) or ""
            if self._sync_base_entry(
                item,
                overlay_paths=overlay_paths,
                base_snapshot_payload=base_snapshot_payload,
                state=state,
                module_name=module_name,
            ):
                continue
            candidates.append((item, module_name))

        # Persistent digest metadata is itself a repository-wide cache.  Load it in
        # bounded SQLite batches rather than issuing one lookup per file on warm
        # reconciliation.  A problematic batch falls back to the established
        # per-file path so one unstable/unreadable file cannot poison its peers.
        digests: dict[str, Digest] = {}
        digest_batch_size = 500
        for start in range(0, len(candidates), digest_batch_size):
            batch = candidates[start : start + digest_batch_size]
            try:
                info = self.file_store.digest_many_info(
                    ((item.path, item.rel) for item, _module in batch),
                    workspace=self.workspace,
                )
            except (OSError, UnstableFileError):
                continue
            for rel, (digest, _executable) in info.items():
                digests[rel] = digest

        candidate_paths = [item.rel for item, _module in candidates]
        reuse_rows = self.store.file_reuse_rows(candidate_paths)
        with self.store.bulk_file_writes(batch_size=32, on_commit=publish_persisted):
            for item, module_name in candidates:
                self._sync_index_file(
                    item=item,
                    warnings=warnings,
                    state=state,
                    digest=digests.get(item.rel),
                    row=reuse_rows.get(item.rel),
                    module_name=module_name,
                )
        return state

    def _sync_finalize_identity(
        self,
        *,
        changed: bool,
        identity_generation_before: int | None,
        warnings: list[str],
    ) -> _SyncIdentity:
        """Seal workspace and observation identities after repository rows are stable."""
        fingerprint = self._workspace_fingerprint_from_store()
        if self.store.meta("workspace_fingerprint") != fingerprint:
            changed = True
        generation = (
            self.store.bump_generation() if changed else self.store.generation()
        )
        observation_after = self._observation_source.observe()
        identity_generation_after = (
            None if observation_after is None else observation_after.generation
        )
        identity_generation = (
            identity_generation_before
            if identity_generation_before is not None
            and identity_generation_before == identity_generation_after
            else None
        )
        if (
            identity_generation_before is not None
            and identity_generation_after is not None
            and identity_generation_before != identity_generation_after
        ):
            warnings.append(
                "identity observation generation changed during CodeMap sync; freshness remains unproven"
            )
        self.store.set_meta("workspace_fingerprint", fingerprint)
        self.store.set_meta(
            "identity_generation",
            "" if identity_generation is None else str(identity_generation),
        )
        self.store.set_meta("last_sync_unix", str(time.time()))
        self.store.set_meta("artifact_db", str(self.artifacts.db_path))
        return _SyncIdentity(generation, fingerprint, identity_generation)

    def _sync_refresh_python_import_roots(
        self,
        discovered: Sequence[_DiscoveredFile],
        *,
        full: bool,
        requested_paths: Sequence[str],
    ) -> None:
        """Refresh packaging-derived import roots from admitted visible manifests."""
        if full:
            pyprojects = tuple(
                item.path
                for item in discovered
                if item.rel.endswith("pyproject.toml")
                and item.visibility is not EvidenceVisibility.DENY
            )
        elif any(rel.endswith("pyproject.toml") for rel in requested_paths):
            pyprojects = self.files.visible_manifests("pyproject.toml")
        else:
            return
        self._python_import_roots = _python_source_roots_from_pyprojects(
            self.workspace, pyprojects
        )

    def _extend_discovered_from_roots(
        self,
        discovered: list[_DiscoveredFile],
        *,
        roots: Sequence[str],
        seen: set[str],
    ) -> None:
        for root in sorted(roots):
            for item in self._discover_subtree(root):
                if item.rel in seen:
                    continue
                discovered.append(item)
                seen.add(item.rel)

    def _python_reprojection_paths(
        self,
        previous_roots: set[str],
        current_roots: set[str],
    ) -> set[str]:
        affected: set[str] = set()
        for root in sorted(previous_roots ^ current_roots):
            affected.update(self.store.paths_under(root))
        return affected

    def _sync_refresh_python_projection(
        self,
        discovered: list[_DiscoveredFile],
        *,
        full: bool,
        requested_paths: Sequence[str],
    ) -> int:
        """Re-index persisted Python files whose import identity changed with packaging authority."""
        previous_roots = self._python_import_roots
        self._sync_refresh_python_import_roots(
            discovered, full=full, requested_paths=requested_paths
        )
        if full or tuple(previous_roots) == tuple(self._python_import_roots):
            return 0
        seen = {item.rel for item in discovered}
        previous = set(previous_roots)
        current = set(self._python_import_roots)

        self._extend_discovered_from_roots(
            discovered,
            roots=tuple(current - previous),
            seen=seen,
        )
        affected_rows = self.store.file_rows(
            self._python_reprojection_paths(previous, current)
        )
        stale_missing: set[str] = set()
        for rel, row in affected_rows.items():
            if not rel.endswith((".py", ".pyi")):
                continue
            if row.get("module_name") == _module_name(rel, self._python_import_roots):
                continue
            if not (self.workspace / rel).exists():
                stale_missing.add(rel)
                continue
            self._extend_discovered_from_roots(
                discovered,
                roots=(rel,),
                seen=seen,
            )
        return self.store.delete_paths(stale_missing) if stale_missing else 0

    def sync(self, paths: Iterable[str | Path] | None = None) -> SyncResult:
        # A semantic policy change changes both negative and positive admission.
        # Discover without a path bound so newly denied rows retire and
        # newly admitted paths are discovered from the same authority cut.
        if self.files.refresh_policy():
            paths = None
        conformance = self._analysis_scope_conformance()
        if paths is not None and self._persisted_analysis_scope_requires_full_discovery(
            conformance
        ):
            paths = None
        started = time.perf_counter()
        warnings: list[str] = []
        # One BEGIN IMMEDIATE owns both cross-process writer admission and the
        # publication boundary. WAL readers continue to see the previously
        # complete generation until rows + generation + COMPLETE commit together.
        with self.store.publication_transaction():
            removed = self._reconcile_persisted_analysis_scope(conformance)
            identity_generation_before = getattr(
                self._observation_source.observe(), "generation", None
            )
            discovery = self._sync_discovery(paths, warnings)
            removed += self._sync_refresh_python_projection(
                discovery.files,
                full=discovery.full,
                requested_paths=discovery.requested_paths,
            )
            preflight = self._preflight_from_discovered(discovery.files)
            cache_state = self._sync_begin_build(
                discovered=discovery.files,
                full=discovery.full,
                requested_paths=discovery.requested_paths,
                preflight=preflight,
            )
            base = self._sync_base_snapshot(full=discovery.full)
            state = self._sync_index_discovered(
                discovered=discovery.files,
                overlay_paths=base.overlay_paths,
                base_snapshot_payload=base.payload,
                warnings=warnings,
            )
            removed += self._sync_remove_stale_paths(
                full=discovery.full,
                present=state.present,
                discovered=discovery.files,
                requested_paths=discovery.requested_paths,
            )
            identity = self._sync_finalize_identity(
                changed=state.changed or bool(removed),
                identity_generation_before=identity_generation_before,
                warnings=warnings,
            )
            self._sync_write_base_snapshot(
                full=discovery.full,
                base_identity=base.identity,
                overlay_paths=base.overlay_paths,
                skipped=state.skipped,
            )
            elapsed = time.perf_counter() - started
            economics = self._sync_economics(
                cache_state=cache_state,
                elapsed=elapsed,
                discovered_count=len(discovery.files),
                source_bytes=int(cast("int", preflight.get("source_bytes") or 0)),
                persisted_file_writes=state.persisted_file_writes,
            )
            self.store.set_meta_many(
                {
                    "sync.build_state": "COMPLETE",
                    "sync.completed_unix": str(time.time()),
                    "sync.persisted_file_writes": str(state.persisted_file_writes),
                    "sync.economics": json.dumps(
                        economics, sort_keys=True, separators=(",", ":")
                    ),
                }
            )
            return SyncResult(
                generation=identity.generation,
                discovered=len(discovery.files),
                indexed=state.indexed,
                reused_artifacts=state.reused,
                parsed_artifacts=state.parsed,
                removed=removed,
                skipped=state.skipped,
                parse_errors=state.parse_errors,
                seconds=elapsed,
                workspace_fingerprint=identity.fingerprint,
                identity_generation=identity.identity_generation,
                derived_surfaces_changed=state.derived_changed,
                derived_surfaces_preserved=state.derived_preserved,
                semantic_invalidation_shields=state.semantic_shields,
                base_snapshot_reused=state.base_snapshot_reused,
                base_identity=base.identity,
                overlay_paths=(
                    0 if base.overlay_paths is None else len(base.overlay_paths)
                ),
                warnings=tuple(warnings),
                preflight=preflight,
                economics=economics,
                build_state="COMPLETE",
            )

    def clean(self, *, shared_artifacts: bool = False) -> dict[str, object]:
        workspace_before = self.store.clear()
        artifacts_removed = self.artifacts.clear() if shared_artifacts else 0
        return {
            "schema": "hashmarks.codemap-clean.v1",
            "workspace": str(self.workspace),
            "workspace_rows": workspace_before,
            "shared_artifacts_removed": artifacts_removed,
            "shared_artifact_db": str(self.artifacts.db_path),
        }

    def watch_continuity(self) -> WatchContinuityRecord | None:
        return WatchContinuityRecord.from_json(
            self.store.meta(WATCH_CONTINUITY_META, "") or ""
        )

    def is_current(self, relpath: str) -> bool:
        """Return whether durable file evidence still matches current workspace bytes."""
        rel = normalize_relative_path(relpath, allow_root=False)
        row = self.store.file_row(rel)
        path = self.workspace / rel
        if row is None or path.is_symlink() or not path.is_file():
            return False
        try:
            actual = self.file_store.digest(
                path, workspace=self.workspace, relative_path=rel, force=True
            ).hash
        except OSError:
            return False
        return actual == str(row["file_digest"] or "")

    def _path_unavailable(self, rel: str, path: Path) -> bool:
        return (
            not self.files.is_admitted(rel) or path.is_symlink() or not path.is_file()
        )

    def needs_reconcile(self, relpath: str) -> bool:
        rel = normalize_relative_path(relpath, allow_root=False)
        row = self.store.file_row(rel)
        path = self.workspace / rel
        if self._path_unavailable(rel, path):
            return row is not None
        language = _language_for_path(path)
        if language is None:
            return False
        decision = self.files.decide(rel)
        digest = self.file_store.digest(
            path,
            workspace=self.workspace,
            relative_path=rel,
        )
        expected_artifact = artifact_key_for(
            digest.hash,
            language,
            range_provider=self.range_provider,
        )
        module_name = _module_name(rel, self._python_import_roots) or ""
        return not (
            row is not None
            and self._sync_file_reusable(
                self._sync_reuse_state(rel, row),
                digest_hash=digest.hash,
                expected_artifact=expected_artifact,
                visibility=decision.evidence_visibility,
                module_name=module_name,
            )
        )

    def reconcile_path(self, relpath: str) -> None:
        rel = normalize_relative_path(relpath, allow_root=False)
        with self.store.publication_transaction():
            if not self.needs_reconcile(rel):
                return
            row = self.store.file_row(rel)
            path = self.workspace / rel
            if self._path_unavailable(rel, path):
                if row is None:
                    return
                self.store.delete_paths((rel,))
            else:
                language = _language_for_path(path)
                if language is None:
                    return
                decision = self.files.decide(rel)
                digest = self.file_store.digest(
                    path,
                    workspace=self.workspace,
                    relative_path=rel,
                )
                artifact, _ = self._parse_or_reuse(rel, path, language, digest.hash)
                self.store.set_file(
                    rel,
                    artifact,
                    module_name=_module_name(rel, self._python_import_roots),
                    visibility=decision.evidence_visibility,
                    index_surface=self._index_surface_for_path(rel),
                )
            self.store.bump_generation()
            self.store.set_meta(
                "workspace_fingerprint", self._workspace_fingerprint_from_store()
            )

    def ensure_ready(
        self, *, _allow_incomplete: bool = False
    ) -> RepositoryObservation | None:
        # A durable BUILDING marker means a prior sync did not finish. Query
        # paths must not silently turn that incomplete generation into fresh
        # authority by auto-rebuilding it; the caller/execution layer decides
        # when another sync attempt is appropriate.
        if self.store.meta("sync.build_state") == "BUILDING":
            if _allow_incomplete:
                return None
            raise RuntimeError(
                "CodeMap generation is incomplete (BUILDING); run sync() before querying repository intelligence"
            )
        # Context policy is live repository admission authority, not a
        # construction-time snapshot. Stable policy checks are one exact-file
        # read; semantic changes reconcile once before persisted evidence returns.
        self._reconcile_context_policy_for_query()
        conformance = self._analysis_scope_conformance()
        if (
            self.store.meta("analysis_scope_conformance_identity", "")
            != conformance.identity
        ):
            self.sync()
            return self._observation_source.observe()
        self._reconcile_persisted_analysis_scope(conformance)
        if not self.store.has_files():
            self.sync()
            return self._observation_source.observe()
        synced_raw = self.store.meta("identity_generation", "") or ""
        observation = self._observation_source.observe()
        self._reconcile_daemon_generation(observation, synced_raw)
        return observation

    def _reconcile_daemon_generation(
        self, observation: RepositoryObservation | None, synced_raw: str
    ) -> None:
        if observation is not None and not synced_raw:
            # A daemon/barrier is now available but this map was built without
            # generation-bound freshness evidence. Reconcile in the evidence lane.
            self.sync()
            return
        if observation is None or not synced_raw:
            return
        synced = int(synced_raw)
        if observation.generation == synced:
            return
        if observation.can_incrementally_reconcile:
            self.sync(observation.dirty_paths)
            return
        self.sync()
