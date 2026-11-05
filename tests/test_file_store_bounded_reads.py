"""Byte-returning observations enforce their budget before accumulation."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, cast

import pytest

from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.file_store import FileDigestStore, FileReadBoundError


@pytest.fixture
def store(tmp_path: Path) -> Iterator[FileDigestStore]:
    native = FileDigestStore(tmp_path / "identity.sqlite3")
    try:
        yield native
    finally:
        native.close()


@pytest.mark.parametrize("raw", [b"", b"exact"])
def test_exact_transfer_bound_retains_the_same_bytes_and_native_digest(
    tmp_path: Path, store: FileDigestStore, raw: bytes
) -> None:
    path = tmp_path / "member.bin"
    path.write_bytes(raw)

    observed, digest = store.read_bytes_stable(path, max_bytes=len(raw))

    assert observed == raw
    assert digest == hash_bytes(raw, domain=FILE_DOMAIN)


def test_known_oversized_source_is_refused_before_opening_its_contents(
    tmp_path: Path, store: FileDigestStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "member.bin"
    path.write_bytes(b"oversized")

    def forbidden_open(_path: Path, _mode: str = "r") -> BinaryIO:
        raise AssertionError("known oversized source contents must not be opened")

    monkeypatch.setattr(Path, "open", forbidden_open)

    with pytest.raises(FileReadBoundError):
        store.read_bytes_stable(path, max_bytes=4)


class _TrackingReader:
    def __init__(self, stream: BinaryIO, returned: list[int]) -> None:
        self.stream = stream
        self.returned = returned

    def read(self, size: int = -1) -> bytes:
        assert 0 <= size <= 5, "growth cannot turn a bounded transfer into a full read"
        data = self.stream.read(size)
        self.returned.append(len(data))
        return data


def test_growth_after_preflight_cannot_accumulate_the_oversized_member(
    tmp_path: Path, store: FileDigestStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "member.bin"
    path.write_bytes(b"tiny")
    native_open = Path.open
    returned: list[int] = []

    @contextmanager
    def grow_before_open(
        selected: Path, mode: str = "r"
    ) -> Generator[_TrackingReader, None, None]:
        assert selected == path and mode == "rb"
        with native_open(path, "wb") as writer:
            writer.write(b"oversized after metadata observation")
        with native_open(path, mode) as stream:
            yield _TrackingReader(cast(BinaryIO, stream), returned)

    monkeypatch.setattr(Path, "open", grow_before_open)

    with pytest.raises(FileReadBoundError):
        store.read_bytes_stable(path, max_bytes=4)

    assert sum(returned) <= 5


@pytest.mark.parametrize("bound", [-1, True, 1.5])
def test_invalid_transfer_bound_is_rejected_before_source_observation(
    tmp_path: Path, store: FileDigestStore, bound: int
) -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        store.read_bytes_stable(tmp_path / "missing", max_bytes=bound)
