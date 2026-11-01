"""Content observations never promote signatures or pointers to validated assets."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import pytest
from contract_assertions import assert_object

from hashmarks import CodeMap
from hashmarks.codemap.repository_observation import evidence_identity
from hashmarks.codemap.source_content import (
    SOURCE_CONTENT_SCHEMA,
    source_content_observation,
)

_MEMBER = {"path": "asset.bin", "state": "known-present", "member_revision": "abc"}
_POINTER = (
    b"version https://git-lfs.github.com/spec/v1\n"
    b"oid sha256:" + b"a" * 64 + b"\nsize 434782\n"
)


@pytest.mark.parametrize(
    ("raw", "kind", "media"),
    [
        (b"\x89PNG\r\n\x1a\n", "binary", "image/png"),
        (b"\xff\xd8\xff", "binary", "image/jpeg"),
        (b"GIF89a", "binary", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBP", "binary", "image/webp"),
        (b"%PDF-1.7", "binary", "application/pdf"),
        (b"PK\x05\x06", "binary", "application/zip"),
        (b"\x1f\x8b", "binary", "application/gzip"),
        (b"plain text", "text", None),
        (b"", "text", None),
        (b"binary\x00bytes", "binary", None),
        (b"\xff", "binary", None),
    ],
)
def test_signature_observation_is_not_integrity_validation(
    raw: bytes, kind: str, media: str | None
) -> None:
    content = source_content_observation(_MEMBER, raw)
    assert content["state"] == "observed"
    assert content["kind"] == kind
    assert content["byte_count"] == len(raw)
    assert content["media_type"] == media
    assert content["media_type_basis"] == (
        "signature-only" if media is not None else "not-established"
    )
    assert content["integrity"] == "not-validated"
    assert content["lfs"] is None


def test_pointer_size_and_oid_are_declarations_not_observed_object_bytes() -> None:
    content = source_content_observation(_MEMBER, _POINTER)
    assert content["kind"] == "lfs-pointer"
    assert content["byte_count"] == len(_POINTER)
    assert content["media_type"] is None
    assert content["lfs"] == {
        "state": "pointer",
        "oid": "sha256:" + "a" * 64,
        "size": 434782,
        "object_bytes_observed": False,
    }
    identity = content.pop("evidence_identity")
    assert identity == evidence_identity(SOURCE_CONTENT_SCHEMA, content)


@pytest.mark.parametrize(
    "pointer",
    [
        _POINTER.replace(b"size 434782", b"size -1"),
        _POINTER.replace(b"size 434782", b"size 0434782"),
        _POINTER.replace(b"sha256:", b"sha1:"),
        _POINTER.replace(b"spec/v1", b"spec/v2"),
        _POINTER.replace(b"\n", b"\r\n"),
        _POINTER + b"extension opaque\n",
        _POINTER[:-1],
    ],
)
def test_unsupported_pointer_syntax_is_not_ordinary_text(pointer: bytes) -> None:
    content = source_content_observation(_MEMBER, pointer)
    assert content["state"] == "unavailable"
    assert content["kind"] == "unknown"
    assert content["byte_count"] == len(pointer)
    assert content["reason"] == "lfs-pointer-syntax-unsupported"
    assert content["lfs"] == {
        "state": "unqualified-pointer",
        "object_bytes_observed": False,
    }


@pytest.mark.parametrize("state", ["unsupported", "unknown", "known-absent"])
def test_unqualified_members_cannot_acquire_content_authority(state: str) -> None:
    member = {**_MEMBER, "state": state, "reason": "member-unavailable"}
    content = source_content_observation(member, b"\x89PNG\r\n\x1a\n")
    assert content["state"] == "unavailable"
    assert content["kind"] == "unknown"
    assert content["byte_count"] is None
    assert content["media_type"] is None
    assert content["source_member"] == member
    assert content["reason"] == "member-unavailable"


def test_public_source_keeps_binary_metadata_separate_from_text_availability(
    tmp_path: Path,
) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".hashmarks",
        artifact_db=tmp_path / ".hashmarks/artifacts.sqlite3",
    ) as repository:
        repository.index.sync()
        observed = repository.source.observe("image.png")
    content = assert_object(observed["content"])
    assert observed["availability"] == "unsupported"
    assert content["state"] == "observed"
    assert content["media_type"] == "image/png"
    assert content["source_member"] == observed["member"]


def test_public_source_preserves_denied_missing_and_bounded_content(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "large.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".hashmarks",
        artifact_db=tmp_path / ".hashmarks/artifacts.sqlite3",
    ) as repository:
        repository.index.sync()
        denied = repository.source.observe(".env")
        missing = repository.source.observe("missing.png")
        bounded = repository.source.observe("large.png", max_bytes=8)
    for observed in (denied, missing, bounded):
        content = assert_object(observed["content"])
        assert content["state"] == "unavailable"
        assert content["kind"] == "unknown"
        assert content["byte_count"] is None
        assert content["source_member"] == observed["member"]
    assert assert_object(missing["member"])["state"] == "known-absent"
    assert assert_object(bounded["content"])["reason"] == "source-size-bound"


def test_public_source_distinguishes_pointer_and_materialized_content(
    tmp_path: Path,
) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(_POINTER)
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".hashmarks",
        artifact_db=tmp_path / ".hashmarks/artifacts.sqlite3",
    ) as repository:
        repository.index.sync()
        pointer = assert_object(repository.source.observe("image.png")["content"])
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        repository.index.sync()
        image_content = assert_object(repository.source.observe("image.png")["content"])
    assert pointer["kind"] == "lfs-pointer"
    assert image_content["kind"] == "binary"
    assert image_content["lfs"] is None
    assert pointer["evidence_identity"] != image_content["evidence_identity"]
    assert (
        assert_object(pointer["source_member"])["member_revision"]
        != (assert_object(image_content["source_member"])["member_revision"])
    )


def test_unreadable_source_cannot_return_signature_or_pointer_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    def unavailable(_path: Path) -> NoReturn:
        raise OSError("source unavailable")

    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".hashmarks",
        artifact_db=tmp_path / ".hashmarks/artifacts.sqlite3",
    ) as repository:
        repository.index.sync()
        monkeypatch.setattr(repository.file_store, "read_bytes_stable", unavailable)
        observed = repository.source.observe("image.png")
    content = assert_object(observed["content"])
    assert assert_object(observed["member"])["state"] == "unknown"
    assert content["state"] == "unavailable"
    assert content["byte_count"] is None
    assert content["media_type"] is None
    assert content["reason"] == "member-read-unstable-or-unavailable"


def test_unreconciled_content_replacement_keeps_revision_mismatch_unknown(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 'old'\n", encoding="utf-8")
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".hashmarks",
        artifact_db=tmp_path / ".hashmarks/artifacts.sqlite3",
    ) as repository:
        repository.index.sync()
        before = assert_object(repository.source.observe("source.py")["content"])
        source.write_bytes(b"\x89PNG\r\n\x1a\n")
        after = assert_object(repository.source.observe("source.py")["content"])
    assert before["kind"] == "text"
    assert after["state"] == "unavailable"
    assert after["kind"] == "unknown"
    assert after["reason"] == "member-revision-mismatch"
    assert after["media_type"] is None
