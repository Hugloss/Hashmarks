from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.adapters import (
    maven_dependency_observation,
    uv_lock_dependency_observation,
)
from hashmarks.codemap.engine import CodeMap

_FIXTURES = Path(__file__).parent / "fixtures" / "dependency_dogfood"


def _observation(producer: str, state: str) -> dict[str, object]:
    base = _FIXTURES / producer / state
    if producer == "uv":
        return uv_lock_dependency_observation(lock=(base / "uv.lock").read_bytes())
    return maven_dependency_observation(
        trees={"compile": (base / "tree.json").read_bytes()},
        inventories={"compile": (base / "list.txt").read_bytes()},
    )


def _query(
    codemap: CodeMap,
    observation: dict[str, object],
    request: dict[str, object],
) -> dict[str, object]:
    return codemap.dependency_resolution_queries(observation, [request])["results"][0]


@pytest.mark.parametrize("producer", ["uv", "maven"])
@pytest.mark.parametrize(
    ("before_state", "after_state", "expected_added", "expected_removed"),
    [
        ("absent", "v1", 1, 0),
        ("v1", "v2", 1, 1),
        ("v2", "absent", 0, 1),
    ],
    ids=["add", "version-change", "remove"],
)
def test_real_producer_dependency_change_dogfood(
    tmp_path: Path,
    producer: str,
    before_state: str,
    after_state: str,
    expected_added: int,
    expected_removed: int,
) -> None:
    context = "lock" if producer == "uv" else "compile"
    component_id = "dummy-dep" if producer == "uv" else "example.fixture:dummy-dep"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(
            _observation(producer, before_state)
        )
        after = codemap.dependency_resolution_evidence(
            _observation(producer, after_state)
        )
        delta = codemap.dependency_resolution_delta(before, after)
        before_root = before["roots"][0]["node_id"]
        after_root = after["roots"][0]["node_id"]
        before_graph = _query(
            codemap,
            before,
            {"operation": "dependencies", "node_id": before_root, "context": context},
        )
        after_graph = _query(
            codemap,
            after,
            {"operation": "dependencies", "node_id": after_root, "context": context},
        )
        after_component = _query(
            codemap,
            after,
            {"operation": "component", "component_id": component_id},
        )
        selected_side = before if expected_removed else after
        missing_selection = next(
            row["node_id"]
            for row in selected_side["selections"]
            if row["component_id"] == component_id
        )
        absence_observation = after if expected_removed else before
        inventory_absence = _query(
            codemap,
            absence_observation,
            {
                "operation": "inventory",
                "node_id": missing_selection,
                "context": context,
            },
        )
        if producer == "maven":
            after_module = _query(
                codemap,
                after,
                {
                    "operation": "module-owners",
                    "module": "dummy.dep",
                    "context": context,
                },
            )

    assert before["definition_identity"] == after["definition_identity"]
    assert delta["comparability"] == "comparable"
    assert delta["producer_authority"] == "caller-claimed"
    for field in ("selections", "inventory", "relationships"):
        assert len(delta[f"{field}_added"]) == expected_added
        assert len(delta[f"{field}_removed"]) == expected_removed
    assert len(delta["components_added"]) == (before_state == "absent")
    assert len(delta["components_removed"]) == (after_state == "absent")
    assert len(before["evidence_sources"]) == (1 if producer == "uv" else 2)
    assert len(after["evidence_sources"]) == (1 if producer == "uv" else 2)
    assert len(before_graph["result"]) == (before_state != "absent")
    assert len(after_graph["result"]) == (after_state != "absent")
    assert after_graph["negative_evidence"] == (
        "admissible-within-declared-scope"
        if after_state == "absent"
        else "not-applicable"
    )
    assert after_component["negative_evidence"] == (
        "admissible-within-declared-scope"
        if after_state == "absent"
        else "not-applicable"
    )
    assert inventory_absence["result"] == []
    assert inventory_absence["negative_evidence"] == "admissible-within-declared-scope"
    if producer == "maven":
        assert len(delta["module_ownership_added"]) == (before_state == "absent")
        assert len(delta["module_ownership_removed"]) == (after_state == "absent")
        assert len(delta["module_ownership_changed"]) == (
            before_state == "v1" and after_state == "v2"
        )
        assert after_module["negative_evidence"] == (
            "admissible-within-declared-scope"
            if after_state == "absent"
            else "not-applicable"
        )
