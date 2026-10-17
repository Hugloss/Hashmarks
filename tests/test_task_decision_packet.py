from __future__ import annotations

from typing import TYPE_CHECKING

from contract_assertions import assert_array, assert_number, assert_object, assert_text

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def test_decision_packet_discriminates_unproven_ranked_candidate(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adapter.py").write_text("class Adapter:\n    pass\n")
    (tmp_path / "tests" / "test_adapter.py").write_text(
        "from src.adapter import Adapter\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.task_decision_packet("Adapter implementation test", limit=20)
    assert assert_object(packet["edit"])["path"] == "src/adapter.py"
    assert assert_object(packet["verify"])["path"] == "tests/test_adapter.py"
    discrimination = assert_object(packet["discrimination"])
    assert discrimination["needed"] is True
    assert discrimination["reason"] == "ownership-unresolved"
    assert assert_object(packet["ownership_authority"])["owner_resolved"] is False
    metrics = assert_object(packet["decision_metrics"])
    assert metrics["schema"] == "hashmarks.task-decision-metrics.v1"
    seconds = assert_object(metrics["seconds"])
    assert set(seconds) == {
        "action_map",
        "work_context",
        "verification_plan",
        "packet_assembly",
        "total",
    }
    assert all(assert_number(value) >= 0 for value in seconds.values())


def test_decision_packet_requires_discrimination_when_no_supported_owner_exists(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_only.py").write_text("def test_widget():\n    pass\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.task_decision_packet("widget test verification", limit=20)
    assert packet["edit"] is None
    discrimination = assert_object(packet["discrimination"])
    assert discrimination["needed"] is True
    assert discrimination["reason"] == "no-supported-owner-candidate"


def test_structural_candidate_without_authority_requires_discrimination(
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
        codemap.index.sync()
        packet = codemap.task_decision_packet(
            "Fix widget accepted response to '-new'", limit=20
        )
    assert assert_object(packet["edit"])["path"] == "src/engine.py"
    assert assert_object(packet["ownership_authority"])["owner_resolved"] is False
    discrimination = assert_object(packet["discrimination"])
    assert discrimination["needed"] is True
    assert discrimination["reason"] == "ownership-unresolved"


def test_decision_packet_build_guard_overrides_action_discrimination(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/adapter.py").write_text("class Adapter:\n    pass\n")
    (tmp_path / "tests/test_adapter.py").write_text(
        "from src.adapter import Adapter\ndef test_adapter(): assert Adapter\n"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.task_action_map("Adapter implementation test", limit=20)
        assert action["action_discrimination"]["reason"] == "ownership-unresolved"
        result = codemap._decision_packet_discrimination(
            action=action,
            verify=action["verify"],
            build={"complete": False},
        )

    assert result["needed"] is True
    assert result["reason"] == "codemap-generation-incomplete"


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
        codemap.index.sync()
        packet = codemap.task_decision_packet("Adapter implementation test", limit=20)

    membership = assert_object(packet["verification_membership"])
    envelope = assert_object(packet["verification_selection_envelope"])
    assert membership["member_count"] == 1
    assert (
        assert_object(assert_array(membership["members"])[0])["path"]
        == "tests/test_adapter.py"
    )
    assert assert_text(membership["membership_identity"]).startswith("sha256:")
    assert (
        assert_object(envelope["selection"])["membership_identity"]
        == membership["membership_identity"]
    )
    assert (
        assert_object(envelope["repository"])["repository_identity"]
        == assert_object(packet["identity"])["repository_identity"]
    )
    assert (
        assert_object(envelope["repository"])["source_identity"]
        == assert_object(packet["identity"])["source_identity"]
    )
    assert (
        assert_object(packet["identity"])["verification_membership_identity"]
        == membership["membership_identity"]
    )
    assert (
        assert_object(packet["identity"])["verification_selection_envelope_identity"]
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
        codemap.index.sync()
        first = codemap.task_decision_packet("Adapter implementation test", limit=20)
        second = codemap.task_decision_packet("Adapter implementation test", limit=20)

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifact_db) as codemap:
        third = codemap.task_decision_packet("Adapter implementation test", limit=20)

    for packet in (second, third):
        assert (
            assert_object(packet["identity"])["verification_membership_identity"]
            == assert_object(first["identity"])["verification_membership_identity"]
        )
        assert (
            assert_object(packet["identity"])[
                "verification_selection_envelope_identity"
            ]
            == assert_object(first["identity"])[
                "verification_selection_envelope_identity"
            ]
        )
        assert (
            assert_object(packet["downstream_verification_contract"])["provenance_hash"]
            == assert_object(first["downstream_verification_contract"])[
                "provenance_hash"
            ]
        )


def test_decision_packet_is_observation_not_consumer_decision(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adapter.py").write_text("class Adapter:\n    pass\n")
    (tmp_path / "tests" / "test_adapter.py").write_text(
        "from src.adapter import Adapter\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.task_decision_packet("Adapter implementation test", limit=20)

    assert packet["authority"] == "repository-observation-only"
    assert packet["consumer_action"] == "external"
    assert assert_object(packet["discrimination"])["interpretation"] == (
        "evidence-discrimination-only"
    )


def test_decision_packet_preserves_explicit_owner_with_named_dependency(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/publish.py").write_text(
        "def publish_result(value):\n    return value\n", encoding="utf-8"
    )
    (tmp_path / "src/authority.py").write_text(
        "class AuthorityReceipt:\n"
        "    def canonical_identity(self):\n"
        "        return 'canonical'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_publish.py").write_text(
        "from src.publish import publish_result\n"
        "def test_publish(): assert publish_result('x') == 'x'\n",
        encoding="utf-8",
    )
    task = "Fix publish_result so it uses AuthorityReceipt.canonical_identity"

    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.task_decision_packet(task, limit=20, token_budget=256)

    assert assert_object(packet["edit"])["path"] == "src/publish.py"
    assert assert_object(packet["ambiguity"])["ambiguous"] is False
    discrimination = assert_object(packet["discrimination"])
    assert discrimination["needed"] is False
    assert discrimination["reason"] == "resolved"


def test_leading_dependency_context_does_not_steal_explicit_edit_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/publish.py").write_text(
        "def publish_result(value):\n    return value\n", encoding="utf-8"
    )
    (tmp_path / "src/authority.py").write_text(
        "class AuthorityReceipt:\n    canonical_identity = 'canonical'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_publish.py").write_text(
        "from src.publish import publish_result\n"
        "def test_publish(): assert publish_result('x') == 'x'\n",
        encoding="utf-8",
    )
    task = (
        "With AuthorityReceipt.canonical_identity available, "
        "fix publish_result to use the canonical identity."
    )

    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.task_action_map(task, limit=20, per_role=3)
        packet = codemap.task_decision_packet(task, limit=20, token_budget=256)

    assert action["edit"] is not None
    assert action["edit"]["path"] == "src/publish.py"
    assert action["ownership_authority"]["owner_resolved"] is True
    assert action["admitted_edit"] is not None
    assert action["admitted_edit"]["path"] == "src/publish.py"
    assert assert_object(packet["edit"])["path"] == "src/publish.py"
    assert assert_object(packet["candidate"])["path"] == "src/publish.py"
    assert assert_object(packet["discrimination"])["needed"] is False


def test_decision_packet_consumes_canonical_action_edit(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/engine.py").write_text(
        "def widget_value():\n    return 'old'\n", encoding="utf-8"
    )
    (tmp_path / "tests/test_engine.py").write_text(
        "from src.engine import widget_value\n"
        "def test_widget_value(): assert widget_value() == 'old'\n",
        encoding="utf-8",
    )
    task = "Change widget_value behavior"

    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.task_action_map(task)
        assert action["edit"] is not None
        assert action["edit"]["path"] == "src/engine.py"
        assert action["action_edit"] is not None
        assert action["action_edit"]["path"] == "src/engine.py"
        assert action["admitted_edit"] is not None
        assert action["admitted_edit"]["path"] == "src/engine.py"

        action["action_edit"] = None
        codemap.task_action_map = lambda *args, **kwargs: action  # type: ignore[method-assign]
        packet = codemap.task_decision_packet(task, token_budget=256)

    assert assert_object(packet["candidate"])["path"] == "src/engine.py"
    assert packet["edit"] is None
