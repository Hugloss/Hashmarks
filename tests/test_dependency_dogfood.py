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


def _realworld_maven_observation(state: str) -> dict[str, object]:
    base = _FIXTURES / "maven" / "transitive-upgrade" / state
    return maven_dependency_observation(
        trees={"compile": (base / "tree.json").read_bytes()},
        inventories={"compile": (base / "list.txt").read_bytes()},
        complete_tree_contexts=("compile",),
        complete_inventory_contexts=("compile",),
    )


def _maven_scenario_observation(
    scenario: str,
    state: str,
) -> dict[str, object]:
    base = _FIXTURES / "maven" / scenario / state
    return maven_dependency_observation(
        trees={"compile": (base / "tree.json").read_bytes()},
        inventories={"compile": (base / "list.txt").read_bytes()},
        complete_tree_contexts=("compile",),
        complete_inventory_contexts=("compile",),
    )


def _maven_multi_module_observation(state: str) -> dict[str, object]:
    base = _FIXTURES / "maven" / "multi-module" / state / "captures"
    contexts = ("alpha", "beta")
    return maven_dependency_observation(
        trees={context: (base / context / "tree.json").read_bytes() for context in contexts},
        inventories={
            context: (base / context / "list.txt").read_bytes() for context in contexts
        },
        complete_tree_contexts=contexts,
        complete_inventory_contexts=contexts,
    )


def _maven_profile_observation() -> dict[str, object]:
    base = _FIXTURES / "maven" / "profiles"
    contexts = ("default", "extra")
    return maven_dependency_observation(
        trees={context: (base / context / "tree.json").read_bytes() for context in contexts},
        inventories={
            context: (base / context / "list.txt").read_bytes() for context in contexts
        },
        complete_tree_contexts=contexts,
        complete_inventory_contexts=contexts,
    )


def _selection_versions(
    observation: dict[str, object],
) -> dict[str, set[str]]:
    versions: dict[str, set[str]] = {}
    for row in observation["selections"]:
        versions.setdefault(row["component_id"], set()).add(row["version"])
    return versions


def _changed_component_versions(
    before: dict[str, object],
    after: dict[str, object],
) -> dict[str, tuple[set[str], set[str]]]:
    before_versions = _selection_versions(before)
    after_versions = _selection_versions(after)
    return {
        component_id: (before_versions[component_id], after_versions[component_id])
        for component_id in before_versions.keys() & after_versions.keys()
        if before_versions[component_id] != after_versions[component_id]
    }


def _selection(
    observation: dict[str, object],
    component_id: str,
) -> dict[str, object]:
    selection = _dummy_selection(observation, component_id)
    assert selection is not None
    return selection


def _root_id(observation: dict[str, object], context: str) -> str:
    return next(row["node_id"] for row in observation["roots"] if row["context"] == context)


def _direct_components(
    observation: dict[str, object],
    context: str,
) -> set[str]:
    root_id = _root_id(observation, context)
    selections = {row["node_id"]: row for row in observation["selections"]}
    return {
        selections[row["target"]]["component_id"]
        for row in observation["relationships"]
        if row["context"] == context and row["source"] == root_id
    }


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


def test_real_maven_transitive_upgrade_dogfood_preserves_large_graph_delta(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(
            _realworld_maven_observation("before")
        )
        after = codemap.dependency_resolution_evidence(
            _realworld_maven_observation("after")
        )
        delta = codemap.dependency_resolution_delta(before, after)

        before_okhttp = _dummy_selection(before, "com.squareup.okhttp3:okhttp")
        after_okhttp = _dummy_selection(after, "com.squareup.okhttp3:okhttp")
        before_okhttp_graph = _query(
            codemap,
            before,
            {
                "operation": "dependencies",
                "node_id": before_okhttp["node_id"],
                "context": "compile",
            },
        )
        after_okhttp_graph = _query(
            codemap,
            after,
            {
                "operation": "dependencies",
                "node_id": after_okhttp["node_id"],
                "context": "compile",
            },
        )

    assert delta["comparability"] == "comparable"
    assert delta["producer_authority"] == "caller-claimed"
    assert len(before["inventory"]) == 26
    assert len(after["inventory"]) == 22
    assert len(delta["selections_removed"]) == 21
    assert len(delta["selections_added"]) == 17
    assert len(delta["relationships_removed"]) == 26
    assert len(delta["relationships_added"]) == 22

    assert delta["components_added"] == ["org.jspecify:jspecify"]
    assert delta["components_removed"] == [
        "com.google.code.findbugs:jsr305",
        "org.checkerframework:checker-qual",
        "org.jetbrains.kotlin:kotlin-stdlib-common",
        "org.jetbrains.kotlin:kotlin-stdlib-jdk7",
        "org.jetbrains.kotlin:kotlin-stdlib-jdk8",
    ]

    changed_versions = _changed_component_versions(before, after)
    assert len(changed_versions) == 16
    assert changed_versions["io.minio:minio"] == ({"8.5.17"}, {"8.6.0"})
    assert changed_versions["com.squareup.okhttp3:okhttp"] == (
        {"4.12.0"},
        {"5.1.0"},
    )
    assert changed_versions["com.squareup.okio:okio-jvm"] == (
        {"3.6.0"},
        {"3.15.0"},
    )

    before_okhttp_components = {
        row["selection"]["component_id"] for row in before_okhttp_graph["result"]
    }
    after_okhttp_components = {
        row["selection"]["component_id"] for row in after_okhttp_graph["result"]
    }
    assert "org.jetbrains.kotlin:kotlin-stdlib-jdk8" in before_okhttp_components
    assert "org.jetbrains.kotlin:kotlin-stdlib-jdk8" not in after_okhttp_components
    assert "com.squareup.okio:okio-jvm" in after_okhttp_components
    assert before_okhttp_graph["completeness"] == "complete"
    assert after_okhttp_graph["completeness"] == "complete"


def test_real_maven_mediation_changes_only_transitive_selections(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(
            _maven_scenario_observation("mediation", "before")
        )
        after = codemap.dependency_resolution_evidence(
            _maven_scenario_observation("mediation", "after")
        )
        delta = codemap.dependency_resolution_delta(before, after)
        before_graph = _query(
            codemap,
            before,
            {
                "operation": "dependencies",
                "node_id": _root_id(before, "compile"),
                "context": "compile",
            },
        )
        after_graph = _query(
            codemap,
            after,
            {
                "operation": "dependencies",
                "node_id": _root_id(after, "compile"),
                "context": "compile",
            },
        )

    before_direct = _direct_components(before, "compile")
    after_direct = _direct_components(after, "compile")
    changed_versions = _changed_component_versions(before, after)
    before_versions = _selection_versions(before)
    after_versions = _selection_versions(after)

    assert before["definition_identity"] == after["definition_identity"]
    assert delta["comparability"] == "comparable"
    assert delta["causation"] == "not-inferred"
    assert before_direct == after_direct
    assert len(before_direct) == 2
    assert all(
        before_versions[component_id] == after_versions[component_id]
        for component_id in before_direct
    )
    assert len(changed_versions) == 5
    assert not (set(changed_versions) & before_direct)
    assert delta["components_added"] == []
    assert delta["components_removed"] == []
    assert len(delta["selections_added"]) == 5
    assert len(delta["selections_removed"]) == 5
    assert before_graph["completeness"] == "complete"
    assert after_graph["completeness"] == "complete"


def test_real_maven_exclusion_removes_complete_transitive_branch(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(
            _maven_scenario_observation("exclusion", "before")
        )
        after = codemap.dependency_resolution_evidence(
            _maven_scenario_observation("exclusion", "after")
        )
        delta = codemap.dependency_resolution_delta(before, after)

        removed_absence = [
            _query(
                codemap,
                after,
                {
                    "operation": "inventory",
                    "node_id": node_id,
                    "context": "compile",
                },
            )
            for node_id in delta["selections_removed"]
        ]

    before_direct = _direct_components(before, "compile")
    after_direct = _direct_components(after, "compile")
    direct_component = next(iter(before_direct))

    assert before["definition_identity"] == after["definition_identity"]
    assert delta["comparability"] == "comparable"
    assert delta["causation"] == "not-inferred"
    assert before_direct == after_direct
    assert len(before_direct) == 1
    assert _selection(before, direct_component)["version"] == _selection(
        after, direct_component
    )["version"]
    assert delta["components_added"] == []
    assert len(delta["components_removed"]) == 6
    assert len(delta["selections_removed"]) == 6
    assert delta["selections_added"] == []
    assert len(delta["relationships_removed"]) == 6
    assert delta["relationships_added"] == []
    assert all(result["result"] == [] for result in removed_absence)
    assert all(
        result["negative_evidence"] == "admissible-within-declared-scope"
        for result in removed_absence
    )


def test_real_maven_bom_upgrade_changes_many_versions_without_component_churn(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(
            _maven_scenario_observation("bom-upgrade", "before")
        )
        after = codemap.dependency_resolution_evidence(
            _maven_scenario_observation("bom-upgrade", "after")
        )
        delta = codemap.dependency_resolution_delta(before, after)

    direct_components = _direct_components(before, "compile")
    changed_versions = _changed_component_versions(before, after)

    assert before["definition_identity"] == after["definition_identity"]
    assert delta["comparability"] == "comparable"
    assert delta["causation"] == "not-inferred"
    assert direct_components == _direct_components(after, "compile")
    assert len(direct_components) == 5
    assert direct_components <= set(changed_versions)
    assert len(changed_versions) == 17
    assert len(before["inventory"]) == 18
    assert len(after["inventory"]) == 18
    assert delta["components_added"] == []
    assert delta["components_removed"] == []
    assert len(delta["selections_added"]) == 17
    assert len(delta["selections_removed"]) == 17


def test_real_maven_multi_module_change_propagates_across_contexts(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(
            _maven_multi_module_observation("before")
        )
        after = codemap.dependency_resolution_evidence(
            _maven_multi_module_observation("after")
        )
        delta = codemap.dependency_resolution_delta(before, after)

        before_graphs = {
            context: _query(
                codemap,
                before,
                {
                    "operation": "dependencies",
                    "node_id": _root_id(before, context),
                    "context": context,
                },
            )
            for context in ("alpha", "beta")
        }
        after_graphs = {
            context: _query(
                codemap,
                after,
                {
                    "operation": "dependencies",
                    "node_id": _root_id(after, context),
                    "context": context,
                },
            )
            for context in ("alpha", "beta")
        }

    changed_versions = _changed_component_versions(before, after)

    assert before["definition_identity"] == after["definition_identity"]
    assert delta["comparability"] == "comparable"
    assert before["contexts"] == ["alpha", "beta"]
    assert after["contexts"] == ["alpha", "beta"]
    assert len(changed_versions) == 3
    assert all(
        _selection(before, component_id)["contexts"] == ["alpha", "beta"]
        for component_id in changed_versions
    )
    assert all(
        _selection(after, component_id)["contexts"] == ["alpha", "beta"]
        for component_id in changed_versions
    )
    assert len(delta["components_added"]) == 1
    assert len(delta["components_removed"]) == 2
    assert all(graph["completeness"] == "complete" for graph in before_graphs.values())
    assert all(graph["completeness"] == "complete" for graph in after_graphs.values())


def test_real_maven_profile_contexts_remain_isolated(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(
            _maven_profile_observation()
        )
        root_id = _root_id(observation, "default")

        with pytest.raises(
            ValueError,
            match="graph query requires context for multi-context observation",
        ):
            _query(
                codemap,
                observation,
                {"operation": "dependencies", "node_id": root_id},
            )

        default_graph = _query(
            codemap,
            observation,
            {
                "operation": "dependencies",
                "node_id": root_id,
                "context": "default",
            },
        )
        extra_graph = _query(
            codemap,
            observation,
            {
                "operation": "dependencies",
                "node_id": root_id,
                "context": "extra",
            },
        )

        default_direct = _direct_components(observation, "default")
        extra_direct = _direct_components(observation, "extra")
        extra_only_direct = next(iter(extra_direct - default_direct))
        extra_only_selection = _selection(observation, extra_only_direct)

        selection_contexts = _query(
            codemap,
            observation,
            {
                "operation": "contexts",
                "node_id": extra_only_selection["node_id"],
            },
        )
        default_absence = _query(
            codemap,
            observation,
            {
                "operation": "inventory",
                "node_id": extra_only_selection["node_id"],
                "context": "default",
            },
        )

    assert observation["contexts"] == ["default", "extra"]
    assert _root_id(observation, "default") == _root_id(observation, "extra")
    assert len(default_direct) == 1
    assert len(extra_direct - default_direct) == 1
    assert selection_contexts["result"] == ["extra"]
    assert default_absence["result"] == []
    assert default_absence["negative_evidence"] == "admissible-within-declared-scope"
    assert default_graph["completeness"] == "complete"
    assert extra_graph["completeness"] == "complete"
    assert len(extra_graph["result"]) > len(default_graph["result"])


def test_real_uv_grouped_edges_do_not_duplicate_topology_paths(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(
            _observation("uv", "grouped")
        )
        root_id = observation["roots"][0]["node_id"]
        selection = _dummy_selection(observation, "dummy-dep")
        paths = _query(
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

    assert paths["result"] == [[root_id, selection["node_id"]]]
    assert paths["completeness"] == "complete"
    assert paths["omissions"] == []


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
        present_graph = _query(
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
    assert present_graph["result"] == [
        {"depth": 1, "node_id": selection["node_id"], "selection": selection}
    ]
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
