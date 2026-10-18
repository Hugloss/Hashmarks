"""Read scopes reuse one authority without owning task decisions or a facade."""

import subprocess
import sys
from pathlib import Path

import pytest
from test_repository_index_component import index as index

from hashmarks.codemap.decision_session import DecisionScope, ReadScope
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex


def _reads(index: RepositoryIndex) -> DecisionScope:
    (index.workspace / "owner.py").write_text("def owner(): pass\n")
    index.sync()
    return DecisionScope(index)


def test_nested_scopes_share_the_same_read_binding(index: RepositoryIndex) -> None:
    reads = _reads(index)
    with reads.session() as outer:
        assert isinstance(outer, ReadScope)
        assert reads.depth == 1
        with reads.session(expected_generation=outer.generation) as inner:
            assert inner is outer
            assert reads.depth == 2
            assert reads.scope is inner
        assert reads.depth == 1
    assert reads.depth == 0
    assert reads.scope is None


def test_equal_repository_generations_do_not_reuse_an_ended_scope(
    index: RepositoryIndex,
) -> None:
    reads = _reads(index)
    with reads.session() as first:
        reads.symbols_for_path("owner.py")
        reads.symbols_for_path("owner.py")
        assert reads.stats()["symbols_hit"] == 1
    with reads.session() as second:
        assert second.generation == first.generation
        assert second is not first
        reads.symbols_for_path("owner.py")
        assert reads.stats()["symbols_miss"] == 1
        assert reads.stats()["symbols_hit"] == 0


def test_scope_rejects_generation_change_and_releases_its_state(
    index: RepositoryIndex,
) -> None:
    reads = _reads(index)
    with pytest.raises(
        RuntimeError, match="generation changed during decision session"
    ):
        with reads.session():
            index.store.bump_generation()
    assert reads.scope is None
    assert reads.depth == 0


def test_wrong_nested_expected_generation_does_not_destroy_the_outer_scope(
    index: RepositoryIndex,
) -> None:
    reads = _reads(index)
    with reads.session() as outer:
        with pytest.raises(
            RuntimeError, match="changed before expected decision session"
        ):
            with reads.session(expected_generation=outer.generation + 1):
                pytest.fail("wrong generation was admitted")
        assert reads.scope is outer
        assert reads.depth == 1


def test_symbol_projection_bound_does_not_truncate_later_path_evidence(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "a.py").write_text("def first(): pass\ndef second(): pass\n")
    (index.workspace / "z.py").write_text("def last(): pass\n")
    index.sync()
    reads = DecisionScope(index)
    paths = ["z.py", "a.py", "z.py", "missing.py"]
    expected = index.store.symbols_for_paths(paths, limit=20)
    with reads.session():
        assert reads.symbols_for_paths(paths, limit=1) == expected[:1]
        assert reads.symbols_for_paths(list(reversed(paths)), limit=20) == expected
        assert [row["name"] for row in reads.symbols_for_path("z.py")] == ["last"]
        assert reads.symbols_for_paths([], limit=20) == []
        assert reads.stats()["store_symbols_for_paths_complete"] == 1
    (index.workspace / "z.py").write_text("def replacement(): pass\n")
    index.sync()
    with reads.session():
        assert [row["name"] for row in reads.symbols_for_path("z.py")] == [
            "replacement"
        ]


def test_lexical_frequency_reuse_is_normalized_and_ends_with_its_scope(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "a.txt").write_text("alpha alpha beta\n")
    (index.workspace / "b.txt").write_text("alpha\n")
    index.sync()
    reads = DecisionScope(index)
    with reads.session():
        total, frequencies = reads.lexical_document_frequencies(["Alpha", "beta"])
        assert total == 2
        assert frequencies == {"alpha": 2, "beta": 1}
        assert reads.lexical_document_frequencies(["beta", "alpha", "Alpha"]) == (
            total,
            frequencies,
        )
        assert reads.stats()["store_lexical_document_frequencies"] == 1
        assert reads.lexical_document_frequencies(["beta"]) == (2, {"beta": 1})
        assert reads.stats()["store_lexical_document_frequencies"] == 2
    (index.workspace / "b.txt").write_text("beta\n")
    index.sync()
    with reads.session():
        assert reads.lexical_document_frequencies(["alpha", "beta"]) == (
            2,
            {"alpha": 1, "beta": 2},
        )
        assert reads.stats()["store_lexical_document_frequencies"] == 1


def test_scope_import_does_not_load_task_composition_or_facade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.decision_session import DecisionScope; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.task_retrieval' not in sys.modules; assert 'hashmarks.codemap.evidence_packet' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_final_task_reuse_is_scoped_by_its_domain(tmp_path: Path) -> None:
    from hashmarks.codemap import CodeMap

    (tmp_path / "owner.py").write_text("def owner(): pass\n")
    with CodeMap(
        tmp_path,
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as repository:
        repository.index.sync()
        with repository.reads.session() as first:
            repository.tasks.action_map("inspect owner")
            repository.tasks.action_map("inspect owner")
            assert repository.reads.stats()["task_action_hit"] == 1
        with repository.reads.session() as second:
            assert first.generation == second.generation
            repository.tasks.action_map("inspect owner")
            assert repository.reads.stats()["task_action_hit"] == 0
            assert repository.reads.stats()["task_action_miss"] == 1


def test_root_does_not_keep_retired_read_scope_aliases() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "decision_session",
        "decision_session_stats",
        "_session_file_row",
        "_ensure_map_ready",
        "_repository_packet_identity",
    ):
        assert not hasattr(CodeMap, name)


def test_diagnostic_failure_releases_the_completed_scope_and_allows_a_fresh_read(
    index: RepositoryIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = _reads(index)
    original_stats = reads.stats

    def unavailable_stats() -> dict[str, int]:
        raise RuntimeError("diagnostic counters unavailable")

    monkeypatch.setattr(reads, "stats", unavailable_stats)
    failed_scope: ReadScope | None = None
    with pytest.raises(RuntimeError, match="diagnostic counters unavailable"):
        with reads.session(diagnostics=True) as failed_scope:
            assert reads.symbols_for_path("owner.py")[0]["name"] == "owner"
    assert failed_scope is not None
    assert reads.depth == 0
    assert reads.scope is None
    assert reads.generation is None
    assert reads.observation is None
    monkeypatch.setattr(reads, "stats", original_stats)
    with reads.session() as fresh_scope:
        assert fresh_scope is not failed_scope
        assert reads.symbols_for_path("owner.py")[0]["name"] == "owner"
        assert reads.stats()["symbols_hit"] == 0
        assert reads.stats()["symbols_miss"] == 1


def test_failed_diagnostic_collection_does_not_publish_an_older_receipt(
    index: RepositoryIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = _reads(index)
    with reads.session(diagnostics=True):
        reads.symbols_for_path("owner.py")
    assert reads.diagnostics() is not None

    def unavailable_stats() -> dict[str, int]:
        raise RuntimeError("diagnostic counters unavailable")

    monkeypatch.setattr(reads, "stats", unavailable_stats)
    with pytest.raises(RuntimeError, match="diagnostic counters unavailable"):
        with reads.session(diagnostics=True):
            reads.symbols_for_path("owner.py")
    assert reads.diagnostics() is None
    assert reads.scope is None
    assert reads.generation is None


def test_diagnostic_startup_failure_does_not_publish_a_scope(
    index: RepositoryIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = _reads(index)
    original_reset = index.store.reset_read_counters

    def unavailable_counters() -> None:
        raise RuntimeError("diagnostic counters unavailable at entry")

    monkeypatch.setattr(index.store, "reset_read_counters", unavailable_counters)
    with pytest.raises(RuntimeError, match="diagnostic counters unavailable at entry"):
        with reads.session(diagnostics=True):
            pytest.fail("session entered after failed diagnostic initialization")
    assert reads.depth == 0
    assert reads.scope is None
    assert reads.generation is None
    assert reads.observation is None
    monkeypatch.setattr(index.store, "reset_read_counters", original_reset)
    with reads.session() as scope:
        assert scope.generation == index.store.generation()
        assert reads.depth == 1
