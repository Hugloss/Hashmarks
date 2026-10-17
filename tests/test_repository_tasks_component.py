"""Task convenience views share one observation and never call through CodeMap."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from contract_assertions import assert_object
from test_repository_index_component import index as index
from test_repository_ownership_component import _ownership

from hashmarks.codemap.context_cache import ContextCache
from hashmarks.codemap.evidence_verification import RepositoryVerification
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.repository_context import RepositoryContext
from hashmarks.codemap.repository_tasks import RepositoryTasks
from hashmarks.codemap.task_action_types import (
    _TaskActionMapContext,
    _TaskActionSelectionState,
)
from hashmarks.codemap.task_evidence_initial import decode_initial_packet


@pytest.fixture
def tasks(index: RepositoryIndex) -> Iterator[RepositoryTasks]:
    ownership = _ownership(index)
    verification = RepositoryVerification(ownership.source, ownership.imports)
    cache = ContextCache(index.workspace.parent / "task-context-cache")
    try:
        context = RepositoryContext(
            ownership.source, ownership.search, ownership.structure.relationships, cache
        )
        yield RepositoryTasks(
            ownership.search,
            ownership,
            verification,
            ownership.structure.relationships,
            context,
        )
    finally:
        cache.close()


def test_task_verification_view_observes_owner_once_and_preserves_source_fact(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (index.workspace / "owner.py").write_text("def calculate_total(): return 1\n")
    (index.workspace / "tests").mkdir()
    (index.workspace / "tests/test_total.py").write_text(
        "from owner import calculate_total\ndef test_total(): assert calculate_total() == 1\n"
    )
    index.sync()
    original = tasks.ownership.nominate
    nominations = 0

    def nominate(
        task: str, context: _TaskActionMapContext, limit: int, per_role: int
    ) -> _TaskActionSelectionState:
        nonlocal nominations
        nominations += 1
        return original(task, context, limit, per_role)

    monkeypatch.setattr(tasks.ownership, "nominate", nominate)
    graph = tasks.verification_ownership_graph("Change owner.calculate_total")
    assert nominations == 1
    assert graph["edit_candidates"] == ["owner.py"]
    assert graph["verification_owners"]


def test_task_input_is_reused_across_entry_and_action_views_in_one_scope(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    query = "Change owner.py"
    with tasks.reads.session():
        tasks.entry_points(query)
        before = tasks._task_observation(query, 20)
        tasks.action_map(query)
        after = tasks._task_observation(query, 20)
        assert before is after
        assert before.scope is tasks.reads.scope
    with tasks.reads.session():
        assert tasks._task_observation(query, 20) is not before


def test_root_has_no_retired_task_or_verifier_convenience_methods() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "task_action_map",
        "task_entry_points",
        "task_graph_adjacency",
        "task_relationships",
        "verification_relevance",
        "verification_ownership_graph",
        "explain_verification_selection",
        "verification_plan",
        "_decision_evidence_receipt",
        "task_evidence",
        "task_action_brief",
        "task_decision_packet",
        "task_decision_brief",
        "task_decision_brief_budget_sweep",
    ):
        assert not hasattr(CodeMap, name)


def test_packet_views_preserve_owner_identity_and_one_task_observation(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
) -> None:
    (index.workspace / "owner.py").write_text("def calculate_total(): return 1\n")
    (index.workspace / "tests").mkdir()
    (index.workspace / "tests/test_total.py").write_text(
        "from owner import calculate_total\ndef test_total(): assert calculate_total() == 1\n"
    )
    index.sync()
    query = "Change owner.calculate_total"
    with tasks.reads.session():
        packet = tasks.evidence(query)
        observation = tasks._task_observation(query, 20)
        initial = tasks.evidence(query, result_mode="initial")
        decoded = decode_initial_packet(initial)
        brief = tasks.decision_brief(query)
        assert tasks._task_observation(query, 20) is observation
    assert decoded["ownership"]["authority"] == packet["ownership"]["authority"]
    assert packet["ownership"]["owner"] is not None
    assert decoded["ownership"]["owner"]["path"] == packet["ownership"]["owner"]["path"]
    assert decoded["freshness"] == packet["freshness"]
    assert packet["verification"]["selected"] is not None
    assert (
        decoded["verification"]["selected"]["path"]
        == packet["verification"]["selected"]["path"]
    )
    assert assert_object(brief["edit"])["path"] == "owner.py"
    assert assert_object(brief["evidence_receipt"])["evidence_identity"]
