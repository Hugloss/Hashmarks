from __future__ import annotations

import copy
from pathlib import Path

from contract_assertions import assert_array, assert_object, assert_records, assert_text

from hashmarks.codemap.engine import CodeMap


def _declaration(
    declaration_id: str,
    path: str,
    value: object,
) -> dict[str, object]:
    return {
        "declaration_id": declaration_id,
        "value_state": "resolved",
        "value": value,
        "producer": {"kind": "authority-adversarial-fixture", "version": "1"},
        "evidence": [
            {
                "path": path,
                "start_line": 1,
                "end_line": 1,
            }
        ],
    }


def _group(
    declarations: list[dict[str, object]],
    *,
    basis_version: str = "1",
) -> dict[str, object]:
    ids = [str(row["declaration_id"]) for row in declarations]
    return {
        "group_id": "component-owner",
        "semantic_namespace": "authority-adversarial-fixture",
        "concept": {"kind": "ownership", "identity": "component-a"},
        "scope": {"environment": "all"},
        "correspondence": {
            "state": "declared",
            "basis": {
                "provider": "authority-adversarial-fixture",
                "version": basis_version,
            },
        },
        "declarations": declarations,
        "coverage": {
            "state": "complete",
            "truncation": "complete",
            "expected_declaration_ids": ids,
            "scope": {"repository": "fixture"},
            "provenance": {"provider": "authority-adversarial-fixture"},
        },
    }


def _by_id(packet: dict[str, object]) -> dict[str, dict[str, object]]:
    group = assert_records(packet["groups"])[0]
    return {
        assert_text(row["declaration_id"]): row
        for row in assert_records(group["declarations"])
    }


def _binding_change(
    packet: dict[str, object],
    declaration: dict[str, object],
) -> dict[str, object]:
    changed = assert_records(
        assert_object(
            assert_object(
                assert_object(packet["delta_from_previous"])["repository_evidence"]
            )["bindings"]
        )["changed"]
    )
    return next(
        row for row in changed if row["binding_id"] == declaration["binding_id"]
    )


def test_declaration_evidence_path_move_is_definition_change_not_value_change(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    old_path = repo / "owner-secondary.yaml"
    new_path = repo / "moved" / "owner-secondary.yaml"
    (repo / "owner-primary.yaml").write_text("owner: team-a\n", encoding="utf-8")
    old_path.write_text("owner: team-a\n", encoding="utf-8")

    before_group = _group(
        [
            _declaration("primary", "owner-primary.yaml", "team-a"),
            _declaration("secondary", "owner-secondary.yaml", "team-a"),
        ]
    )
    after_group = _group(
        [
            _declaration("primary", "owner-primary.yaml", "team-a"),
            _declaration("secondary", "moved/owner-secondary.yaml", "team-a"),
        ]
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.repository_declarations([before_group])

        new_path.parent.mkdir()
        old_path.replace(new_path)
        codemap.index.sync(["owner-secondary.yaml", "moved/owner-secondary.yaml"])
        after = codemap.repository_declarations(
            [after_group],
            previous_observation=before,
        )

    before_group_row = assert_records(before["groups"])[0]
    after_group_row = assert_records(after["groups"])[0]
    before_declarations = _by_id(before)
    after_declarations = _by_id(after)
    secondary_before = before_declarations["secondary"]
    secondary_after = after_declarations["secondary"]

    assert assert_object(before_group_row["comparison"])["state"] == "equivalent"
    assert assert_object(after_group_row["comparison"])["state"] == "equivalent"
    assert assert_object(before_group_row["absence"])["state"] == "known-present"
    assert assert_object(after_group_row["absence"])["state"] == "known-present"
    assert secondary_before["value"] == secondary_after["value"] == "team-a"
    assert (
        secondary_before["declaration_definition_identity"]
        != secondary_after["declaration_definition_identity"]
    )

    changed = assert_records(
        assert_object(after["delta_from_previous"])["changed_groups"]
    )[0]
    assert changed["definition_changed"] is True
    assert changed["definition_changed_declaration_ids"] == ["secondary"]
    assert changed["value_changed_declaration_ids"] == []
    assert changed["observation_changed_declaration_ids"] == []
    assert changed["comparison_changed"] is False
    assert changed["absence_changed"] is False

    binding_change = _binding_change(after, secondary_after)
    assert assert_object(binding_change["definition"])["state"] == "changed"
    assert assert_object(binding_change["direct_evidence"])["state"] == "preserved"
    assert assert_object(binding_change["locator_evidence"])["state"] == "preserved"
    assert assert_object(binding_change["member_evidence"])["state"] == "preserved"


def _loss_restoration_packets(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner-primary.yaml").write_text("owner: team-a\n", encoding="utf-8")
    secondary = repo / "owner-secondary.yaml"
    secondary.write_text("owner: team-a\n", encoding="utf-8")
    group = _group(
        [
            _declaration("primary", "owner-primary.yaml", "team-a"),
            _declaration("secondary", "owner-secondary.yaml", "team-a"),
        ]
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        present = codemap.repository_declarations([group])

        secondary.unlink()
        codemap.index.sync(["owner-secondary.yaml"])
        missing = codemap.repository_declarations(
            [group],
            previous_observation=present,
        )

        secondary.write_text("owner: team-a\n", encoding="utf-8")
        codemap.index.sync(["owner-secondary.yaml"])
        restored = codemap.repository_declarations(
            [group],
            previous_observation=missing,
        )
    return present, missing, restored


def _assert_evidence_loss(
    present: dict[str, object],
    missing: dict[str, object],
) -> None:
    present_group = assert_records(present["groups"])[0]
    missing_group = assert_records(missing["groups"])[0]
    present_secondary = _by_id(present)["secondary"]
    missing_secondary = _by_id(missing)["secondary"]

    assert (
        present_secondary["declaration_definition_identity"]
        == missing_secondary["declaration_definition_identity"]
    )
    assert present_secondary["evidence_state"] == "known-present"
    assert missing_secondary["evidence_state"] == "known-absent"
    assert assert_object(present_group["comparison"])["state"] == "equivalent"
    assert missing_group["comparison"] == {
        "state": "ambiguous",
        "reason": "repository-evidence-not-qualified",
        "unqualified_declaration_ids": ["secondary"],
        "distinct_values": [],
    }
    assert assert_object(present_group["absence"])["state"] == "known-present"
    assert missing_group["absence"] == {
        "state": "known-absent",
        "missing_declaration_ids": ["secondary"],
        "unseen_expected_declaration_ids": [],
        "unexpected_declaration_ids": [],
    }

    delta = assert_records(
        assert_object(missing["delta_from_previous"])["changed_groups"]
    )[0]
    assert delta["definition_changed"] is False
    assert delta["value_changed_declaration_ids"] == []
    assert delta["observation_changed_declaration_ids"] == ["secondary"]
    assert delta["comparison_changed"] is True
    assert delta["absence_changed"] is True

    subject = assert_records(
        assert_object(
            assert_object(missing["delta_from_previous"])["semantic_subjects"]
        )["changed"]
    )[0]
    assert subject["evidence_state_changed_declaration_ids"] == ["secondary"]
    assert subject["value_changed_declaration_ids"] == []
    assert (
        assert_object(assert_object(subject["comparison_transition"])["before"])[
            "state"
        ]
        == "equivalent"
    )
    assert (
        assert_object(assert_object(subject["comparison_transition"])["after"])["state"]
        == "ambiguous"
    )
    assert (
        assert_object(assert_object(subject["absence_transition"])["before"])["state"]
        == "known-present"
    )
    assert (
        assert_object(assert_object(subject["absence_transition"])["after"])["state"]
        == "known-absent"
    )

    binding = _binding_change(missing, missing_secondary)
    assert assert_object(binding["definition"])["state"] == "preserved"
    assert (
        assert_object(
            assert_records(assert_object(binding["member_evidence"])["changes"])[0]
        )["state"]
        == "removed"
    )


def _assert_evidence_restoration(
    missing: dict[str, object],
    restored: dict[str, object],
) -> None:
    missing_secondary = _by_id(missing)["secondary"]
    restored_secondary = _by_id(restored)["secondary"]

    assert (
        missing_secondary["declaration_definition_identity"]
        == restored_secondary["declaration_definition_identity"]
    )
    assert missing_secondary["evidence_state"] == "known-absent"
    assert restored_secondary["evidence_state"] == "known-present"
    assert (
        assert_object(
            assert_object(assert_records(missing["groups"])[0])["comparison"]
        )["state"]
        == "ambiguous"
    )
    assert (
        assert_object(
            assert_object(assert_records(restored["groups"])[0])["comparison"]
        )["state"]
        == "equivalent"
    )
    assert (
        assert_object(assert_object(assert_records(missing["groups"])[0])["absence"])[
            "state"
        ]
        == "known-absent"
    )
    assert (
        assert_object(assert_object(assert_records(restored["groups"])[0])["absence"])[
            "state"
        ]
        == "known-present"
    )

    delta = assert_records(
        assert_object(restored["delta_from_previous"])["changed_groups"]
    )[0]
    assert delta["definition_changed"] is False
    assert delta["value_changed_declaration_ids"] == []
    assert delta["observation_changed_declaration_ids"] == ["secondary"]
    assert delta["comparison_changed"] is True
    assert delta["absence_changed"] is True

    subject = assert_records(
        assert_object(
            assert_object(restored["delta_from_previous"])["semantic_subjects"]
        )["changed"]
    )[0]
    assert subject["evidence_state_changed_declaration_ids"] == ["secondary"]
    assert subject["value_changed_declaration_ids"] == []
    assert (
        assert_object(assert_object(subject["comparison_transition"])["before"])[
            "state"
        ]
        == "ambiguous"
    )
    assert (
        assert_object(assert_object(subject["comparison_transition"])["after"])["state"]
        == "equivalent"
    )
    assert (
        assert_object(assert_object(subject["absence_transition"])["before"])["state"]
        == "known-absent"
    )
    assert (
        assert_object(assert_object(subject["absence_transition"])["after"])["state"]
        == "known-present"
    )

    binding = _binding_change(restored, restored_secondary)
    assert assert_object(binding["definition"])["state"] == "preserved"
    assert (
        assert_object(
            assert_records(assert_object(binding["member_evidence"])["changes"])[0]
        )["state"]
        == "added"
    )


def test_declaration_evidence_loss_and_restoration_change_observation_not_definition(
    tmp_path: Path,
) -> None:
    present, missing, restored = _loss_restoration_packets(tmp_path)
    _assert_evidence_loss(present, missing)
    _assert_evidence_restoration(missing, restored)


def test_declaration_producer_provenance_change_is_observation_only(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.yaml").write_text("owner: team-a\n", encoding="utf-8")

    before_group = _group([_declaration("owner", "owner.yaml", "team-a")])
    assert_object(assert_records(before_group["declarations"])[0])["semantic_role"] = {
        "kind": "repository-owner"
    }
    after_group = copy.deepcopy(before_group)
    assert_object(
        assert_object(assert_records(after_group["declarations"])[0])["producer"]
    )["version"] = "2"

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.repository_declarations([before_group])
        after = codemap.repository_declarations(
            [after_group],
            previous_observation=before,
        )

    before_declaration = _by_id(before)["owner"]
    after_declaration = _by_id(after)["owner"]
    assert (
        before_declaration["declaration_definition_identity"]
        == after_declaration["declaration_definition_identity"]
    )
    assert (
        before_declaration["declaration_observation_identity"]
        != after_declaration["declaration_observation_identity"]
    )
    assert (
        before_declaration["semantic_declaration_identity"]
        == after_declaration["semantic_declaration_identity"]
    )
    assert (
        assert_object(assert_records(before["groups"])[0])["group_definition_identity"]
        == assert_object(assert_records(after["groups"])[0])[
            "group_definition_identity"
        ]
    )
    assert (
        assert_object(assert_records(before["groups"])[0])["comparison"]
        == assert_object(assert_records(after["groups"])[0])["comparison"]
    )

    changed = assert_records(
        assert_object(after["delta_from_previous"])["changed_groups"]
    )[0]
    assert changed["definition_changed"] is False
    assert changed["value_changed_declaration_ids"] == []
    assert changed["observation_changed_declaration_ids"] == ["owner"]
    assert changed["comparison_changed"] is False
    assert changed["absence_changed"] is False
    semantic = assert_object(
        assert_object(
            assert_records(
                assert_object(
                    assert_object(after["delta_from_previous"])["semantic_subjects"]
                )["changed"]
            )[0]
        )["semantic_declarations"]
    )
    assert semantic["added"] == []
    assert semantic["removed"] == []
    assert semantic["ambiguous"] == []
    assert len(assert_array(semantic["changed"])) == 1
    role_change = assert_records(semantic["changed"])[0]
    assert role_change["semantic_role"] == {"kind": "repository-owner"}
    assert role_change["declaration_id_changed"] is False
    assert (
        assert_object(assert_object(role_change["producer_transition"])["before"])[
            "version"
        ]
        == "1"
    )
    assert (
        assert_object(assert_object(role_change["producer_transition"])["after"])[
            "version"
        ]
        == "2"
    )
    assert "value_transition" not in role_change
    assert (
        assert_object(
            assert_object(
                assert_object(after["delta_from_previous"])["repository_evidence"]
            )["bindings"]
        )["changed"]
        == []
    )


def test_correspondence_basis_change_is_group_observation_only(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner-a.yaml").write_text("owner: team-a\n", encoding="utf-8")
    (repo / "owner-b.yaml").write_text("owner: team-a\n", encoding="utf-8")
    declarations = [
        _declaration("a", "owner-a.yaml", "team-a"),
        _declaration("b", "owner-b.yaml", "team-a"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.repository_declarations(
            [_group(declarations, basis_version="1")]
        )
        after = codemap.repository_declarations(
            [_group(declarations, basis_version="2")],
            previous_observation=before,
        )

    assert (
        assert_object(assert_records(before["groups"])[0])["group_definition_identity"]
        == assert_object(assert_records(after["groups"])[0])[
            "group_definition_identity"
        ]
    )
    assert (
        assert_object(assert_records(before["groups"])[0])["comparison"]
        == assert_object(assert_records(after["groups"])[0])["comparison"]
    )
    assert (
        assert_object(assert_records(before["groups"])[0])["absence"]
        == assert_object(assert_records(after["groups"])[0])["absence"]
    )

    changed = assert_records(
        assert_object(after["delta_from_previous"])["changed_groups"]
    )[0]
    assert changed["definition_changed"] is False
    assert changed["definition_changed_declaration_ids"] == []
    assert changed["value_changed_declaration_ids"] == []
    assert changed["observation_changed_declaration_ids"] == []
    assert changed["correspondence_changed"] is True
    assert changed["comparison_changed"] is False
    assert changed["absence_changed"] is False
    assert (
        assert_object(
            assert_object(
                assert_object(after["delta_from_previous"])["repository_evidence"]
            )["bindings"]
        )["changed"]
        == []
    )
