from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

PRODUCER_IDENTITY_SCHEMA = "hashmarks.producer-implementation.v1"
PRODUCER_IDENTITY_PROVENANCE_SCHEMA = "hashmarks.producer-implementation-provenance.v1"


@lru_cache(maxsize=1)
def _native_package_identity() -> str:
    return _producer_implementation_identity(Path(__file__).resolve().parent)


def _producer_implementation_identity(root: Path) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    digest.update(PRODUCER_IDENTITY_SCHEMA.encode("utf-8"))
    digest.update(b"\0")
    files = sorted(
        path
        for path in root.rglob("*.py")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if not files:
        raise ValueError("Hashmarks package contains no Python implementation files")
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def producer_implementation_provenance(
    package_root: Path | None = None,
) -> dict[str, object]:
    """Explain the normalized package inputs contributing to producer identity.

    This is non-authoritative diagnostic metadata. The implementation identity
    remains producer-owned and opaque to consumers; callers must not recreate
    Hashmarks' canonicalization rules from this projection. Only package-relative
    paths, byte counts, and content digests are exposed. Host paths, mtimes,
    inodes, and file contents are intentionally excluded.
    """
    root = (package_root or Path(__file__).resolve().parent).resolve()
    files = sorted(
        path
        for path in root.rglob("*.py")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if not files:
        raise ValueError("Hashmarks package contains no Python implementation files")
    inputs: list[dict[str, object]] = []
    for path in files:
        data = path.read_bytes()
        inputs.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": len(data),
            "content_sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        })
    return {
        "schema": PRODUCER_IDENTITY_PROVENANCE_SCHEMA,
        "authority": "non-authoritative-explanation",
        "storage": "derived-not-persisted",
        "identity_schema": PRODUCER_IDENTITY_SCHEMA,
        "implementation_identity": native_producer_implementation_identity(root),
        "input_count": len(inputs),
        "inputs": inputs,
    }


def native_producer_implementation_identity(package_root: Path | None = None) -> str:
    """Return a deterministic identity for the exact installed/native Hashmarks package bytes.

    The native package identity is immutable for the lifetime of an imported
    installation, so cache that hot-path result. Explicit package roots remain
    uncached for drift/conformance tests and arbitrary artifact inspection.
    """
    if package_root is None:
        return _native_package_identity()
    return _producer_implementation_identity(package_root)
