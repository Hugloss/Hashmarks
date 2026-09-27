from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from hashmarks import CodeMap
from hashmarks.adapters import uv_lock_dependency_observation


_FIXTURES = Path(__file__).parent / "fixtures" / "dependency_dogfood"


def _member_revision(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_loss_snapshot() -> dict[str, object]:
    return {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {
            "kind": "authority-adversarial-fixture",
            "schema_version": "1",
            "adapter_semantics": "hashmarks.authority-adversarial.v1",
        },
        "scope": {},
        "contexts": ["runtime"],
        "roots": [],
        "evidence_sources": [
            {
                "source_id": "fixture:primary",
                "kind": "fixture-resolution",
                "authorities": ["resolved-inventory", "selection"],
                "context": "runtime",
                "completeness": "complete",
                "truncation": "complete",
            },
            {
                "source_id": "fixture:secondary",
                "kind": "fixture-resolution",
                "authorities": ["resolved-inventory", "selection"],
                "context": "runtime",
                "completeness": "complete",
                "truncation": "complete",
            },
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
                "evidence_sources": ["fixture:primary", "fixture:secondary"],
            }
        ],
        "inventory": [
            {
                "node_id": "example@1",
                "context": "runtime",
                "evidence_sources": ["fixture:primary", "fixture:secondary"],
            }
        ],
        "relationships": [],
        "coverage": [
            {
                "context": "runtime",
                "kind": "selection",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["fixture:primary", "fixture:secondary"],
            },
            {
                "context": "runtime",
                "kind": "resolved-inventory",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["fixture:primary", "fixture:secondary"],
            },
        ],
        "repository_inputs": [],
        "module_ownership": [],
    }


def test_uv_repository_input_path_move_preserves_resolution_and_source_bytes(
    tmp_path: Path,
) -> None:
    lock = (_FIXTURES / "uv" / "v1" / "uv.lock").read_bytes()
    revision = _member_revision(lock)
    old_path = tmp_path / "before" / "uv.lock"
    new_path = tmp_path / "after" / "uv.lock"
    old_path.parent.mkdir()
    new_path.parent.mkdir()
    old_path.write_bytes(lock)

    before_raw = uv_lock_dependency_observation(
        lock=lock,
        repository_inputs=[
            {"path": "before/uv.lock", "member_revision": revision},
        ],
    )
    after_raw = uv_lock_dependency_observation(
        lock=lock,
        repository_inputs=[
            {"path": "after/uv.lock", "member_revision": revision},
        ],
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_raw)

        old_path.unlink()
        new_path.write_bytes(lock)
        codemap.sync(["before/uv.lock", "after/uv.lock"])
        after = codemap.dependency_resolution_evidence(after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["definition_identity"] == after["definition_identity"]
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert before["repository_inputs"][0]["source_equivalence"] == "proven"
    assert after["repository_inputs"][0]["source_equivalence"] == "proven"
    assert (
        before["repository_inputs"][0]["observed_member_revision"]
        == after["repository_inputs"][0]["observed_member_revision"]
        == revision
    )
    assert delta["comparability"] == "comparable"
    assert delta["change_axes"]["semantic_resolution"] == "unchanged"
    assert delta["change_axes"]["repository_inputs"] == "changed"
    assert delta["change_axes"]["physical_evidence_topology"] == "unchanged"
    assert delta["change_axes"]["physical_evidence_content"] == "unchanged"
    assert delta["change_axes"]["repository_generation"] == "changed"


def test_identical_repository_input_bytes_keep_distinct_path_authority(
    tmp_path: Path,
) -> None:
    lock = (_FIXTURES / "uv" / "v1" / "uv.lock").read_bytes()
    revision = _member_revision(lock)
    for relpath in ("one/uv.lock", "two/uv.lock"):
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(lock)

    raw = uv_lock_dependency_observation(
        lock=lock,
        repository_inputs=[
            {"path": "one/uv.lock", "member_revision": revision},
            {"path": "two/uv.lock", "member_revision": revision},
        ],
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)
        derivation = codemap.dependency_resolution_derivation_authority(observation)

    assert [row["path"] for row in observation["repository_inputs"]] == [
        "one/uv.lock",
        "two/uv.lock",
    ]
    assert {
        row["observed_member_revision"] for row in observation["repository_inputs"]
    } == {revision}
    assert {row["source_equivalence"] for row in observation["repository_inputs"]} == {
        "proven"
    }
    assert derivation["repository_inputs"] == observation["repository_inputs"]


def test_evidence_source_disappearance_degrades_qualification_not_semantics(
    tmp_path: Path,
) -> None:
    before_raw = _source_loss_snapshot()
    after_raw = copy.deepcopy(before_raw)
    after_raw["evidence_sources"] = [after_raw["evidence_sources"][0]]
    after_raw["evidence_sources"][0]["completeness"] = "incomplete"
    for family in ("selections", "inventory", "coverage"):
        for row in after_raw[family]:
            row["evidence_sources"] = ["fixture:primary"]
    for row in after_raw["coverage"]:
        row["completeness"] = "incomplete"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_raw)
        after = codemap.dependency_resolution_evidence(after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["definition_identity"] == after["definition_identity"]
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["comparability"] == "comparable"
    assert delta["change_axes"]["semantic_resolution"] == "unchanged"
    assert delta["change_axes"]["physical_evidence_topology"] == "changed"
    assert delta["change_axes"]["physical_evidence_content"] == "unknown"
    assert delta["change_axes"]["evidence_qualification"] == "changed"
    assert delta["change_axes"]["coverage"] == "changed"
