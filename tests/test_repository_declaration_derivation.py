from __future__ import annotations

import copy
from pathlib import Path

import pytest

from hashmarks import CodeMap


def _declaration(
    declaration_id: str,
    path: str,
    value: object,
    *,
    producer: str = "fixture-config",
    line: int = 1,
) -> dict[str, object]:
    return {
        "declaration_id": declaration_id,
        "value_state": "resolved",
        "value": value,
        "producer": {"kind": producer},
        "evidence": [
            {
                "path": path,
                "start_line": line,
                "end_line": line,
            }
        ],
    }


def _group(
    declarations: list[dict[str, object]],
    *,
    group_id: str = "runtime-python",
) -> dict[str, object]:
    ids = [str(row["declaration_id"]) for row in declarations]
    return {
        "group_id": group_id,
        "concept": {"kind": "runtime-compatibility", "identity": "python"},
        "scope": {},
        "correspondence": {
            "state": "declared",
            "basis": {"provider": "fixture", "rule": "explicit-semantic-mapping"},
        },
        "declarations": declarations,
        "coverage": {
            "state": "complete",
            "truncation": "complete",
            "expected_declaration_ids": ids,
            "scope": {"repository": "fixture"},
            "provenance": {"provider": "fixture"},
        },
    }


def test_declaration_derivation_traces_exact_repository_evidence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        'requires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    (repo / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    group = _group(
        [
            _declaration("python-intent", "pyproject.toml", ">=3.12"),
            _declaration("python-container", "Dockerfile", ">=3.12"),
        ]
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.repository_declarations([group])
        derivation = codemap.repository_declaration_derivation_authority(packet)

    assert derivation["schema"] == "hashmarks.repository-declaration-derivation.v1"
    assert derivation["observation_identity"] == packet["observation_identity"]
    assert derivation["repository_evidence_identity"] == packet[
        "repository_evidence"
    ]["bindings_identity"]
    assert derivation["semantic_value_authority"] == "provider-claimed"
    assert derivation["interpretation_authority"] == "consumer-owned"

    group_authority = derivation["groups"][0]
    assert group_authority["group_id"] == "runtime-python"
    by_id = {
        row["declaration_id"]: row for row in group_authority["declarations"]
    }
    assert {
        row["repository_evidence"][0]["path"] for row in by_id.values()
    } == {"pyproject.toml", "Dockerfile"}
    assert all(
        row["binding_observation_identity"].startswith("sha256:")
        for row in by_id.values()
    )


def test_declaration_explain_is_endpoint_local_after_repository_advances(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    path = repo / "owner.yaml"
    path.write_text("owner: team-a\n", encoding="utf-8")
    group = _group([_declaration("owner", "owner.yaml", "team-a")])

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.repository_declarations([group])
        original_repository = copy.deepcopy(packet["repository"])

        path.write_text("owner: team-b\n", encoding="utf-8")
        codemap.sync(["owner.yaml"])

        explanation = codemap.repository_declaration_explain(packet)

    assert explanation["schema"] == "hashmarks.repository-declaration-explain.v1"
    assert explanation["semantic_result"]["observation_identity"] == packet[
        "observation_identity"
    ]
    assert explanation["semantic_result"]["group_count"] == 1
    assert explanation["semantic_result"]["declaration_count"] == 1
    assert explanation["derivation"]["repository"] == original_repository


def test_declaration_derivation_rejects_resigned_nested_identity_tamper(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.yaml").write_text("owner: team-a\n", encoding="utf-8")
    group = _group([_declaration("owner", "owner.yaml", "team-a")])

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.repository_declarations([group])
        tampered = copy.deepcopy(packet)
        tampered["groups"][0]["declarations"][0]["producer"] = {
            "kind": "forged-provider"
        }
        tampered["observation_identity"] = codemap._declaration_packet_identity(
            tampered
        )

        with pytest.raises(
            ValueError,
            match="declaration observation identity mismatch",
        ):
            codemap.repository_declaration_derivation_authority(tampered)


def test_declaration_producer_change_preserves_definition_but_changes_derivation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.yaml").write_text("owner: team-a\n", encoding="utf-8")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.repository_declarations(
            [
                _group(
                    [
                        _declaration(
                            "owner",
                            "owner.yaml",
                            "team-a",
                            producer="fixture-a",
                        )
                    ]
                )
            ]
        )
        after = codemap.repository_declarations(
            [
                _group(
                    [
                        _declaration(
                            "owner",
                            "owner.yaml",
                            "team-a",
                            producer="fixture-b",
                        )
                    ]
                )
            ]
        )
        before_derivation = codemap.repository_declaration_derivation_authority(
            before
        )
        after_derivation = codemap.repository_declaration_derivation_authority(
            after
        )

    before_row = before["groups"][0]["declarations"][0]
    after_row = after["groups"][0]["declarations"][0]
    assert (
        before_row["declaration_definition_identity"]
        == after_row["declaration_definition_identity"]
    )
    assert (
        before_row["declaration_observation_identity"]
        != after_row["declaration_observation_identity"]
    )
    assert (
        before_derivation["derivation_identity"]
        != after_derivation["derivation_identity"]
    )


def test_declaration_evidence_definition_change_is_explicit_authority_change(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.yaml").write_text(
        "owner: team-a\nowner: team-a\n",
        encoding="utf-8",
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.repository_declarations(
            [_group([_declaration("owner", "owner.yaml", "team-a", line=1)])]
        )
        after = codemap.repository_declarations(
            [_group([_declaration("owner", "owner.yaml", "team-a", line=2)])]
        )
        before_derivation = codemap.repository_declaration_derivation_authority(
            before
        )
        after_derivation = codemap.repository_declaration_derivation_authority(
            after
        )

    before_row = before["groups"][0]["declarations"][0]
    after_row = after["groups"][0]["declarations"][0]
    assert (
        before_row["declaration_definition_identity"]
        != after_row["declaration_definition_identity"]
    )
    assert (
        before_derivation["derivation_identity"]
        != after_derivation["derivation_identity"]
    )


def test_declaration_explain_preserves_provider_claims_without_adapter_contract(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.yaml").write_text("owner: team-a\n", encoding="utf-8")
    group = _group([_declaration("owner", "owner.yaml", "team-a")])

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.repository_declarations([group])
        explanation = codemap.repository_declaration_explain(packet)

    declaration = explanation["derivation"]["groups"][0]["declarations"][0]
    assert declaration["producer"] == {"kind": "fixture-config"}
    assert "adapter_semantics" not in declaration["producer"]
    assert explanation["semantic_value_authority"] == "provider-claimed"
    assert explanation["interpretation_authority"] == "consumer-owned"
