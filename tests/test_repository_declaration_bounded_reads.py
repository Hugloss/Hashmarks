"""Provider byte bounds survive qualification and final source rechecks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks import CodeMap
from hashmarks.codemap import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderError,
    RepositoryDeclarationProviderResult,
)
from hashmarks.digest import Digest


@dataclass(frozen=True)
class _BoundedProvider:
    name: str = "bounded-input"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return context.exists("input.txt")

    def discover(
        self, context: RepositoryDeclarationProviderContext
    ) -> RepositoryDeclarationProviderResult:
        raw = context.read_bytes("input.txt", max_bytes=4)
        return RepositoryDeclarationProviderResult(
            groups=(), provenance={"byte_count": len(raw)}
        )


def test_provider_input_keeps_its_bound_for_every_native_recheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "input.txt").write_bytes(b"tiny")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        native = repository.file_store.read_bytes_stable
        bounds: list[int | None] = []

        def observed(
            path: str | Path, *, max_attempts: int = 3, max_bytes: int | None = None
        ) -> tuple[bytes, Digest]:
            bounds.append(max_bytes)
            return native(path, max_attempts=max_attempts, max_bytes=max_bytes)

        monkeypatch.setattr(repository.file_store, "read_bytes_stable", observed)

        packet = repository.declarations.discover([_BoundedProvider()])

    inputs = assert_records(assert_records(packet["providers"])[0]["inputs"])
    assert inputs[0]["max_bytes"] == 4
    assert bounds == [4, 4, 4]


def test_oversized_provider_input_does_not_reach_an_unbounded_content_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "input.txt").write_bytes(b"oversized")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        native = repository.file_store.read_bytes_stable

        def observed(
            path: str | Path, *, max_attempts: int = 3, max_bytes: int | None = None
        ) -> tuple[bytes, Digest]:
            assert max_bytes == 4
            return native(path, max_attempts=max_attempts, max_bytes=max_bytes)

        monkeypatch.setattr(repository.file_store, "read_bytes_stable", observed)

        with pytest.raises(RepositoryDeclarationProviderError):
            repository.declarations.discover([_BoundedProvider()])
