"""Dependency/verifier relevance is composed by the producer, with bounded proof."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from copy import deepcopy
from pathlib import Path

import pytest
from contract_assertions import (
    assert_array,
    assert_integer,
    assert_object,
    assert_records,
)

from hashmarks import CodeMap, hash_file
from hashmarks.adapters import (
    npm_lock_dependency_observation,
    uv_lock_dependency_observation,
)
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.codemap.repository_observation import evidence_identity
from hashmarks.dependency_verification_validation import (
    validate_dependency_verification,
)
from hashmarks.file_store import UnstableFileError

_LOCK = b"""version = 1
revision = 3
[[package]]
name = "application"
version = "0.1"
source = { virtual = "." }
dependencies = [{ name = "sample-distribution" }]
[[package]]
name = "sample-distribution"
version = "1.0"
source = { registry = "https://example.invalid/simple" }
dependencies = [{ name = "child-distribution" }]
[[package]]
name = "child-distribution"
version = "1.0"
source = { registry = "https://example.invalid/simple" }
"""


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[CodeMap]:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "bridge.py").write_text(
        "import sample_api\ndef run(): return sample_api.answer()\n"
    )
    (workspace / "tests").mkdir()
    (workspace / "tests/test_bridge.py").write_text(
        "from bridge import run\ndef test_run(): assert run() == 1\n"
    )
    (workspace / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    (workspace / "uv.lock").write_bytes(_LOCK)
    with CodeMap(workspace, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        yield repository


def _observation(
    repository: CodeMap,
    *,
    conditional: bool = False,
    ambiguous: bool = False,
    extra_context: bool = False,
) -> tuple[dict[str, object], dict[str, str]]:
    lock = (
        _LOCK.replace(
            b'{ name = "child-distribution" }',
            b'{ name = "child-distribution", marker = "python_version >= \'3.12\'" }',
        )
        if conditional
        else _LOCK
    )
    (repository.workspace / "uv.lock").write_bytes(lock)
    repository.index.sync()
    raw = uv_lock_dependency_observation(lock=lock)
    nodes = {
        str(row["component_id"]): str(row["node_id"])
        for row in assert_records(raw["selections"])
    }
    metadata = [
        {
            "node_id": nodes[name],
            "metadata": f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n\n".encode(),
            "record": b"sample_api/__init__.py,,\n",
        }
        for name in (
            ["sample-distribution", "child-distribution"]
            if ambiguous
            else ["sample-distribution"]
        )
    ]
    snapshot = uv_lock_dependency_observation(
        lock=lock,
        repository_inputs=[
            {
                "path": "uv.lock",
                "member_revision": hash_file(repository.workspace / "uv.lock").hash,
            }
        ],
        distribution_metadata=metadata,
    )
    if extra_context:
        assert_array(snapshot["contexts"]).append("other")
    observation = repository.dependencies.observe(snapshot)
    return observation, nodes


def _packet(
    repository: CodeMap,
    observation: Mapping[str, object],
    nodes: Mapping[str, str],
) -> dict[str, object]:
    return repository.dependencies.verification(
        observation,
        source_paths=["bridge.py"],
        node_ids=[nodes["sample-distribution"], nodes["child-distribution"]],
        context="lock",
        dependency_pairs=[
            {
                "source_node_id": nodes["sample-distribution"],
                "target_node_id": nodes["child-distribution"],
            }
        ],
    )


def test_native_dependency_path_and_import_share_one_verifier_packet(
    repository: CodeMap,
) -> None:
    observation, nodes = _observation(repository)
    packet = _packet(repository, observation, nodes)
    chains = assert_records(packet["chains"])
    assert {row["node_id"] for row in chains} == {
        nodes["sample-distribution"],
        nodes["child-distribution"],
    }
    child = next(row for row in chains if row["node_id"] == nodes["child-distribution"])
    assert child["consumer_node_id"] == nodes["sample-distribution"]
    assert child["dependency_path"] == [
        nodes["sample-distribution"],
        nodes["child-distribution"],
    ]
    assert len(assert_records(packet["verification_packets"])) == 1
    assert (
        child["consumer_index"]
        == child["verification_index"]
        == child["target_index"]
        == 0
    )
    assert validate_dependency_verification(packet, observation)["valid"] is True
    assert packet["negative_evidence_admissible"] is False
    assert packet["completeness"] == "incomplete"


def test_delta_projects_selected_component_inventory_and_root_dependency_facts(
    repository: CodeMap,
) -> None:
    before_lock = _LOCK.replace(
        b'dependencies = [{ name = "child-distribution" }]\n', b""
    ).split(b'[[package]]\nname = "child-distribution"')[0]
    before_lock = before_lock.replace(
        b'name = "sample-distribution"\nversion = "1.0"',
        b'name = "sample-distribution"\nversion = "0.9"',
    )
    before = repository.dependencies.observe(
        uv_lock_dependency_observation(lock=before_lock)
    )
    after = repository.dependencies.observe(uv_lock_dependency_observation(lock=_LOCK))
    delta = repository.dependencies.delta(before, after)
    rows = {
        assert_object(row["component"])["name"]: row
        for row in assert_records(assert_object(delta["selection_changes"])["added"])
    }
    parent, child = rows["sample-distribution"], rows["child-distribution"]
    assert (
        parent["component_selection_count"] == child["component_selection_count"] == 1
    )
    assert child["roots"] == []
    assert len(assert_records(child["inventory"])) == 1
    assert child["root_relationships"] == []
    assert len(assert_records(parent["root_relationships"])) == 1
    edge = assert_records(child["incoming_relationships"])[0]
    assert edge["source"] == assert_object(parent["selection"])["node_id"]
    assert edge["target"] == assert_object(child["selection"])["node_id"]
    # Projection ownership does not alias retained endpoint facts.
    assert_object(parent["component"])["name"] = "changed-projection"
    assert all(
        row["name"] != "changed-projection"
        for row in assert_records(after["components"])
    )


def test_conditional_path_is_retained_without_claiming_child_relevance(
    repository: CodeMap,
) -> None:
    observation, nodes = _observation(repository, conditional=True)
    packet = _packet(repository, observation, nodes)
    assert {row["node_id"] for row in assert_records(packet["chains"])} == {
        nodes["sample-distribution"]
    }
    query = assert_records(assert_records(packet["path_queries"])[0]["results"])[0]
    assert query["completeness"] == "incomplete"
    assert query["omissions"]
    assert validate_dependency_verification(packet, observation)["valid"] is True


def test_ambiguous_import_never_becomes_a_unique_dependency_chain(
    repository: CodeMap,
) -> None:
    observation, nodes = _observation(repository, ambiguous=True)
    packet = _packet(repository, observation, nodes)
    assert packet["chains"] == []
    assert packet["verification_packets"] == []
    consumer = assert_records(assert_object(packet["consumer_packet"])["consumers"])[0]
    assert consumer["distribution_state"] == "resolved-ambiguous"
    assert validate_dependency_verification(packet, observation)["valid"] is True


@pytest.mark.parametrize(
    "mutation",
    ["chain", "path", "membership", "source", "boolean-index", "duplicate-member"],
)
def test_rehashed_tampering_cannot_change_native_chain_membership(
    repository: CodeMap, mutation: str
) -> None:
    observation, nodes = _observation(repository)
    packet = deepcopy(_packet(repository, observation, nodes))
    if mutation == "chain":
        packet["chains"] = assert_records(packet["chains"])[:-1]
    elif mutation == "path":
        assert_records(packet["chains"])[1]["dependency_path"] = [
            nodes["child-distribution"]
        ]
    elif mutation == "boolean-index":
        assert_records(packet["chains"])[0]["consumer_index"] = False
    elif mutation == "duplicate-member":
        scope = assert_object(assert_object(packet["consumer_packet"])["source_scope"])
        scope["members"] = [
            *assert_records(scope["members"]),
            assert_records(scope["members"])[0],
        ]
    else:
        verification = assert_records(packet["verification_packets"])[0]
        if mutation == "membership":
            verification["membership"] = None
        else:
            change = assert_records(verification["changes"])[0]
            member = assert_object(assert_object(change["source"])["member"])
            member["member_revision"] = "0" * 64
        verification["evidence_identity"] = evidence_identity(
            str(verification["schema"]),
            {
                key: value
                for key, value in verification.items()
                if key != "evidence_identity"
            },
        )
    packet["evidence_identity"] = evidence_identity(
        str(packet["schema"]),
        {key: value for key, value in packet.items() if key != "evidence_identity"},
    )
    assert validate_dependency_verification(packet, observation)["valid"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "query-bound",
        "path-request",
        "membership-count",
        "consumer-generation",
        "verifier-generation",
    ],
)
def test_rehashed_numeric_correspondence_keeps_json_value_types(
    repository: CodeMap, mutation: str
) -> None:
    observation, nodes = _observation(repository)
    packet = deepcopy(_packet(repository, observation, nodes))
    assert validate_dependency_verification(packet, observation)["valid"] is True
    verification = assert_records(packet["verification_packets"])[0]
    if mutation == "query-bound":
        query = assert_records(assert_records(packet["path_queries"])[0]["results"])[0]
        assert_object(query["bounds"])["max_depth"] = True
    elif mutation == "path-request":
        assert_records(packet["path_requests"])[0]["max_depth"] = True
    elif mutation == "membership-count":
        assert_object(verification["membership"])["member_count"] = True
    elif mutation == "consumer-generation":
        binding = assert_object(
            assert_object(packet["consumer_packet"])["repository_binding"]
        )
        binding["codemap_generation"] = float(
            assert_integer(binding["codemap_generation"])
        )
    else:
        binding = assert_object(verification["repository"])
        binding["codemap_generation"] = float(
            assert_integer(binding["codemap_generation"])
        )
    verification["evidence_identity"] = evidence_identity(
        str(verification["schema"]),
        {
            key: value
            for key, value in verification.items()
            if key != "evidence_identity"
        },
    )
    packet["evidence_identity"] = evidence_identity(
        str(packet["schema"]),
        {key: value for key, value in packet.items() if key != "evidence_identity"},
    )
    assert validate_dependency_verification(packet, observation)["valid"] is False


def test_verifier_changes_during_composition_cannot_reuse_earlier_source(
    repository: CodeMap,
) -> None:
    observation, nodes = _observation(repository)
    retained = _packet(repository, observation, nodes)
    (repository.workspace / "bridge.py").write_text(
        "import unrelated\ndef run(): return 1\n"
    )
    repository.index.sync()
    with pytest.raises(ValueError, match="generation|stale|repository"):
        _packet(repository, observation, nodes)
    # The retained validator is explicitly a pure structural proof, not freshness.
    assert validate_dependency_verification(retained, observation)["valid"] is True


def test_source_changes_after_verifier_observation_fail_the_composite_read(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation, nodes = _observation(repository)
    original = repository.verification.changed_set

    def changing(paths: list[str], *, limit: int) -> dict[str, object]:
        packet = original(paths, limit=limit)
        (repository.workspace / "bridge.py").write_text("def run(): return 2\n")
        return packet

    monkeypatch.setattr(repository.verification, "changed_set", changing)
    with pytest.raises(
        (UnstableFileError, ValueError), match="changed|binding mismatch"
    ):
        _packet(repository, observation, nodes)


@pytest.mark.parametrize(
    "mutation", ["kind", "revision", "identity", "stale", "reference-claim"]
)
def test_rehashed_relationship_changes_cannot_keep_a_positive_chain(
    repository: CodeMap, mutation: str
) -> None:
    observation, nodes = _observation(repository)
    packet = deepcopy(_packet(repository, observation, nodes))
    verification = assert_records(packet["verification_packets"])[0]
    relationship = assert_records(
        assert_records(verification["changes"])[0]["relationships"]
    )[0]
    if mutation == "kind":
        relationship["relation_kind"] = "unsupported-scope"
    elif mutation == "revision":
        member = assert_records(relationship["supporting_source_members"])[0]
        member["member_revision"] = "0" * 64
    elif mutation == "stale":
        verification["freshness"] = "stale"
    elif mutation == "reference-claim":
        assert_object(relationship["reference_evidence"])["direct_reference"] = False
    if mutation == "identity":
        relationship["evidence_identity"] = "sha256:" + "0" * 64
    else:
        base = {
            key: relationship[key]
            for key in (
                "source",
                "target",
                "classification",
                "relation_kind",
                "provenance",
            )
        }
        identity = evidence_identity("hashmarks.verification-relationship.v1", base)
        relationship["relationship_identity"] = relationship["evidence_identity"] = (
            identity
        )
        relationship["evidence_identity"] = evidence_identity(
            "hashmarks.changed-verification-relationship.v1", relationship
        )
    verification["evidence_identity"] = evidence_identity(
        str(verification["schema"]),
        {
            key: value
            for key, value in verification.items()
            if key != "evidence_identity"
        },
    )
    packet["evidence_identity"] = evidence_identity(
        str(packet["schema"]),
        {key: value for key, value in packet.items() if key != "evidence_identity"},
    )
    assert validate_dependency_verification(packet, observation)["valid"] is False


def test_indirect_reference_keeps_intermediate_source_qualification(
    repository: CodeMap,
) -> None:
    (repository.workspace / "helper.py").write_text(
        "from bridge import run\ndef result(): return run()\n"
    )
    (repository.workspace / "tests/test_bridge.py").write_text(
        "from helper import result\ndef test_run(): assert result() == 1\n"
    )
    observation, nodes = _observation(repository)
    packet = _packet(repository, observation, nodes)
    assert packet["chains"]
    verification = assert_records(packet["verification_packets"])[0]
    relationship = assert_records(
        assert_records(verification["changes"])[0]["relationships"]
    )[0]
    assert relationship["relation_kind"] == "bounded-indirect-reference"
    assert validate_dependency_verification(packet, observation)["valid"] is True


def test_missing_verifier_remains_an_incomplete_observation(
    repository: CodeMap,
) -> None:
    (repository.workspace / "tests/test_bridge.py").unlink()
    observation, nodes = _observation(repository)
    packet = _packet(repository, observation, nodes)
    assert packet["chains"] == []
    assert packet["negative_evidence_admissible"] is False
    assert len(assert_records(packet["verification_packets"])) == 1
    assert validate_dependency_verification(packet, observation)["valid"] is True


@pytest.mark.parametrize("limit", [0, 1001, True])
def test_invalid_verifier_bound_is_rejected(repository: CodeMap, limit: int) -> None:
    observation, nodes = _observation(repository)
    with pytest.raises(ValueError, match="limit"):
        repository.dependencies.verification(
            observation,
            source_paths=["bridge.py"],
            node_ids=[nodes["sample-distribution"]],
            verification_limit=limit,
        )


def test_unknown_context_is_rejected_even_without_dependency_pairs(
    repository: CodeMap,
) -> None:
    observation, nodes = _observation(repository)
    with pytest.raises(ValueError, match="context"):
        repository.dependencies.verification(
            observation,
            source_paths=["bridge.py"],
            node_ids=[nodes["sample-distribution"]],
            context="unknown",
        )


def test_explicit_context_does_not_borrow_another_contexts_import_ownership(
    repository: CodeMap,
) -> None:
    observation, nodes = _observation(repository, extra_context=True)
    packet = repository.dependencies.verification(
        observation,
        source_paths=["bridge.py"],
        node_ids=[nodes["sample-distribution"]],
        context="other",
    )
    consumer = assert_records(assert_object(packet["consumer_packet"])["consumers"])[0]
    assert consumer["observed_contexts"] == ["lock"]
    assert packet["chains"] == []
    assert validate_dependency_verification(packet, observation)["valid"] is True


def test_validator_rejects_non_json_transport_without_repo_reads(
    repository: CodeMap,
) -> None:
    observation, nodes = _observation(repository)
    packet = _packet(repository, observation, nodes)
    packet["consumer_packet"] = packet
    assert validate_dependency_verification(packet, observation)["valid"] is False


def test_composition_cannot_smuggle_unqualified_assessment_authority(
    repository: CodeMap,
) -> None:
    observation, nodes = _observation(repository)
    packet = _packet(repository, observation, nodes)
    packet["assessment"] = {
        "status": "COMPLETE",
        "negative_evidence_admissible": True,
        "resolved": True,
    }
    packet["evidence_identity"] = evidence_identity(
        str(packet["schema"]),
        {key: value for key, value in packet.items() if key != "evidence_identity"},
    )
    assert validate_dependency_verification(packet, observation)["valid"] is False


def test_npm_dependency_path_uses_the_same_composition_without_python_metadata(
    tmp_path: Path,
) -> None:
    (tmp_path / "bridge.ts").write_text(
        'import parent from "parent";\nexport function run() { return parent(); }\n'
    )
    (tmp_path / "bridge.test.ts").write_text(
        'import { test } from "vitest";\nimport parent from "parent";\ntest("run", () => parent());\n'
    )
    (tmp_path / "package.json").write_text(
        '{"name":"application","devDependencies":{"vitest":"^3"}}'
    )
    lock = json.dumps(
        {
            "lockfileVersion": 3,
            "packages": {
                "": {
                    "name": "application",
                    "version": "1.0",
                    "dependencies": {"parent": "1.0"},
                },
                "node_modules/parent": {
                    "name": "parent",
                    "version": "1.0",
                    "dependencies": {"child": "1.0"},
                },
                "node_modules/child": {"name": "child", "version": "1.0"},
            },
        }
    ).encode()
    (tmp_path / "package-lock.json").write_bytes(lock)
    provider = TreeSitterRangeProvider.auto()
    assert provider.available
    with CodeMap(
        tmp_path, state_dir=tmp_path / "state", range_provider=provider
    ) as repository:
        repository.index.sync()
        observation = repository.dependencies.observe(
            npm_lock_dependency_observation(
                lock=lock,
                repository_inputs=[
                    {
                        "path": "package-lock.json",
                        "member_revision": hash_file(
                            tmp_path / "package-lock.json"
                        ).hash,
                    }
                ],
            )
        )
        names = {
            row["component_id"]: row["name"]
            for row in assert_records(observation["components"])
        }
        nodes = {
            names[row["component_id"]]: str(row["node_id"])
            for row in assert_records(observation["selections"])
        }
        packet = repository.dependencies.verification(
            observation,
            source_paths=["bridge.test.ts"],
            node_ids=[nodes["parent"], nodes["child"]],
            context="lock",
            dependency_pairs=[
                {"source_node_id": nodes["parent"], "target_node_id": nodes["child"]}
            ],
        )
    chains = assert_records(packet["chains"])
    # The npm adapter supplies module ownership, but not a qualified resolved
    # graph. Authored dependency words cannot manufacture the child path.
    assert {row["node_id"] for row in chains} == {nodes["parent"]}
    assert all(row["consumer_node_id"] == nodes["parent"] for row in chains)
    query = assert_records(assert_records(packet["path_queries"])[0]["results"])[0]
    assert query["completeness"] == "incomplete"
    assert validate_dependency_verification(packet, observation)["valid"] is True
