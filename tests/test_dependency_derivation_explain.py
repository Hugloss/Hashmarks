from __future__ import annotations

import copy
from pathlib import Path

import pytest

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
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot())
        explanation = codemap.dependency_resolution_explain(observation)

    assert explanation["schema"] == "hashmarks.dependency-resolution-explain.v1"
    assert explanation["authority"] == "qualified-external-observation"
    assert explanation["producer_authority"] == "caller-claimed"

    semantic = explanation["semantic_result"]
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

    derivation = explanation["derivation"]
    assert derivation["schema"] == "hashmarks.dependency-resolution-derivation.v1"
    assert derivation["observation_identity"] == observation["observation_identity"]
    assert derivation["adapter_semantics"] == "fixture.dependency-adapter.v1"
    assert derivation["contributing_source_ids"] == ["fixture:resolution"]


def test_dependency_explain_remains_endpoint_local_after_repository_advances(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot())
        original_binding = copy.deepcopy(observation["repository_binding"])

        (tmp_path / "later.py").write_text("VALUE = 1\n", encoding="utf-8")
        codemap.sync(["later.py"])
        explanation = codemap.dependency_resolution_explain(observation)

    derivation = explanation["derivation"]
    assert derivation["repository_binding"] == original_binding
    assert (
        explanation["semantic_result"]["observation_identity"]
        == observation["observation_identity"]
    )


def test_dependency_explain_revalidates_before_projecting(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot())
        tampered = copy.deepcopy(observation)
        tampered["producer"]["adapter_semantics"] = "fixture.forged.v2"

        with pytest.raises(ValueError, match="content identity mismatch"):
            codemap.dependency_resolution_explain(tampered)
