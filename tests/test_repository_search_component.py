"""Candidate retrieval and reuse are independent of task authority and Context."""

import subprocess
import sys
from pathlib import Path

import pytest
from test_repository_index_component import index as index
from test_repository_native_component import _native

from hashmarks.codemap.find_engine import RepositorySearch
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex


def _search(index: RepositoryIndex) -> RepositorySearch:
    native = _native(index)
    return RepositorySearch(native.source, native)


def test_standalone_search_reobserves_cached_source_after_an_unsignaled_edit(
    index: RepositoryIndex,
) -> None:
    source = index.workspace / "owner.py"
    source.write_text("def calculate_total(): return 1\n")
    index.sync()
    search = _search(index)
    assert any(
        hit.qualname == "calculate_total" for hit in search.find("calculate_total")
    )
    first = search.find_task("calculate_total")
    assert any(hit.qualname == "calculate_total" for hit in first)
    generation = index.store.generation()

    source.write_text("def replacement(): return 2\n")
    search.prepare_task("calculate_total", 20)
    after = search.find_task("calculate_total")
    assert index.store.generation() > generation
    assert all(hit.qualname != "calculate_total" for hit in after)
    assert any(hit.qualname == "replacement" for hit in search.find("replacement"))


def test_standalone_search_does_not_promote_unknown_freshness_to_negative_evidence(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    packet = _search(index).packet("CompletelyAbsentSymbol")
    assert packet["observed_exact_match_count"] == 0
    assert packet["negative_evidence"] == "not-admissible"
    assert packet["freshness"] == "unknown"


def test_search_import_does_not_load_context_tasks_or_facade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.find_engine import RepositorySearch; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_context' not in sys.modules; assert 'hashmarks.codemap.evidence_packet' not in sys.modules; assert 'hashmarks.codemap.ownership_candidates' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_failed_search_releases_flight_and_read_scope_before_retry(
    index: RepositoryIndex,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    search = _search(index)

    def unavailable(*args: object, **kwargs: object) -> None:
        raise RuntimeError("query producer unavailable")

    with monkeypatch.context() as failure:
        failure.setattr(search, "_find_compose", unavailable)
        with pytest.raises(RuntimeError, match="query producer unavailable"):
            search.find("owner")
    assert search._find_flight.in_flight() == 0
    assert search.reads.depth == 0
    assert any(hit.qualname == "owner" for hit in search.find("owner"))


def test_root_has_no_retired_retrieval_operations() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "find",
        "find_packet",
        "find_task",
        "task_query_views",
        "query_route",
        "formulate_task_query",
        "retrieval_stability",
        "explain_task_retrieval",
        "_prepare_task_observation",
        "_score",
    ):
        assert not hasattr(CodeMap, name)
