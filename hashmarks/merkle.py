from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterable, Literal, TypeVar

from .digest import DIR_DOMAIN, INPUT_ROOT_DOMAIN, Digest, encode_field
from .directory_store import DirectoryDigestStore
from .file_store import FileDigestStore
from .inputs import InputManifest
from .observation import ChangeTracker, ObservationState, UnstableObservationError
from .paths import canonical_host_path, normalize_relative_path

DEFAULT_WALK_IGNORE_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)
DEFAULT_MANDATORY_EXCLUDE_NAMES = frozenset({".hashmarks", ".fastidentity"})
SYMLINK_DOMAIN = b"fastidentity.symlink.v1\0"
MANIFEST_DIR_DOMAIN = b"fastidentity.manifest-directory.v1\0"
_MAX_RECONCILE_ATTEMPTS = 3
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class _Node:
    kind: bytes
    name: bytes
    digest: Digest | None = None
    executable: bool = False
    target: bytes | None = None


@dataclass(slots=True)
class _ManifestTrieNode:
    segment: str
    terminal_rel: str | None = None
    children: dict[str, "_ManifestTrieNode"] = field(default_factory=dict)
    cached_node: _Node | None = None
    cached_digest: Digest | None = None
    dirty: bool = True

    def mark_subtree_dirty(self) -> None:
        self.dirty = True
        for child in self.children.values():
            child.mark_subtree_dirty()

    def as_node(self, owner: "MerkleTree", *, verify: bool) -> _Node:
        if self.terminal_rel is not None:
            if not verify and not self.dirty and self.cached_node is not None:
                return self.cached_node
            if verify:
                # digest_manifest() force-primes direct file/symlink terminals
                # in one batch before walking the synthetic tree. Reuse that
                # freshly verified node here; directory terminals intentionally
                # remain absent and take the strong _directory_digest path.
                with owner._lock:
                    direct = owner._path_cache.get(self.terminal_rel)
                if direct is not None:
                    node = _Node(
                        kind=direct.kind,
                        name=owner._entry_name(self.segment),
                        digest=direct.digest,
                        executable=direct.executable,
                        target=direct.target,
                    )
                    self.cached_node = node
                    self.dirty = False
                    return node
            node = owner._node_for_path(
                self.terminal_rel,
                name=self.segment,
                verify=verify,
            )
            self.cached_node = node
            self.dirty = False
            return node

        if not verify and not self.dirty and self.cached_digest is not None:
            return _Node(
                kind=b"D",
                name=owner._entry_name(self.segment),
                digest=self.cached_digest,
            )

        child_nodes = [
            self.children[name].as_node(owner, verify=verify)
            for name in sorted(
                self.children,
                key=lambda value: value.encode("utf-8", errors="surrogateescape"),
            )
        ]
        digest = owner._hash_nodes(child_nodes, domain=MANIFEST_DIR_DOMAIN)
        self.cached_digest = digest
        self.dirty = False
        return _Node(
            kind=b"D",
            name=owner._entry_name(self.segment),
            digest=digest,
        )


class _ManifestTree:
    """Incremental synthetic Merkle tree for one resolved InputManifest."""

    def __init__(self, paths: tuple[str, ...]) -> None:
        self.paths = paths
        self.root = _ManifestTrieNode("")
        self._root_digest: Digest | None = None
        self._root_dirty = True
        for rel in paths:
            self._insert(rel)

    def _insert(self, rel: str) -> None:
        node = self.root
        for segment in Path(rel).parts:
            # A selected ancestor directory already covers all descendants.
            if node.terminal_rel is not None:
                return
            node = node.children.setdefault(segment, _ManifestTrieNode(segment))
        node.terminal_rel = rel
        node.children.clear()
        node.dirty = True

    def invalidate(self, dirty: str) -> bool:
        dirty = normalize_relative_path(dirty)
        if not dirty:
            self.root.mark_subtree_dirty()
            self._root_dirty = True
            return True

        node = self.root
        ancestors = [self.root]
        parts = Path(dirty).parts
        for segment in parts:
            if node.terminal_rel is not None:
                for ancestor in ancestors:
                    ancestor.dirty = True
                self._root_dirty = True
                return True
            child = node.children.get(segment)
            if child is None:
                return False
            node = child
            ancestors.append(node)

        # Dirty path equals a selected leaf or is an ancestor of selected
        # descendants. The latter is uncommon for watcher streams but must be
        # safe for explicit record_changes(["directory"]) calls.
        if node.terminal_rel is None and not node.children:
            return False
        node.mark_subtree_dirty()
        for ancestor in ancestors:
            ancestor.dirty = True
        self._root_dirty = True
        return True

    def terminal_rels(self, *, dirty_only: bool) -> tuple[str, ...]:
        result: list[str] = []

        def visit(node: _ManifestTrieNode) -> None:
            if dirty_only and not node.dirty:
                return
            if node.terminal_rel is not None:
                result.append(node.terminal_rel)
                return
            for child in node.children.values():
                visit(child)

        visit(self.root)
        return tuple(result)

    def digest(self, owner: "MerkleTree", *, verify: bool) -> Digest:
        if not verify and not self._root_dirty and self._root_digest is not None:
            return self._root_digest
        nodes = [
            self.root.children[name].as_node(owner, verify=verify)
            for name in sorted(
                self.root.children,
                key=lambda value: value.encode("utf-8", errors="surrogateescape"),
            )
        ]
        digest = owner._hash_nodes(nodes, domain=INPUT_ROOT_DOMAIN)
        self._root_digest = digest
        self._root_dirty = False
        return digest


class MerkleTree:
    """Incremental Merkle-style directory identity.

    Fast path:
      * exact changed paths invalidate only ancestor directories;
      * clean hot subtrees reuse their in-memory Merkle digest;
      * direct-file SQLite lookups are batched per directory/manifest;
      * unchanged files reuse persistent content digests without reading bytes.

    Safe recovery:
      * UNKNOWN observation state drops all hot directory identities;
      * reconciliation scans requested inputs using filesystem metadata;
      * ``verify=True`` additionally re-reads and hashes selected file bytes;
      * concurrent observer generations cause reconciliation retry.
    """

    def __init__(
        self,
        workspace: str | Path,
        file_store: FileDigestStore,
        *,
        directory_store: DirectoryDigestStore | None = None,
        change_tracker: ChangeTracker | None = None,
        walk_ignore_names: Iterable[str] = DEFAULT_WALK_IGNORE_NAMES,
        mandatory_exclude_names: Iterable[str] = (),
        exclude_paths: Iterable[str | Path] = (),
    ):
        self.workspace = canonical_host_path(workspace)
        self.file_store = file_store
        self.directory_store = directory_store
        self.change_tracker = change_tracker
        self.walk_ignore_names = frozenset(walk_ignore_names)
        self.mandatory_exclude_names = (
            DEFAULT_MANDATORY_EXCLUDE_NAMES | frozenset(mandatory_exclude_names)
        )
        self._excluded_paths = self._build_excluded_paths(exclude_paths)
        self._dir_cache: dict[str, Digest] = {}
        self._dirty_dirs: set[str] = {""}
        # Direct selected-file/symlink nodes are hot observation state too.
        # This lets a 500k explicit-file manifest update one changed leaf
        # without re-stat'ing the other 499,999 members.
        self._path_cache: dict[str, _Node] = {}
        self._manifest_trees: dict[str, _ManifestTree] = {}
        self._stats = {
            "directory_cache_hits": 0,
            "directory_recomputes": 0,
            "path_cache_hits": 0,
            "manifest_tree_hits": 0,
            "manifest_tree_misses": 0,
            "manifest_digest_calls": 0,
            "verify_calls": 0,
            "hot_cache_drops": 0,
        }
        self._last_reconciliation_paths: tuple[str, ...] = ()
        self._last_reconciliation_state: str = "unknown"
        self._lock = threading.RLock()

    def _build_excluded_paths(self, explicit: Iterable[str | Path]) -> frozenset[str]:
        excluded: set[str] = set()

        def add_host_path(candidate: str | Path) -> None:
            host = canonical_host_path(candidate)
            try:
                rel = host.relative_to(self.workspace).as_posix()
            except ValueError:
                return
            excluded.add(normalize_relative_path(rel))

        for item in explicit:
            path = Path(item)
            if path.is_absolute():
                add_host_path(path)
            else:
                # Relative exclusions are workspace identity paths. Preserve
                # their lexical spelling so a symlink leaf can itself be
                # excluded without resolving to the target.
                excluded.add(normalize_relative_path(item))

        stores = [self.file_store]
        if self.directory_store is not None:
            stores.append(self.directory_store)  # type: ignore[arg-type]

        for store in stores:
            # Storage owners define their own internal files. Merkle does not
            # duplicate SQLite/WAL naming knowledge.
            for candidate in store.identity_exclusions():
                add_host_path(candidate)

        return frozenset(excluded)

    def _relative(self, path: str | Path) -> str:
        return normalize_relative_path(path)

    def _is_mandatory_excluded(self, rel: str) -> bool:
        if not rel:
            return False
        parts = Path(rel).parts
        if any(part in self.mandatory_exclude_names for part in parts):
            return True
        return any(
            rel == excluded or rel.startswith(excluded.rstrip("/") + "/")
            for excluded in self._excluded_paths
        )

    def _is_walk_ignored(self, rel: str) -> bool:
        if not rel:
            return False
        # Traversal ignores apply to the entry currently being considered, not
        # forever to every descendant of an explicitly selected ignored root.
        return Path(rel).name in self.walk_ignore_names

    def _should_skip_during_walk(self, rel: str) -> bool:
        return self._is_mandatory_excluded(rel) or self._is_walk_ignored(rel)

    def drop_hot_cache(self) -> None:
        with self._lock:
            self._stats["hot_cache_drops"] += 1
            self._dir_cache.clear()
            self._dirty_dirs = {""}
            self._path_cache.clear()
            self._manifest_trees.clear()

    def _invalidate_manifest_cache(self, dirty_paths: Iterable[str]) -> None:
        dirty = tuple(dirty_paths)
        if not dirty:
            return
        with self._lock:
            trees = tuple(self._manifest_trees.values())
        if not trees:
            return
        # Exact trie traversal is O(path depth) per manifest/change. Very large
        # bursts are safer and cheaper to treat as global hot-cache loss.
        if len(dirty) > 512:
            with self._lock:
                self._manifest_trees.clear()
            return
        for path in dirty:
            for tree in trees:
                tree.invalidate(path)

    def _invalidate_path_cache(self, rel: str, *, kind: str) -> None:
        with self._lock:
            if kind == "file":
                self._path_cache.pop(rel, None)
                return
            prefix = rel.rstrip("/") + "/" if rel else ""
            if not prefix:
                self._path_cache.clear()
                return
            for key in [key for key in self._path_cache if key == rel or key.startswith(prefix)]:
                self._path_cache.pop(key, None)

    def invalidate(
        self,
        path: str | Path,
        *,
        kind: Literal["auto", "file", "directory"] = "auto",
    ) -> None:
        rel = self._relative(path)
        if self._is_mandatory_excluded(rel):
            return

        absolute = self.workspace / rel
        if kind == "auto":
            kind = "directory" if absolute.is_dir() and not absolute.is_symlink() else "file"

        self._invalidate_path_cache(rel, kind=kind)
        # Direct MerkleTree users may not attach a ChangeTracker, so explicit
        # invalidation must update manifest synthetic trees immediately too.
        self._invalidate_manifest_cache((rel,))
        current = Path(rel) if kind == "directory" else Path(rel).parent

        with self._lock:
            while True:
                key = "" if current.as_posix() == "." else current.as_posix()
                self._dirty_dirs.add(key)
                self._dir_cache.pop(key, None)
                if key == "":
                    break
                current = current.parent

    def invalidate_many(self, paths: Iterable[str | Path]) -> None:
        for path in paths:
            self.invalidate(path)

    def _prepare_observation(self) -> int | None:
        if self.change_tracker is None:
            return None
        snapshot = self.change_tracker.snapshot()
        with self._lock:
            self._last_reconciliation_paths = snapshot.paths
            self._last_reconciliation_state = snapshot.state.value
        if snapshot.state is ObservationState.UNKNOWN:
            self.drop_hot_cache()
        elif snapshot.state is ObservationState.DIRTY:
            self.invalidate_many(snapshot.paths)
            self._invalidate_manifest_cache(snapshot.paths)
        return snapshot.generation

    def _finish_observation(self, generation: int | None) -> bool:
        if self.change_tracker is None or generation is None:
            return True
        return self.change_tracker.mark_reconciled(expected_generation=generation)

    def _run_reconciled(self, operation: Callable[[], _T]) -> _T:
        for _ in range(_MAX_RECONCILE_ATTEMPTS):
            generation = self._prepare_observation()
            try:
                result = operation()
            except Exception:
                if self.directory_store is not None:
                    self.directory_store.discard_pending()
                if self.change_tracker is not None:
                    self.change_tracker.mark_unknown("reconciliation failed")
                raise

            if self._finish_observation(generation):
                if self.directory_store is not None:
                    self.directory_store.flush()
                return result

        if self.directory_store is not None:
            self.directory_store.discard_pending()
        if self.change_tracker is not None:
            self.change_tracker.mark_unknown("filesystem changed continuously during reconciliation")
        raise UnstableObservationError(
            "filesystem changed continuously during identity reconciliation"
        )

    @staticmethod
    def _entry_name(name: str) -> bytes:
        return name.encode("utf-8", errors="surrogateescape")

    @staticmethod
    def _sorted_scandir(path: Path):
        entries = list(os.scandir(path))
        entries.sort(key=lambda e: e.name.encode("utf-8", errors="surrogateescape"))
        return entries

    @staticmethod
    def _encode_node(node: _Node) -> bytes:
        out = bytearray()
        out += node.kind
        out += encode_field(node.name)

        if node.kind == b"F":
            assert node.digest is not None
            out += bytes.fromhex(node.digest.hash)
            out += node.digest.size.to_bytes(8, "big")
            out += b"\x01" if node.executable else b"\x00"
        elif node.kind == b"D":
            assert node.digest is not None
            out += bytes.fromhex(node.digest.hash)
            out += node.digest.size.to_bytes(8, "big")
        elif node.kind == b"L":
            assert node.target is not None
            out += encode_field(node.target)
        else:
            raise ValueError(f"unknown node kind: {node.kind!r}")

        return bytes(out)

    @classmethod
    def _hash_nodes(cls, nodes: list[_Node], *, domain: bytes) -> Digest:
        h = sha256()
        h.update(domain)
        size = 0
        for node in nodes:
            encoded = cls._encode_node(node)
            h.update(encoded)
            size += len(encoded)
        return Digest(hash=h.hexdigest(), size=size)

    def _symlink_node(self, absolute: Path, name: str) -> _Node:
        target = os.readlink(absolute).encode("utf-8", errors="surrogateescape")
        return _Node(kind=b"L", name=self._entry_name(name), target=target)

    def _node_for_path(self, rel: str, *, name: str, verify: bool) -> _Node:
        if self._is_mandatory_excluded(rel):
            raise ValueError(f"input path is excluded from identity: {rel}")

        if not verify:
            with self._lock:
                cached = self._path_cache.get(rel)
                if cached is not None:
                    self._stats["path_cache_hits"] += 1
                    # Names differ between direct path_digest() and synthetic
                    # manifest roots; only reuse the canonical content/kind.
                    return _Node(
                        kind=cached.kind,
                        name=self._entry_name(name),
                        digest=cached.digest,
                        executable=cached.executable,
                        target=cached.target,
                    )

        absolute = self.workspace / rel
        if absolute.is_symlink():
            node = self._symlink_node(absolute, name)
            with self._lock:
                self._path_cache[rel] = _Node(
                    kind=node.kind, name=b"", target=node.target
                )
            return node
        if absolute.is_file():
            digest, executable = self.file_store.digest_many_info(
                [(absolute, rel)],
                workspace=self.workspace,
                force=verify,
            )[rel]
            node = _Node(
                kind=b"F",
                name=self._entry_name(name),
                digest=digest,
                executable=executable,
            )
            with self._lock:
                self._path_cache[rel] = _Node(
                    kind=b"F", name=b"", digest=digest, executable=executable
                )
            return node
        if absolute.is_dir():
            return _Node(
                kind=b"D",
                name=self._entry_name(name),
                digest=self._directory_digest(rel, verify=verify),
            )
        raise FileNotFoundError(absolute)

    def directory_digest(self, path: str | Path = "", *, verify: bool = False) -> Digest:
        rel = self._relative(path)
        return self._run_reconciled(lambda: self._directory_digest(rel, verify=verify))

    def _directory_digest(self, rel: str, *, verify: bool) -> Digest:
        if self._is_mandatory_excluded(rel):
            raise ValueError(f"input path is excluded from identity: {rel}")

        with self._lock:
            if not verify and rel not in self._dirty_dirs:
                cached = self._dir_cache.get(rel)
                if cached is not None:
                    self._stats["directory_cache_hits"] += 1
                    return cached

        with self._lock:
            self._stats["directory_recomputes"] += 1
            if verify:
                self._stats["verify_calls"] += 1
        absolute = self.workspace / rel
        if not absolute.is_dir():
            raise NotADirectoryError(absolute)

        entries = self._sorted_scandir(absolute)
        file_items: list[tuple[Path, str]] = []

        for entry in entries:
            child_rel = f"{rel}/{entry.name}" if rel else entry.name
            if self._should_skip_during_walk(child_rel):
                continue
            if entry.is_file(follow_symlinks=False) and not entry.is_symlink():
                file_items.append((Path(entry.path), child_rel))

        file_info = self.file_store.digest_many_info(
            file_items,
            workspace=self.workspace,
            force=verify,
        )

        nodes: list[_Node] = []
        for entry in entries:
            child_rel = f"{rel}/{entry.name}" if rel else entry.name
            if self._should_skip_during_walk(child_rel):
                continue

            if entry.is_symlink():
                nodes.append(self._symlink_node(Path(entry.path), entry.name))
            elif entry.is_file(follow_symlinks=False):
                nodes.append(
                    _Node(
                        kind=b"F",
                        name=self._entry_name(entry.name),
                        digest=file_info[child_rel][0],
                        executable=file_info[child_rel][1],
                    )
                )
            elif entry.is_dir(follow_symlinks=False):
                nodes.append(
                    _Node(
                        kind=b"D",
                        name=self._entry_name(entry.name),
                        digest=self._directory_digest(child_rel, verify=verify),
                    )
                )

        digest = self._hash_nodes(nodes, domain=DIR_DOMAIN)
        with self._lock:
            self._dir_cache[rel] = digest
            self._dirty_dirs.discard(rel)

        if self.directory_store is not None:
            self.directory_store.put(
                workspace=self.workspace,
                relative_path=rel,
                digest=digest,
            )
        return digest

    def path_digest(self, path: str | Path, *, verify: bool = False) -> tuple[bytes, Digest, bool]:
        rel = self._relative(path)
        node = self._run_reconciled(
            lambda: self._node_for_path(rel, name=Path(rel).name or rel, verify=verify)
        )

        if node.kind == b"L":
            assert node.target is not None
            h = sha256()
            h.update(SYMLINK_DOMAIN)
            h.update(encode_field(node.target))
            return b"L", Digest(h.hexdigest(), len(node.target)), False

        assert node.digest is not None
        return node.kind, node.digest, node.executable

    def _prime_manifest_terminals(self, rels: tuple[str, ...], *, verify: bool) -> None:
        """Batch-populate direct file/symlink nodes needed by a manifest update."""
        file_items: list[tuple[Path, str]] = []
        symlinks: dict[str, bytes] = {}
        for rel in rels:
            if self._is_mandatory_excluded(rel):
                raise ValueError(f"input path is excluded from identity: {rel}")
            with self._lock:
                if verify:
                    # Strong verification must classify the current leaf type
                    # too, so stale direct-node kind cannot survive a missed
                    # observation or direct-Merkle use without a tracker.
                    self._path_cache.pop(rel, None)
                elif rel in self._path_cache:
                    continue
            absolute = self.workspace / rel
            if absolute.is_symlink():
                symlinks[rel] = os.readlink(absolute).encode(
                    "utf-8", errors="surrogateescape"
                )
            elif absolute.is_file():
                file_items.append((absolute, rel))
            elif absolute.is_dir():
                # Real directory Merkle state has its own incremental cache.
                continue
            else:
                raise FileNotFoundError(absolute)

        file_info = self.file_store.digest_many_info(
            file_items,
            workspace=self.workspace,
            force=verify,
        )
        if file_info or symlinks:
            with self._lock:
                for rel, (digest, executable) in file_info.items():
                    self._path_cache[rel] = _Node(
                        kind=b"F", name=b"", digest=digest, executable=executable
                    )
                for rel, target in symlinks.items():
                    self._path_cache[rel] = _Node(kind=b"L", name=b"", target=target)

    def digest_manifest(self, manifest: InputManifest, *, verify: bool = False) -> Digest:
        with self._lock:
            self._stats["manifest_digest_calls"] += 1
            if verify:
                self._stats["verify_calls"] += 1
        # One synthetic Merkle trie is built per resolved manifest. After that,
        # hot unchanged reads are O(1), and a dirty explicit file recomputes
        # only that leaf plus synthetic path ancestors rather than re-stat'ing
        # or re-hashing every declared manifest member.
        def compute() -> Digest:
            with self._lock:
                tree = self._manifest_trees.get(manifest.fingerprint)
                if tree is None or tree.paths != manifest.paths:
                    self._stats["manifest_tree_misses"] += 1
                    tree = _ManifestTree(manifest.paths)
                    self._manifest_trees[manifest.fingerprint] = tree
                else:
                    self._stats["manifest_tree_hits"] += 1
            self._prime_manifest_terminals(
                tree.terminal_rels(dirty_only=not verify),
                verify=verify,
            )
            return tree.digest(self, verify=verify)

        return self._run_reconciled(compute)


    def stats(self) -> dict[str, int]:
        with self._lock:
            return dict(self._stats)

    def reset_stats(self) -> None:
        with self._lock:
            for key in self._stats:
                self._stats[key] = 0

    def last_reconciliation(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self._last_reconciliation_state,
                "paths": list(self._last_reconciliation_paths),
            }

    def digest_selected(self, inputs: Iterable[str | Path], *, verify: bool = False) -> Digest:
        """Digest ad-hoc declared inputs using the same manifest Merkle model."""
        requested = tuple(inputs)
        rels = sorted({self._relative(p) for p in requested})
        rels = self._remove_descendants_of_selected_dirs(rels)
        return self.digest_manifest(InputManifest(tuple(rels)), verify=verify)

    def _remove_descendants_of_selected_dirs(self, rels: list[str]) -> list[str]:
        selected: list[str] = []
        selected_dirs: list[str] = []

        for rel in rels:
            if self._is_mandatory_excluded(rel):
                raise ValueError(f"input path is excluded from identity: {rel}")
            if any(rel != d and rel.startswith(d.rstrip("/") + "/") for d in selected_dirs):
                continue

            absolute = self.workspace / rel
            selected.append(rel)
            if absolute.is_dir() and not absolute.is_symlink():
                selected_dirs.append(rel)

        return selected
