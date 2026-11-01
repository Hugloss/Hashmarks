"""Durable indexes converge when canonical source-language coverage expands."""

from pathlib import Path

import pytest
from contract_assertions import assert_present

from hashmarks import CodeMap
from hashmarks.codemap.source_languages import SOURCE_LANGUAGES


def test_reopen_discovers_new_source_suffixes_before_query_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    (workspace / "existing.py").write_text("value = 1\n", encoding="utf-8")
    for suffix in (".mts", ".cts"):
        (workspace / f"new{suffix}").write_text(
            "export function added(): number { return 1; }\n", encoding="utf-8"
        )
    state = tmp_path / "state"
    with monkeypatch.context() as legacy:
        for suffix in (".mts", ".cts"):
            legacy.delitem(SOURCE_LANGUAGES, suffix)
        with CodeMap(workspace, state_dir=state) as repository:
            repository.index.sync()
            before = repository.store.generation()
            scope_identity = repository.store.meta(
                "analysis_scope_conformance_identity"
            )
            assert repository.store.file_row("new.mts") is None
            assert repository.store.file_row("new.cts") is None

    with CodeMap(workspace, state_dir=state) as repository:
        repository.reads.ready()

        for path in ("new.mts", "new.cts"):
            assert assert_present(repository.store.file_row(path))["language"] == (
                "typescript"
            )
        assert (
            repository.store.meta("analysis_scope_conformance_identity")
            != scope_identity
        )
        reconciled = repository.store.generation()
        assert reconciled > before

        repository.reads.ready()

        assert repository.store.generation() == reconciled
