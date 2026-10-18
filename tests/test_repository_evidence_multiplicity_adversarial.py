from __future__ import annotations

from pathlib import Path

from contract_assertions import assert_object, assert_records

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
    delta = codemap.bindings.delta(before, after)
    coverage = codemap.bindings.coverage(
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
    changed = assert_records(assert_object(delta["bindings"])["changed"])
    assert len(changed) == 1
    row = changed[0]
    assert row["binding_id"] == "consumer"
    assert assert_object(row["definition"])["state"] == "changed"
    assert assert_object(row["direct_evidence"])["state"] == "preserved"
    assert assert_object(row["locator_evidence"])["state"] == "preserved"
    assert assert_object(row["member_evidence"])["state"] == "preserved"
    assert assert_object(row["declared_dependencies"])["state"] == "unaffected"
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
        codemap.index.sync()
        single = codemap.bindings.observe(
            _lines_binding(),
            include_relationships=False,
        )
        duplicated = codemap.bindings.observe(
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

    single_row = assert_records(single["bindings"])[0]
    duplicated_row = assert_records(duplicated["bindings"])[0]
    assert len(assert_records(single_row["evidence"])) == 1
    assert len(assert_records(duplicated_row["evidence"])) == 2
    assert (
        assert_records(duplicated_row["evidence"])[0]["span_identity"]
        == assert_records(duplicated_row["evidence"])[1]["span_identity"]
        == assert_records(single_row["evidence"])[0]["span_identity"]
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
        codemap.index.sync()
        lines = codemap.bindings.observe(
            _lines_binding(),
            include_relationships=False,
        )
        member = codemap.bindings.observe(
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

    lines_row = assert_records(lines["bindings"])[0]
    member_row = assert_records(member["bindings"])[0]
    lines_evidence = assert_records(lines_row["evidence"])[0]
    member_evidence = assert_records(member_row["evidence"])[0]

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
