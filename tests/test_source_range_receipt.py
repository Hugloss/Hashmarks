from __future__ import annotations

import base64
import hashlib
from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_object, assert_text

from hashmarks import CodeMap

if TYPE_CHECKING:
    from pathlib import Path

    from hashmarks import Digest


@pytest.mark.parametrize(
    ("raw", "start", "end"),
    [
        (b"first\nsecond\n", 0, 6),
        (b"first\r\nsecond\r\n", 5, 9),
        (b"\xef\xbb\xbfline\r\nlast", 0, 3),
        ("alpha = 'é'\n".encode(), 9, 10),
        (b"\x00\xff\x80\r\n", 0, 5),
        (b"no final newline", 3, 16),
        (b"", 0, 0),
        (b"last\n", 5, 5),
    ],
)
def test_range_receipt_preserves_original_bytes(
    tmp_path: Path, raw: bytes, start: int, end: int
) -> None:
    (tmp_path / "contract.proto").write_bytes(raw)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.source.range_receipt(
            "contract.proto", start_byte=start, end_byte=end
        )
        member, _ = codemap.source.member("contract.proto")
    content = assert_object(packet["content"])
    assert packet["schema"] == "hashmarks.source-range-receipt.v1"
    assert packet["member"] == member
    assert packet["range"] == {
        "coordinate_system": "zero-based-half-open-bytes",
        "start_byte": start,
        "end_byte": end,
    }
    assert content["encoding"] == "base64"
    assert (
        base64.b64decode(assert_text(content["data"]), validate=True) == raw[start:end]
    )
    assert content["byte_count"] == end - start
    assert content["digest"] == "sha256:" + hashlib.sha256(raw[start:end]).hexdigest()
    assert packet["source_byte_count"] == len(raw)
    assert packet["availability"] == "observed"
    assert packet["completeness"] == packet["truncation"] == "complete"
    assert packet["negative_evidence"] == "not-admissible"
    assert assert_text(packet["observation_identity"]).startswith("sha256:")


@pytest.mark.parametrize(
    ("start", "end", "max_bytes"),
    [
        (-1, 1, 10),
        (2, 1, 10),
        (False, 1, 10),
        (0, True, 10),
        (0, 1, False),
        (0, 1.5, 10),
        (0, 1, 0),
        (0, 1, 8_388_609),
    ],
)
def test_range_receipt_rejects_invalid_coordinates_before_member_access(
    tmp_path: Path, start: int, end: int, max_bytes: int
) -> None:
    with CodeMap(tmp_path) as codemap:
        with pytest.raises(ValueError, match="source range|max_bytes"):
            codemap.source.range_receipt(
                "missing.py", start_byte=start, end_byte=end, max_bytes=max_bytes
            )


@pytest.mark.parametrize(("start", "end"), [(0, 4), (4, 4)])
def test_range_receipt_rejects_out_of_member_bounds(
    tmp_path: Path, start: int, end: int
) -> None:
    (tmp_path / "example.py").write_bytes(b"# x")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with pytest.raises(ValueError, match="beyond the observed member"):
            codemap.source.range_receipt("example.py", start_byte=start, end_byte=end)


def test_range_identity_binds_full_revision_path_and_coordinates(
    tmp_path: Path,
) -> None:
    path = tmp_path / "first.py"
    path.write_bytes(b"# same same\n")
    (tmp_path / "second.py").write_bytes(path.read_bytes())
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.source.range_receipt("first.py", start_byte=2, end_byte=6)
        repeated = codemap.source.range_receipt(
            "first.py", start_byte=2, end_byte=6, max_bytes=100
        )
        moved = codemap.source.range_receipt("first.py", start_byte=7, end_byte=11)
        other_path = codemap.source.range_receipt("second.py", start_byte=2, end_byte=6)
        path.write_bytes(b"# same edit\n")
        unknown = codemap.source.range_receipt("first.py", start_byte=2, end_byte=6)
        codemap.index.sync()
        updated = codemap.source.range_receipt("first.py", start_byte=2, end_byte=6)
    assert repeated["observation_identity"] == before["observation_identity"]
    assert (
        moved["content"]
        == other_path["content"]
        == updated["content"]
        == before["content"]
    )
    assert (
        len(
            {
                row["observation_identity"]
                for row in (before, moved, other_path, updated)
            }
        )
        == 4
    )
    assert unknown["availability"] == "unavailable"
    assert assert_object(unknown["member"])["reason"] == "member-revision-mismatch"
    assert unknown["content"] is unknown["observation_identity"] is None
    assert unknown["completeness"] == "unknown"


def test_range_receipt_reuses_one_canonical_byte_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "example.py").write_bytes(b"# exact\r\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        read_bytes = codemap.source.file_store.read_bytes_stable
        reads: list[Path] = []

        def captured(path: Path) -> tuple[bytes, Digest]:
            reads.append(path)
            return read_bytes(path)

        monkeypatch.setattr(codemap.source.file_store, "read_bytes_stable", captured)
        packet = codemap.source.range_receipt("example.py", start_byte=0, end_byte=9)
    assert len(reads) == 1
    assert (
        base64.b64decode(assert_text(assert_object(packet["content"])["data"]))
        == b"# exact\r\n"
    )


def test_range_receipt_unavailable_members_never_publish_bytes(tmp_path: Path) -> None:
    (tmp_path / ".env").write_bytes(b"SECRET=private\n")
    (tmp_path / "large.py").write_bytes(b"# " + b"x" * 100)
    (tmp_path / "alias.py").symlink_to("large.py")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packets = [
            codemap.source.range_receipt(path, start_byte=0, end_byte=0, max_bytes=10)
            for path in (".env", "large.py", "alias.py", "missing.py")
        ]
    for packet in packets:
        assert packet["availability"] == "unavailable"
        assert packet["content"] is packet["observation_identity"] is None
        assert packet["completeness"] == packet["truncation"] == "unknown"
        assert packet["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize(
    ("generation_changed", "stale", "expected"),
    [
        (False, False, "current"),
        (False, True, "stale"),
        (False, None, "unknown"),
        (True, False, "stale"),
    ],
)
def test_range_completeness_never_strengthens_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    generation_changed: bool,
    stale: bool | None,
    expected: str,
) -> None:
    (tmp_path / "example.py").write_bytes(b"# exact\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        generation = codemap.source.store.generation()

        def status() -> tuple[int, int | None, bool | None]:
            return generation + int(generation_changed), None, stale

        monkeypatch.setattr(codemap.reads, "generation_status", status)
        packet = codemap.source.range_receipt("example.py", start_byte=0, end_byte=0)
    assert packet["availability"] == "observed"
    assert packet["completeness"] == "complete"
    assert packet["freshness"] == expected
    assert packet["negative_evidence"] == "not-admissible"
