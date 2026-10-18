from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_integer, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap.decision_session import diagnostic_producer

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> tuple[str, list[str]]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "owner.py").write_text(
        "def widget(value: str) -> str:\n    return value + '-old'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\n\n"
        "def test_widget():\n    assert widget('x') == 'x-new'\n",
        encoding="utf-8",
    )
    return "fix widget behavior and verify owner test", ["src/owner.py"]


def test_opt_in_decision_session_diagnostics_reports_composition_and_reuse(
    tmp_path: Path,
) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session(diagnostics=True):
            codemap.changes.brief(task, paths)
            codemap.changes.freshness_map(task, paths)
            snapshot = codemap.changes.snapshot(task, paths)
            codemap.views.profile(task, paths, profile="compact")
            codemap.economics.receipt(task, paths)
            codemap.changes.delta(task, paths, previous_snapshot=snapshot)
        receipt = codemap.reads.diagnostics()

    assert receipt is not None
    assert receipt["schema"] == "hashmarks.decision-session-diagnostics.v1"
    assert assert_integer(receipt["wall_time_ns"]) > 0
    assert receipt["authority"] == "runtime-diagnostics-only"
    assert receipt["storage"] == "derived-not-persisted"
    assert receipt["execution_effect"] == "none"
    producers = assert_object(receipt["producers"])
    assert (
        assert_integer(
            assert_object(
                producers[
                    "hashmarks.codemap.repository_changes.RepositoryChanges.brief"
                ]
            )["calls"]
        )
        >= 1
    )
    assert (
        assert_integer(
            assert_object(
                producers[
                    "hashmarks.codemap.repository_changes.RepositoryChanges.freshness_map"
                ]
            )["calls"]
        )
        >= 1
    )
    assert (
        assert_integer(
            assert_object(
                producers[
                    "hashmarks.codemap.repository_tasks.RepositoryTasks.action_map"
                ]
            )["calls"]
        )
        >= 1
    )
    assert (
        assert_integer(
            assert_object(
                producers[
                    "hashmarks.codemap.repository_changes.RepositoryChanges.snapshot"
                ]
            )["calls"]
        )
        >= 1
    )
    assert assert_integer(
        assert_object(
            producers["hashmarks.codemap.repository_tasks.RepositoryTasks.action_map"]
        )["inclusive_ns"]
    ) >= assert_integer(
        assert_object(
            producers["hashmarks.codemap.repository_tasks.RepositoryTasks.action_map"]
        )["exclusive_ns"]
    )
    assert assert_integer(assert_object(receipt["reuse"])["task_action_hit"]) >= 1
    assert assert_integer(assert_object(receipt["reuse"])["snapshot_hit"]) >= 1
    assert receipt["spans"]
    assert any(row["parent_id"] is not None for row in assert_records(receipt["spans"]))


def test_diagnostics_classifies_duplicate_semantic_producer_requests(
    tmp_path: Path,
) -> None:
    task, _ = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session(diagnostics=True):
            codemap.tasks.action_map(task)
            codemap.tasks.action_map(task)
            codemap.tasks.action_map(task, limit=21)
        receipt = codemap.reads.diagnostics()

    assert receipt is not None
    action = assert_object(
        assert_object(receipt["producers"])[
            "hashmarks.codemap.repository_tasks.RepositoryTasks.action_map"
        ]
    )
    assert action["calls"] == 3
    assert action["unique_requests"] == 2
    assert action["duplicate_calls"] == 1
    assert assert_integer(assert_object(receipt["reuse"])["task_action_hit"]) == 1
    assert assert_object(receipt["reuse"])["task_action_miss"] == 2


def test_diagnostics_are_opt_in_and_do_not_change_output(tmp_path: Path) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        plain = codemap.changes.brief(task, paths)
        assert codemap.reads.diagnostics() is None
        with codemap.reads.session(diagnostics=True):
            observed = codemap.changes.brief(task, paths)
        receipt = codemap.reads.diagnostics()

    assert observed == plain
    assert receipt is not None


def test_diagnostics_receipt_is_detached_from_internal_state(tmp_path: Path) -> None:
    task, _ = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session(diagnostics=True):
            codemap.tasks.action_map(task)
        first = codemap.reads.diagnostics()
        assert first is not None
        assert_object(first["producers"]).clear()
        second = codemap.reads.diagnostics()

    assert second is not None
    assert (
        "hashmarks.codemap.repository_tasks.RepositoryTasks.action_map"
        in assert_object(second["producers"])
    )


def test_same_named_operations_from_distinct_owners_have_separate_measurements(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        source_observe = diagnostic_producer(type(codemap.source).observe)
        bindings_observe = diagnostic_producer(type(codemap.bindings).observe)
        with codemap.reads.session(diagnostics=True):
            source_observe(codemap.source, "src/owner.py")
            source_observe(codemap.source, "src/owner.py")
            bindings_observe(
                codemap.bindings,
                [
                    {
                        "binding_id": "diagnostic",
                        "evidence": [{"scope": "member", "path": "src/owner.py"}],
                    }
                ],
                include_relationships=False,
            )
        receipt = codemap.reads.diagnostics()

    assert receipt is not None
    producers = assert_object(receipt["producers"])
    source_name = "hashmarks.codemap.repository_source.RepositorySource.observe"
    bindings_name = (
        "hashmarks.codemap.repository_evidence_bindings.RepositoryBindings.observe"
    )
    assert set(producers) == {source_name, bindings_name}
    source = assert_object(producers[source_name])
    bindings = assert_object(producers[bindings_name])
    assert (source["calls"], source["unique_requests"], source["duplicate_calls"]) == (
        2,
        1,
        1,
    )
    assert (
        bindings["calls"],
        bindings["unique_requests"],
        bindings["duplicate_calls"],
    ) == (1, 1, 0)
    assert {row["producer"] for row in assert_records(receipt["spans"])} == {
        source_name,
        bindings_name,
    }


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_diagnostic_span_truncation_reports_actual_omission(
    tmp_path: Path, offset: int
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session(diagnostics=True):
            pass
        initial = codemap.reads.diagnostics()
        assert initial is not None
        bound = assert_integer(initial["span_limit"])
        count = bound + offset
        with codemap.reads.session(diagnostics=True):
            for _ in range(count):
                with codemap.reads.diagnostic_span("bounded", (), {}):
                    pass
        receipt = codemap.reads.diagnostics()

    assert receipt is not None
    assert len(assert_records(receipt["spans"])) == min(count, bound)
    assert receipt["spans_truncated"] is (count > bound)
    assert (
        assert_object(assert_object(receipt["producers"])["bounded"])["calls"] == count
    )
