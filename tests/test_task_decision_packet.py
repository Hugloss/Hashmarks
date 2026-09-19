from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def test_decision_packet_does_not_require_discrimination_when_action_is_resolved(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adapter.py").write_text("class Adapter:\n    pass\n")
    (tmp_path / "tests" / "test_adapter.py").write_text(
        "from src.adapter import Adapter\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet("Adapter implementation test", limit=20)
    assert packet["edit"]["path"] == "src/adapter.py"
    assert packet["verify"]["path"] == "tests/test_adapter.py"
    assert packet["discrimination"]["needed"] is False
    assert packet["discrimination"]["reason"] == "resolved"
    metrics = packet["decision_metrics"]
    assert metrics["schema"] == "hashmarks.task-decision-metrics.v1"
    assert set(metrics["seconds"]) == {
        "action_map",
        "work_context",
        "verification_plan",
        "packet_assembly",
        "total",
    }
    assert all(value >= 0 for value in metrics["seconds"].values())


def test_decision_packet_requires_discrimination_when_no_supported_owner_exists(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_only.py").write_text("def test_widget():\n    pass\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet("widget test verification", limit=20)
    assert packet["edit"] is None
    assert packet["discrimination"]["needed"] is True
    assert packet["discrimination"]["reason"] == "no-supported-owner-candidate"


def test_structural_owner_resolution_does_not_admit_redundant_discrimination(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "engine.py").write_text(
        "def apply_widget(value):\n    return value + '-old'\n"
    )
    (tmp_path / "src" / "route.py").write_text(
        "from .engine import apply_widget\ndef handle_widget(value): return apply_widget(value)\n"
    )
    (tmp_path / "src" / "legacy.py").write_text(
        "def handle_widget(value): return value + '-old'\n"
    )
    (tmp_path / "tests" / "test_widget.py").write_text(
        "from src.route import handle_widget\ndef test_widget_contract(): assert handle_widget('x') == 'x-new'\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet(
            "Fix widget accepted response to '-new'", limit=20
        )
    assert packet["edit"]["path"] == "src/engine.py"
    assert packet["discrimination"]["needed"] is False
    assert packet["discrimination"]["reason"] == "resolved"


def test_decision_packet_exposes_provenance_bound_verification_selection(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adapter.py").write_text("class Adapter:\n    pass\n")
    (tmp_path / "tests" / "test_adapter.py").write_text(
        "from src.adapter import Adapter\ndef test_adapter(): assert Adapter\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet("Adapter implementation test", limit=20)

    membership = packet["verification_membership"]
    envelope = packet["verification_selection_envelope"]
    assert membership["member_count"] == 1
    assert membership["members"][0]["path"] == "tests/test_adapter.py"
    assert membership["membership_identity"].startswith("sha256:")
    assert (
        envelope["selection"]["membership_identity"]
        == membership["membership_identity"]
    )
    assert (
        envelope["repository"]["repository_identity"]
        == packet["identity"]["repository_identity"]
    )
    assert (
        envelope["repository"]["source_identity"]
        == packet["identity"]["source_identity"]
    )
    assert (
        packet["identity"]["verification_membership_identity"]
        == membership["membership_identity"]
    )
    assert (
        packet["identity"]["verification_selection_envelope_identity"]
        == envelope["envelope_identity"]
    )


def test_repeated_stable_query_reproduces_selection_identities(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adapter.py").write_text("class Adapter:\n    pass\n")
    (tmp_path / "tests" / "test_adapter.py").write_text(
        "from src.adapter import Adapter\ndef test_adapter(): assert Adapter\n"
    )
    state = tmp_path / ".hm-state"
    artifact_db = state / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifact_db) as codemap:
        codemap.sync()
        first = codemap.task_decision_packet("Adapter implementation test", limit=20)
        second = codemap.task_decision_packet("Adapter implementation test", limit=20)

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifact_db) as codemap:
        third = codemap.task_decision_packet("Adapter implementation test", limit=20)

    for packet in (second, third):
        assert (
            packet["identity"]["verification_membership_identity"]
            == first["identity"]["verification_membership_identity"]
        )
        assert (
            packet["identity"]["verification_selection_envelope_identity"]
            == first["identity"]["verification_selection_envelope_identity"]
        )
        assert (
            packet["downstream_verification_contract"]["provenance_hash"]
            == first["downstream_verification_contract"]["provenance_hash"]
        )


def test_decision_packet_is_observation_not_consumer_decision(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adapter.py").write_text("class Adapter:\n    pass\n")
    (tmp_path / "tests" / "test_adapter.py").write_text(
        "from src.adapter import Adapter\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet("Adapter implementation test", limit=20)

    assert packet["authority"] == "repository-observation-only"
    assert packet["consumer_action"] == "external"
    assert packet["discrimination"]["interpretation"] == (
        "evidence-discrimination-only"
    )
