from __future__ import annotations

import os
import shutil
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Iterator

from .digest import BLOB_DOMAIN, DEFAULT_CHUNK_SIZE, Digest, hash_bytes, hash_file
from .paths import canonical_host_path


class UnstableCASSourceError(RuntimeError):
    """Raised when a file keeps changing while being captured into CAS."""


class CAS:
    """Small local content-addressable store.

    CAS data is reproducible cache state, not authoritative state. Atomic
    rename prevents partial readers; optional durability can fsync writes when
    crash persistence of cache entries is worth the cost.
    """

    def __init__(self, root: str | Path, *, durable: bool = False):
        self.root = canonical_host_path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.durable = durable

    def _path(self, digest: Digest) -> Path:
        return self.root / digest.hash[:2] / digest.hash[2:]

    def has(self, digest: Digest) -> bool:
        path = self._path(digest)
        try:
            return path.is_file() and path.stat().st_size == digest.size
        except FileNotFoundError:
            return False

    def _finish_temp(self, tmp_name: str, target: Path, *, expected_size: int) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if target.is_file() and target.stat().st_size == expected_size:
                os.unlink(tmp_name)
                return
        except FileNotFoundError:
            pass

        try:
            os.replace(tmp_name, target)
        except OSError:
            # Another process may have won the race. A matching-size object at
            # the content-addressed path is acceptable for the fast path;
            # strong verification can rehash it.
            try:
                if target.is_file() and target.stat().st_size == expected_size:
                    os.unlink(tmp_name)
                    return
            except FileNotFoundError:
                pass
            raise

    def put_bytes(self, data: bytes) -> Digest:
        digest = hash_bytes(data, domain=BLOB_DOMAIN)
        target = self._path(digest)
        if self.has(digest):
            return digest

        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                if self.durable:
                    f.flush()
                    os.fsync(f.fileno())
            self._finish_temp(tmp_name, target, expected_size=digest.size)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return digest

    @staticmethod
    def _source_metadata(path: Path) -> tuple[int, int, int, int, int]:
        st = path.stat()
        return (
            int(st.st_dev),
            int(st.st_ino),
            int(st.st_size),
            int(st.st_mtime_ns),
            int(st.st_ctime_ns),
        )

    def put_file(
        self,
        source: str | Path,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_attempts: int = 3,
    ) -> Digest:
        """Stream a stable file snapshot into CAS while hashing it once per try."""
        source = Path(source)

        for _ in range(max_attempts):
            before = self._source_metadata(source)
            fd, tmp_name = tempfile.mkstemp(dir=self.root, prefix=".tmp-")
            h = sha256()
            h.update(BLOB_DOMAIN)
            size = 0
            try:
                with source.open("rb", buffering=0) as src, os.fdopen(fd, "wb", buffering=0) as dst:
                    while True:
                        chunk = src.read(chunk_size)
                        if not chunk:
                            break
                        h.update(chunk)
                        dst.write(chunk)
                        size += len(chunk)
                    if self.durable:
                        dst.flush()
                        os.fsync(dst.fileno())

                after = self._source_metadata(source)
                if after != before:
                    os.unlink(tmp_name)
                    continue

                digest = Digest(h.hexdigest(), size)
                self._finish_temp(tmp_name, self._path(digest), expected_size=size)
                return digest
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)

        raise UnstableCASSourceError(f"file changed while storing in CAS: {source}")

    def verify(self, digest: Digest) -> None:
        path = self._path(digest)
        if not path.is_file():
            raise FileNotFoundError(digest.as_key())
        actual = hash_file(path, domain=BLOB_DOMAIN)
        if actual != digest:
            raise IOError(f"CAS corruption: expected {digest.as_key()}, got {actual.as_key()}")

    def get_bytes(self, digest: Digest) -> bytes:
        data = self._path(digest).read_bytes()
        actual = hash_bytes(data, domain=BLOB_DOMAIN)
        if actual != digest:
            raise IOError(f"CAS corruption: expected {digest.as_key()}, got {actual.as_key()}")
        return data

    def materialize(
        self,
        digest: Digest,
        target: str | Path,
        *,
        verify: bool = False,
    ) -> Path:
        source = self._path(digest)
        if verify:
            self.verify(digest)
        elif not self.has(digest):
            raise FileNotFoundError(digest.as_key())

        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
        os.close(fd)
        os.unlink(tmp_name)
        try:
            try:
                os.link(source, tmp_name)
            except OSError:
                shutil.copyfile(source, tmp_name)
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return target

    def delete(self, digest: Digest) -> bool:
        path = self._path(digest)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return True

    def iter_digests(self) -> Iterator[str]:
        for prefix in sorted(self.root.iterdir()):
            if not prefix.is_dir() or len(prefix.name) != 2:
                continue
            for blob in sorted(prefix.iterdir()):
                if blob.is_file() and not blob.name.startswith(".tmp-"):
                    yield prefix.name + blob.name

    def size_bytes(self) -> int:
        return sum(
            path.stat().st_size
            for path in self.root.rglob("*")
            if path.is_file() and not path.name.startswith(".tmp-")
        )
