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
) -> dict[str, object]:
    return {
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
    assert changed["definition_changed"] is True
    assert changed["definition_changed_declaration_ids"] == ["runtime"]


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
        "reason": "repository-evidence-not-current",
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
    assert group["comparison"]["reason"] == "repository-evidence-not-current"
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

    assert (
        first["observation_identity"]
        == second["observation_identity"]
    )
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
        packet = codemap.repository_declarations(
            [_group(declarations, expected=["a"])]
        )

    assert packet["groups"][0]["absence"] == {
        "state": "known-present",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": [],
        "unexpected_declaration_ids": ["b"],
    }
