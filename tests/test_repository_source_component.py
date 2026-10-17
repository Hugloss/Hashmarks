"""Canonical source facts work without retrieval or a CodeMap facade."""

import subprocess
import sys
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records, assert_text
from test_repository_index_component import index as index

from hashmarks.codemap.decision_session import DecisionScope
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.repository_source import RepositorySource


def _source(index: RepositoryIndex) -> RepositorySource:
    reads = DecisionScope(index, index.store, index._observation_source)
    return RepositorySource(index.files, index, reads, index.store, index.file_store)


def test_source_observes_an_admitted_unindexed_member(index: RepositoryIndex) -> None:
    path = index.workspace / "contract.proto"
    path.write_text("message Contract { string needle = 1; }\n")
    source = _source(index)
    packet = source.observe("contract.proto", literal="needle")
    member = assert_object(packet["member"])
    assert member["state"] == "known-present"
    assert member["index_state"] == "unindexed"
    assert packet["observed_match_count"] == 1
    assert index.store.file_row("contract.proto") is None


def test_source_outlines_and_discloses_the_same_indexed_revision(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    source = _source(index)
    outline = source.outline("owner.py")
    body = source.read("owner.py::owner")
    assert assert_text(outline["outline"]).startswith("def owner")
    assert body["content"] == "def owner(): return 1"
    assert assert_records(outline["symbols"])[0]["name"] == "owner"


def test_consumer_cannot_mutate_later_source_evidence_in_a_scope(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    source = _source(index)
    with source.reads.session():
        first = source.outline("owner.py")
        assert_records(first["symbols"])[0]["name"] = "invented_owner"
        second = source.outline("owner.py")
        assert assert_records(second["symbols"])[0]["name"] == "owner"


def test_instruction_scope_needs_only_explicit_paths(index: RepositoryIndex) -> None:
    (index.workspace / "AGENTS.md").write_text("root instructions\n")
    (index.workspace / "owner.py").write_text("def owner(): pass\n")
    index.sync()
    value = _source(index).instruction_scope("owner.py", query="owner.py")
    assert value["seed_paths"] == ["owner.py"]
    assert [row["path"] for row in assert_records(value["authority"])] == ["AGENTS.md"]
    assert value["scope_source"] == "explicit-path"
    assert value["ranking_effect"] == "none"


def test_source_import_has_no_facade_search_or_task_dependency() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.repository_source import RepositorySource; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.task_retrieval' not in sys.modules; assert 'hashmarks.codemap.evidence_packet' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "name",
    [
        "outline",
        "source_observation",
        "_repository_member_observation",
        "_source_slice",
    ],
)
def test_retired_root_source_operations_are_removed(name: str) -> None:
    from hashmarks.codemap import CodeMap

    assert not callable(getattr(CodeMap, name, None))
