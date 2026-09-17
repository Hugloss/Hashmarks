from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks import CodeMap

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
        codemap.sync()
        with codemap.decision_session(diagnostics=True):
            codemap.change_intelligence_brief(task, paths)
            codemap.evidence_freshness_map(task, paths)
            snapshot = codemap.repository_intelligence_snapshot(task, paths)
            codemap.repository_intelligence_profile(task, paths, profile="compact")
            codemap.intelligence_economics_receipt(task, paths)
            codemap.repository_intelligence_delta(
                task, paths, previous_snapshot=snapshot
            )
        receipt = codemap.decision_session_diagnostics()

    assert receipt is not None
    assert receipt["schema"] == "hashmarks.decision-session-diagnostics.v1"
    assert receipt["wall_time_ns"] > 0
    assert receipt["authority"] == "runtime-diagnostics-only"
    assert receipt["storage"] == "derived-not-persisted"
    assert receipt["execution_effect"] == "none"
    producers = receipt["producers"]
    assert producers["change_intelligence_brief"]["calls"] >= 1
    assert producers["evidence_freshness_map"]["calls"] >= 1
    assert producers["task_action_map"]["calls"] >= 1
    assert producers["repository_intelligence_snapshot"]["calls"] >= 1
    assert (
        producers["task_action_map"]["inclusive_ns"]
        >= producers["task_action_map"]["exclusive_ns"]
    )
    assert receipt["reuse"]["task_action_hit"] >= 1
    assert receipt["reuse"]["snapshot_hit"] >= 1
    assert receipt["spans"]
    assert any(row["parent_id"] is not None for row in receipt["spans"])


def test_diagnostics_classifies_duplicate_semantic_producer_requests(
    tmp_path: Path,
) -> None:
    task, _ = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with codemap.decision_session(diagnostics=True):
            codemap.task_action_map(task)
            codemap.task_action_map(task)
            codemap.task_action_map(task, limit=21)
        receipt = codemap.decision_session_diagnostics()

    assert receipt is not None
    action = receipt["producers"]["task_action_map"]
    assert action["calls"] == 3
    assert action["unique_requests"] == 2
    assert action["duplicate_calls"] == 1
    assert receipt["reuse"]["task_action_hit"] == 1
    assert receipt["reuse"]["task_action_miss"] == 2


def test_diagnostics_are_opt_in_and_do_not_change_output(tmp_path: Path) -> None:
    task, paths = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        plain = codemap.change_intelligence_brief(task, paths)
        assert codemap.decision_session_diagnostics() is None
        with codemap.decision_session(diagnostics=True):
            observed = codemap.change_intelligence_brief(task, paths)
        receipt = codemap.decision_session_diagnostics()

    assert observed == plain
    assert receipt is not None


def test_diagnostics_receipt_is_detached_from_internal_state(tmp_path: Path) -> None:
    task, _ = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with codemap.decision_session(diagnostics=True):
            codemap.task_action_map(task)
        first = codemap.decision_session_diagnostics()
        assert first is not None
        first["producers"].clear()
        second = codemap.decision_session_diagnostics()

    assert second is not None
    assert "task_action_map" in second["producers"]
