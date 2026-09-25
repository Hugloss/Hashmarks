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
        complete_tree_contexts=("compile",),
        complete_inventory_contexts=("compile",),
    )


def _query(
    codemap: CodeMap,
    observation: dict[str, object],
    request: dict[str, object],
) -> dict[str, object]:
    return codemap.dependency_resolution_queries(observation, [request])["results"][0]


def _dummy_selection(
    observation: dict[str, object], component_id: str
) -> dict[str, object] | None:
    return next(
        (
            row
            for row in observation["selections"]
            if row["component_id"] == component_id
        ),
        None,
    )


def _assert_dependency_state(
    observation: dict[str, object],
    graph: dict[str, object],
    component_id: str,
    state: str,
) -> None:
    selection = _dummy_selection(observation, component_id)
    expected_version = {"absent": None, "v1": "1.0.0", "v2": "2.0.0"}[state]
    if expected_version is None:
        assert selection is None
        assert observation["relationships"] == []
        assert graph["result"] == []
        return
    assert selection is not None
    assert selection["version"] == expected_version
    assert graph["result"] == [
        {"depth": 1, "node_id": selection["node_id"], "selection": selection}
    ]
    assert [
        row["target"]
        for row in observation["relationships"]
        if row["source"] == observation["roots"][0]["node_id"]
    ] == [selection["node_id"]]


def _assert_maven_module_change(
    after: dict[str, object],
    after_module: dict[str, object],
    delta: dict[str, object],
    before_state: str,
    after_state: str,
) -> None:
    assert after_module["result"] == (
        []
        if after_state == "absent"
        else [
            next(
                row for row in after["module_ownership"] if row["module"] == "dummy.dep"
            )
        ]
    )
    if after_state != "absent":
        assert after_module["result"][0]["owners"] == [
            _dummy_selection(after, "example.fixture:dummy-dep")["node_id"]
        ]
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


def _assert_delta_side(
    delta: dict[str, object],
    side: str,
    observation: dict[str, object],
    component_id: str,
    effective_scopes: tuple[str, ...],
) -> None:
    selection = _dummy_selection(observation, component_id)
    context = observation["roots"][0]["context"]
    root_id = observation["roots"][0]["node_id"]
    expected_node = [] if selection is None else [selection["node_id"]]
    assert delta[f"selections_{side}"] == expected_node
    assert delta[f"inventory_{side}"] == (
        [] if selection is None else [[selection["node_id"], context]]
    )
    assert delta[f"relationships_{side}"] == (
        []
        if selection is None
        else [
            [root_id, selection["node_id"], "dependency", context, scope, ""]
            for scope in effective_scopes
        ]
    )


@pytest.mark.parametrize("producer", ["uv", "maven"])
@pytest.mark.parametrize(
    ("before_state", "after_state"),
    [
        ("absent", "v1"),
        ("v1", "v2"),
        ("v2", "absent"),
    ],
    ids=["add", "version-change", "remove"],
)
def test_real_producer_dependency_change_dogfood(
    tmp_path: Path,
    producer: str,
    before_state: str,
    after_state: str,
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
        selected_side = before if after_state == "absent" else after
        missing_selection = _dummy_selection(selected_side, component_id)["node_id"]
        absence_observation = after if after_state == "absent" else before
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
    _assert_dependency_state(before, before_graph, component_id, before_state)
    _assert_dependency_state(after, after_graph, component_id, after_state)
    _assert_delta_side(
        delta, "added", after, component_id, ("",) if producer == "uv" else ("compile",)
    )
    _assert_delta_side(
        delta,
        "removed",
        before,
        component_id,
        ("",) if producer == "uv" else ("compile",),
    )
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
        _assert_maven_module_change(
            after, after_module, delta, before_state, after_state
        )


def test_real_uv_grouped_conditional_edges_are_not_flattened(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(
            _observation("uv", "grouped")
        )
        root_id = observation["roots"][0]["node_id"]
        selection = _dummy_selection(observation, "dummy-dep")

        with pytest.raises(
            ValueError,
            match="graph query cannot flatten conditional relationships",
        ):
            _query(
                codemap,
                observation,
                {
                    "operation": "paths",
                    "node_id": root_id,
                    "target_id": selection["node_id"],
                    "context": "lock",
                    "max_results": 1,
                },
            )


@pytest.mark.parametrize(
    ("before_state", "after_state"),
    [("absent", "grouped"), ("grouped", "absent")],
    ids=["grouped-add", "grouped-remove"],
)
def test_real_uv_grouped_dependency_dogfood(
    tmp_path: Path, before_state: str, after_state: str
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(
            _observation("uv", before_state)
        )
        after = codemap.dependency_resolution_evidence(_observation("uv", after_state))
        delta = codemap.dependency_resolution_delta(before, after)
        present = before if before_state == "grouped" else after
        absent = after if after_state == "absent" else before
        selection = _dummy_selection(present, "dummy-dep")
        with pytest.raises(
            ValueError,
            match="graph query cannot flatten conditional relationships",
        ):
            _query(
                codemap,
                present,
                {
                    "operation": "dependencies",
                    "node_id": present["roots"][0]["node_id"],
                    "context": "lock",
                },
            )
        absent_graph = _query(
            codemap,
            absent,
            {
                "operation": "dependencies",
                "node_id": absent["roots"][0]["node_id"],
                "context": "lock",
            },
        )
        absent_inventory = _query(
            codemap,
            absent,
            {
                "operation": "inventory",
                "node_id": selection["node_id"],
                "context": "lock",
            },
        )

    assert before["definition_identity"] == after["definition_identity"]
    assert delta["comparability"] == "comparable"
    assert delta["producer_authority"] == "caller-claimed"
    assert selection["version"] == "1.0.0"
    assert len(present["evidence_sources"]) == 1
    assert _dummy_selection(absent, "dummy-dep") is None
    assert {row["effective_scope"] for row in present["relationships"]} == {
        "extra:extra",
        "dev:test",
    }
    assert {row["target"] for row in present["relationships"]} == {selection["node_id"]}
    assert absent_graph["result"] == []
    assert absent_graph["negative_evidence"] == "admissible-within-declared-scope"
    assert absent_inventory["result"] == []
    assert absent_inventory["negative_evidence"] == "admissible-within-declared-scope"
    change = "added" if before_state == "absent" else "removed"
    reverse = "removed" if change == "added" else "added"
    _assert_delta_side(delta, change, present, "dummy-dep", ("dev:test", "extra:extra"))
    _assert_delta_side(delta, reverse, absent, "dummy-dep", ())
    assert delta[f"components_{change}"] == ["dummy-dep"]
    assert delta[f"components_{reverse}"] == []
