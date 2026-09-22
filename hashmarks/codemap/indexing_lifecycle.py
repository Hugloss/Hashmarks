from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import json
import os
import time
import tomllib
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast

from hashmarks.file_store import UnstableFileError
from hashmarks.paths import normalize_relative_path

from .index_surfaces import index_surface_for_path
from .model import EvidenceVisibility, SyncResult
from .parsers import artifact_key_for, parse_source
from .policy import ContextPolicy
from .source_languages import SOURCE_LANGUAGES
from .repository_index_store import (
    default_base_snapshot,
    git_base_identity,
    git_overlay_paths,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from hashmarks.client import RepositoryObservation

    from .engine import CodeMap

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
_PRUNE_DIRS = {
    ".git",
    ".hashmarks",
    ".fastidentity",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    "target",
    ".tox",
    ".nox",
    "coverage",
    ".coverage",
}
_ANALYSIS_SCOPE_CONFORMANCE_SCHEMA = "hashmarks.analysis-scope-conformance.v1"


def _is_pruned_relative_path(rel: str) -> bool:
    """Return whether repository discovery must stop at any path segment."""
    normalized = rel.replace("\\", "/").strip("/")
    if not normalized:
        return False
    return any(part in _PRUNE_DIRS for part in PurePosixPath(normalized).parts)


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


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _uv_workspace_pyprojects(
    workspace: Path, pyprojects: Sequence[Path]
) -> tuple[Path, ...]:
    """Restrict nested project metadata to declared uv workspace members when configured."""
    root_manifest = workspace / "pyproject.toml"
    try:
        data = tomllib.loads(root_manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return tuple(pyprojects)
    tool = data.get("tool") if isinstance(data, dict) else None
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

    def selected(pyproject: Path) -> bool:
        if pyproject == root_manifest:
            return True
        try:
            project = pyproject.parent.relative_to(workspace).as_posix()
        except ValueError:
            return False
        if not any(
            fnmatch.fnmatchcase(project, pattern) for pattern in member_patterns
        ):
            return False
        return not any(
            fnmatch.fnmatchcase(project, pattern) for pattern in exclude_patterns
        )

    return tuple(pyproject for pyproject in pyprojects if selected(pyproject))


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


def _python_source_roots(workspace: Path) -> tuple[str, ...]:
    """Return explicitly configured Python import roots from root project metadata."""
    return _python_source_roots_from_pyprojects(
        workspace, (workspace / "pyproject.toml",)
    )


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


class IndexingLifecycleMixin:
    def _refresh_context_policy(self) -> bool:
        """Reload the repository context policy and report semantic change.

        Policy is repository authority, not ordinary indexed content. Query/sync
        boundaries therefore re-read this one exact authority file rather than
        trusting a process-lifetime snapshot. The semantic fingerprint avoids
        generation churn for byte-only rewrites that preserve the same rules.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        current = ContextPolicy.load(self.workspace, self._policy_config_path)
        if current.fingerprint() == self.policy.fingerprint():
            return False
        self.policy = current
        return True

    def _reconcile_context_policy_for_query(self) -> None:
        """Converge a semantic live-policy change before query evidence returns."""
        if self._refresh_context_policy():
            self.sync()

    def _path_admitted_for_analysis(self, rel: str) -> bool:
        """Return whether an explicit repository path may feed analysis surfaces."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return (
            not self._internal_path(rel)
            and not _is_pruned_relative_path(rel)
            and self.policy.decide(rel).index
        )

    def _analysis_scope_conformance_identity(self) -> str:
        """Bind the inputs that decide whether persisted repository rows are admissible."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        payload = {
            "schema": _ANALYSIS_SCOPE_CONFORMANCE_SCHEMA,
            "pruned_segments": sorted(_PRUNE_DIRS),
            "policy_fingerprint": self.policy.fingerprint(),
            "internal_state_path": self._state_rel or "",
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def _workspace_fingerprint_from_store(self) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        fingerprint_blob = json.dumps(
            self.store.file_digests(), separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(
            b"hashmarks.codemap-workspace.v1\0" + fingerprint_blob
        ).hexdigest()

    def _reconcile_persisted_analysis_scope(self) -> int:
        """Retire persisted rows admitted under an older analysis-scope contract.

        Reconciliation is paid only when the scope contract or repository context
        policy changes.  Stable queries reuse the persisted conformance identity
        and do not rescan the repository map.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        identity = self._analysis_scope_conformance_identity()
        if self.store.meta("analysis_scope_conformance_identity", "") == identity:
            return 0
        rejected = tuple(
            sorted(
                rel
                for rel in self.store.paths()
                if not self._path_admitted_for_analysis(rel)
            )
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
        self.store.set_meta("analysis_scope_conformance_identity", identity)
        return removed

    def _workspace_relative_path(self, path: Path) -> str | None:
        try:
            value = path.relative_to(self.workspace).as_posix()
        except ValueError:
            return None
        return "" if value == "." else value

    def _prune_discovery_dirs(self, root_path: Path, dirs: list[str]) -> None:
        root_rel = self._workspace_relative_path(root_path) or ""
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in _PRUNE_DIRS
            and not self._internal_path(f"{root_rel}/{name}".strip("/"))
        )

    def _discovered_file(
        self,
        path: Path,
        *,
        warnings: list[str] | None = None,
    ) -> _DiscoveredFile | None:
        if path.is_symlink():
            return None
        rel = self._workspace_relative_path(path)
        if rel is None:
            return None
        decision = self.policy.decide(rel)
        language = _language_for_path(path)
        if not decision.index or language is None:
            return None
        try:
            size = int(path.stat().st_size)
        except OSError as exc:
            if warnings is not None:
                warnings.append(f"cannot stat {rel}: {exc}")
            return None
        if size > self.max_index_bytes:
            if warnings is not None:
                warnings.append(f"skipped oversized source {rel} ({size} bytes)")
            return None
        return _DiscoveredFile(
            rel,
            path,
            language,
            decision.evidence_visibility,
            size,
        )

    def _discover(self) -> tuple[list[_DiscoveredFile], list[str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        result: list[_DiscoveredFile] = []
        warnings: list[str] = []
        for root, dirs, files in os.walk(
            self.workspace, topdown=True, followlinks=False
        ):
            root_path = Path(root)
            self._prune_discovery_dirs(root_path, dirs)
            for name in sorted(files):
                item = self._discovered_file(root_path / name, warnings=warnings)
                if item is not None:
                    result.append(item)
        return result, warnings

    def _parse_or_reuse(self, rel: str, path: Path, language: str, digest_hash: str):
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        key = artifact_key_for(
            digest_hash, language, range_provider=self.range_provider
        )
        cached = self.artifacts.get(key)
        if cached is not None:
            return cached, True
        source = path.read_text(encoding="utf-8", errors="replace")
        artifact = parse_source(
            source,
            file_digest=digest_hash,
            language=language,
            range_provider=self.range_provider,
        )
        self.artifacts.put(artifact)
        return artifact, False

    def _discover_subtree(self, rel: str) -> list[_DiscoveredFile]:
        self = cast("CodeMap", self)
        if not self._path_admitted_for_analysis(rel):
            return []
        path = self.workspace / rel
        if path.is_symlink():
            return []
        if path.is_file():
            item = self._discovered_file(path)
            return [] if item is None else [item]
        if not path.is_dir():
            return []

        result: list[_DiscoveredFile] = []
        for root, dirs, files in os.walk(path, topdown=True, followlinks=False):
            root_path = Path(root)
            self._prune_discovery_dirs(root_path, dirs)
            for name in sorted(files):
                item = self._discovered_file(root_path / name)
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
        }

    def index_preflight(self) -> dict[str, object]:
        """Cheap, read-only repository indexing cost evidence.

        This reports directly measurable repository shape.  It does not choose a
        deadline, retry, worker count, or execution policy.
        """
        discovered, warnings = self._discover()
        result = self._preflight_from_discovered(discovered)
        result["warnings"] = list(warnings)
        return result

    def _codemap_build_state(self) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if full:
            to_remove = self.store.paths() - present
            for rel in to_remove:
                if (self.workspace / rel).exists() and not self.policy.decide(
                    rel
                ).index:
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
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
            files_payload[str(row["path"])] = {
                "file_digest": str(current["file_digest"]),
                "artifact_key": str(current["artifact_key"]),
                "language": str(current["language"]),
                "evidence_visibility": str(current["evidence_visibility"]),
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
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        base_identity = git_base_identity(self.workspace) if full else None
        overlay_paths = (
            git_overlay_paths(self.workspace)
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

    def _sync_base_entry(
        self,
        *,
        rel: str,
        language: str,
        visibility: EvidenceVisibility,
        overlay_paths: set[str] | None,
        base_snapshot_payload: dict[str, object] | None,
        state: _SyncIndexState,
    ) -> bool:
        """Reuse one qualified base-snapshot artifact when its evidence still matches."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if (
            base_snapshot_payload is None
            or overlay_paths is None
            or rel in overlay_paths
        ):
            return False
        entries = base_snapshot_payload.get("files")
        entry = entries.get(rel) if isinstance(entries, dict) else None
        if not isinstance(entry, dict):
            return False
        snap_digest = entry.get("file_digest")
        snap_artifact_key = entry.get("artifact_key")
        artifact = (
            self.artifacts.get(str(snap_artifact_key))
            if isinstance(snap_artifact_key, str)
            else None
        )
        if not (
            isinstance(snap_digest, str)
            and artifact is not None
            and artifact.file_digest == snap_digest
            and entry.get("language") == language
            and entry.get("evidence_visibility") == visibility.value
        ):
            return False
        row = self.store.file_row(rel)
        expected_artifact = str(snap_artifact_key)
        if (
            row is not None
            and str(row["file_digest"]) == snap_digest
            and str(row["artifact_key"]) == expected_artifact
            and str(row["evidence_visibility"]) == visibility.value
            and self.store.has_derived_nodes(rel)
        ):
            state.indexed += 1
            state.reused += 1
            state.base_snapshot_reused += 1
            return True
        derived_update = self.store.set_file(
            rel,
            artifact,
            module_name=_module_name(rel, getattr(self, "_python_import_roots", ())),
            visibility=visibility,
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
        item: _DiscoveredFile,
        *,
        warnings: list[str],
        state: _SyncIndexState,
        digest=None,
    ):
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

    def _sync_reuse_state(self, rel: str, row) -> _FileReuseState:
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
        derived_update: dict[str, object],
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
        digest=None,
        row=None,
    ) -> None:
        """Reuse or parse one already-discovered repository file and persist its evidence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        digest = self._sync_file_digest(
            item,
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
        module_name = (
            _module_name(item.rel, getattr(self, "_python_import_roots", ())) or ""
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
        except OSError as exc:
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
        self = cast("CodeMap", self)
        state = _SyncIndexState()

        def publish_persisted(committed: int) -> None:
            self.store.set_meta_many(
                {
                    "sync.persisted_file_writes": str(committed),
                    "sync.progress_unix": str(time.time()),
                }
            )

        candidates: list[_DiscoveredFile] = []
        for item in discovered:
            rel, path, language, visibility = (
                item.rel,
                item.path,
                item.language,
                item.visibility,
            )
            state.present.add(rel)
            if self._sync_base_entry(
                rel=rel,
                language=language,
                visibility=visibility,
                overlay_paths=overlay_paths,
                base_snapshot_payload=base_snapshot_payload,
                state=state,
            ):
                continue
            candidates.append(item)

        # Persistent digest metadata is itself a repository-wide cache.  Load it in
        # bounded SQLite batches rather than issuing one lookup per file on warm
        # reconciliation.  A problematic batch falls back to the established
        # per-file path so one unstable/unreadable file cannot poison its peers.
        digests: dict[str, object] = {}
        digest_batch_size = 500
        for start in range(0, len(candidates), digest_batch_size):
            batch = candidates[start : start + digest_batch_size]
            try:
                info = self.file_store.digest_many_info(
                    ((item.path, item.rel) for item in batch),
                    workspace=self.workspace,
                )
            except (OSError, UnstableFileError):
                continue
            for rel, (digest, _executable) in info.items():
                digests[rel] = digest

        candidate_paths = [item.rel for item in candidates]
        reuse_rows = self.store.file_reuse_rows(candidate_paths)
        with self.store.bulk_file_writes(batch_size=32, on_commit=publish_persisted):
            for item in candidates:
                rel, path, language, visibility = (
                    item.rel,
                    item.path,
                    item.language,
                    item.visibility,
                )
                self._sync_index_file(
                    item=item,
                    warnings=warnings,
                    state=state,
                    digest=digests.get(rel),
                    row=reuse_rows.get(rel),
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
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        fingerprint = self._workspace_fingerprint_from_store()
        if self.store.meta("workspace_fingerprint") != fingerprint:
            changed = True
        generation = (
            self.store.bump_generation() if changed else self.store.generation()
        )
        observation_after = self._daemon_observation()
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
        """Refresh packaging-derived import roots without a second full repository walk."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if full:
            pyprojects = tuple(
                item.path for item in discovered if item.rel.endswith("pyproject.toml")
            )
            self._python_import_roots = _python_source_roots_from_pyprojects(
                self.workspace, pyprojects
            )
            return
        if not any(rel.endswith("pyproject.toml") for rel in requested_paths):
            return
        # Packaging edits are rare. A targeted configuration sync must also notice
        # deleted project manifests, so rebuild roots from current repository manifests.
        pyprojects = tuple(
            path
            for path in self.workspace.rglob("pyproject.toml")
            if not _is_pruned_relative_path(path.relative_to(self.workspace).as_posix())
            and not self._internal_path(path.relative_to(self.workspace).as_posix())
        )
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

    def _sync_expand_python_reprojection(
        self,
        discovered: list[_DiscoveredFile],
        *,
        full: bool,
        previous_roots: Sequence[str],
    ) -> int:
        """Re-index persisted Python files whose import identity changed with packaging authority."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
        # Re-enter once without a path bound so newly denied rows retire and
        # newly admitted paths are discovered from the same authority cut.
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if self._refresh_context_policy():
            return self.sync()
        started = time.perf_counter()
        warnings: list[str] = []
        removed = self._reconcile_persisted_analysis_scope()
        identity_generation_before = getattr(
            self._daemon_observation(), "generation", None
        )
        discovery = self._sync_discovery(paths, warnings)
        previous_python_import_roots = self._python_import_roots
        self._sync_refresh_python_import_roots(
            discovery.files,
            full=discovery.full,
            requested_paths=discovery.requested_paths,
        )
        reprojection_removed = self._sync_expand_python_reprojection(
            discovery.files,
            full=discovery.full,
            previous_roots=previous_python_import_roots,
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
        removed += reprojection_removed + self._sync_remove_stale_paths(
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
            source_bytes=int(preflight.get("source_bytes") or 0),
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
        self._reverse_file_graph_cache = None
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

    def derived_graph(self, path: str | None = None) -> dict[str, object]:
        """Expose dependency-tracked derived CodeMap surfaces for diagnostics.

        Retrieval does not consume this graph yet; 0.10.8 records identities and
        dependencies only so later invalidation work has a measured foundation.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        normalized = (
            None if path is None else normalize_relative_path(path, allow_root=False)
        )
        if normalized is not None:
            self._ensure_path_current(normalized)
        nodes = self.store.derived_nodes(normalized)
        return {
            "schema": "hashmarks.codemap-derived-graph.v1",
            "generation": self.store.generation(),
            "path": normalized,
            "nodes": nodes,
        }

    def clean(self, *, shared_artifacts: bool = False) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        workspace_before = self.store.clear()
        artifacts_removed = self.artifacts.clear() if shared_artifacts else 0
        return {
            "schema": "hashmarks.codemap-clean.v1",
            "workspace": str(self.workspace),
            "workspace_rows": workspace_before,
            "shared_artifacts_removed": artifacts_removed,
            "shared_artifact_db": str(self.artifacts.db_path),
        }

    def _generation_status(
        self, observation: RepositoryObservation | None = None
    ) -> tuple[int, int | None, bool | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        generation = self.store.generation()
        synced_raw = self.store.meta("identity_generation", "") or ""
        synced = None if not synced_raw else int(synced_raw)
        if observation is None:
            if self._decision_session_depth > 0:
                observation = self._decision_session_observation
            else:
                observation = self._daemon_observation()
        if synced is not None and observation is not None:
            return generation, synced, observation.generation != synced

        pid_raw = self.store.meta("watcher_pid", "") or ""
        state = self.store.meta("watcher_state", "") or ""
        heartbeat_raw = self.store.meta("watcher_heartbeat_unix", "") or ""
        try:
            pid = int(pid_raw)
            heartbeat = float(heartbeat_raw)
        except ValueError:
            return generation, synced, None
        alive = _pid_alive(pid)
        fresh_heartbeat = (time.time() - heartbeat) < 2.5
        if alive and fresh_heartbeat:
            return generation, synced, state != "clean"
        return generation, synced, None

    def _query_freshness_fields(self) -> dict[str, object]:
        """Project existing CodeMap freshness authority into query responses."""
        generation, identity_generation, stale = self._generation_status()
        return {
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
        }

    def status(self) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        generation, identity_generation, stale = self._generation_status()
        return {
            "schema": "hashmarks.codemap-status.v1",
            "workspace": str(self.workspace),
            "state_dir": str(self.state_dir),
            "generation": generation,
            "identity_generation_at_sync": identity_generation,
            "daemon_generation_changed": stale,
            "workspace_fingerprint": self.store.meta("workspace_fingerprint"),
            "last_sync_unix": None
            if self.store.meta("last_sync_unix") is None
            else float(self.store.meta("last_sync_unix") or 0),
            "artifact_db": str(self.artifacts.db_path),
            "artifact_count": self.artifacts.count(),
            "build": self._codemap_build_state(),
            "last_index_economics": (
                json.loads(self.store.meta("sync.economics") or "null")
                if self.store.meta("sync.economics")
                else None
            ),
            "precision_providers": [
                self.range_provider.status().as_dict(),
                self.structural_search_provider.status().as_dict(),
                {
                    "name": self.typescript_resolver.name,
                    "available": self.typescript_resolver.detect(self.workspace),
                    "version": None,
                    "detail": None,
                },
                *[
                    {
                        "name": provider.name,
                        "available": provider.detect(self.workspace),
                        "version": None,
                        "detail": None,
                    }
                    for provider in self.project_graph_providers
                ],
            ],
            "native_evidence": self._native_evidence_status(),
            "watcher": {
                "pid": self.store.meta("watcher_pid", "") or None,
                "state": self.store.meta("watcher_state", "") or None,
                "heartbeat_unix": None
                if not (self.store.meta("watcher_heartbeat_unix", "") or "")
                else float(self.store.meta("watcher_heartbeat_unix", "0") or 0),
            },
            **self.store.stats(),
        }

    def _indexed_path_current(self, relpath: str) -> bool:
        """Return whether durable file evidence still matches current workspace bytes."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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

    def _retire_indexed_path(self, rel: str, row) -> None:
        if row is None:
            return
        self.store.delete_paths((rel,))
        self.store.bump_generation()

    def _ensure_path_current(self, relpath: str) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rel = normalize_relative_path(relpath, allow_root=False)
        row = self.store.file_row(rel)
        path = self.workspace / rel
        if (
            not self._path_admitted_for_analysis(rel)
            or path.is_symlink()
            or not path.is_file()
        ):
            self._retire_indexed_path(rel, row)
            return
        language = _language_for_path(path)
        if language is None:
            return
        decision = self.policy.decide(rel)
        digest = self.file_store.digest(
            path,
            workspace=self.workspace,
            relative_path=rel,
        )
        if (
            row is not None
            and str(row["file_digest"]) == digest.hash
            and str(row["evidence_visibility"]) == decision.evidence_visibility.value
        ):
            return
        artifact, _ = self._parse_or_reuse(rel, path, language, digest.hash)
        self.store.set_file(
            rel,
            artifact,
            module_name=_module_name(rel, getattr(self, "_python_import_roots", ())),
            visibility=decision.evidence_visibility,
            index_surface=self._index_surface_for_path(rel),
        )
        self.store.bump_generation()
