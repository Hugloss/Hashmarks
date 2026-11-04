from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_integer, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap.decision_session import (
    DecisionRefreshRequired,
    ReadScope,
    diagnostic_producer,
)

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


def test_wrapping_observe_in_a_diagnostic_session_cannot_reconcile_source_drift(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        generation = codemap.store.generation()
        with codemap.reads.session(diagnostics=True):
            (tmp_path / "src" / "owner.py").write_text(
                "def widget(value: str) -> str:\n    return value + '-new'\n",
                encoding="utf-8",
            )
            with pytest.raises(DecisionRefreshRequired):
                codemap.reads.observe(
                    lambda _scope: codemap.source.ensure_current("src/owner.py")
                )
            assert codemap.store.generation() == generation
        assert codemap.index.needs_reconcile("src/owner.py")


def test_observe_diagnostics_preserve_result_and_remain_opt_in(tmp_path: Path) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        plain = codemap.reads.observe(lambda _scope: codemap.changes.brief(task, paths))
        assert codemap.reads.diagnostics() is None
        observed = codemap.reads.observe(
            lambda _scope: codemap.changes.brief(task, paths), diagnostics=True
        )
        receipt = codemap.reads.diagnostics()

    assert observed == plain
    assert receipt is not None
    observation = assert_object(receipt["observation"])
    assert observation["outcome"] == "accepted"
    assert observation["session_outcome"] == "accepted"
    assert observation["attempts"] == 1
    assert observation["abandoned_attempts"] == 0
    assert observation["reconciliations"] == 0
    assert observation["reconciliation_time_ns"] == 0
    assert assert_integer(observation["wall_time_ns"]) >= assert_integer(
        receipt["wall_time_ns"]
    )
    assert assert_object(receipt["producers"])


def test_profiled_observe_reconciles_and_only_retains_the_accepted_session(
    tmp_path: Path,
) -> None:
    task, _paths = _repo(tmp_path)
    calls = 0
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        generation = codemap.store.generation()

        def operation(_scope: ReadScope) -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls == 1:
                (tmp_path / "src" / "owner.py").write_text(
                    "def widget(value: str) -> str:\n    return value + '-new'\n",
                    encoding="utf-8",
                )
            codemap.source.ensure_current("src/owner.py")
            codemap.tasks.action_map(task)
            return codemap.source.observe("src/owner.py")

        observed = codemap.reads.observe(operation, diagnostics=True)
        receipt = codemap.reads.diagnostics()
        assert observed == codemap.source.observe("src/owner.py")
        assert codemap.store.generation() > generation
        assert receipt is not None
        assert receipt["generation"] == codemap.store.generation()
        assert codemap.reads.depth == 0

    assert calls == 2
    observation = assert_object(receipt["observation"])
    assert observation["outcome"] == "accepted"
    assert observation["session_outcome"] == "accepted"
    assert observation["attempts"] == 2
    assert observation["abandoned_attempts"] == 1
    assert observation["reconciliations"] == 1
    assert assert_integer(observation["reconciliation_time_ns"]) > 0
    action = assert_object(
        assert_object(receipt["producers"])[
            "hashmarks.codemap.repository_tasks.RepositoryTasks.action_map"
        ]
    )
    assert action["calls"] == 1


def test_failed_observe_replaces_previous_successful_diagnostics(
    tmp_path: Path,
) -> None:
    task, _paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        codemap.reads.observe(lambda _scope: "previous success", diagnostics=True)

        def fail(_scope: ReadScope) -> None:
            codemap.tasks.action_map(task)
            raise LookupError("callback failure")

        with pytest.raises(LookupError, match="callback failure"):
            codemap.reads.observe(fail, diagnostics=True)
        receipt = codemap.reads.diagnostics()
        assert codemap.reads.depth == 0

    assert receipt is not None
    observation = assert_object(receipt["observation"])
    assert observation["outcome"] == "failed"
    assert observation["session_outcome"] == "failed"
    assert observation["attempts"] == 1
    assert assert_object(receipt["producers"])


def test_callback_return_does_not_accept_a_generation_change_on_session_exit(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    returned = object()
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()

        def change_generation(_scope: ReadScope) -> object:
            codemap.store.bump_generation()
            return returned

        with pytest.raises(RuntimeError, match="changed during decision session"):
            codemap.reads.observe(change_generation, diagnostics=True)
        receipt = codemap.reads.diagnostics()
        assert codemap.reads.depth == 0

    assert receipt is not None
    observation = assert_object(receipt["observation"])
    assert observation["outcome"] == "failed"
    assert observation["session_outcome"] == "failed"
    assert observation["abandoned_attempts"] == 0


def test_failed_reconciliation_keeps_the_session_explicitly_abandoned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()

        def fail_reconciliation(
            _path: str, *, expected_generation: int | None = None
        ) -> int:
            raise OSError("publication unavailable")

        monkeypatch.setattr(codemap.index, "reconcile_path", fail_reconciliation)

        def drift(_scope: ReadScope) -> None:
            (tmp_path / "src" / "owner.py").write_text(
                "def widget(value): return value + '-new'\n", encoding="utf-8"
            )
            codemap.source.ensure_current("src/owner.py")

        with pytest.raises(OSError, match="publication unavailable"):
            codemap.reads.observe(drift, diagnostics=True)
        receipt = codemap.reads.diagnostics()

    assert receipt is not None
    observation = assert_object(receipt["observation"])
    assert observation["outcome"] == "failed"
    assert observation["session_outcome"] == "abandoned"
    assert observation["attempts"] == 1
    assert observation["abandoned_attempts"] == 1
    assert observation["reconciliations"] == 0
    assert assert_integer(observation["reconciliation_time_ns"]) > 0


def test_repeated_source_drift_still_stops_after_one_reconciliation(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    calls = 0
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()

        def drift(_scope: ReadScope) -> None:
            nonlocal calls
            calls += 1
            (tmp_path / "src" / "owner.py").write_text(
                f"def widget(value): return value + {calls}\n", encoding="utf-8"
            )
            codemap.source.ensure_current("src/owner.py")

        with pytest.raises(RuntimeError, match="path remained stale after refresh"):
            codemap.reads.observe(drift, diagnostics=True)
        receipt = codemap.reads.diagnostics()
        assert codemap.reads.depth == 0

    assert calls == 2
    assert receipt is not None
    observation = assert_object(receipt["observation"])
    assert observation["outcome"] == "failed"
    assert observation["session_outcome"] == "abandoned"
    assert observation["attempts"] == 2
    assert observation["abandoned_attempts"] == 2
    assert observation["reconciliations"] == 1


@pytest.mark.parametrize("outer_diagnostics", [False, True])
def test_nested_explicit_profiling_fails_before_the_callback(
    tmp_path: Path, outer_diagnostics: bool
) -> None:
    _repo(tmp_path)
    called = False
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()

        def callback(_scope: ReadScope) -> None:
            nonlocal called
            called = True

        codemap.reads.observe(callback, diagnostics=True)
        previous = codemap.reads.diagnostics()
        called = False
        with codemap.reads.session(diagnostics=outer_diagnostics):
            with pytest.raises(ValueError, match="outermost read owner"):
                codemap.reads.observe(callback, diagnostics=True)
            assert codemap.reads.depth == 1
            assert codemap.reads.diagnostics() == previous

    assert not called


def test_default_nested_observation_inherits_outer_producer_instrumentation(
    tmp_path: Path,
) -> None:
    task, _paths = _repo(tmp_path)
    expected = object()
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()

        def inner(_scope: ReadScope) -> object:
            codemap.tasks.action_map(task)
            return expected

        result = codemap.reads.observe(
            lambda _scope: codemap.reads.observe(inner), diagnostics=True
        )
        receipt = codemap.reads.diagnostics()

    assert result is expected
    assert receipt is not None
    observation = assert_object(receipt["observation"])
    assert observation["outcome"] == "accepted"
    assert observation["attempts"] == 1
    assert assert_object(receipt["producers"])


def test_readiness_failure_cannot_return_a_previous_successful_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        codemap.reads.observe(lambda _scope: "previous success", diagnostics=True)

        def fail_readiness(*, _allow_incomplete: bool = False) -> None:
            raise RuntimeError("readiness unavailable")

        monkeypatch.setattr(codemap.index, "ensure_ready", fail_readiness)
        with pytest.raises(RuntimeError, match="readiness unavailable"):
            codemap.reads.observe(lambda _scope: "never called", diagnostics=True)
        assert codemap.reads.diagnostics() is None
        assert codemap.reads.depth == 0


def test_foreign_publication_after_refresh_is_rejected_when_profiled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        reconcile = codemap.index.reconcile_path

        def publish_another_generation(
            path: str, *, expected_generation: int | None = None
        ) -> int:
            generation = reconcile(path, expected_generation=expected_generation)
            codemap.store.bump_generation()
            return generation

        monkeypatch.setattr(codemap.index, "reconcile_path", publish_another_generation)

        def drift(_scope: ReadScope) -> None:
            (tmp_path / "src" / "owner.py").write_text(
                "def widget(value): return value + '-new'\n", encoding="utf-8"
            )
            codemap.source.ensure_current("src/owner.py")

        with pytest.raises(RuntimeError, match="changed before expected decision"):
            codemap.reads.observe(drift, diagnostics=True)
        receipt = codemap.reads.diagnostics()

    assert receipt is not None
    observation = assert_object(receipt["observation"])
    assert observation["outcome"] == "failed"
    assert observation["session_outcome"] == "failed"
    assert observation["attempts"] == 2
    assert observation["abandoned_attempts"] == 1
    assert observation["reconciliations"] == 1


def test_distinct_refreshes_retain_only_the_final_profile_and_scalar_costs(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    paths = ["src/owner.py", "src/other.py", "src/third.py"]
    for path in paths[1:]:
        (tmp_path / path).write_text("VALUE = 'old'\n", encoding="utf-8")
    calls = 0
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()

        def observe_paths(_scope: ReadScope) -> int:
            nonlocal calls
            if calls < len(paths):
                (tmp_path / paths[calls]).write_text(
                    "VALUE = 'changed'\n", encoding="utf-8"
                )
            calls += 1
            for path in paths:
                codemap.source.ensure_current(path)
            return calls

        result = codemap.reads.observe(observe_paths, diagnostics=True)
        receipt = codemap.reads.diagnostics()
        assert receipt is not None
        assert receipt["generation"] == codemap.store.generation()

    assert result == 4
    observation = assert_object(receipt["observation"])
    assert observation["outcome"] == "accepted"
    assert observation["session_outcome"] == "accepted"
    assert observation["attempts"] == 4
    assert observation["abandoned_attempts"] == 3
    assert observation["reconciliations"] == 3
    assert all(isinstance(value, (int, str)) for value in observation.values())
