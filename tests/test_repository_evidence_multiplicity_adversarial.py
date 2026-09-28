from __future__ import annotations

from pathlib import Path

from hashmarks.codemap.engine import CodeMap


def _lines_binding(*, duplicate: bool = False) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = [
        {"path": "owner.py", "start_line": 1, "end_line": 1},
    ]
    if duplicate:
        evidence.append({"path": "owner.py", "start_line": 1, "end_line": 1})
    return [{"binding_id": "consumer", "evidence": evidence}]


def _member_binding() -> list[dict[str, object]]:
    return [
        {
            "binding_id": "consumer",
            "evidence": [{"scope": "member", "path": "owner.py"}],
        }
    ]


def _delta_and_coverage(
    codemap: CodeMap,
    before: dict[str, object],
    after: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    delta = codemap.repository_evidence_binding_delta(before, after)
    coverage = codemap.repository_evidence_coverage(
        after,
        changed_paths=[],
        change_set_complete=True,
        binding_delta=delta,
        binding_delta_before=before,
    )
    return delta, coverage


def _assert_definition_only_transition(
    delta: dict[str, object],
    coverage: dict[str, object],
) -> None:
    changed = delta["bindings"]["changed"]
    assert len(changed) == 1
    row = changed[0]
    assert row["binding_id"] == "consumer"
    assert row["definition"]["state"] == "changed"
    assert row["direct_evidence"]["state"] == "preserved"
    assert row["locator_evidence"]["state"] == "preserved"
    assert row["member_evidence"]["state"] == "preserved"
    assert row["declared_dependencies"]["state"] == "unaffected"
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "consumer",
            "reasons": ["binding-definition-changed"],
        }
    ]


def test_duplicate_locator_multiplicity_is_definition_topology_not_content_change(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        single = codemap.repository_evidence_bindings(
            _lines_binding(),
            include_relationships=False,
        )
        duplicated = codemap.repository_evidence_bindings(
            _lines_binding(duplicate=True),
            include_relationships=False,
        )
        added_delta, added_coverage = _delta_and_coverage(
            codemap,
            single,
            duplicated,
        )
        removed_delta, removed_coverage = _delta_and_coverage(
            codemap,
            duplicated,
            single,
        )

    single_row = single["bindings"][0]
    duplicated_row = duplicated["bindings"][0]
    assert len(single_row["evidence"]) == 1
    assert len(duplicated_row["evidence"]) == 2
    assert (
        duplicated_row["evidence"][0]["span_identity"]
        == duplicated_row["evidence"][1]["span_identity"]
        == single_row["evidence"][0]["span_identity"]
    )
    assert (
        single_row["binding_definition_identity"]
        != duplicated_row["binding_definition_identity"]
    )
    assert (
        single_row["binding_observation_identity"]
        != duplicated_row["binding_observation_identity"]
    )

    _assert_definition_only_transition(added_delta, added_coverage)
    _assert_definition_only_transition(removed_delta, removed_coverage)


def test_lines_to_member_scope_switch_is_definition_not_repository_content_change(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        lines = codemap.repository_evidence_bindings(
            _lines_binding(),
            include_relationships=False,
        )
        member = codemap.repository_evidence_bindings(
            _member_binding(),
            include_relationships=False,
        )
        to_member_delta, to_member_coverage = _delta_and_coverage(
            codemap,
            lines,
            member,
        )
        to_lines_delta, to_lines_coverage = _delta_and_coverage(
            codemap,
            member,
            lines,
        )

    lines_row = lines["bindings"][0]
    member_row = member["bindings"][0]
    lines_evidence = lines_row["evidence"][0]
    member_evidence = member_row["evidence"][0]

    assert lines_evidence["scope"] == "lines"
    assert member_evidence["scope"] == "member"
    assert lines_evidence["member_revision"] == member_evidence["member_revision"]
    assert (
        lines_row["binding_definition_identity"]
        != member_row["binding_definition_identity"]
    )
    assert (
        lines_row["binding_observation_identity"]
        != member_row["binding_observation_identity"]
    )

    _assert_definition_only_transition(to_member_delta, to_member_coverage)
    _assert_definition_only_transition(to_lines_delta, to_lines_coverage)
