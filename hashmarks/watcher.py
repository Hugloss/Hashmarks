from __future__ import annotations

import contextlib
import ctypes
import errno
import os
import select
import struct
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from .paths import canonical_event_relative_path, canonical_host_path

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .observation import ChangeTracker

# Linux inotify constants from <sys/inotify.h>.
_IN_MODIFY = 0x00000002
_IN_ATTRIB = 0x00000004
_IN_CLOSE_WRITE = 0x00000008
_IN_MOVED_FROM = 0x00000040
_IN_MOVED_TO = 0x00000080
_IN_CREATE = 0x00000100
_IN_DELETE = 0x00000200
_IN_DELETE_SELF = 0x00000400
_IN_MOVE_SELF = 0x00000800
_IN_Q_OVERFLOW = 0x00004000
_IN_IGNORED = 0x00008000
_IN_ISDIR = 0x40000000
_IN_CLOEXEC = 0x00080000
_IN_NONBLOCK = 0x00000800

_IN_WATCH_MASK = (
    _IN_MODIFY
    | _IN_ATTRIB
    | _IN_CLOSE_WRITE
    | _IN_MOVED_FROM
    | _IN_MOVED_TO
    | _IN_CREATE
    | _IN_DELETE
    | _IN_DELETE_SELF
    | _IN_MOVE_SELF
)

_INOTIFY_EVENT = struct.Struct("iIII")


def should_ignore_observer_event(*, event_type: str, is_directory: bool) -> bool:
    """Ignore parent-directory mtime noise, never membership changes."""
    return is_directory and event_type == "modified"


class DirtyBatch:
    """Thread-safe changed-path accumulator with cheap deduplication."""

    def __init__(self):
        self._lock = threading.Lock()
        self._paths: set[str] = set()

    def add(self, path: str | Path) -> None:
        with self._lock:
            self._paths.add(Path(path).as_posix())

    def extend(self, paths: Iterable[str | Path]) -> None:
        with self._lock:
            self._paths.update(Path(p).as_posix() for p in paths)

    def drain(self) -> list[str]:
        with self._lock:
            result = sorted(self._paths)
            self._paths.clear()
            return result


class _BatchedWatcherBase:
    def __init__(
        self,
        root: str | Path,
        callback: Callable[[list[str]], None],
        *,
        debounce_seconds: float = 0.05,
        change_tracker: ChangeTracker | None = None,
        exclude_relative_paths: Iterable[str | Path] = (),
    ):
        self.root = canonical_host_path(root)
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.change_tracker = change_tracker
        self.exclude_relative_paths = tuple(
            sorted(
                {
                    Path(p).as_posix().strip("/")
                    for p in exclude_relative_paths
                    if Path(p).as_posix().strip("/")
                }
            )
        )
        self._batch = DirtyBatch()
        self._flush_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _excluded(self, rel: str) -> bool:
        return any(
            rel == excluded or rel.startswith(excluded + "/")
            for excluded in self.exclude_relative_paths
        )

    def _start_flush_thread(self, *, observer_alive: Callable[[], bool]) -> None:
        owner = self

        def flush_loop() -> None:
            while not owner._stop.wait(owner.debounce_seconds):
                if not observer_alive():
                    owner.mark_unknown("watcher observer thread stopped")
                    return
                owner._flush_now()

        self._flush_thread = threading.Thread(
            target=flush_loop,
            name="hashmarks-watch-flush",
            daemon=True,
        )
        self._flush_thread.start()

    def mark_unknown(self, reason: str = "watcher continuity lost") -> None:
        if self.change_tracker is not None:
            self.change_tracker.mark_unknown(reason)

    def _flush_now(self) -> None:
        paths = self._batch.drain()
        if not paths:
            return
        if self.change_tracker is not None:
            self.change_tracker.mark_dirty(paths)
        try:
            self.callback(paths)
        except Exception:
            self.mark_unknown("watcher callback failed")

    def synchronize(self) -> bool:
        """Establish a request-time observation barrier when supported.

        False means the backend cannot prove that queued events preceding the
        request have reached ChangeTracker; callers must use safe UNKNOWN
        reconciliation instead of trusting hot cache state.
        """
        return False

    def _join_flush_thread(self) -> None:
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=1)


class NativeLinuxBatchWatcher(_BatchedWatcherBase):
    """Recursive dependency-free Linux watcher using kernel inotify.

    This backend exists specifically so the fast/safe daemon does not require
    a PyPI download on Linux/WSL. inotify is observation only: queue overflow,
    watch-limit exhaustion, read failure, or observer death marks the attached
    ChangeTracker UNKNOWN. Canonical identity is still established from file
    bytes/Merkle reconciliation, never from watcher events.
    """

    def __init__(self, *args, **kwargs):
        if not sys.platform.startswith("linux"):
            raise RuntimeError("NativeLinuxBatchWatcher is only available on Linux")
        super().__init__(*args, **kwargs)
        self._fd: int | None = None
        self._thread: threading.Thread | None = None
        self._wd_to_rel: dict[int, str] = {}
        self._rel_to_wd: dict[str, int] = {}
        self._watch_lock = threading.RLock()
        self._read_lock = threading.RLock()
        self._libc = ctypes.CDLL(None, use_errno=True)
        self._init1 = self._libc.inotify_init1
        self._init1.argtypes = [ctypes.c_int]
        self._init1.restype = ctypes.c_int
        self._add_watch_fn = self._libc.inotify_add_watch
        self._add_watch_fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self._add_watch_fn.restype = ctypes.c_int
        self._rm_watch_fn = self._libc.inotify_rm_watch
        self._rm_watch_fn.argtypes = [ctypes.c_int, ctypes.c_int]
        self._rm_watch_fn.restype = ctypes.c_int

    def _add_watch(self, absolute: Path, rel: str) -> None:
        if self._fd is None or self._excluded(rel):
            return
        if absolute.is_symlink() or not absolute.is_dir():
            return
        with self._watch_lock:
            if rel in self._rel_to_wd:
                return
            wd = self._add_watch_fn(
                self._fd,
                os.fsencode(absolute),
                ctypes.c_uint32(_IN_WATCH_MASK),
            )
            if wd < 0:
                err = ctypes.get_errno()
                if err in (errno.ENOSPC, errno.EMFILE, errno.ENFILE):
                    self.mark_unknown("inotify watch capacity exhausted")
                    raise RuntimeError(
                        "inotify watch capacity exhausted while indexing workspace; "
                        "increase fs.inotify.max_user_watches or use the optional watchdog backend"
                    )
                raise OSError(err, os.strerror(err), str(absolute))
            self._wd_to_rel[wd] = rel
            self._rel_to_wd[rel] = wd

    def _add_recursive(self, absolute: Path, rel: str) -> None:
        if self._excluded(rel):
            return
        self._add_watch(absolute, rel)
        try:
            with os.scandir(absolute) as entries:
                children = [
                    entry for entry in entries if entry.is_dir(follow_symlinks=False)
                ]
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            return
        for entry in children:
            child_rel = f"{rel}/{entry.name}" if rel else entry.name
            if self._excluded(child_rel):
                continue
            self._add_recursive(Path(entry.path), child_rel)

    def _remove_prefix_watches(self, rel: str) -> None:
        if self._fd is None:
            return
        prefix = rel + "/" if rel else ""
        with self._watch_lock:
            victims = [
                (path, wd)
                for path, wd in self._rel_to_wd.items()
                if path == rel or (prefix and path.startswith(prefix))
            ]
            for path, wd in victims:
                self._rel_to_wd.pop(path, None)
                self._wd_to_rel.pop(wd, None)
                result = self._rm_watch_fn(self._fd, wd)
                if result < 0 and ctypes.get_errno() not in (
                    errno.EINVAL,
                    errno.ENOENT,
                ):
                    self.mark_unknown("failed to remove inotify watch")

    def _event_path(self, wd: int, name: str) -> tuple[str, Path] | None:
        with self._watch_lock:
            parent_rel = self._wd_to_rel.get(wd)
        if parent_rel is None:
            return None
        rel = f"{parent_rel}/{name}" if parent_rel and name else (name or parent_rel)
        rel = rel.strip("/")
        if not rel or self._excluded(rel):
            return None
        return rel, self.root / rel

    def _process_data(self, data: bytes) -> None:
        offset = 0
        while offset + _INOTIFY_EVENT.size <= len(data):
            wd, mask, _cookie, name_len = _INOTIFY_EVENT.unpack_from(data, offset)
            offset += _INOTIFY_EVENT.size
            raw_name = data[offset : offset + name_len]
            offset += name_len
            name = os.fsdecode(raw_name.split(b"\0", 1)[0]) if name_len else ""
            if self._handle_watch_state_event(wd, mask, name):
                continue
            item = self._event_path(wd, name)
            if item is None:
                continue
            if not self._handle_path_event(*item, mask):
                return

    def _handle_watch_state_event(self, wd: int, mask: int, name: str) -> bool:
        if mask & _IN_Q_OVERFLOW:
            self.mark_unknown("inotify queue overflow")
            return True
        if mask & _IN_IGNORED:
            with self._watch_lock:
                old_rel = self._wd_to_rel.pop(wd, None)
                if old_rel is not None:
                    self._rel_to_wd.pop(old_rel, None)
            if old_rel == "" and not self._stop.is_set():
                self.mark_unknown("workspace root inotify watch was lost")
            return True
        if name == "" and mask & (_IN_DELETE_SELF | _IN_MOVE_SELF):
            with self._watch_lock:
                watched_rel = self._wd_to_rel.get(wd)
            if watched_rel == "":
                self.mark_unknown("workspace root moved or deleted")
                return True
        return False

    def _handle_path_event(self, rel: str, absolute: Path, mask: int) -> bool:
        is_dir = bool(mask & _IN_ISDIR)
        if mask & (_IN_CREATE | _IN_MOVED_TO):
            self._batch.add(rel)
            if is_dir:
                try:
                    self._add_recursive(absolute, rel)
                except RuntimeError:
                    self.mark_unknown("failed to extend recursive inotify coverage")
                    return False
            return True

        if mask & (_IN_DELETE | _IN_MOVED_FROM | _IN_DELETE_SELF | _IN_MOVE_SELF):
            self._batch.add(rel)
            if is_dir:
                self._remove_prefix_watches(rel)
            return True

        if not is_dir and mask & (_IN_MODIFY | _IN_ATTRIB | _IN_CLOSE_WRITE):
            self._batch.add(rel)
        return True

    def _drain_ready(self) -> None:
        if self._fd is None:
            return
        with self._read_lock:
            while True:
                try:
                    data = os.read(self._fd, 1024 * 1024)
                except BlockingIOError:
                    break
                except OSError:
                    if not self._stop.is_set():
                        self.mark_unknown("inotify read failed")
                    break
                if not data:
                    break
                self._process_data(data)

    def synchronize(self) -> bool:
        if self._fd is None or self._thread is None or not self._thread.is_alive():
            self.mark_unknown("inotify observer unavailable at request barrier")
            return False
        self._drain_ready()
        self._flush_now()
        return (
            self.change_tracker is None
            or self.change_tracker.snapshot().state.value != "unknown"
        )

    def _read_loop(self) -> None:
        assert self._fd is not None
        fd = self._fd
        try:
            while not self._stop.is_set():
                readable, _, _ = select.select([fd], [], [], 0.25)
                if not readable:
                    continue
                self._drain_ready()
        except Exception:
            if not self._stop.is_set():
                self.mark_unknown("inotify observer failed")
            return

    def start(self) -> None:
        if self._thread is not None:
            return
        fd = self._init1(_IN_CLOEXEC | _IN_NONBLOCK)
        if fd < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        self._fd = fd
        try:
            self._add_recursive(self.root, "")
        except Exception:
            os.close(fd)
            self._fd = None
            raise

        self._thread = threading.Thread(
            target=self._read_loop,
            name="hashmarks-inotify",
            daemon=True,
        )
        self._thread.start()
        self._start_flush_thread(
            observer_alive=lambda: bool(self._thread and self._thread.is_alive())
        )

    def stop(self) -> None:
        self.mark_unknown("watcher stopped")
        self._stop.set()
        if self._fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._fd)
            self._fd = None
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._join_flush_thread()


class WatchdogBatchWatcher(_BatchedWatcherBase):
    """Optional portable watcher backed by the third-party ``watchdog``."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._observer = None

    def start(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError as exc:
            raise RuntimeError(
                "portable watcher requires `watchdog`; run/install it explicitly (for example `uv run --with watchdog hashmarks ...`)."
            ) from exc

        owner = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                if should_ignore_observer_event(
                    event_type=str(getattr(event, "event_type", "")),
                    is_directory=bool(getattr(event, "is_directory", False)),
                ):
                    return
                for raw in (
                    getattr(event, "src_path", None),
                    getattr(event, "dest_path", None),
                ):
                    if not raw:
                        continue
                    rel = canonical_event_relative_path(owner.root, raw)
                    if rel is None or owner._excluded(rel):
                        continue
                    owner._batch.add(rel)

        observer = Observer()
        observer.schedule(Handler(), str(self.root), recursive=True)
        observer.start()
        self._observer = observer
        self._start_flush_thread(
            observer_alive=lambda: bool(self._observer and self._observer.is_alive())
        )

    def stop(self) -> None:
        self.mark_unknown("watcher stopped")
        self._stop.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
        self._join_flush_thread()


def create_default_watcher(
    root: str | Path,
    callback: Callable[[list[str]], None],
    *,
    debounce_seconds: float = 0.05,
    change_tracker: ChangeTracker | None = None,
    exclude_relative_paths: Iterable[str | Path] = (),
):
    """Create the fastest safe watcher available without mandatory extras.

    Linux/WSL uses native inotify and needs no third-party package. Other
    platforms use watchdog when installed; otherwise daemon startup fails with
    a precise message rather than silently falling back to an unsafe observer.
    """
    kwargs = {
        "debounce_seconds": debounce_seconds,
        "change_tracker": change_tracker,
        "exclude_relative_paths": exclude_relative_paths,
    }
    if sys.platform.startswith("linux"):
        return NativeLinuxBatchWatcher(root, callback, **kwargs)
    try:
        import watchdog  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "no native watcher backend is available on this platform; "
            "install/run the optional portable backend explicitly, e.g. with `uv run --with watchdog ...`"
        ) from exc
    return WatchdogBatchWatcher(root, callback, **kwargs)
