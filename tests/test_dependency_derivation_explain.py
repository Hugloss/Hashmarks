from __future__ import annotations

import copy
from pathlib import Path

import pytest
from contract_assertions import assert_object

from hashmarks.codemap.engine import CodeMap


def _snapshot() -> dict[str, object]:
    return {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {
            "kind": "fixture-resolver",
            "schema_version": "1",
            "adapter_semantics": "fixture.dependency-adapter.v1",
        },
        "scope": {},
        "contexts": ["runtime"],
        "roots": [],
        "evidence_sources": [
            {
                "source_id": "fixture:resolution",
                "kind": "fixture-resolution",
                "authorities": ["resolved-inventory", "selection"],
                "context": "runtime",
                "completeness": "complete",
                "truncation": "complete",
                "producer_digest": "sha256:" + "a" * 64,
            }
        ],
        "components": [
            {
                "component_id": "example",
                "name": "example",
                "ecosystem": "fixture",
            }
        ],
        "selections": [
            {
                "node_id": "example@1",
                "component_id": "example",
                "version": "1",
                "source": "fixture",
                "contexts": ["runtime"],
                "evidence_sources": ["fixture:resolution"],
            }
        ],
        "inventory": [
            {
                "node_id": "example@1",
                "context": "runtime",
                "evidence_sources": ["fixture:resolution"],
            }
        ],
        "relationships": [],
        "coverage": [
            {
                "context": "runtime",
                "kind": "selection",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["fixture:resolution"],
            },
            {
                "context": "runtime",
                "kind": "resolved-inventory",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["fixture:resolution"],
            },
        ],
        "repository_inputs": [],
        "module_ownership": [],
    }


def test_dependency_explain_projects_semantics_and_derivation(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(_snapshot())
        explanation = codemap.dependencies.explain(observation)

    assert explanation["schema"] == "hashmarks.dependency-resolution-explain.v1"
    assert explanation["authority"] == "qualified-external-observation"
    assert explanation["producer_authority"] == "caller-claimed"

    semantic = assert_object(explanation["semantic_result"])
    assert semantic["definition_identity"] == observation["definition_identity"]
    assert semantic["resolution_identity"] == observation["resolution_identity"]
    assert semantic["observation_identity"] == observation["observation_identity"]
    assert semantic["contexts"] == ["runtime"]
    assert semantic["roots"] == []
    assert semantic["counts"] == {
        "components": 1,
        "selections": 1,
        "inventory": 1,
        "relationships": 0,
        "module_ownership": 0,
    }

    derivation = assert_object(explanation["derivation"])
    assert derivation["schema"] == "hashmarks.dependency-resolution-derivation.v1"
    assert derivation["observation_identity"] == observation["observation_identity"]
    assert derivation["adapter_semantics"] == "fixture.dependency-adapter.v1"
    assert derivation["contributing_source_ids"] == ["fixture:resolution"]


def test_dependency_explain_remains_endpoint_local_after_repository_advances(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(_snapshot())
        original_binding = copy.deepcopy(observation["repository_binding"])

        (tmp_path / "later.py").write_text("VALUE = 1\n", encoding="utf-8")
        codemap.index.sync(["later.py"])
        explanation = codemap.dependencies.explain(observation)

    derivation = assert_object(explanation["derivation"])
    assert derivation["repository_binding"] == original_binding
    assert (
        assert_object(explanation["semantic_result"])["observation_identity"]
        == observation["observation_identity"]
    )


def test_dependency_explain_revalidates_before_projecting(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(_snapshot())
        tampered = copy.deepcopy(observation)
        assert_object(tampered["producer"])["adapter_semantics"] = "fixture.forged.v2"

        with pytest.raises(ValueError, match="content identity mismatch"):
            codemap.dependencies.explain(tampered)
