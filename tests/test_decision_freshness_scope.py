from __future__ import annotations

from pathlib import Path

from hashmarks.client import RepositoryObservation
from hashmarks.codemap.engine import CodeMap
from hashmarks.observation import ObservationState


def _map(tmp_path: Path) -> CodeMap:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "observation.py").write_text(
        "def repository_observation():\n    return 'clean'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_observation.py").write_text(
        "from src.observation import repository_observation\n\n"
        "def test_repository_observation():\n    assert repository_observation() == 'clean'\n",
        encoding="utf-8",
    )
    codemap = CodeMap(root, artifact_db=tmp_path / "artifacts.sqlite3")
    codemap.sync()
    generation = codemap.store.generation()
    codemap.store.set_meta("identity_generation", str(generation))
    return codemap


def _count_observations(codemap: CodeMap, monkeypatch) -> list[int]:
    generation = codemap.store.generation()
    calls: list[int] = []

    def sample() -> RepositoryObservation:
        calls.append(generation)
        return RepositoryObservation(
            state=ObservationState.CLEAN,
            generation=generation,
            dirty_paths=(),
            paths_complete=True,
            dirty_path_count=0,
        )

    monkeypatch.setattr(codemap, "_daemon_observation", sample)
    return calls


def test_find_task_reuses_one_freshness_sample_for_nested_find(tmp_path: Path, monkeypatch):
    codemap = _map(tmp_path)
    calls = _count_observations(codemap, monkeypatch)
    try:
        codemap.find_task("repository observation", limit=20)
        assert len(calls) == 1
    finally:
        codemap.close()


def test_context_reuses_one_freshness_sample_for_nested_find(tmp_path: Path, monkeypatch):
    codemap = _map(tmp_path)
    calls = _count_observations(codemap, monkeypatch)
    try:
        codemap.context("repository observation", token_budget=512, limit=20)
        assert len(calls) == 1
    finally:
        codemap.close()


def test_decision_packet_reuses_one_freshness_sample_for_nested_surfaces(tmp_path: Path, monkeypatch):
    codemap = _map(tmp_path)
    calls = _count_observations(codemap, monkeypatch)
    try:
        codemap.task_decision_packet("repository observation", limit=20, token_budget=512)
        assert len(calls) == 1
    finally:
        codemap.close()


def test_decision_session_still_fails_if_generation_changes(tmp_path: Path):
    codemap = _map(tmp_path)
    try:
        try:
            with codemap.decision_session():
                codemap.store.bump_generation()
        except RuntimeError as exc:
            assert "generation changed during decision session" in str(exc)
        else:
            raise AssertionError("decision session accepted a generation change")
    finally:
        codemap.close()


def test_task_evidence_uses_selection_and_closing_freshness_samples(tmp_path: Path, monkeypatch):
    codemap = _map(tmp_path)
    calls = _count_observations(codemap, monkeypatch)
    try:
        codemap.task_evidence("repository observation", limit=20, token_budget=512)
        assert len(calls) == 2
    finally:
        codemap.close()
