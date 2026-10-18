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
