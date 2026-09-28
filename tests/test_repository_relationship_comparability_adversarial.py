from __future__ import annotations

from pathlib import Path

from hashmarks.codemap.engine import CodeMap


def _binding() -> list[dict[str, object]]:
    return [
        {
            "binding_id": "relationship-authority",
            "evidence": [
                {"path": "source.py", "start_line": 2, "end_line": 2},
            ],
        }
    ]


def _resign_packet(codemap: CodeMap, packet: dict[str, object]) -> None:
    packet["bindings_identity"] = "sha256:" + codemap._packet_digest(
        "hashmarks.repository-evidence-bindings.v1",
        {key: value for key, value in packet.items() if key != "bindings_identity"},
    )


def _assert_config_transition(
    delta: dict[str, object],
    coverage: dict[str, object],
    *,
    before_state: str,
    after_state: str,
) -> None:
    assert delta["observer"]["changed"] is False
    assert delta["bindings"]["preserved"] == []
    changed = delta["bindings"]["changed"]
    assert len(changed) == 1
    row = changed[0]
    assert row["binding_id"] == "relationship-authority"
    assert row["definition"]["state"] == "changed"
    assert row["direct_evidence"]["state"] == "preserved"
    assert row["locator_evidence"]["state"] == "preserved"
    assert row["member_evidence"]["state"] == "preserved"

    relationships = row["relationship_evidence"]
    assert relationships["state"] == "unknown"
    assert relationships["comparability"] == "observation-configuration-changed"
    assert relationships["facts"] == {
        "state": "unknown",
        "added": [],
        "removed": [],
    }
    assert relationships["locators"] == {
        "state": "unknown",
        "changes": [],
    }
    assert relationships["observation"]["changed"] is True
    assert relationships["observation"]["before"]["state"] == before_state
    assert relationships["observation"]["after"]["state"] == after_state

    assert coverage["binding_impacts"] == [
        {
            "binding_id": "relationship-authority",
            "reasons": [
                "binding-definition-changed",
                "relationship-observation-config-changed",
            ],
        }
    ]


def test_relationship_observation_enable_disable_is_non_comparable_not_fact_change(
    tmp_path: Path,
) -> None:
    (tmp_path / "dependency.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "source.py").write_text(
        "from dependency import VALUE\nKEEP = 1\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        not_requested = codemap.repository_evidence_bindings(
            _binding(),
            include_relationships=False,
        )
        observed = codemap.repository_evidence_bindings(
            _binding(),
            relationship_limit_per_path=8,
        )
        disabled_again = codemap.repository_evidence_bindings(
            _binding(),
            include_relationships=False,
        )

        enabled_delta = codemap.repository_evidence_binding_delta(
            not_requested,
            observed,
        )
        enabled_coverage = codemap.repository_evidence_coverage(
            observed,
            changed_paths=[],
            change_set_complete=True,
            binding_delta=enabled_delta,
            binding_delta_before=not_requested,
        )

        disabled_delta = codemap.repository_evidence_binding_delta(
            observed,
            disabled_again,
        )
        disabled_coverage = codemap.repository_evidence_coverage(
            disabled_again,
            changed_paths=[],
            change_set_complete=True,
            binding_delta=disabled_delta,
            binding_delta_before=observed,
        )

    _assert_config_transition(
        enabled_delta,
        enabled_coverage,
        before_state="not-requested",
        after_state="observed",
    )
    _assert_config_transition(
        disabled_delta,
        disabled_coverage,
        before_state="observed",
        after_state="not-requested",
    )


def test_observer_change_keeps_relationship_facts_unknown_but_member_change_visible(
    tmp_path: Path,
) -> None:
    (tmp_path / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "beta.py").write_text("VALUE = 1\n", encoding="utf-8")
    source = tmp_path / "source.py"
    source.write_text("from alpha import VALUE\nKEEP = 1\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(_binding())

        source.write_text("from beta import VALUE\nKEEP = 1\n", encoding="utf-8")
        codemap.sync(["source.py"])
        after = codemap.repository_evidence_bindings(_binding())
        after["observer"] = {
            **after["observer"],
            "identity": "sha256:" + "a" * 64,
        }
        _resign_packet(codemap, after)

        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["source.py"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )

    assert delta["observer"]["changed"] is True
    changed = delta["bindings"]["changed"]
    assert len(changed) == 1
    row = changed[0]
    assert row["binding_id"] == "relationship-authority"
    assert row["direct_evidence"]["state"] == "preserved"
    assert row["member_evidence"]["state"] == "changed"

    relationships = row["relationship_evidence"]
    assert relationships["state"] == "unknown"
    assert relationships["comparability"] == "observer-changed"
    assert relationships["facts"] == {
        "state": "unknown",
        "added": [],
        "removed": [],
    }
    assert relationships["locators"] == {
        "state": "unknown",
        "changes": [],
    }
    assert relationships["observation"]["changed"] is True

    assert coverage["binding_impacts"] == [
        {
            "binding_id": "relationship-authority",
            "reasons": ["bound-member-changed"],
        }
    ]
