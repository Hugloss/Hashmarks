"""Disclosure and cache ownership work without constructing the facade."""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_repository_index_component import index as index
from test_repository_relationships_component import _relationships

from hashmarks.codemap.context_cache import ContextCache
from hashmarks.codemap.find_engine import RepositorySearch
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.model import ContextDisclosure
from hashmarks.codemap.repository_context import RepositoryContext


@pytest.fixture
def context(index: RepositoryIndex) -> Iterator[RepositoryContext]:
    relationships = _relationships(index)
    search = RepositorySearch(relationships.source, relationships.native)
    cache = ContextCache(index.workspace.parent / "context-cache")
    try:
        yield RepositoryContext(relationships.source, search, relationships, cache)
    finally:
        cache.close()


def test_standalone_context_preserves_unknown_identity_and_reobserves_source(
    context: RepositoryContext,
) -> None:
    path = context.workspace / "owner.py"
    path.write_text("def owner():\n    return 'original'\n")
    context.source.index.sync()
    first = context.build("owner", disclosure=ContextDisclosure.SOURCE)
    assert first.items
    assert first.identity_generation is None
    assert first.stale is None
    assert first.cache_hit is False
    assert any("original" in item.content for item in first.items)

    path.write_text("def owner():\n    return 'replacement'\n")
    context.source.index.sync()
    second = context.build("owner", disclosure=ContextDisclosure.SOURCE)
    assert second.generation > first.generation
    assert any("replacement" in item.content for item in second.items)
    assert all("original" not in item.content for item in second.items)


def test_standalone_context_uses_search_only_to_nominate_instruction_paths(
    context: RepositoryContext,
) -> None:
    (context.workspace / "AGENTS.md").write_text("repository instructions\n")
    (context.workspace / "owner.py").write_text("def owner(): return 1\n")
    context.source.index.sync()
    packet = context.instruction_scope("owner.py")
    assert packet["seed_paths"] == ["owner.py"]
    assert packet["ranking_effect"] == "none"
    assert context.task("owner").items


def test_context_import_does_not_load_facade_or_task_authority() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.repository_context import RepositoryContext; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.ownership_graph' not in sys.modules; assert 'hashmarks.codemap.evidence_packet' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_failed_context_releases_flight_and_read_scope_before_retry(
    context: RepositoryContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (context.workspace / "owner.py").write_text("def owner(): return 1\n")
    context.source.index.sync()

    def unavailable(*args: object, **kwargs: object) -> None:
        raise RuntimeError("context producer unavailable")

    with monkeypatch.context() as failure:
        failure.setattr(context, "_context_impl", unavailable)
        with pytest.raises(RuntimeError, match="context producer unavailable"):
            context.build("owner", disclosure=ContextDisclosure.OUTLINE)
    assert context._context_flight.in_flight() == 0
    assert context.reads.depth == 0
    assert context.build("owner", disclosure=ContextDisclosure.OUTLINE).items


def test_root_has_no_retired_context_methods() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "context",
        "orient",
        "task_context",
        "task_context_plan",
        "work_context",
        "work_context_budget_sweep",
        "repository_instruction_scope",
        "_work_context_anchor",
    ):
        assert not callable(getattr(CodeMap, name, None))
