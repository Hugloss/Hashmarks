"""Exercise ingestion and readiness without the facade or upper evidence owners."""

import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path

import pytest

from hashmarks.client import DaemonUnavailableError, RepositoryObservation
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.codemap.repository_file_discovery import RepositoryFiles
from hashmarks.codemap.repository_index_store import ArtifactStore, WorkspaceMapStore
from hashmarks.codemap.repository_observation import RepositoryObservationSource
from hashmarks.file_store import FileDigestStore


class _UnavailableReader:
    def repository_observation(self) -> RepositoryObservation:
        raise DaemonUnavailableError("no identity observation available")


@pytest.fixture
def index(tmp_path: Path) -> Iterator[RepositoryIndex]:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    with ExitStack() as resources:
        store = WorkspaceMapStore(tmp_path / "state/codemap.sqlite3")
        resources.callback(store.close)
        store.bind_workspace(workspace)
        digests = FileDigestStore(tmp_path / "state/identity.sqlite3")
        resources.callback(digests.close)
        artifacts = ArtifactStore(tmp_path / "artifacts.sqlite3")
        resources.callback(artifacts.close)
        yield RepositoryIndex(
            RepositoryFiles(workspace),
            store,
            digests,
            artifacts,
            range_provider=TreeSitterRangeProvider(),
            observation_source=RepositoryObservationSource(_UnavailableReader()),
        )


def test_standalone_index_ingests_reuses_and_reconciles_exact_source(
    index: RepositoryIndex,
) -> None:
    source = index.workspace / "owner.py"
    source.write_text("def original(): return 1\n")
    first = index.sync()
    assert first.parsed_artifacts == 1
    assert index.store.symbol("original")
    assert index.is_current("owner.py")
    warm = index.sync()
    assert warm.parsed_artifacts == 0
    assert warm.reused_artifacts == 1

    source.write_text("def replacement(): return 2\n")
    assert index.needs_reconcile("owner.py")
    index.reconcile_path("owner.py")
    assert index.store.generation() > first.generation
    assert not index.store.symbol("original")
    assert index.store.symbol("replacement")
    assert index.is_current("owner.py")


def test_readiness_does_not_repair_an_incomplete_build(index: RepositoryIndex) -> None:
    (index.workspace / "owner.py").write_text("def owner(): pass\n")
    index.sync()
    generation = index.store.generation()
    index.store.set_meta("sync.build_state", "BUILDING")
    with pytest.raises(RuntimeError, match="generation is incomplete"):
        index.ensure_ready()
    assert index.ensure_ready(_allow_incomplete=True) is None
    assert index.store.meta("sync.build_state") == "BUILDING"
    assert index.store.generation() == generation
    index.sync()
    assert index.store.meta("sync.build_state") == "COMPLETE"


def test_member_reconciliation_rejects_a_competing_publication_before_writing(
    index: RepositoryIndex,
) -> None:
    source = index.workspace / "owner.py"
    source.write_text("def original(): return 1\n")
    first = index.sync()
    source.write_text("def replacement(): return 2\n")
    with index.store.publication_transaction():
        index.store.bump_generation()
    competing_generation = index.store.generation()

    with pytest.raises(RuntimeError, match="changed before expected decision session"):
        index.reconcile_path("owner.py", expected_generation=first.generation)

    assert index.store.generation() == competing_generation
    assert index.store.symbol("original")
    assert not index.store.symbol("replacement")
    published = index.reconcile_path(
        "owner.py", expected_generation=competing_generation
    )
    assert published == index.store.generation() > competing_generation
    assert index.store.symbol("replacement")


def test_admission_and_index_support_remain_separate(index: RepositoryIndex) -> None:
    (index.workspace / "owner.py").write_text("def owner(): pass\n")
    (index.workspace / "contract.proto").write_text("message Contract {}\n")
    assert {item.rel for item in index.files.iter_files()} == {
        "owner.py",
        "contract.proto",
    }
    result = index.sync()
    assert result.discovered == 1
    assert index.store.file_row("owner.py") is not None
    assert index.store.file_row("contract.proto") is None


def test_failed_clear_preserves_published_rows_and_generation(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): pass\n")
    index.sync()
    before = (index.store.stats(), index.store.generation(), index.store.meta_items())
    index.store._db.execute(
        "CREATE TRIGGER reject_symbol_delete BEFORE DELETE ON symbol "
        "BEGIN SELECT RAISE(ABORT, 'deliberate clear failure'); END"
    )
    index.store._db.commit()
    with pytest.raises(sqlite3.IntegrityError, match="deliberate clear failure"):
        index.clean()
    after = (index.store.stats(), index.store.generation(), index.store.meta_items())
    assert after == before
    assert index.store.symbol("owner")


def test_index_import_does_not_load_upper_components_or_facade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.indexing_lifecycle import RepositoryIndex; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.evidence_graph' not in sys.modules; assert 'hashmarks.codemap.repository_source' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_root_does_not_keep_retired_index_operations() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "sync",
        "index_preflight",
        "watch_forever",
        "clean",
        "_parse_or_reuse",
        "_refresh_path_current",
    ):
        assert not hasattr(CodeMap, name)
