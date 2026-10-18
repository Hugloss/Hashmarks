from pathlib import Path

import pytest
from contract_assertions import assert_object

from hashmarks.codemap import CodeMap
from hashmarks.codemap.model import ParsedArtifact


def _write_partial_fixture(root: Path) -> None:
    (root / "src").mkdir()
    for index in range(40):
        (root / "src" / f"m{index:02d}.py").write_text(
            f"def symbol_{index:02d}():\n    return {index}\n", encoding="utf-8"
        )


def _interrupt_after_one_staged_batch(
    codemap: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = codemap.index._parse_or_reuse
    calls = 0

    def interrupt(
        rel: str, path: Path, language: str, digest_hash: str
    ) -> tuple[ParsedArtifact, bool]:
        nonlocal calls
        calls += 1
        if calls == 34:
            raise RuntimeError("synthetic mid-build interruption")
        return original(rel, path, language, digest_hash)

    monkeypatch.setattr(codemap.index, "_parse_or_reuse", interrupt)
    with pytest.raises(RuntimeError, match="synthetic mid-build interruption"):
        codemap.index.sync()
    assert assert_object(codemap.views.status()["build"])["state"] == "NEVER_SYNCED"
    assert codemap.store.paths() == set()


def test_interrupted_generation_never_publishes_partial_rows_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_partial_fixture(tmp_path)
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as codemap:
        _interrupt_after_one_staged_batch(codemap, monkeypatch)

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as reopened:
        assert (
            assert_object(reopened.views.status()["build"])["state"] == "NEVER_SYNCED"
        )
        assert reopened.store.paths() == set()
        assert reopened.search.find("symbol_00")[0].path == "src/m00.py"
        assert assert_object(reopened.views.status()["build"])["complete"] is True
        assert len(reopened.store.paths()) == 40
        assert reopened.search.find("symbol_39")[0].path == "src/m39.py"
        assert reopened.source.outline("src/m39.py")["path"] == "src/m39.py"
