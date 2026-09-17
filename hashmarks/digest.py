from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO

from .schema import DIGEST_ALGORITHM

DEFAULT_CHUNK_SIZE = 1024 * 1024

# Domain separation keeps identical byte strings used for different logical
# object types from sharing the same identity accidentally.
BLOB_DOMAIN = b"fastidentity.blob.v1\0"
FILE_DOMAIN = b"fastidentity.file.v1\0"
DIR_DOMAIN = b"fastidentity.directory.v1\0"
INPUT_ROOT_DOMAIN = b"fastidentity.input-root.v1\0"


@dataclass(frozen=True, slots=True)
class Digest:
    hash: str
    size: int

    @property
    def algorithm(self) -> str:
        return DIGEST_ALGORITHM

    def as_key(self) -> str:
        return f"{self.algorithm}:{self.hash}:{self.size}"


def _new_hasher(domain: bytes):
    h = sha256()
    h.update(domain)
    return h


def hash_bytes(data: bytes, *, domain: bytes = BLOB_DOMAIN) -> Digest:
    h = _new_hasher(domain)
    h.update(data)
    return Digest(h.hexdigest(), len(data))


def _hash_stream(stream: BinaryIO, *, domain: bytes, chunk_size: int) -> Digest:
    h = _new_hasher(domain)
    size = 0
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        h.update(chunk)
        size += len(chunk)
    return Digest(h.hexdigest(), size)


def hash_file(
    path: str | Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    domain: bytes = FILE_DOMAIN,
) -> Digest:
    path = Path(path)
    # buffering=0 avoids an extra Python buffering layer for large sequential
    # reads; the OS page cache still applies.
    with path.open("rb", buffering=0) as f:
        return _hash_stream(f, domain=domain, chunk_size=chunk_size)


def encode_field(data: bytes) -> bytes:
    """Unambiguous length-prefixed field encoding."""
    return len(data).to_bytes(8, "big") + data


def encode_text(value: str) -> bytes:
    return encode_field(value.encode("utf-8", errors="surrogateescape"))
