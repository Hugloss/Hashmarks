from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records, assert_text

from hashmarks import CodeMap


def _group(
    declarations: list[dict[str, object]],
    *,
    group_id: str = "runtime-python",
    coverage: tuple[str, str] = ("complete", "complete"),
    expected: list[str] | None = None,
    correspondence_state: str = "declared",
    scope: dict[str, object] | None = None,
) -> dict[str, object]:
    ids = [str(row["declaration_id"]) for row in declarations]
    coverage_state, truncation = coverage
    return {
        "group_id": group_id,
        "semantic_namespace": "fixture",
        "concept": {"kind": "runtime-compatibility", "identity": "python"},
        "scope": {} if scope is None else scope,
        "correspondence": {
            "state": correspondence_state,
            "basis": {"provider": "fixture", "rule": "explicit-semantic-mapping"},
        },
        "declarations": declarations,
        "coverage": {
            "state": coverage_state,
            "truncation": truncation,
            "expected_declaration_ids": ids if expected is None else expected,
            "scope": {"repository": "fixture"},
            "provenance": {"provider": "fixture"},
        },
    }


def _declaration(
    declaration_id: str,
    path: str,
    value: object,
    *,
    line: int = 1,
    semantic_role: Mapping[str, object] | None = None,
) -> dict[str, object]:
    declaration: dict[str, object] = {
        "declaration_id": declaration_id,
        "value_state": "resolved",
        "value": value,
        "producer": {"kind": "fixture-config"},
        "evidence": [
            {
                "path": path,
                "start_line": line,
                "end_line": line,
            }
        ],
    }
    if semantic_role is not None:
        declaration["semantic_role"] = semantic_role
    return declaration


def test_cross_file_declarations_preserve_exact_evidence_and_equivalence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        'requires-python = ">=3.12"\n', encoding="utf-8"
    )
    (repo / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    declarations = [
        _declaration("python-intent", "pyproject.toml", ">=3.12"),
        _declaration("python-container", "Dockerfile", ">=3.12"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet = codemap.declarations.observe([_group(declarations)])

    group = assert_array(packet["groups"])[0]
    assert packet["schema"] == "hashmarks.repository-declarations.v1"
    assert packet["winner"] == "not-selected"
    assert packet["correspondence_authority"] == "provider-claimed"
    assert assert_object(group)["comparison"] == {
        "state": "equivalent",
        "distinct_values": [">=3.12"],
    }
    assert assert_object(assert_object(group)["absence"])["state"] == "known-present"
    bindings = {
        assert_object(row)["binding_id"]: row
        for row in assert_array(
            assert_object(packet["repository_evidence"])["bindings"]
        )
    }
    paths = {
        assert_object(
            assert_array(
                assert_object(bindings[assert_object(row)["binding_id"]])["evidence"]
            )[0]
        )["path"]
        for row in assert_array(assert_object(group)["declarations"])
    }
    assert paths == {"pyproject.toml", "Dockerfile"}
    assert all(
        assert_text(
            assert_object(
                assert_array(
                    assert_object(bindings[assert_object(row)["binding_id"]])[
                        "evidence"
                    ]
                )[0]
            )["span_identity"]
        ).startswith("sha256:")
        for row in assert_array(assert_object(group)["declarations"])
    )


def test_differing_declarations_are_reported_without_precedence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.yaml").write_text("python: 3.12\n", encoding="utf-8")
    (repo / "b.yaml").write_text("python: 3.13\n", encoding="utf-8")
    declarations = [
        _declaration("runtime-a", "a.yaml", "3.12"),
        _declaration("runtime-b", "b.yaml", "3.13"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet = codemap.declarations.observe([_group(declarations)])

    comparison = assert_object(assert_array(packet["groups"])[0])["comparison"]
    assert assert_object(comparison)["state"] == "differing"
    assert assert_object(comparison)["distinct_values"] == ["3.12", "3.13"]
    assert packet["winner"] == "not-selected"
    assert "preferred" not in assert_object(comparison)
    assert "authoritative_value" not in assert_object(comparison)


def test_absence_requires_complete_untruncated_semantic_coverage(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.yaml").write_text("owner: team-a\n", encoding="utf-8")
    declarations = [_declaration("owner-a", "a.yaml", "team-a")]
    expected = ["owner-a", "owner-b"]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        unknown = codemap.declarations.observe(
            [
                _group(
                    declarations,
                    coverage=("incomplete", "unknown"),
                    expected=expected,
                )
            ]
        )
        absent = codemap.declarations.observe([_group(declarations, expected=expected)])

    assert assert_object(assert_array(unknown["groups"])[0])["absence"] == {
        "state": "unknown",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": ["owner-b"],
        "unexpected_declaration_ids": [],
        "reason": "coverage-does-not-authorize-negative-evidence",
    }
    assert assert_object(assert_array(absent["groups"])[0])["absence"] == {
        "state": "known-absent",
        "missing_declaration_ids": ["owner-b"],
        "unseen_expected_declaration_ids": [],
        "unexpected_declaration_ids": [],
    }


def test_semantic_role_does_not_create_expected_membership_or_absence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = _declaration(
        "runtime",
        "runtime.yaml",
        "3.12",
        semantic_role={"kind": "container-runtime"},
    )
    group = _group([declaration], expected=[])

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet = codemap.declarations.observe([group])

    projected = assert_array(packet["groups"])[0]
    assert (
        assert_object(assert_object(projected)["coverage"])["expected_declaration_ids"]
        == []
    )
    assert assert_text(
        assert_object(assert_array(assert_object(projected)["declarations"])[0])[
            "semantic_declaration_identity"
        ]
    ).startswith("sha256:")
    assert assert_object(projected)["absence"] == {
        "state": "unknown",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": [],
        "unexpected_declaration_ids": [],
        "reason": "expected-membership-not-declared",
    }


def test_ambiguous_correspondence_never_becomes_a_conflict_or_equivalence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.json").write_text('{"name":"alpha"}\n', encoding="utf-8")
    (repo / "b.json").write_text('{"name":"beta"}\n', encoding="utf-8")
    declarations = [
        _declaration("a", "a.json", "alpha"),
        _declaration("b", "b.json", "beta"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet = codemap.declarations.observe(
            [_group(declarations, correspondence_state="ambiguous")]
        )

    assert assert_object(assert_array(packet["groups"])[0])["comparison"] == {
        "state": "ambiguous",
        "reason": "correspondence-not-uniquely-declared",
        "distinct_values": [],
    }


def test_semantic_namespace_is_required_and_prevents_cross_namespace_collision(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = [_declaration("runtime", "runtime.yaml", "3.12")]
    missing_namespace = _group(declaration)
    missing_namespace.pop("semantic_namespace")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        with pytest.raises(ValueError, match="semantic_namespace"):
            codemap.declarations.observe([missing_namespace])
        first_group = _group(declaration)
        first_group["semantic_namespace"] = "provider-a"
        second_group = _group(declaration)
        second_group["semantic_namespace"] = "provider-b"
        first = codemap.declarations.observe([first_group])
        second = codemap.declarations.observe([second_group])

    assert (
        assert_object(assert_array(first["groups"])[0])["semantic_subject_identity"]
        != assert_object(assert_array(second["groups"])[0])["semantic_subject_identity"]
    )


def test_semantic_subject_identity_is_independent_of_group_label_and_locator(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.txt").write_text("3.12\n3.12\n", encoding="utf-8")

    first_group = _group(
        [_declaration("runtime", "runtime.txt", "3.12", line=1)],
        group_id="request-a",
    )
    second_group = _group(
        [_declaration("runtime", "runtime.txt", "3.12", line=2)],
        group_id="request-b",
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        first = codemap.declarations.observe([first_group])
        second = codemap.declarations.observe([second_group])

    first_group_result = assert_array(first["groups"])[0]
    second_group_result = assert_array(second["groups"])[0]
    assert (
        assert_object(first_group_result)["semantic_subject_identity"]
        == assert_object(second_group_result)["semantic_subject_identity"]
    )
    assert (
        assert_object(first_group_result)["group_definition_identity"]
        != assert_object(second_group_result)["group_definition_identity"]
    )
    first_declaration = assert_array(assert_object(first_group_result)["declarations"])[
        0
    ]
    second_declaration = assert_array(
        assert_object(second_group_result)["declarations"]
    )[0]
    assert (
        assert_object(first_declaration)["semantic_subject_identity"]
        == assert_object(first_group_result)["semantic_subject_identity"]
    )
    assert (
        assert_object(second_declaration)["semantic_subject_identity"]
        == assert_object(second_group_result)["semantic_subject_identity"]
    )
    assert (
        assert_object(first_declaration)["declaration_definition_identity"]
        != assert_object(second_declaration)["declaration_definition_identity"]
    )


def test_scope_is_part_of_definition_identity_and_prevents_cross_context_merging(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = [_declaration("runtime", "runtime.yaml", "3.12")]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        linux = codemap.declarations.observe(
            [_group(declaration, scope={"platform": "linux"})]
        )
        windows = codemap.declarations.observe(
            [_group(declaration, scope={"platform": "windows"})]
        )

    assert (
        assert_object(assert_array(linux["groups"])[0])["group_definition_identity"]
        != assert_object(assert_array(windows["groups"])[0])[
            "group_definition_identity"
        ]
    )
    assert (
        assert_object(assert_array(linux["groups"])[0])["semantic_subject_identity"]
        != assert_object(assert_array(windows["groups"])[0])[
            "semantic_subject_identity"
        ]
    )
    assert (
        assert_object(assert_object(assert_array(linux["groups"])[0])["comparison"])[
            "state"
        ]
        == "insufficient"
    )
    assert (
        assert_object(assert_object(assert_array(windows["groups"])[0])["comparison"])[
            "state"
        ]
        == "insufficient"
    )


def test_declaration_delta_separates_value_change_from_group_definition(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.toml").write_text('version = "1"\n', encoding="utf-8")
    (repo / "b.toml").write_text('version = "1"\n', encoding="utf-8")
    before_declarations = [
        _declaration("a", "a.toml", "1"),
        _declaration("b", "b.toml", "1"),
    ]
    after_declarations = [
        _declaration("a", "a.toml", "1"),
        _declaration("b", "b.toml", "2"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([_group(before_declarations)])
        after = codemap.declarations.observe(
            [_group(after_declarations)],
            previous_observation=before,
        )

    delta = after["delta_from_previous"]
    assert (
        assert_object(delta)["schema"] == "hashmarks.repository-declarations-delta.v1"
    )
    assert len(assert_array(assert_object(delta)["changed_groups"])) == 1
    changed = assert_array(assert_object(delta)["changed_groups"])[0]
    assert assert_object(changed)["definition_changed"] is False
    assert assert_object(changed)["value_changed_declaration_ids"] == ["b"]
    assert assert_object(changed)["comparison_changed"] is True
    subject_change = assert_array(
        assert_object(assert_object(delta)["semantic_subjects"])["changed"]
    )[0]
    assert assert_object(subject_change)["value_changed_declaration_ids"] == ["b"]
    assert (
        assert_object(
            assert_object(assert_object(subject_change)["comparison_transition"])[
                "before"
            ]
        )["state"]
        == "equivalent"
    )
    assert (
        assert_object(
            assert_object(assert_object(subject_change)["comparison_transition"])[
                "after"
            ]
        )["state"]
        == "differing"
    )
    assert (
        assert_object(
            assert_object(assert_object(delta)["repository_evidence"])["bindings"]
        )["changed"]
        == []
    )


@pytest.mark.parametrize("before_value,after_value", [(True, 1), (1, 1.0)])
def test_declaration_delta_uses_canonical_json_value_identity(
    tmp_path: Path, before_value: object, after_value: object
) -> None:
    source = tmp_path / "value.toml"
    source.write_text("value = 1\n", encoding="utf-8")
    role = {"kind": "project-intent", "identity": "value"}
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe(
            [
                _group(
                    [
                        _declaration(
                            "value", "value.toml", before_value, semantic_role=role
                        )
                    ]
                )
            ]
        )
        after = codemap.declarations.observe(
            [
                _group(
                    [
                        _declaration(
                            "value", "value.toml", after_value, semantic_role=role
                        )
                    ]
                )
            ],
            previous_observation=before,
        )

    assert (
        assert_object(assert_array(before["groups"])[0])["group_observation_identity"]
        != (
            assert_object(assert_array(after["groups"])[0])[
                "group_observation_identity"
            ]
        )
    )
    delta = after["delta_from_previous"]
    group_change = assert_array(assert_object(delta)["changed_groups"])[0]
    assert assert_object(group_change)["value_changed_declaration_ids"] == ["value"]
    assert assert_object(group_change)["observation_changed_declaration_ids"] == []
    assert assert_object(group_change)["comparison_changed"] is True
    subject_change = assert_array(
        assert_object(assert_object(delta)["semantic_subjects"])["changed"]
    )[0]
    assert assert_object(subject_change)["value_changed_declaration_ids"] == ["value"]
    role_change = assert_array(
        assert_object(assert_object(subject_change)["semantic_declarations"])["changed"]
    )[0]
    assert (
        assert_object(
            assert_object(assert_object(role_change)["value_transition"])["before"]
        )["value"]
        == before_value
    )
    assert (
        assert_object(
            assert_object(assert_object(role_change)["value_transition"])["after"]
        )["value"]
        == after_value
    )


def test_previous_declaration_packet_is_revalidated_before_delta(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.toml").write_text('version = "1"\n', encoding="utf-8")
    declarations = [_declaration("a", "a.toml", "1")]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([_group(declarations)])
        assert_object(assert_object(assert_array(before["groups"])[0])["concept"])[
            "identity"
        ] = "tampered"
        with pytest.raises(
            ValueError, match="previous declaration observation identity mismatch"
        ):
            codemap.declarations.observe(
                [_group(declarations)],
                previous_observation=before,
            )


def test_previous_declaration_rejects_resigned_nested_repository_evidence_tamper(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.toml").write_text('version = "1"\n', encoding="utf-8")
    declarations = [_declaration("a", "a.toml", "1")]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([_group(declarations)])
        evidence = before["repository_evidence"]
        assert_object(
            assert_array(
                assert_object(assert_array(assert_object(evidence)["bindings"])[0])[
                    "evidence"
                ]
            )[0]
        )["state"] = "known-absent"
        before["observation_identity"] = (
            codemap.declarations._declaration_packet_identity(before)
        )

        with pytest.raises(ValueError, match="bindings identity mismatch"):
            codemap.declarations.observe(
                [_group(declarations)],
                previous_observation=before,
            )


def test_fail_closed_unknown_fields_and_invalid_complete_coverage(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.toml").write_text('version = "1"\n', encoding="utf-8")
    declaration = _declaration("a", "a.toml", "1")
    bad = _group([declaration])
    bad["invented_policy"] = "prefer-first"

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        with pytest.raises(ValueError, match="unknown fields"):
            codemap.declarations.observe([bad])
        with pytest.raises(ValueError, match="complete declaration coverage requires"):
            codemap.declarations.observe(
                [
                    _group(
                        [declaration],
                        coverage=("complete", "unknown"),
                    )
                ]
            )


def test_definition_identity_binds_exact_evidence_definition(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.txt").write_text("3.12\n3.12\n", encoding="utf-8")
    before_group = _group([_declaration("runtime", "runtime.txt", "3.12", line=1)])
    after_group = _group([_declaration("runtime", "runtime.txt", "3.12", line=2)])

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([before_group])
        after = codemap.declarations.observe(
            [after_group],
            previous_observation=before,
        )

    previous = assert_array(
        assert_object(assert_array(before["groups"])[0])["declarations"]
    )[0]
    current = assert_array(
        assert_object(assert_array(after["groups"])[0])["declarations"]
    )[0]
    assert (
        assert_object(previous)["declaration_definition_identity"]
        != assert_object(current)["declaration_definition_identity"]
    )
    changed = assert_array(
        assert_object(after["delta_from_previous"])["changed_groups"]
    )[0]
    assert assert_object(changed)["semantic_subject_changed"] is False
    assert assert_object(changed)["definition_changed"] is True
    assert assert_object(changed)["definition_changed_declaration_ids"] == ["runtime"]


def test_semantic_subject_delta_correlates_group_label_change_without_history(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = [_declaration("runtime", "runtime.yaml", "3.12")]
    before_group = _group(declaration, group_id="request-a")
    after_group = _group(declaration, group_id="request-b")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([before_group])
        after = codemap.declarations.observe(
            [after_group],
            previous_observation=before,
        )

    delta = after["delta_from_previous"]
    assert assert_object(delta)["added_group_ids"] == ["request-b"]
    assert assert_object(delta)["removed_group_ids"] == ["request-a"]
    subjects = assert_object(delta)["semantic_subjects"]
    assert assert_object(subjects)["added"] == []
    assert assert_object(subjects)["removed"] == []
    assert assert_object(subjects)["ambiguous"] == []
    assert len(assert_array(assert_object(subjects)["changed"])) == 1
    change = assert_array(assert_object(subjects)["changed"])[0]
    assert assert_object(change)["group_id_changed"] is True
    assert assert_object(change)["previous_group_id"] == "request-a"
    assert assert_object(change)["current_group_id"] == "request-b"
    assert "value_changed_declaration_ids" not in assert_object(change)
    assert "producer_changed_declaration_ids" not in assert_object(change)
    assert "evidence_state_changed_declaration_ids" not in assert_object(change)
    assert "added_declaration_ids" not in assert_object(change)
    assert "removed_declaration_ids" not in assert_object(change)
    assert "semantic_declarations" not in assert_object(change)
    assert "comparison_transition" not in assert_object(change)
    assert "absence_transition" not in assert_object(change)


def test_semantic_role_correlates_child_change_across_request_label_renames(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("python = 3.12\n", encoding="utf-8")
    (repo / "Dockerfile").write_text("python = 3.12\n", encoding="utf-8")
    before_group = _group(
        [
            _declaration(
                "intent-before",
                "pyproject.toml",
                "3.12",
                semantic_role={"kind": "project-intent"},
            ),
            _declaration(
                "runtime-before",
                "Dockerfile",
                "3.12",
                semantic_role={"kind": "container-runtime"},
            ),
        ],
        group_id="request-before",
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([before_group])
        moved = repo / "container" / "Dockerfile"
        moved.parent.mkdir()
        (repo / "Dockerfile").replace(moved)
        moved.write_text("python = 3.13\n", encoding="utf-8")
        codemap.index.sync(["Dockerfile", "container/Dockerfile"])
        after_group = _group(
            [
                _declaration(
                    "intent-after",
                    "pyproject.toml",
                    "3.12",
                    semantic_role={"kind": "project-intent"},
                ),
                _declaration(
                    "runtime-after",
                    "container/Dockerfile",
                    "3.13",
                    semantic_role={"kind": "container-runtime"},
                ),
            ],
            group_id="request-after",
        )
        after = codemap.declarations.observe(
            [after_group],
            previous_observation=before,
        )

    before_by_role = {
        assert_object(assert_object(row)["semantic_role"])["kind"]: row
        for row in assert_array(
            assert_object(assert_array(before["groups"])[0])["declarations"]
        )
    }
    after_by_role = {
        assert_object(assert_object(row)["semantic_role"])["kind"]: row
        for row in assert_array(
            assert_object(assert_array(after["groups"])[0])["declarations"]
        )
    }
    assert (
        assert_object(before_by_role["project-intent"])["semantic_declaration_identity"]
        == assert_object(after_by_role["project-intent"])[
            "semantic_declaration_identity"
        ]
    )
    assert (
        assert_object(before_by_role["container-runtime"])[
            "semantic_declaration_identity"
        ]
        == assert_object(after_by_role["container-runtime"])[
            "semantic_declaration_identity"
        ]
    )

    subject = assert_array(
        assert_object(assert_object(after["delta_from_previous"])["semantic_subjects"])[
            "changed"
        ]
    )[0]
    assert assert_object(subject)["group_id_changed"] is True
    assert "value_changed_declaration_ids" not in assert_object(subject)
    roles = assert_object(subject)["semantic_declarations"]
    assert assert_object(roles)["added"] == []
    assert assert_object(roles)["removed"] == []
    assert assert_object(roles)["ambiguous"] == []
    changed_by_role = {
        assert_object(assert_object(row)["semantic_role"])["kind"]: row
        for row in assert_array(assert_object(roles)["changed"])
    }
    intent = changed_by_role["project-intent"]
    assert assert_object(intent)["declaration_id_changed"] is True
    assert assert_object(intent)["previous_declaration_id"] == "intent-before"
    assert assert_object(intent)["current_declaration_id"] == "intent-after"
    assert "value_transition" not in assert_object(intent)

    runtime = changed_by_role["container-runtime"]
    assert assert_object(runtime)["declaration_id_changed"] is True
    assert assert_object(runtime)["previous_declaration_id"] == "runtime-before"
    assert assert_object(runtime)["current_declaration_id"] == "runtime-after"
    assert assert_object(runtime)["value_transition"] == {
        "before": {"value_state": "resolved", "value": "3.12"},
        "after": {"value_state": "resolved", "value": "3.13"},
    }
    assert (
        assert_object(before_by_role["container-runtime"])[
            "declaration_definition_identity"
        ]
        != assert_object(after_by_role["container-runtime"])[
            "declaration_definition_identity"
        ]
    )
    assert (
        assert_object(
            assert_object(assert_object(subject)["comparison_transition"])["before"]
        )["state"]
        == "equivalent"
    )
    assert (
        assert_object(
            assert_object(assert_object(subject)["comparison_transition"])["after"]
        )["state"]
        == "differing"
    )


def test_semantic_role_identity_is_scoped_by_semantic_subject(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    role = {"kind": "runtime-source"}
    first_group = _group(
        [_declaration("runtime", "runtime.yaml", "3.12", semantic_role=role)]
    )
    second_group = _group(
        [_declaration("runtime", "runtime.yaml", "3.12", semantic_role=role)]
    )
    second_group["concept"] = {
        "kind": "runtime-compatibility",
        "identity": "pypy",
    }

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        first = codemap.declarations.observe([first_group])
        second = codemap.declarations.observe([second_group])

    first_row = assert_array(
        assert_object(assert_array(first["groups"])[0])["declarations"]
    )[0]
    second_row = assert_array(
        assert_object(assert_array(second["groups"])[0])["declarations"]
    )[0]
    assert (
        assert_object(first_row)["semantic_role"]
        == assert_object(second_row)["semantic_role"]
    )
    assert (
        assert_object(first_row)["semantic_declaration_identity"]
        != assert_object(second_row)["semantic_declaration_identity"]
    )


def test_semantic_role_change_is_remove_add_not_guessed_rename(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    before_group = _group(
        [
            _declaration(
                "runtime",
                "runtime.yaml",
                "3.12",
                semantic_role={"kind": "project-intent"},
            )
        ]
    )
    after_group = _group(
        [
            _declaration(
                "runtime",
                "runtime.yaml",
                "3.12",
                semantic_role={"kind": "container-runtime"},
            )
        ]
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([before_group])
        after = codemap.declarations.observe(
            [after_group],
            previous_observation=before,
        )

    before_declaration = assert_array(
        assert_object(assert_array(before["groups"])[0])["declarations"]
    )[0]
    after_declaration = assert_array(
        assert_object(assert_array(after["groups"])[0])["declarations"]
    )[0]
    assert (
        assert_object(before_declaration)["semantic_declaration_identity"]
        != assert_object(after_declaration)["semantic_declaration_identity"]
    )
    roles = assert_object(
        assert_array(
            assert_object(
                assert_object(after["delta_from_previous"])["semantic_subjects"]
            )["changed"]
        )[0]
    )["semantic_declarations"]
    assert assert_object(roles)["removed"] == [
        assert_object(before_declaration)["semantic_declaration_identity"]
    ]
    assert assert_object(roles)["added"] == [
        assert_object(after_declaration)["semantic_declaration_identity"]
    ]
    assert assert_object(roles)["ambiguous"] == []
    assert assert_object(roles)["changed"] == []


def test_unchanged_duplicate_semantic_roles_do_not_manufacture_delta(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.yaml").write_text("python: 3.12\n", encoding="utf-8")
    (repo / "b.yaml").write_text("python: 3.12\n", encoding="utf-8")
    role = {"kind": "runtime-source"}
    group = _group(
        [
            _declaration("a", "a.yaml", "3.12", semantic_role=role),
            _declaration("b", "b.yaml", "3.12", semantic_role=role),
        ]
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([group])
        after = codemap.declarations.observe(
            [group],
            previous_observation=before,
        )

    delta = after["delta_from_previous"]
    assert assert_object(delta)["changed_groups"] == []
    assert assert_object(assert_object(delta)["semantic_subjects"])["changed"] == []
    assert assert_object(assert_object(delta)["semantic_subjects"])["ambiguous"] == []


def test_semantic_role_delta_preserves_duplicate_role_ambiguity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for path in ("a.yaml", "b.yaml", "c.yaml"):
        (repo / path).write_text("python: 3.12\n", encoding="utf-8")
    role = {"kind": "runtime-source"}
    before_group = _group(
        [
            _declaration("a", "a.yaml", "3.12", semantic_role=role),
            _declaration("b", "b.yaml", "3.12", semantic_role=role),
        ],
        group_id="before",
    )
    after_group = _group(
        [_declaration("c", "c.yaml", "3.12", semantic_role=role)],
        group_id="after",
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([before_group])
        after = codemap.declarations.observe(
            [after_group],
            previous_observation=before,
        )

    identity = assert_object(
        assert_array(assert_object(assert_array(before["groups"])[0])["declarations"])[
            0
        ]
    )["semantic_declaration_identity"]
    roles = assert_object(
        assert_array(
            assert_object(
                assert_object(after["delta_from_previous"])["semantic_subjects"]
            )["changed"]
        )[0]
    )["semantic_declarations"]
    assert assert_object(roles)["added"] == []
    assert assert_object(roles)["removed"] == []
    assert assert_object(roles)["changed"] == []
    assert assert_object(roles)["ambiguous"] == [
        {
            "semantic_declaration_identity": identity,
            "previous_declaration_ids": ["a", "b"],
            "current_declaration_ids": ["c"],
            "reason": "semantic-declaration-not-unique",
        }
    ]


def test_one_sided_duplicate_semantic_roles_remain_ambiguous(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    base = _group(
        [_declaration("base", "runtime.yaml", "3.12", semantic_role={"kind": "base"})]
    )
    duplicates = _group(
        [
            *assert_records(base["declarations"]),
            _declaration("a", "runtime.yaml", "3.12", semantic_role={"kind": "extra"}),
            _declaration("b", "runtime.yaml", "3.12", semantic_role={"kind": "extra"}),
        ]
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([base])
        added = codemap.declarations.observe([duplicates], previous_observation=before)
        removed = codemap.declarations.observe([base], previous_observation=added)

    identity = next(
        assert_object(row)["semantic_declaration_identity"]
        for row in assert_array(
            assert_object(assert_array(added["groups"])[0])["declarations"]
        )
        if assert_object(row)["declaration_id"] == "a"
    )
    added_roles = assert_object(
        assert_array(
            assert_object(
                assert_object(added["delta_from_previous"])["semantic_subjects"]
            )["changed"]
        )[0]
    )["semantic_declarations"]
    removed_roles = assert_object(
        assert_array(
            assert_object(
                assert_object(removed["delta_from_previous"])["semantic_subjects"]
            )["changed"]
        )[0]
    )["semantic_declarations"]
    assert added_roles == {
        "added": [identity],
        "removed": [],
        "ambiguous": [
            {
                "semantic_declaration_identity": identity,
                "previous_declaration_ids": [],
                "current_declaration_ids": ["a", "b"],
                "reason": "semantic-declaration-not-unique",
            }
        ],
        "changed": [],
    }
    assert removed_roles == {
        "added": [],
        "removed": [identity],
        "ambiguous": [
            {
                "semantic_declaration_identity": identity,
                "previous_declaration_ids": ["a", "b"],
                "current_declaration_ids": [],
                "reason": "semantic-declaration-not-unique",
            }
        ],
        "changed": [],
    }


@pytest.mark.parametrize("semantic_role", [{}, [], "runtime"])
def test_semantic_role_requires_non_empty_object(
    tmp_path: Path,
    semantic_role: object,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = _declaration("runtime", "runtime.yaml", "3.12")
    declaration["semantic_role"] = semantic_role

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        with pytest.raises(
            ValueError,
            match="semantic_role must be a non-empty object",
        ):
            codemap.declarations.observe([_group([declaration])])


def test_semantic_subject_delta_preserves_duplicate_subject_ambiguity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = [_declaration("runtime", "runtime.yaml", "3.12")]
    before_group = _group(declaration, group_id="single")
    after_groups = [
        _group(declaration, group_id="first"),
        _group(declaration, group_id="second"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([before_group])
        after = codemap.declarations.observe(
            after_groups,
            previous_observation=before,
        )

    subjects = assert_object(after["delta_from_previous"])["semantic_subjects"]
    assert assert_object(subjects)["added"] == []
    assert assert_object(subjects)["removed"] == []
    assert assert_object(subjects)["changed"] == []
    assert assert_object(subjects)["ambiguous"] == [
        {
            "semantic_subject_identity": assert_object(
                assert_array(before["groups"])[0]
            )["semantic_subject_identity"],
            "previous_group_ids": ["single"],
            "current_group_ids": ["first", "second"],
            "reason": "semantic-subject-not-unique",
        }
    ]


def test_one_sided_duplicate_semantic_subjects_remain_ambiguous(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = [_declaration("runtime", "runtime.yaml", "3.12")]
    duplicate_groups = [
        _group(declaration, group_id="first"),
        _group(declaration, group_id="second"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        empty = codemap.declarations.observe([])
        added = codemap.declarations.observe(
            duplicate_groups, previous_observation=empty
        )
        removed = codemap.declarations.observe([], previous_observation=added)

    identity = assert_object(assert_array(added["groups"])[0])[
        "semantic_subject_identity"
    ]
    assert assert_object(added["delta_from_previous"])["semantic_subjects"] == {
        "added": [identity],
        "removed": [],
        "ambiguous": [
            {
                "semantic_subject_identity": identity,
                "previous_group_ids": [],
                "current_group_ids": ["first", "second"],
                "reason": "semantic-subject-not-unique",
            }
        ],
        "changed": [],
    }
    assert assert_object(removed["delta_from_previous"])["semantic_subjects"] == {
        "added": [],
        "removed": [identity],
        "ambiguous": [
            {
                "semantic_subject_identity": identity,
                "previous_group_ids": ["first", "second"],
                "current_group_ids": [],
                "reason": "semantic-subject-not-unique",
            }
        ],
        "changed": [],
    }


def test_semantic_subject_change_is_explicit_in_delta(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = [_declaration("runtime", "runtime.yaml", "3.12")]
    before_group = _group(declaration)
    after_group = _group(declaration)
    after_group["concept"] = {"kind": "runtime-compatibility", "identity": "pypy"}

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        before = codemap.declarations.observe([before_group])
        after = codemap.declarations.observe(
            [after_group],
            previous_observation=before,
        )

    assert (
        assert_object(assert_array(before["groups"])[0])["semantic_subject_identity"]
        != assert_object(assert_array(after["groups"])[0])["semantic_subject_identity"]
    )
    delta = after["delta_from_previous"]
    changed = assert_array(assert_object(delta)["changed_groups"])[0]
    assert assert_object(changed)["semantic_subject_changed"] is True
    assert assert_object(changed)["definition_changed"] is True
    before_subject = assert_object(assert_array(before["groups"])[0])[
        "semantic_subject_identity"
    ]
    after_subject = assert_object(assert_array(after["groups"])[0])[
        "semantic_subject_identity"
    ]
    assert assert_object(assert_object(delta)["semantic_subjects"])["removed"] == [
        before_subject
    ]
    assert assert_object(assert_object(delta)["semantic_subjects"])["added"] == [
        after_subject
    ]
    assert assert_object(assert_object(delta)["semantic_subjects"])["changed"] == []
    assert assert_object(assert_object(delta)["semantic_subjects"])["ambiguous"] == []


def test_group_definition_identity_binds_coverage_scope(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.yaml").write_text("owner: team-a\n", encoding="utf-8")
    declaration = [_declaration("owner", "owner.yaml", "team-a")]
    team_scope = _group(declaration)
    org_scope = _group(declaration)
    assert_object(team_scope["coverage"])["scope"] = {"registry": "team"}
    assert_object(org_scope["coverage"])["scope"] = {"registry": "organization"}

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        team = codemap.declarations.observe([team_scope])
        organization = codemap.declarations.observe([org_scope])

    assert (
        assert_object(assert_array(team["groups"])[0])["group_definition_identity"]
        != assert_object(assert_array(organization["groups"])[0])[
            "group_definition_identity"
        ]
    )


@pytest.mark.parametrize(
    ("concept", "paths", "value"),
    [
        (
            {"kind": "runtime-compatibility", "identity": "python"},
            ("pyproject.toml", "Dockerfile"),
            "3.12",
        ),
        (
            {"kind": "package-identity", "identity": "widget"},
            ("package.json", "Cargo.toml"),
            "widget",
        ),
        (
            {"kind": "ownership", "identity": "component-a"},
            ("CODEOWNERS", "metadata.yaml"),
            "team-a",
        ),
    ],
)
def test_contract_is_format_and_concept_neutral(
    tmp_path: Path,
    concept: dict[str, object],
    paths: tuple[str, str],
    value: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for path in paths:
        (repo / path).write_text(f"{value}\n", encoding="utf-8")
    declarations = [
        _declaration("first", paths[0], value),
        _declaration("second", paths[1], value),
    ]
    group = _group(declarations)
    group["concept"] = concept

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet = codemap.declarations.observe([group])

    assert assert_object(assert_array(packet["groups"])[0])["concept"] == concept
    assert (
        assert_object(assert_object(assert_array(packet["groups"])[0])["comparison"])[
            "state"
        ]
        == "equivalent"
    )


def test_encoded_request_budget_fails_closed_before_repository_projection(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.toml").write_text('version = "1"\n', encoding="utf-8")
    group = _group([_declaration("a", "a.toml", "1")])
    group["concept"] = {"opaque": "x" * 1_048_576}

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        with pytest.raises(ValueError, match="groups exceeds .* encoded bytes"):
            codemap.declarations.observe([group])


def test_resolved_provider_value_with_missing_evidence_cannot_create_conflict(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "current.yaml").write_text("owner: team-a\n", encoding="utf-8")
    declarations = [
        _declaration("current", "current.yaml", "team-a"),
        _declaration("missing", "missing.yaml", "team-b"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet = codemap.declarations.observe([_group(declarations)])

    group = assert_array(packet["groups"])[0]
    by_id = {
        assert_object(row)["declaration_id"]: row
        for row in assert_array(assert_object(group)["declarations"])
    }
    assert assert_object(by_id["current"])["evidence_state"] == "known-present"
    assert assert_object(by_id["missing"])["evidence_state"] == "known-absent"
    assert assert_object(group)["comparison"] == {
        "state": "ambiguous",
        "reason": "repository-evidence-not-qualified",
        "unqualified_declaration_ids": ["missing"],
        "distinct_values": [],
    }
    assert assert_object(group)["absence"] == {
        "state": "known-absent",
        "missing_declaration_ids": ["missing"],
        "unseen_expected_declaration_ids": [],
        "unexpected_declaration_ids": [],
    }


def test_unsupported_declaration_evidence_cannot_create_equivalence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "current.txt").write_text("same\n", encoding="utf-8")
    (repo / "binary.dat").write_bytes(b"\xff\xfe")
    declarations = [
        _declaration("current", "current.txt", "same"),
        _declaration("binary", "binary.dat", "same"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet = codemap.declarations.observe([_group(declarations)])

    group = assert_array(packet["groups"])[0]
    by_id = {
        assert_object(row)["declaration_id"]: row
        for row in assert_array(assert_object(group)["declarations"])
    }
    assert assert_object(by_id["binary"])["evidence_state"] == "unsupported"
    assert assert_object(assert_object(group)["comparison"])["state"] == "ambiguous"
    assert (
        assert_object(assert_object(group)["comparison"])["reason"]
        == "repository-evidence-not-qualified"
    )
    assert assert_object(assert_object(group)["comparison"])[
        "unqualified_declaration_ids"
    ] == ["binary"]


def test_declaration_claims_require_provenance_and_distinct_ambiguity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.yaml").write_text("value: a\n", encoding="utf-8")
    base = _group([_declaration("a", "a.yaml", "a")])

    missing_basis = _group([_declaration("a", "a.yaml", "a")])
    assert_object(missing_basis["correspondence"])["basis"] = {}

    missing_coverage_provenance = _group([_declaration("a", "a.yaml", "a")])
    assert_object(missing_coverage_provenance["coverage"])["provenance"] = {}

    missing_producer = _group([_declaration("a", "a.yaml", "a")])
    assert_object(assert_array(missing_producer["declarations"])[0])["producer"] = {}

    duplicate_candidates = _group([_declaration("a", "a.yaml", "a")])
    ambiguous = assert_array(duplicate_candidates["declarations"])[0]
    assert_object(ambiguous)["value_state"] = "ambiguous"
    assert_object(ambiguous).pop("value")
    assert_object(ambiguous)["candidate_values"] = ["same", "same"]

    empty_concept = dict(base)
    empty_concept["concept"] = {}

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        with pytest.raises(ValueError, match="correspondence.basis"):
            codemap.declarations.observe([missing_basis])
        with pytest.raises(ValueError, match="coverage.provenance"):
            codemap.declarations.observe([missing_coverage_provenance])
        with pytest.raises(ValueError, match="producer must be"):
            codemap.declarations.observe([missing_producer])
        with pytest.raises(ValueError, match="distinct candidate values"):
            codemap.declarations.observe([duplicate_candidates])
        with pytest.raises(ValueError, match="concept must be"):
            codemap.declarations.observe([empty_concept])


def test_ambiguous_candidate_order_does_not_change_observation_identity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.yaml").write_text("value: maybe\n", encoding="utf-8")

    def ambiguous(values: list[str]) -> dict[str, object]:
        declaration = _declaration("value", "value.yaml", "unused")
        declaration["value_state"] = "ambiguous"
        declaration.pop("value")
        declaration["candidate_values"] = values
        return _group([declaration])

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        first = codemap.declarations.observe([ambiguous(["b", "a"])])
        second = codemap.declarations.observe([ambiguous(["a", "b"])])

    assert first["observation_identity"] == second["observation_identity"]
    assert assert_object(
        assert_array(assert_object(assert_array(first["groups"])[0])["declarations"])[0]
    )["candidate_values"] == ["a", "b"]


def test_expected_membership_exposes_unexpected_current_declaration(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.yaml").write_text("value: a\n", encoding="utf-8")
    (repo / "b.yaml").write_text("value: b\n", encoding="utf-8")
    declarations = [
        _declaration("a", "a.yaml", "a"),
        _declaration("b", "b.yaml", "b"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet = codemap.declarations.observe([_group(declarations, expected=["a"])])

    assert assert_object(assert_array(packet["groups"])[0])["absence"] == {
        "state": "known-present",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": [],
        "unexpected_declaration_ids": ["b"],
    }


def test_previous_declaration_packet_from_foreign_repository_fails_closed(
    tmp_path: Path,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    for repo in (left, right):
        (repo / "owner.yaml").write_text("owner: team-a\n", encoding="utf-8")
    group = _group([_declaration("owner", "owner.yaml", "team-a")])

    with CodeMap(left, state_dir=tmp_path / "left-state") as codemap:
        codemap.index.sync()
        previous = codemap.declarations.observe([group])

    with CodeMap(right, state_dir=tmp_path / "right-state") as codemap:
        codemap.index.sync()
        with pytest.raises(
            ValueError,
            match="previous declaration observation repository-mismatch",
        ):
            codemap.declarations.observe([group], previous_observation=previous)
