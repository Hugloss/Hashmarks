from __future__ import annotations

from pathlib import Path

import pytest

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
    semantic_role: dict[str, object] | None = None,
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
        codemap.sync()
        packet = codemap.repository_declarations([_group(declarations)])

    group = packet["groups"][0]
    assert packet["schema"] == "hashmarks.repository-declarations.v1"
    assert packet["winner"] == "not-selected"
    assert packet["correspondence_authority"] == "provider-claimed"
    assert group["comparison"] == {
        "state": "equivalent",
        "distinct_values": [">=3.12"],
    }
    assert group["absence"]["state"] == "known-present"
    bindings = {
        row["binding_id"]: row for row in packet["repository_evidence"]["bindings"]
    }
    paths = {
        bindings[row["binding_id"]]["evidence"][0]["path"]
        for row in group["declarations"]
    }
    assert paths == {"pyproject.toml", "Dockerfile"}
    assert all(
        bindings[row["binding_id"]]["evidence"][0]["span_identity"].startswith(
            "sha256:"
        )
        for row in group["declarations"]
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
        codemap.sync()
        packet = codemap.repository_declarations([_group(declarations)])

    comparison = packet["groups"][0]["comparison"]
    assert comparison["state"] == "differing"
    assert comparison["distinct_values"] == ["3.12", "3.13"]
    assert packet["winner"] == "not-selected"
    assert "preferred" not in comparison
    assert "authoritative_value" not in comparison


def test_absence_requires_complete_untruncated_semantic_coverage(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.yaml").write_text("owner: team-a\n", encoding="utf-8")
    declarations = [_declaration("owner-a", "a.yaml", "team-a")]
    expected = ["owner-a", "owner-b"]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        unknown = codemap.repository_declarations(
            [
                _group(
                    declarations,
                    coverage=("incomplete", "unknown"),
                    expected=expected,
                )
            ]
        )
        absent = codemap.repository_declarations(
            [_group(declarations, expected=expected)]
        )

    assert unknown["groups"][0]["absence"] == {
        "state": "unknown",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": ["owner-b"],
        "unexpected_declaration_ids": [],
        "reason": "coverage-does-not-authorize-negative-evidence",
    }
    assert absent["groups"][0]["absence"] == {
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
        codemap.sync()
        packet = codemap.repository_declarations([group])

    projected = packet["groups"][0]
    assert projected["declarations"][0]["semantic_declaration_identity"].startswith(
        "sha256:"
    )
    assert projected["absence"] == {
        "state": "unknown",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": [],
        "unexpected_declaration_ids": ["runtime"],
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
        codemap.sync()
        packet = codemap.repository_declarations(
            [_group(declarations, correspondence_state="ambiguous")]
        )

    assert packet["groups"][0]["comparison"] == {
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
        codemap.sync()
        with pytest.raises(ValueError, match="semantic_namespace"):
            codemap.repository_declarations([missing_namespace])
        first_group = _group(declaration)
        first_group["semantic_namespace"] = "provider-a"
        second_group = _group(declaration)
        second_group["semantic_namespace"] = "provider-b"
        first = codemap.repository_declarations([first_group])
        second = codemap.repository_declarations([second_group])

    assert (
        first["groups"][0]["semantic_subject_identity"]
        != second["groups"][0]["semantic_subject_identity"]
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
        codemap.sync()
        first = codemap.repository_declarations([first_group])
        second = codemap.repository_declarations([second_group])

    first_group_result = first["groups"][0]
    second_group_result = second["groups"][0]
    assert (
        first_group_result["semantic_subject_identity"]
        == second_group_result["semantic_subject_identity"]
    )
    assert (
        first_group_result["group_definition_identity"]
        != second_group_result["group_definition_identity"]
    )
    first_declaration = first_group_result["declarations"][0]
    second_declaration = second_group_result["declarations"][0]
    assert (
        first_declaration["semantic_subject_identity"]
        == first_group_result["semantic_subject_identity"]
    )
    assert (
        second_declaration["semantic_subject_identity"]
        == second_group_result["semantic_subject_identity"]
    )
    assert (
        first_declaration["declaration_definition_identity"]
        != second_declaration["declaration_definition_identity"]
    )


def test_scope_is_part_of_definition_identity_and_prevents_cross_context_merging(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = [_declaration("runtime", "runtime.yaml", "3.12")]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        linux = codemap.repository_declarations(
            [_group(declaration, scope={"platform": "linux"})]
        )
        windows = codemap.repository_declarations(
            [_group(declaration, scope={"platform": "windows"})]
        )

    assert (
        linux["groups"][0]["group_definition_identity"]
        != windows["groups"][0]["group_definition_identity"]
    )
    assert (
        linux["groups"][0]["semantic_subject_identity"]
        != windows["groups"][0]["semantic_subject_identity"]
    )
    assert linux["groups"][0]["comparison"]["state"] == "insufficient"
    assert windows["groups"][0]["comparison"]["state"] == "insufficient"


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
        codemap.sync()
        before = codemap.repository_declarations([_group(before_declarations)])
        after = codemap.repository_declarations(
            [_group(after_declarations)],
            previous_observation=before,
        )

    delta = after["delta_from_previous"]
    assert delta["schema"] == "hashmarks.repository-declarations-delta.v1"
    assert len(delta["changed_groups"]) == 1
    changed = delta["changed_groups"][0]
    assert changed["definition_changed"] is False
    assert changed["value_changed_declaration_ids"] == ["b"]
    assert changed["comparison_changed"] is True
    subject_change = delta["semantic_subjects"]["changed"][0]
    assert subject_change["value_changed_declaration_ids"] == ["b"]
    assert subject_change["comparison_transition"]["before"]["state"] == "equivalent"
    assert subject_change["comparison_transition"]["after"]["state"] == "differing"
    assert delta["repository_evidence"]["bindings"]["changed"] == []


def test_previous_declaration_packet_is_revalidated_before_delta(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.toml").write_text('version = "1"\n', encoding="utf-8")
    declarations = [_declaration("a", "a.toml", "1")]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.repository_declarations([_group(declarations)])
        before["groups"][0]["concept"]["identity"] = "tampered"
        with pytest.raises(
            ValueError, match="previous declaration observation identity mismatch"
        ):
            codemap.repository_declarations(
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
        codemap.sync()
        before = codemap.repository_declarations([_group(declarations)])
        evidence = before["repository_evidence"]
        evidence["bindings"][0]["evidence"][0]["state"] = "known-absent"
        before["observation_identity"] = codemap._declaration_packet_identity(before)

        with pytest.raises(ValueError, match="bindings identity mismatch"):
            codemap.repository_declarations(
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
        codemap.sync()
        with pytest.raises(ValueError, match="unknown fields"):
            codemap.repository_declarations([bad])
        with pytest.raises(ValueError, match="complete declaration coverage requires"):
            codemap.repository_declarations(
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
        codemap.sync()
        before = codemap.repository_declarations([before_group])
        after = codemap.repository_declarations(
            [after_group],
            previous_observation=before,
        )

    previous = before["groups"][0]["declarations"][0]
    current = after["groups"][0]["declarations"][0]
    assert (
        previous["declaration_definition_identity"]
        != current["declaration_definition_identity"]
    )
    changed = after["delta_from_previous"]["changed_groups"][0]
    assert changed["semantic_subject_changed"] is False
    assert changed["definition_changed"] is True
    assert changed["definition_changed_declaration_ids"] == ["runtime"]


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
        codemap.sync()
        before = codemap.repository_declarations([before_group])
        after = codemap.repository_declarations(
            [after_group],
            previous_observation=before,
        )

    delta = after["delta_from_previous"]
    assert delta["added_group_ids"] == ["request-b"]
    assert delta["removed_group_ids"] == ["request-a"]
    subjects = delta["semantic_subjects"]
    assert subjects["added"] == []
    assert subjects["removed"] == []
    assert subjects["ambiguous"] == []
    assert len(subjects["changed"]) == 1
    change = subjects["changed"][0]
    assert change["group_id_changed"] is True
    assert change["previous_group_id"] == "request-a"
    assert change["current_group_id"] == "request-b"
    assert "value_changed_declaration_ids" not in change
    assert "producer_changed_declaration_ids" not in change
    assert "evidence_state_changed_declaration_ids" not in change
    assert "added_declaration_ids" not in change
    assert "removed_declaration_ids" not in change
    assert "semantic_declarations" not in change
    assert "comparison_transition" not in change
    assert "absence_transition" not in change


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
        codemap.sync()
        before = codemap.repository_declarations([before_group])
        moved = repo / "container" / "Dockerfile"
        moved.parent.mkdir()
        (repo / "Dockerfile").replace(moved)
        moved.write_text("python = 3.13\n", encoding="utf-8")
        codemap.sync(["Dockerfile", "container/Dockerfile"])
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
        after = codemap.repository_declarations(
            [after_group],
            previous_observation=before,
        )

    before_by_role = {
        row["semantic_role"]["kind"]: row for row in before["groups"][0]["declarations"]
    }
    after_by_role = {
        row["semantic_role"]["kind"]: row for row in after["groups"][0]["declarations"]
    }
    assert (
        before_by_role["project-intent"]["semantic_declaration_identity"]
        == after_by_role["project-intent"]["semantic_declaration_identity"]
    )
    assert (
        before_by_role["container-runtime"]["semantic_declaration_identity"]
        == after_by_role["container-runtime"]["semantic_declaration_identity"]
    )

    subject = after["delta_from_previous"]["semantic_subjects"]["changed"][0]
    assert subject["group_id_changed"] is True
    assert "value_changed_declaration_ids" not in subject
    roles = subject["semantic_declarations"]
    assert roles["added"] == []
    assert roles["removed"] == []
    assert roles["ambiguous"] == []
    changed_by_role = {
        row["semantic_role"]["kind"]: row for row in roles["changed"]
    }
    intent = changed_by_role["project-intent"]
    assert intent["declaration_id_changed"] is True
    assert intent["previous_declaration_id"] == "intent-before"
    assert intent["current_declaration_id"] == "intent-after"
    assert "value_transition" not in intent

    runtime = changed_by_role["container-runtime"]
    assert runtime["declaration_id_changed"] is True
    assert runtime["previous_declaration_id"] == "runtime-before"
    assert runtime["current_declaration_id"] == "runtime-after"
    assert runtime["value_transition"] == {
        "before": {"value_state": "resolved", "value": "3.12"},
        "after": {"value_state": "resolved", "value": "3.13"},
    }
    assert (
        before_by_role["container-runtime"]["declaration_definition_identity"]
        != after_by_role["container-runtime"]["declaration_definition_identity"]
    )
    assert subject["comparison_transition"]["before"]["state"] == "equivalent"
    assert subject["comparison_transition"]["after"]["state"] == "differing"


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
        codemap.sync()
        first = codemap.repository_declarations([first_group])
        second = codemap.repository_declarations([second_group])

    first_row = first["groups"][0]["declarations"][0]
    second_row = second["groups"][0]["declarations"][0]
    assert first_row["semantic_role"] == second_row["semantic_role"]
    assert (
        first_row["semantic_declaration_identity"]
        != second_row["semantic_declaration_identity"]
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
        codemap.sync()
        before = codemap.repository_declarations([before_group])
        after = codemap.repository_declarations(
            [after_group],
            previous_observation=before,
        )

    before_declaration = before["groups"][0]["declarations"][0]
    after_declaration = after["groups"][0]["declarations"][0]
    assert (
        before_declaration["semantic_declaration_identity"]
        != after_declaration["semantic_declaration_identity"]
    )
    roles = after["delta_from_previous"]["semantic_subjects"]["changed"][0][
        "semantic_declarations"
    ]
    assert roles["removed"] == [
        before_declaration["semantic_declaration_identity"]
    ]
    assert roles["added"] == [after_declaration["semantic_declaration_identity"]]
    assert roles["ambiguous"] == []
    assert roles["changed"] == []


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
        codemap.sync()
        before = codemap.repository_declarations([group])
        after = codemap.repository_declarations(
            [group],
            previous_observation=before,
        )

    delta = after["delta_from_previous"]
    assert delta["changed_groups"] == []
    assert delta["semantic_subjects"]["changed"] == []
    assert delta["semantic_subjects"]["ambiguous"] == []


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
        codemap.sync()
        before = codemap.repository_declarations([before_group])
        after = codemap.repository_declarations(
            [after_group],
            previous_observation=before,
        )

    identity = before["groups"][0]["declarations"][0][
        "semantic_declaration_identity"
    ]
    roles = after["delta_from_previous"]["semantic_subjects"]["changed"][0][
        "semantic_declarations"
    ]
    assert roles["added"] == []
    assert roles["removed"] == []
    assert roles["changed"] == []
    assert roles["ambiguous"] == [
        {
            "semantic_declaration_identity": identity,
            "previous_declaration_ids": ["a", "b"],
            "current_declaration_ids": ["c"],
            "reason": "semantic-declaration-not-unique",
        }
    ]


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
        codemap.sync()
        with pytest.raises(ValueError, match="semantic_role must be a non-empty object"):
            codemap.repository_declarations([_group([declaration])])


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
        codemap.sync()
        before = codemap.repository_declarations([before_group])
        after = codemap.repository_declarations(
            after_groups,
            previous_observation=before,
        )

    subjects = after["delta_from_previous"]["semantic_subjects"]
    assert subjects["added"] == []
    assert subjects["removed"] == []
    assert subjects["changed"] == []
    assert subjects["ambiguous"] == [
        {
            "semantic_subject_identity": before["groups"][0][
                "semantic_subject_identity"
            ],
            "previous_group_ids": ["single"],
            "current_group_ids": ["first", "second"],
            "reason": "semantic-subject-not-unique",
        }
    ]


def test_semantic_subject_change_is_explicit_in_delta(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "runtime.yaml").write_text("python: 3.12\n", encoding="utf-8")
    declaration = [_declaration("runtime", "runtime.yaml", "3.12")]
    before_group = _group(declaration)
    after_group = _group(declaration)
    after_group["concept"] = {"kind": "runtime-compatibility", "identity": "pypy"}

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.repository_declarations([before_group])
        after = codemap.repository_declarations(
            [after_group],
            previous_observation=before,
        )

    assert (
        before["groups"][0]["semantic_subject_identity"]
        != after["groups"][0]["semantic_subject_identity"]
    )
    delta = after["delta_from_previous"]
    changed = delta["changed_groups"][0]
    assert changed["semantic_subject_changed"] is True
    assert changed["definition_changed"] is True
    before_subject = before["groups"][0]["semantic_subject_identity"]
    after_subject = after["groups"][0]["semantic_subject_identity"]
    assert delta["semantic_subjects"]["removed"] == [before_subject]
    assert delta["semantic_subjects"]["added"] == [after_subject]
    assert delta["semantic_subjects"]["changed"] == []
    assert delta["semantic_subjects"]["ambiguous"] == []


def test_group_definition_identity_binds_coverage_scope(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.yaml").write_text("owner: team-a\n", encoding="utf-8")
    declaration = [_declaration("owner", "owner.yaml", "team-a")]
    team_scope = _group(declaration)
    org_scope = _group(declaration)
    team_scope["coverage"]["scope"] = {"registry": "team"}
    org_scope["coverage"]["scope"] = {"registry": "organization"}

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        team = codemap.repository_declarations([team_scope])
        organization = codemap.repository_declarations([org_scope])

    assert (
        team["groups"][0]["group_definition_identity"]
        != organization["groups"][0]["group_definition_identity"]
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
        codemap.sync()
        packet = codemap.repository_declarations([group])

    assert packet["groups"][0]["concept"] == concept
    assert packet["groups"][0]["comparison"]["state"] == "equivalent"


def test_encoded_request_budget_fails_closed_before_repository_projection(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.toml").write_text('version = "1"\n', encoding="utf-8")
    group = _group([_declaration("a", "a.toml", "1")])
    group["concept"] = {"opaque": "x" * 1_048_576}

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="groups exceeds .* encoded bytes"):
            codemap.repository_declarations([group])


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
        codemap.sync()
        packet = codemap.repository_declarations([_group(declarations)])

    group = packet["groups"][0]
    by_id = {row["declaration_id"]: row for row in group["declarations"]}
    assert by_id["current"]["evidence_state"] == "known-present"
    assert by_id["missing"]["evidence_state"] == "known-absent"
    assert group["comparison"] == {
        "state": "ambiguous",
        "reason": "repository-evidence-not-qualified",
        "unqualified_declaration_ids": ["missing"],
        "distinct_values": [],
    }
    assert group["absence"] == {
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
        codemap.sync()
        packet = codemap.repository_declarations([_group(declarations)])

    group = packet["groups"][0]
    by_id = {row["declaration_id"]: row for row in group["declarations"]}
    assert by_id["binary"]["evidence_state"] == "unsupported"
    assert group["comparison"]["state"] == "ambiguous"
    assert group["comparison"]["reason"] == "repository-evidence-not-qualified"
    assert group["comparison"]["unqualified_declaration_ids"] == ["binary"]


def test_declaration_claims_require_provenance_and_distinct_ambiguity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.yaml").write_text("value: a\n", encoding="utf-8")
    base = _group([_declaration("a", "a.yaml", "a")])

    missing_basis = _group([_declaration("a", "a.yaml", "a")])
    missing_basis["correspondence"]["basis"] = {}

    missing_coverage_provenance = _group([_declaration("a", "a.yaml", "a")])
    missing_coverage_provenance["coverage"]["provenance"] = {}

    missing_producer = _group([_declaration("a", "a.yaml", "a")])
    missing_producer["declarations"][0]["producer"] = {}

    duplicate_candidates = _group([_declaration("a", "a.yaml", "a")])
    ambiguous = duplicate_candidates["declarations"][0]
    ambiguous["value_state"] = "ambiguous"
    ambiguous.pop("value")
    ambiguous["candidate_values"] = ["same", "same"]

    empty_concept = dict(base)
    empty_concept["concept"] = {}

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="correspondence.basis"):
            codemap.repository_declarations([missing_basis])
        with pytest.raises(ValueError, match="coverage.provenance"):
            codemap.repository_declarations([missing_coverage_provenance])
        with pytest.raises(ValueError, match="producer must be"):
            codemap.repository_declarations([missing_producer])
        with pytest.raises(ValueError, match="distinct candidate values"):
            codemap.repository_declarations([duplicate_candidates])
        with pytest.raises(ValueError, match="concept must be"):
            codemap.repository_declarations([empty_concept])


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
        codemap.sync()
        first = codemap.repository_declarations([ambiguous(["b", "a"])])
        second = codemap.repository_declarations([ambiguous(["a", "b"])])

    assert first["observation_identity"] == second["observation_identity"]
    assert first["groups"][0]["declarations"][0]["candidate_values"] == ["a", "b"]


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
        codemap.sync()
        packet = codemap.repository_declarations([_group(declarations, expected=["a"])])

    assert packet["groups"][0]["absence"] == {
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
        codemap.sync()
        previous = codemap.repository_declarations([group])

    with CodeMap(right, state_dir=tmp_path / "right-state") as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="previous declaration observation repository-mismatch",
        ):
            codemap.repository_declarations([group], previous_observation=previous)
