from __future__ import annotations

import copy
from pathlib import Path

import pytest

from hashmarks.codemap.engine import CodeMap


def _snapshot(
    *,
    source_id: str = "fixture:resolution",
    digest: str = "a",
    adapter_semantics: str = "fixture.dependency-adapter.v1",
) -> dict[str, object]:
    return {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {
            "kind": "fixture-resolver",
            "schema_version": "1",
            "adapter_semantics": adapter_semantics,
        },
        "scope": {},
        "contexts": ["runtime"],
        "roots": [],
        "evidence_sources": [
            {
                "source_id": source_id,
                "kind": "fixture-resolution",
                "authorities": ["resolved-inventory", "selection"],
                "context": "runtime",
                "completeness": "complete",
                "truncation": "complete",
                "producer_digest": "sha256:" + digest * 64,
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
                "evidence_sources": [source_id],
            }
        ],
        "inventory": [
            {
                "node_id": "example@1",
                "context": "runtime",
                "evidence_sources": [source_id],
            }
        ],
        "relationships": [],
        "coverage": [
            {
                "context": "runtime",
                "kind": "selection",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": [source_id],
            },
            {
                "context": "runtime",
                "kind": "resolved-inventory",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": [source_id],
            },
        ],
        "repository_inputs": [],
        "module_ownership": [],
    }


def _qualify(codemap: CodeMap, snapshot: dict[str, object]) -> dict[str, object]:
    return codemap.dependency_resolution_evidence(snapshot)


def test_dependency_delta_compares_explicit_endpoints_across_generations(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = _qualify(codemap, _snapshot())

        (tmp_path / "later.py").write_text("VALUE = 1\n", encoding="utf-8")
        codemap.sync(["later.py"])
        after = _qualify(codemap, _snapshot())

        delta = codemap.dependency_resolution_delta(before, after)

    assert before["repository_binding"]["codemap_generation"] != after[
        "repository_binding"
    ]["codemap_generation"]
    assert delta["comparability"] == "comparable"
    assert delta["change_axes"]["repository_generation"] == "changed"
    assert delta["change_axes"]["semantic_definition"] == "unchanged"
    assert delta["change_axes"]["semantic_resolution"] == "unchanged"
    assert delta["change_axes"]["observation"] == "changed"
    assert delta["change_axes"]["adapter_semantics"] == "unchanged"
    assert delta["change_axes"]["physical_evidence_topology"] == "unchanged"
    assert delta["change_axes"]["physical_evidence_content"] == "unchanged"


def test_dependency_delta_separates_adapter_semantics_from_repository_meaning(
    tmp_path: Path,
) -> None:
    before_raw = _snapshot(adapter_semantics="fixture.dependency-adapter.v1")
    after_raw = _snapshot(adapter_semantics="fixture.dependency-adapter.v2")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = _qualify(codemap, before_raw)
        after = _qualify(codemap, after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["change_axes"]["semantic_resolution"] == "unchanged"
    assert delta["change_axes"]["adapter_semantics"] == "changed"
    assert delta["change_axes"]["producer_provenance"] == "unchanged"
    assert delta["change_axes"]["physical_evidence_content"] == "unchanged"


def test_dependency_delta_separates_evidence_topology_from_equal_bytes(
    tmp_path: Path,
) -> None:
    before_raw = _snapshot(source_id="fixture:before", digest="a")
    after_raw = _snapshot(source_id="fixture:after", digest="a")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = _qualify(codemap, before_raw)
        after = _qualify(codemap, after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert delta["change_axes"]["semantic_resolution"] == "unchanged"
    assert delta["change_axes"]["physical_evidence_topology"] == "changed"
    assert delta["change_axes"]["physical_evidence_content"] == "unchanged"
    assert delta["change_axes"]["evidence_qualification"] == "unchanged"


def test_dependency_delta_reports_source_content_change_without_semantic_change(
    tmp_path: Path,
) -> None:
    before_raw = _snapshot(digest="a")
    after_raw = _snapshot(digest="b")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = _qualify(codemap, before_raw)
        after = _qualify(codemap, after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert delta["change_axes"]["semantic_resolution"] == "unchanged"
    assert delta["change_axes"]["physical_evidence_topology"] == "unchanged"
    assert delta["change_axes"]["physical_evidence_content"] == "changed"


def test_dependency_delta_keeps_coverage_change_separate_from_resolution(
    tmp_path: Path,
) -> None:
    before_raw = _snapshot()
    after_raw = copy.deepcopy(before_raw)
    after_raw["coverage"][0]["completeness"] = "incomplete"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = _qualify(codemap, before_raw)
        after = _qualify(codemap, after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert delta["change_axes"]["semantic_resolution"] == "unchanged"
    assert delta["change_axes"]["coverage"] == "changed"
    assert delta["change_axes"]["observation"] == "changed"


def test_dependency_delta_marks_definition_change_non_comparable(
    tmp_path: Path,
) -> None:
    before_raw = _snapshot()
    after_raw = copy.deepcopy(before_raw)
    after_raw["scope"] = {"environment": "production"}

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = _qualify(codemap, before_raw)
        after = _qualify(codemap, after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert delta["comparability"] == "not-comparable"
    assert delta["reason"] == "definition-changed"
    assert delta["change_axes"]["semantic_definition"] == "changed"
    assert delta["change_axes"]["semantic_resolution"] == "not-comparable"


def test_dependency_delta_still_refuses_different_repository_identity(
    tmp_path: Path,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()

    with CodeMap(left) as left_map:
        left_map.sync()
        before = _qualify(left_map, _snapshot())
    with CodeMap(right) as right_map:
        right_map.sync()
        after = _qualify(right_map, _snapshot())
        with pytest.raises(ValueError, match="repository-mismatch"):
            right_map.dependency_resolution_delta(before, after)
