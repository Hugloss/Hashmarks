"""Ownership observations and proof have explicit lower repository inputs."""

import subprocess
import sys
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records
from test_repository_index_component import index as index
from test_repository_structure_component import _structure

from hashmarks.codemap.find_engine import RepositorySearch
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.ownership_graph import RepositoryOwnership
from hashmarks.codemap.query_router import normalize_task_query
from hashmarks.codemap.task_action_types import TaskObservation


def _ownership(index: RepositoryIndex) -> RepositoryOwnership:
    structure = _structure(index)
    search = RepositorySearch(structure.native)
    return RepositoryOwnership(structure.source, structure.imports, structure, search)


def test_standalone_ownership_observes_cache_owner_and_explicit_invalidator(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text(
        "from functools import lru_cache\n"
        "@lru_cache(maxsize=8)\ndef lookup(key): return key\n"
        "def reset(): lookup.cache_clear()\n"
    )
    index.sync()
    ownership = _ownership(index)
    owners = assert_records(ownership.cache_findings()["owners"])
    assert any(row["owner"] == "lookup" for row in owners)
    graph = ownership.cache_invalidation_graph()
    assert assert_object(graph["summary"])["invalidation_edges"] == 1
    assert any(
        row["relation"] == "invalidates-cache" for row in assert_records(graph["edges"])
    )


def test_ownership_rejects_candidate_reuse_after_its_read_scope_ends(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    ownership = _ownership(index)
    query = normalize_task_query("Change owner.py")
    with ownership.reads.session() as scope:
        observation = TaskObservation(
            query, ownership.search.observe_task(query.text), scope
        )
        context = ownership.observe_candidates(observation, 20)
        assert ownership.nominate(query.text, context, 20, 3).edit is not None
    with ownership.reads.session():
        with pytest.raises(RuntimeError, match="different read scope"):
            ownership.nominate(query.text, context, 20, 3)


def test_ownership_import_has_no_facade_tasks_or_verifier_dependency() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.ownership_graph import RepositoryOwnership; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_tasks' not in sys.modules; assert 'hashmarks.codemap.evidence_verification' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_root_has_no_retired_ownership_operations() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "repository_findings",
        "repository_ownership_graph",
        "ownership_relation_graph",
        "cache_ownership_findings",
        "cache_invalidation_ownership_graph",
        "concurrency_risk_findings",
        "import_ownership_findings",
        "_task_action_resolve_owner",
        "_task_action_projection_ambiguity_state",
    ):
        assert not hasattr(CodeMap, name)
