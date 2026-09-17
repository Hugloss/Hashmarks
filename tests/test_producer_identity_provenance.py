from __future__ import annotations

import os
from pathlib import Path

from hashmarks.producer_identity import (
    PRODUCER_IDENTITY_PROVENANCE_SCHEMA,
    native_producer_implementation_identity,
    producer_implementation_provenance,
)


def _package(root: Path, *, engine: str = "VALUE = 1\n") -> Path:
    root.mkdir()
    (root / "_version.py").write_text('__version__ = "same"\n')
    (root / "engine.py").write_text(engine)
    return root


def _rows(receipt: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(row["path"]): row for row in receipt["inputs"]}  # type: ignore[index]


def test_producer_identity_provenance_explains_same_version_byte_drift(
    tmp_path: Path,
) -> None:
    a = _package(tmp_path / "a")
    b = _package(tmp_path / "b", engine="VALUE = 2\n")

    before = producer_implementation_provenance(a)
    after = producer_implementation_provenance(b)

    assert before["implementation_identity"] != after["implementation_identity"]
    assert _rows(before)["_version.py"] == _rows(after)["_version.py"]
    assert (
        _rows(before)["engine.py"]["content_sha256"]
        != _rows(after)["engine.py"]["content_sha256"]
    )


def test_producer_identity_provenance_explains_same_content_rename(
    tmp_path: Path,
) -> None:
    a = _package(tmp_path / "a")
    b = _package(tmp_path / "b")
    (b / "engine.py").rename(b / "core.py")

    before = producer_implementation_provenance(a)
    after = producer_implementation_provenance(b)

    assert before["implementation_identity"] != after["implementation_identity"]
    assert set(_rows(before)) - set(_rows(after)) == {"engine.py"}
    assert set(_rows(after)) - set(_rows(before)) == {"core.py"}
    assert (
        _rows(before)["engine.py"]["content_sha256"]
        == _rows(after)["core.py"]["content_sha256"]
    )


def test_producer_identity_provenance_ignores_inode_and_mtime_churn(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path / "package")
    before = producer_implementation_provenance(package)
    engine = package / "engine.py"
    data = engine.read_bytes()
    engine.unlink()
    engine.write_bytes(data)
    os.utime(engine, (engine.stat().st_atime, engine.stat().st_mtime + 1000))
    after = producer_implementation_provenance(package)

    assert after == before


def test_producer_identity_provenance_is_relative_bounded_metadata() -> None:
    receipt = producer_implementation_provenance()

    assert receipt["schema"] == PRODUCER_IDENTITY_PROVENANCE_SCHEMA
    assert receipt["authority"] == "non-authoritative-explanation"
    assert receipt["storage"] == "derived-not-persisted"
    assert (
        receipt["implementation_identity"] == native_producer_implementation_identity()
    )
    assert receipt["input_count"] == len(receipt["inputs"])
    for row in receipt["inputs"]:  # type: ignore[union-attr]
        path = str(row["path"])
        assert not Path(path).is_absolute()
        assert ".." not in Path(path).parts
        assert set(row) == {"path", "bytes", "content_sha256"}
        assert str(row["content_sha256"]).startswith("sha256:")
