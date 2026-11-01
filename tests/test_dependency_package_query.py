"""Package projections preserve retained inventory scope before result bounds."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import cast

import pytest
from contract_assertions import assert_array, assert_object, assert_records
from test_dependency_resolution_evidence import _snapshot_v3

from hashmarks import CodeMap
from hashmarks.codemap.dependency_resolution_query import dependency_package_query


def _package_snapshot() -> dict[str, object]:
    snapshot = _snapshot_v3()
    assert_array(snapshot["selections"]).append(
        {
            "node_id": "library@2",
            "component_id": "library",
            "version": "2",
            "source": "registry",
            "marker": "environment == 'optional'",
            "contexts": ["compile"],
            "evidence_sources": ["tree:compile"],
        }
    )
    snapshot["inventory"] = [
        row
        for row in assert_records(snapshot["inventory"])
        if row["node_id"] != "library@1"
    ]
    assert_array(snapshot["inventory"]).append(
        {
            "node_id": "library@2",
            "context": "compile",
            "evidence_sources": ["list:compile"],
        }
    )
    assert_array(snapshot["relationships"]).append(
        {
            "source": "app@1",
            "target": "library@2",
            "kind": "dependency",
            "context": "compile",
            "effective_scope": "optional",
            "marker": "environment == 'optional'",
            "evidence_sources": ["tree:compile"],
        }
    )
    snapshot["module_ownership"] = [
        {
            "module": "library.api",
            "context": "compile",
            "owners": ["library@1", "library@2"],
            "completeness": "incomplete",
            "evidence_sources": ["list:compile"],
        }
    ]
    return snapshot


@pytest.fixture(scope="module")
def package_observations(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, dict[str, object]]:
    workspace = tmp_path_factory.mktemp("dependency-package-query")
    result = {}
    with CodeMap(workspace) as repository:
        for state in ("complete", "incomplete", "truncated", "uncovered"):
            snapshot = _package_snapshot()
            inventory = next(
                row
                for row in assert_records(snapshot["coverage"])
                if row["kind"] == "resolved-inventory"
            )
            if state == "uncovered":
                assert_array(snapshot["coverage"]).remove(inventory)
            elif state != "complete":
                inventory.update(
                    completeness="incomplete",
                    truncation="truncated" if state == "truncated" else "complete",
                )
            result[state] = repository.dependencies.observe(snapshot)
    return result


def test_package_query_keeps_all_versions_contexts_and_owner_ambiguity(
    package_observations: dict[str, dict[str, object]],
) -> None:
    result = dependency_package_query(
        package_observations["complete"], {"ecosystem": "test", "name": "library"}
    )

    assert result["match_count"] == 2
    assert result["ambiguity"] == {
        "multiple_selections": True,
        "multiple_versions": True,
        "multiple_contexts": True,
        "uniqueness": "not-established",
    }
    matches = assert_records(result["matches"])
    assert [assert_object(row["selection"])["node_id"] for row in matches] == [
        "library@1",
        "library@2",
    ]
    assert (
        assert_object(matches[1]["selection"])["marker"] == "environment == 'optional'"
    )
    assert (
        assert_records(matches[1]["relationships"])[0]["effective_scope"] == "optional"
    )
    assert assert_records(matches[1]["relationships"])[0]["marker"] == (
        "environment == 'optional'"
    )
    for match in matches:
        owners = assert_records(match["module_ownership"])[0]
        assert owners["owners"] == ["library@1", "library@2"]
        assert owners["state"] == "resolved-ambiguous"
        assert owners["completeness"] == "incomplete"
    assert result["evidence_scope"] == "retained-dependency-observation"
    assert result["producer_authority"] == "caller-claimed"


def test_bounds_cannot_hide_membership_or_strengthen_selection_uniqueness(
    package_observations: dict[str, dict[str, object]],
) -> None:
    result = dependency_package_query(
        package_observations["complete"],
        {"ecosystem": "test", "name": "library"},
        max_results=1,
    )

    matches = assert_records(result["matches"])
    assert len(matches) == 1
    assert assert_object(matches[0]["selection"])["node_id"] == "library@1"
    assert matches[0]["inventory"] == []
    assert assert_object(matches[0]["omitted"])["relationships"] == 1
    assert result["match_count"] == 2
    assert assert_object(result["ambiguity"])["multiple_selections"] is True
    contexts = {row["context"]: row for row in assert_records(result["contexts"])}
    assert contexts["compile"]["membership"] == "present"
    assert contexts["compile"]["matching_inventory_node_ids"] == ["library@2"]
    assert contexts["runtime"]["membership"] == "unknown"
    assert result["truncation"] == "truncated"


@pytest.mark.parametrize(
    ("version", "context", "count", "membership"),
    [
        ("1", "compile", 1, "absent"),
        ("2", "compile", 1, "present"),
        ("2", "runtime", 0, "unknown"),
        ("99", "compile", 0, "absent"),
    ],
)
def test_package_inventory_membership_is_independent_of_selection_presence(
    package_observations: dict[str, dict[str, object]],
    version: str,
    context: str,
    count: int,
    membership: str,
) -> None:
    selector = {
        "ecosystem": "test",
        "name": "library",
        "version": version,
        "context": context,
    }
    result = dependency_package_query(package_observations["complete"], selector)

    assert result["selector"] == selector
    assert result["match_count"] == count
    scope = assert_records(result["contexts"])
    assert len(scope) == 1
    assert scope[0]["context"] == context
    assert scope[0]["membership"] == membership
    assert scope[0]["scope"] == "declared-resolved-inventory"
    assert scope[0]["negative_evidence"] == (
        "admissible-within-declared-scope"
        if membership == "absent"
        else "not-applicable"
        if membership == "present"
        else "not-admissible"
    )


@pytest.mark.parametrize("state", ["incomplete", "truncated", "uncovered"])
def test_missing_or_partial_inventory_cannot_borrow_complete_selection_coverage(
    package_observations: dict[str, dict[str, object]], state: str
) -> None:
    result = dependency_package_query(
        package_observations[state],
        {"ecosystem": "test", "name": "library", "version": "1", "context": "compile"},
    )

    assert result["match_count"] == 1
    scope = assert_records(result["contexts"])[0]
    assert scope["membership"] == "unknown"
    assert scope["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize(
    "selector",
    [
        {},
        {"ecosystem": "test"},
        {"ecosystem": "test", "name": "library", "version": None},
        {"ecosystem": "test", "name": "library", "version": 1},
        {"ecosystem": "test", "name": "library", "context": ""},
        {"ecosystem": "test", "name": "library", "context": "foreign"},
        {"ecosystem": "test", "name": "library", "scope": "runtime"},
        "library",
    ],
)
def test_package_selector_rejects_ignored_or_unqualified_fields(
    package_observations: dict[str, dict[str, object]], selector: object
) -> None:
    with pytest.raises(ValueError):
        dependency_package_query(
            package_observations["complete"], cast("Mapping[str, object]", selector)
        )


@pytest.mark.parametrize("bound", [0, True, 1.5, "1", 257])
def test_package_projection_bound_requires_supported_integer(
    package_observations: dict[str, dict[str, object]], bound: object
) -> None:
    with pytest.raises(ValueError):
        dependency_package_query(
            package_observations["complete"],
            {"ecosystem": "test", "name": "library"},
            max_results=cast("int", bound),
        )


def test_package_projection_detaches_nested_retained_claims(
    package_observations: dict[str, dict[str, object]],
) -> None:
    observation = package_observations["complete"]
    before = deepcopy(observation)
    result = dependency_package_query(
        observation, {"ecosystem": "test", "name": "library"}
    )
    match = assert_records(result["matches"])[0]
    assert_array(assert_object(match["selection"])["contexts"]).clear()
    assert_array(assert_records(match["module_ownership"])[0]["owners"]).clear()

    assert observation == before
