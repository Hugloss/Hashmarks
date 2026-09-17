from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap


def _write_partial_fixture(root: Path) -> None:
    (root / "src").mkdir()
    for index in range(40):
        (root / "src" / f"m{index:02d}.py").write_text(
            f"def symbol_{index:02d}():\n    return {index}\n", encoding="utf-8"
        )


def _interrupt_after_one_committed_batch(
    codemap: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = codemap._parse_or_reuse
    calls = 0

    def interrupt(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 34:
            raise RuntimeError("synthetic mid-build interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(codemap, "_parse_or_reuse", interrupt)
    with pytest.raises(RuntimeError, match="synthetic mid-build interruption"):
        codemap.sync()
    assert codemap.status()["build"]["state"] == "BUILDING"
    assert len(codemap.store.paths()) == 32


def test_interrupted_generation_blocks_partial_query_surfaces_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_partial_fixture(tmp_path)
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as codemap:
        _interrupt_after_one_committed_batch(codemap, monkeypatch)

    message = r"CodeMap generation is incomplete \(BUILDING\)"
    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as reopened:
        assert reopened.status()["build"]["complete"] is False
        blocked = (
            lambda: reopened.find("symbol_00"),
            lambda: reopened.grep("symbol_00"),
            lambda: reopened.symbol("symbol_00"),
            lambda: reopened.outline("src/m00.py"),
            lambda: reopened.affected("src/m00.py"),
            lambda: reopened.repository_findings(["src/m00.py"]),
            lambda: reopened.task_action_map("change symbol_00"),
        )
        for query in blocked:
            with pytest.raises(RuntimeError, match=message):
                query()

        packet = reopened.task_decision_packet("change symbol_00")
        assert packet["identity"]["codemap_complete"] is False
        assert packet["identity"]["stale"] is True
        assert packet["context_budget"]["safe"] is False
        assert packet["discrimination"]["reason"] == "codemap-generation-incomplete"

        recovered = reopened.sync()
        assert recovered.build_state == "COMPLETE"
        assert len(reopened.store.paths()) == 40
        assert reopened.find("symbol_39")[0].path == "src/m39.py"
        assert reopened.outline("src/m39.py")["path"] == "src/m39.py"
