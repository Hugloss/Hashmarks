"""Candidate retrieval and reuse are independent of task authority and Context."""

import subprocess
import sys
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_records
from test_repository_index_component import index as index
from test_repository_native_component import _native

from hashmarks.codemap.find_engine import RepositorySearch
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.model import SearchHit


def _search(index: RepositoryIndex) -> RepositorySearch:
    native = _native(index)
    return RepositorySearch(native)


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


@pytest.mark.parametrize(
    ("query", "source"),
    [
        ("部署順序", "def 部署順序(): return 1\n"),
        ("räkna", "def räkna(): return 1\n"),
        ("testé", "def testé(): return 1\n"),
        ("Διατάξεις", "def Διατάξεις(): return 1\n"),
        ("Réconcile.données", "class Réconcile:\n    def données(self): return 1\n"),
    ],
)
def test_exact_unicode_symbol_queries_retrieve_indexed_owners(
    index: RepositoryIndex, query: str, source: str
) -> None:
    (index.workspace / "owner.py").write_text(source, encoding="utf-8")
    index.sync()

    packet = _search(index).packet(query)

    assert any(
        row["path"] == "owner.py" and row["qualname"] == query
        for row in assert_records(packet["results"])
    )
    assert packet["query_intent"] == "identifier"
    assert packet["observed_exact_match_count"] == 1
    assert packet["scope"] == "indexed-visible-symbol-surface"
    assert packet["negative_evidence"] == "not-applicable"
    assert packet["uniqueness_evidence"] == "not-admissible"
    assert packet["freshness"] == "unknown"


def test_missing_unicode_symbol_preserves_unknown_freshness_qualification(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text(
        "def 部署順序(): return 1\n", encoding="utf-8"
    )
    index.sync()

    packet = _search(index).packet("未定義")

    assert packet["query_intent"] == "identifier"
    assert packet["observed_exact_match_count"] == 0
    assert packet["negative_evidence"] == "not-admissible"
    assert packet["freshness"] == "unknown"


@pytest.mark.parametrize(("count", "limit"), [(101, 1), (1025, 2048)])
def test_bounded_unicode_symbol_lookup_preserves_incompleteness(
    index: RepositoryIndex, count: int, limit: int
) -> None:
    for number in range(count):
        (index.workspace / f"owner_{number:03}.py").write_text(
            "def Διατάξεις(): return 1\n", encoding="utf-8"
        )
    index.sync()

    packet = _search(index).packet("Διατάξεις", limit=limit)

    assert 0 < len(assert_records(packet["results"])) < count
    omissions = assert_array(packet["omissions"])
    assert "find-exact-symbol-limit" in omissions
    assert packet["completeness"] == "incomplete"
    assert packet["uniqueness_evidence"] in {"not-admissible", "not-applicable"}


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


def test_retrieval_diagnostic_binds_replays_to_the_reconciled_generation(
    index: RepositoryIndex,
) -> None:
    source = index.workspace / "owner.py"
    source.write_text("def original(): return 1\n")
    index.sync()
    search = _search(index)
    query = "original implementation"
    search.find_task(query)
    before = index.store.generation()
    source.write_text("def replacement(): return 2\n")

    packet = search.retrieval_stability(query, repeats=2)

    assert index.store.generation() > before
    assert packet["generation"] == index.store.generation()
    assert packet["stable"] is True
    assert packet["divergences"] == []
    assert all(hit.qualname != "original" for hit in search.find_task(query))
    assert any(hit.qualname == "replacement" for hit in search.find("replacement"))


def test_retrieval_diagnostic_rejects_publication_between_replays(
    index: RepositoryIndex,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    search = _search(index)
    original = search.find_task
    calls = 0

    def publish_after_first_replay(
        task: str, *, limit: int = 20
    ) -> tuple[SearchHit, ...]:
        nonlocal calls
        result = original(task, limit=limit)
        calls += 1
        if calls == 1:
            with index.store.publication_transaction():
                index.store.bump_generation()
        return result

    monkeypatch.setattr(search, "find_task", publish_after_first_replay)
    with pytest.raises(RuntimeError, match="generation changed"):
        search.retrieval_stability("owner", repeats=2)
    assert search.reads.scope is None
    assert search.reads.depth == 0


def test_retrieval_explanation_reconciles_cached_selected_source(
    index: RepositoryIndex,
) -> None:
    original = index.workspace / "owner.py"
    original.write_text("def original(): return 1\n")
    index.sync()
    search = _search(index)
    query = "original implementation"
    assert search.find_task(query)
    generation = index.store.generation()
    original.write_text("def replacement(): return 2\n")
    (index.workspace / "current.py").write_text("def original(): return 3\n")
    index.sync(["current.py"])

    packet = search.explain_retrieval(query)

    assert packet["generation"] == index.store.generation() > generation + 1
    assert [row["path"] for row in assert_records(packet["selected"])] == [
        hit.path for hit in search.find_task(query)
    ]
    assert any(hit.qualname == "replacement" for hit in search.find("replacement"))
    assert packet["ranking_effect"] == "none"


def test_retrieval_explanation_rejects_publication_between_selected_and_lanes(
    index: RepositoryIndex,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    search = _search(index)
    original = search.task_query_views

    def publish_after_views(task: str) -> dict[str, str]:
        views = original(task)
        with index.store.publication_transaction():
            index.store.bump_generation()
        return views

    monkeypatch.setattr(search, "task_query_views", publish_after_views)
    with pytest.raises(RuntimeError, match="generation changed"):
        search.explain_retrieval("owner")
    assert search.reads.scope is None
    assert search.reads.depth == 0


def test_failed_retrieval_replay_preserves_canonical_results_and_releases_scope(
    index: RepositoryIndex,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    search = _search(index)
    baseline = search.find_task("owner")
    original = search.find_task
    calls = 0

    def fail_second_replay(task: str, *, limit: int = 20) -> tuple[SearchHit, ...]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("replay unavailable")
        return original(task, limit=limit)

    with monkeypatch.context() as failure:
        failure.setattr(search, "find_task", fail_second_replay)
        with pytest.raises(RuntimeError, match="replay unavailable"):
            search.retrieval_stability("owner", repeats=2)

    assert search.reads.scope is None
    assert search.reads.depth == 0
    assert search.find_task("owner") == baseline
    assert search.retrieval_stability("owner", repeats=2)["stable"] is True


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
