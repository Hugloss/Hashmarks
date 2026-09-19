from __future__ import annotations

import hashlib
from collections.abc import Iterable
from functools import lru_cache
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

PRODUCER_IDENTITY_SCHEMA = "hashmarks.producer-implementation.v1"
PRODUCER_IDENTITY_PROVENANCE_SCHEMA = "hashmarks.producer-implementation-provenance.v1"

_PythonInput = tuple[str, bytes]


def _filesystem_python_inputs(root: Path) -> list[_PythonInput]:
    root = root.resolve()
    return [
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*.py"))
        if path.is_file() and "__pycache__" not in path.parts
    ]


def _resource_python_inputs(
    root: Traversable, prefix: str = ""
) -> list[_PythonInput]:
    inputs: list[_PythonInput] = []
    for child in root.iterdir():
        if child.name == "__pycache__":
            continue
        relative = f"{prefix}/{child.name}" if prefix else child.name
        if child.is_dir():
            inputs.extend(_resource_python_inputs(child, relative))
        elif child.is_file() and child.name.endswith(".py"):
            inputs.append((relative, child.read_bytes()))
    return sorted(inputs)


def _implementation_identity(inputs: Iterable[_PythonInput]) -> str:
    rows = list(inputs)
    if not rows:
        raise ValueError("Hashmarks package contains no Python implementation files")
    digest = hashlib.sha256()
    digest.update(PRODUCER_IDENTITY_SCHEMA.encode("utf-8"))
    digest.update(b"\0")
    for relative, data in rows:
        rel = relative.encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def _producer_implementation_identity_from_resource(root: Traversable) -> str:
    return _implementation_identity(_resource_python_inputs(root))


@lru_cache(maxsize=1)
def _native_package_identity() -> str:
    return _producer_implementation_identity_from_resource(files("hashmarks"))


def _producer_implementation_identity(root: Path) -> str:
    return _implementation_identity(_filesystem_python_inputs(root))


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
    inputs = (
        _resource_python_inputs(files("hashmarks"))
        if package_root is None
        else _filesystem_python_inputs(package_root)
    )
    implementation_identity = _implementation_identity(inputs)
    rows = [
        {
            "path": relative,
            "bytes": len(data),
            "content_sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        }
        for relative, data in inputs
    ]
    return {
        "schema": PRODUCER_IDENTITY_PROVENANCE_SCHEMA,
        "authority": "non-authoritative-explanation",
        "storage": "derived-not-persisted",
        "identity_schema": PRODUCER_IDENTITY_SCHEMA,
        "implementation_identity": implementation_identity,
        "input_count": len(rows),
        "inputs": rows,
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
