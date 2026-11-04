"""Package projections preserve retained inventory scope before result bounds."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from contract_assertions import assert_array, assert_object, assert_records
from test_dependency_resolution_evidence import _snapshot_v3

from hashmarks import CodeMap, dependency_package_query_identity
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


def _name_snapshot() -> dict[str, object]:
    snapshot = _snapshot_v3()
    component = next(
        row
        for row in assert_records(snapshot["components"])
        if row["component_id"] == "library"
    )
    component.update(ecosystem="pypi", name="mlflow")
    for identifier, ecosystem, name in (
        ("py-separated", "pypi", "ML_Flow"),
        ("npm-same", "npm", "mlflow"),
        ("npm-scoped", "npm", "@scope/ml_flow"),
    ):
        assert_array(snapshot["components"]).append(
            {"component_id": identifier, "ecosystem": ecosystem, "name": name}
        )
        assert_array(snapshot["selections"]).append(
            {
                "node_id": identifier + "@1",
                "component_id": identifier,
                "version": "1",
                "source": "registry",
                "contexts": ["compile"],
                "evidence_sources": ["tree:compile"],
            }
        )
        assert_array(snapshot["inventory"]).append(
            {
                "node_id": identifier + "@1",
                "context": "compile",
                "evidence_sources": ["list:compile"],
            }
        )
    return snapshot


@pytest.mark.parametrize(
    "ecosystem,name,canonical,expected",
    [
        ("pypi", "MLFlow", "mlflow", "library@1"),
        ("pypi", "ML_Flow", "ml-flow", "py-separated@1"),
        ("pypi", "ml.__--flow", "ml-flow", "py-separated@1"),
        ("npm", "mlflow", "mlflow", "npm-same@1"),
        ("npm", "MLFlow", "MLFlow", None),
        ("npm", "@scope/ml_flow", "@scope/ml_flow", "npm-scoped@1"),
        ("npm", "@scope/ml-flow", "@scope/ml-flow", None),
    ],
)
def test_query_names_use_only_the_selected_ecosystem_without_rewriting_ids(
    tmp_path: Path, ecosystem: str, name: str, canonical: str, expected: str | None
) -> None:
    with CodeMap(tmp_path) as repository:
        observed = repository.dependencies.observe(_name_snapshot())
        original = deepcopy(observed)
        package = dependency_package_query(
            observed, {"ecosystem": ecosystem, "name": name, "context": "compile"}
        )
    assert observed == original
    identity = assert_object(package["package_identity"])
    assert identity == dependency_package_query_identity(ecosystem, name)
    assert identity["requested_name"] == name
    assert identity["canonical_name"] == canonical
    assert package["selector"] == {
        "ecosystem": ecosystem,
        "name": name,
        "context": "compile",
    }
    matches = assert_records(package["matches"])
    assert [assert_object(row["selection"])["node_id"] for row in matches] == (
        [expected] if expected else []
    )
    for row in matches:
        selection = assert_object(row["selection"])
        assert selection in assert_records(original["selections"])
        assert assert_object(row["component"]) in assert_records(original["components"])
    context = assert_records(package["contexts"])[0]
    assert context["membership"] == ("present" if expected else "absent")
    assert context["negative_evidence"] == (
        "not-applicable" if expected else "admissible-within-declared-scope"
    )


def test_public_query_identity_retains_caller_spelling_and_native_provenance() -> None:
    identity = dependency_package_query_identity("pypi", " ML_Flow ")
    assert identity["requested_name"] == " ML_Flow "
    assert identity["canonical_name"] == "ml-flow"
    assert (
        assert_object(identity["engine"])["operation"]
        == "packaging.utils.canonicalize_name"
    )
    assert identity["coordinate_existence"] == "not-observed"
    assert (
        identity["identity"]
        != dependency_package_query_identity("pypi", "ml-flow")["identity"]
    )
    assert (
        dependency_package_query_identity("npm", "@scope/ML_Flow")["canonical_name"]
        == "@scope/ML_Flow"
    )


def test_query_identity_bounds_the_original_spelling_before_retaining_it() -> None:
    with pytest.raises(ValueError, match="text bound"):
        dependency_package_query_identity("pypi", " " * 4096 + "x")


def test_canonical_name_equivalence_preserves_declared_ambiguity_and_bounds(
    tmp_path: Path,
) -> None:
    snapshot = _name_snapshot()
    assert_array(snapshot["components"]).append(
        {"component_id": "py-alias", "ecosystem": "pypi", "name": "MLFLOW"}
    )
    assert_array(snapshot["selections"]).append(
        {
            "node_id": "py-alias@1",
            "component_id": "py-alias",
            "version": "1",
            "source": "registry",
            "contexts": ["compile"],
            "evidence_sources": ["tree:compile"],
        }
    )
    assert_array(snapshot["inventory"]).append(
        {
            "node_id": "py-alias@1",
            "context": "compile",
            "evidence_sources": ["list:compile"],
        }
    )
    with CodeMap(tmp_path) as repository:
        observed = repository.dependencies.observe(snapshot)
        original = deepcopy(observed)
        result = dependency_package_query(
            observed,
            {"ecosystem": "pypi", "name": "MLFlow", "context": "compile"},
            max_results=1,
        )
    assert observed == original
    assert result["match_count"] == 2 and len(assert_records(result["matches"])) == 1
    assert assert_object(result["ambiguity"])["multiple_selections"] is True
    assert assert_object(result["ambiguity"])["uniqueness"] == "not-established"
    assert result["truncation"] == "truncated"
    assert assert_records(result["contexts"])[0]["membership"] == "present"


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
