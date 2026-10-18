"""Ingestion must bind parsed structure to the bytes it actually observed."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

import pytest
from contract_assertions import assert_records, assert_text

from hashmarks.codemap import CodeMap
from hashmarks.codemap.model import CODEMAP_SCHEMA, EvidenceVisibility
from hashmarks.codemap.parsers import parse_source, parser_signature
from hashmarks.digest import FILE_DOMAIN, Digest, hash_bytes
from hashmarks.file_store import UnstableFileError


def _source(name: str, language: str) -> bytes:
    if language == "python":
        return f"def {name}():\n    return {name!r}\n".encode()
    return f"export function {name}() {{ return {name!r}; }}\n".encode()


def _names(codemap: CodeMap, path: str) -> list[str]:
    return [
        assert_text(row["name"])
        for row in assert_records(codemap.source.outline(path)["symbols"])
    ]


@pytest.mark.parametrize(
    "language,filename", [("python", "owner.py"), ("typescript", "owner.ts")]
)
def test_source_change_after_hash_never_poison_artifact_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    filename: str,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    source = workspace / filename
    before = _source("original_owner", language)
    after = _source("replacement_owner", language)
    source.write_bytes(before)
    state, artifacts = tmp_path / "state", tmp_path / "artifacts.sqlite3"
    with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as codemap:
        digest_files = codemap.file_store.digest_many_info

        def replace_after_hash(
            files: Iterable[tuple[str | Path, str]],
            *,
            workspace: str | Path,
            force: bool = False,
        ) -> dict[str, tuple[Digest, bool]]:
            result = digest_files(files, workspace=workspace, force=force)
            source.write_bytes(after)
            return result

        with monkeypatch.context() as transition:
            transition.setattr(
                codemap.file_store, "digest_many_info", replace_after_hash
            )
            codemap.index.sync()
        assert _names(codemap, filename) == ["replacement_owner"]
        assert (
            codemap.source.outline(filename)["file_digest"]
            == hash_bytes(after, domain=FILE_DOMAIN).hash
        )
        source.write_bytes(before)
        codemap.index.sync(paths=[filename])
        assert _names(codemap, filename) == ["original_owner"]
        assert (
            codemap.source.outline(filename)["file_digest"]
            == hash_bytes(before, domain=FILE_DOMAIN).hash
        )

    with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as reopened:
        reopened.index.sync()
        assert _names(reopened, filename) == ["original_owner"]

    other = tmp_path / "other"
    other.mkdir()
    (other / filename).write_bytes(before)
    with CodeMap(
        other, state_dir=tmp_path / "other-state", artifact_db=artifacts
    ) as shared:
        shared.index.sync()
        assert _names(shared, filename) == ["original_owner"]


@pytest.mark.parametrize("failure", ["deleted", "unavailable", "unstable"])
def test_source_unavailable_after_hash_never_publishes_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    source = workspace / "owner.py"
    source.write_bytes(_source("original_owner", "python"))
    with CodeMap(
        workspace,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        digest_files = codemap.file_store.digest_many_info

        def fail_after_hash(
            files: Iterable[tuple[str | Path, str]],
            *,
            workspace: str | Path,
            force: bool = False,
        ) -> dict[str, tuple[Digest, bool]]:
            result = digest_files(files, workspace=workspace, force=force)
            if failure == "deleted":
                source.unlink()
            return result

        def unreadable(
            path: str | Path, *, max_attempts: int = 3
        ) -> tuple[bytes, Digest]:
            if failure == "unstable":
                raise UnstableFileError("controlled moving source")
            raise PermissionError("controlled unavailable source")

        monkeypatch.setattr(codemap.file_store, "digest_many_info", fail_after_hash)
        if failure != "deleted":
            monkeypatch.setattr(codemap.file_store, "read_bytes_stable", unreadable)
        result = codemap.index.sync()
        assert result.skipped == 1
        assert result.warnings
        assert codemap.store.file_row("owner.py") is None


def test_warm_ingestion_reuses_artifact_without_source_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "owner.py"
    source.write_bytes(_source("original_owner", "python"))
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".state",
        artifact_db=tmp_path / ".state/artifacts.sqlite3",
    ) as codemap:
        first = codemap.index.sync()

        def unexpected_read(
            path: str | Path, *, max_attempts: int = 3
        ) -> tuple[bytes, Digest]:
            raise AssertionError("unchanged ingestion must reuse qualified artifact")

        monkeypatch.setattr(codemap.file_store, "read_bytes_stable", unexpected_read)
        second = codemap.index.sync()
        assert second.generation == first.generation
        assert second.parsed_artifacts == 0
        assert second.reused_artifacts == 1


def test_legacy_misbound_artifact_is_not_reused_after_reopen(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    before = _source("original_owner", "python")
    (workspace / "owner.py").write_bytes(before)
    revision = hash_bytes(before, domain=FILE_DOMAIN).hash
    state, artifacts = tmp_path / "state", tmp_path / "artifacts.sqlite3"
    with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as seed:
        payload = json.dumps(
            {
                "schema": CODEMAP_SCHEMA,
                "parser": parser_signature("python", seed.index.range_provider),
                "file_digest": revision,
                "language": "python",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        legacy_key = hashlib.sha256(
            b"hashmarks.codemap-artifact.v1\0" + payload
        ).hexdigest()
        poisoned = replace(
            parse_source(
                _source("wrong_owner", "python").decode(),
                file_digest=revision,
                language="python",
                range_provider=seed.index.range_provider,
            ),
            artifact_key=legacy_key,
        )
        seed.artifacts.put(poisoned)
        seed.store.set_file(
            "owner.py",
            poisoned,
            module_name="owner",
            visibility=EvidenceVisibility.SOURCE,
            index_surface="source",
        )
    with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as reopened:
        reopened.index.sync()
        assert _names(reopened, "owner.py") == ["original_owner"]
        assert reopened.source.outline("owner.py")["file_digest"] == revision
