"""Version predicates qualify retained selections before bounded projection."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path

import packaging
import pytest
from contract_assertions import assert_array, assert_object, assert_records
from test_dependency_resolution_evidence import _snapshot_v3

from hashmarks import CodeMap, hash_file
from hashmarks.codemap.dependency_resolution_query import dependency_package_query
from hashmarks.operation_contract import validate_operation_response


def _versions(versions: Sequence[str], *, ecosystem: str = "pypi") -> dict[str, object]:
    snapshot = _snapshot_v3()
    component = next(
        row
        for row in assert_records(snapshot["components"])
        if row["component_id"] == "library"
    )
    component["ecosystem"] = ecosystem
    selections = assert_records(snapshot["selections"])
    selected = next(row for row in selections if row["component_id"] == "library")
    selected["version"] = versions[0]
    for index, version in enumerate(versions[1:], start=2):
        node = f"library@{index}"
        selections.append({**selected, "node_id": node, "version": version})
        assert_array(snapshot["inventory"]).append(
            {
                "node_id": node,
                "context": "compile",
                "evidence_sources": ["list:compile"],
            }
        )
    snapshot["selections"] = selections
    return snapshot


def _selector(
    expression: str, *, dialect: str = "pep440", ecosystem: str = "pypi"
) -> dict[str, object]:
    return {
        "ecosystem": ecosystem,
        "name": "library",
        "version_predicate": {"dialect": dialect, "expression": expression},
    }


def _predicate(package: dict[str, object]) -> dict[str, object]:
    return assert_object(package["version_predicate"])


def test_matching_selection_beyond_first_page_is_not_lost(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as repository:
        observed = repository.dependencies.observe(_versions(["1", "2", "3"]))
        result = dependency_package_query(observed, _selector(">=3"), max_results=1)

    assert result["match_count"] == 1
    assert (
        assert_object(assert_records(result["matches"])[0]["selection"])["version"]
        == "3"
    )
    predicate = _predicate(result)
    assert predicate["counts"] == {"match": 1, "nonmatch": 2, "unclassified": 0}
    assert len(assert_records(predicate["selections"])) == 1
    assert predicate["omitted_selection_count"] == 2
    assert predicate["truncation"] == result["truncation"] == "truncated"
    assert predicate["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize("expression", [">99", "not a native predicate"])
def test_predicate_nonmatch_or_unknown_cannot_become_package_absence(
    tmp_path: Path, expression: str
) -> None:
    with CodeMap(tmp_path) as repository:
        observed = repository.dependencies.observe(_versions(["1", "2"]))
        result = dependency_package_query(observed, _selector(expression))

    assert result["match_count"] == 0
    assert result["matches"] == []
    compile_scope = next(
        row for row in assert_records(result["contexts"]) if row["context"] == "compile"
    )
    assert compile_scope["membership"] == "present"
    assert compile_scope["negative_evidence"] == "not-applicable"
    assert _predicate(result)["negative_evidence"] == "not-admissible"


def test_unclassified_versions_and_coverage_survive_projection(tmp_path: Path) -> None:
    raw = _versions(["1.1", "unparseable-version", "4"])
    coverage = next(
        row
        for row in assert_records(raw["coverage"])
        if row["context"] == "runtime" and row["kind"] == "selection"
    )
    coverage["completeness"] = "incomplete"
    with CodeMap(tmp_path) as repository:
        observed = repository.dependencies.observe(raw)
        result = dependency_package_query(observed, _selector("<2"), max_results=1)

    predicate = _predicate(result)
    assert predicate["counts"] == {"match": 1, "nonmatch": 1, "unclassified": 1}
    assert predicate["completeness"] == "incomplete"
    assert predicate["omitted_selection_count"] == 2
    assert predicate["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize(
    ("ecosystem", "dialect", "expression", "counts"),
    [
        ("pypi", "pep440", ">=1,<2", {"match": 1, "nonmatch": 1, "unclassified": 0}),
        ("npm", "npm-semver", "^1.0.0", {"match": 1, "nonmatch": 1, "unclassified": 0}),
        ("npm", "pep440", ">=1,<2", {"match": 0, "nonmatch": 0, "unclassified": 2}),
        ("maven", "pep440", ">=1,<2", {"match": 0, "nonmatch": 0, "unclassified": 2}),
    ],
)
def test_predicate_uses_selected_ecosystem_and_exact_native_dialect(
    tmp_path: Path,
    ecosystem: str,
    dialect: str,
    expression: str,
    counts: dict[str, int],
) -> None:
    with CodeMap(tmp_path) as repository:
        observed = repository.dependencies.observe(
            _versions(["1.1.0", "2.0.0"], ecosystem=ecosystem)
        )
        result = dependency_package_query(
            observed, _selector(expression, dialect=dialect, ecosystem=ecosystem)
        )
    assert _predicate(result)["counts"] == counts


def test_predicate_does_not_change_legacy_exact_version_identity(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as repository:
        observed = repository.dependencies.observe(_versions(["1", "2"]))
        exact = dependency_package_query(
            observed, {"ecosystem": "pypi", "name": "library", "version": "2"}
        )
        conflicting = {**_selector(">1"), "version": "2"}
        with pytest.raises(ValueError, match="mutually exclusive"):
            dependency_package_query(observed, conflicting)
    assert exact["match_count"] == 1
    assert "version_predicate" not in exact


def test_prerelease_policy_participates_in_projection_identity(tmp_path: Path) -> None:
    selector = _selector(">=1.0rc1,<2")
    inclusive = deepcopy(selector)
    assert_object(inclusive["version_predicate"])["prereleases"] = True
    with CodeMap(tmp_path) as repository:
        observed = repository.dependencies.observe(_versions(["1.0rc1", "1.0"]))
        stable = repository.dependencies.projection(observed, packages=[selector])
        prereleases = repository.dependencies.projection(observed, packages=[inclusive])
        assert repository.dependencies.requalify(stable) == stable
    stable_package = assert_records(stable["packages"])[0]
    inclusive_package = assert_records(prereleases["packages"])[0]
    assert _predicate(stable_package)["counts"] == {
        "match": 1,
        "nonmatch": 1,
        "unclassified": 0,
    }
    assert _predicate(inclusive_package)["counts"] == {
        "match": 2,
        "nonmatch": 0,
        "unclassified": 0,
    }
    assert stable["projection_identity"] != prereleases["projection_identity"]
    assert (
        _predicate(stable_package)["predicate_identity"]
        != _predicate(inclusive_package)["predicate_identity"]
    )


def test_predicate_preserves_component_ecosystem_and_context_scope(
    tmp_path: Path,
) -> None:
    raw = _versions(["1.1", "2.0"])
    second = next(
        row
        for row in assert_records(raw["selections"])
        if row["node_id"] == "library@2"
    )
    second.update(contexts=["runtime"], evidence_sources=["tree:runtime"])
    raw["inventory"] = [
        row for row in assert_records(raw["inventory"]) if row["node_id"] != "library@2"
    ]
    assert_array(raw["components"]).append(
        {"component_id": "npm-library", "name": "library", "ecosystem": "npm"}
    )
    assert_array(raw["selections"]).append(
        {
            **second,
            "node_id": "npm-library@2",
            "component_id": "npm-library",
            "version": "2.0.0",
        }
    )
    with CodeMap(tmp_path) as repository:
        observed = repository.dependencies.observe(raw)
        compile_scope = dependency_package_query(
            observed, {**_selector("<3"), "context": "compile"}
        )
        runtime_scope = dependency_package_query(
            observed, {**_selector("<3"), "context": "runtime"}
        )
        npm = dependency_package_query(
            observed, _selector("^2", dialect="npm-semver", ecosystem="npm")
        )
    assert _predicate(compile_scope)["counts"] == {
        "match": 1,
        "nonmatch": 0,
        "unclassified": 0,
    }
    assert _predicate(runtime_scope)["counts"] == {
        "match": 2,
        "nonmatch": 0,
        "unclassified": 0,
    }
    assert [
        assert_object(row["selection"])["node_id"]
        for row in assert_records(npm["matches"])
    ] == ["npm-library@2"]
    assert (
        _predicate(npm)["predicate_identity"]
        != _predicate(runtime_scope)["predicate_identity"]
    )


def _bound_observation(repository: CodeMap) -> dict[str, object]:
    path = repository.workspace / "dependency.lock"
    path.write_text("frozen producer input\n", encoding="utf-8")
    raw = _versions(["1.1", "2", "unparseable-version"])
    raw["repository_inputs"] = [
        {"path": "dependency.lock", "member_revision": hash_file(path).hash}
    ]
    return repository.dependencies.observe(raw)


def test_retained_predicate_requalification_preserves_source_and_identity(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as repository:
        observed = _bound_observation(repository)
        before = repository.dependencies.projection(
            observed, packages=[_selector("<2")]
        )
        unchanged = repository.dependencies.requalify(before)
        assert unchanged == before
        (tmp_path / "dependency.lock").write_text(
            "changed producer input\n", encoding="utf-8"
        )
        stale = repository.dependencies.requalify(before)

    validate_operation_response("dependency_projection", stale)
    package = assert_records(stale["packages"])[0]
    assert _predicate(package)["counts"] == {
        "match": 1,
        "nonmatch": 1,
        "unclassified": 1,
    }
    assert stale["observation"] == before["observation"]
    assert stale["negative_evidence"] == "not-admissible"
    assert assert_records(package["current_inventory"])[0]["membership"] == "unknown"
    assert stale["projection_identity"] != before["projection_identity"]


def test_engine_drift_rejects_retained_predicate_before_source_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with CodeMap(tmp_path) as repository:
        observed = _bound_observation(repository)
        retained = repository.dependencies.projection(
            observed, packages=[_selector("<2")]
        )

        def forbid_assessment(_observation: object) -> dict[str, object]:
            raise AssertionError(
                "predicate engine drift reached current-source assessment"
            )

        monkeypatch.setattr(repository.dependencies, "assessment", forbid_assessment)
        monkeypatch.setattr(packaging, "__version__", "changed-native-engine")
        with pytest.raises(ValueError, match="predicate semantics changed"):
            repository.dependencies.requalify(retained)


def test_engine_drift_during_requalification_rejects_mixed_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with CodeMap(tmp_path) as repository:
        observed = _bound_observation(repository)
        retained = repository.dependencies.projection(
            observed, packages=[_selector("<2")]
        )
        native_assessment = repository.dependencies.assessment

        def change_engine(observation: dict[str, object]) -> dict[str, object]:
            assessed = native_assessment(observation)
            monkeypatch.setattr(
                packaging, "__version__", "changed-during-source-assessment"
            )
            return assessed

        monkeypatch.setattr(repository.dependencies, "assessment", change_engine)
        with pytest.raises(
            ValueError, match="semantics changed during requalification"
        ):
            repository.dependencies.requalify(retained)


def test_unknown_empty_predicate_scope_stays_unavailable(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as repository:
        observed = _bound_observation(repository)
        packet = repository.dependencies.projection(
            observed,
            packages=[{**_selector("not a native predicate"), "name": "not-present"}],
            source_paths=["dependency.lock"],
        )
    predicate = _predicate(assert_records(packet["packages"])[0])
    assert predicate["counts"] == {"match": 0, "nonmatch": 0, "unclassified": 0}
    assert predicate["availability"] == "unsupported"
    assert predicate["completeness"] == "incomplete"
    consumers = assert_object(packet["consumer_evidence"])
    assert consumers["state"] == "unavailable"
    assert consumers["reason"] == "version-predicate-unclassified"


def test_predicate_projection_detaches_retained_nested_evidence(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as repository:
        observed = _bound_observation(repository)
        original = deepcopy(observed)
        result = dependency_package_query(observed, _selector("<2"))
    evidence = _predicate(result)
    assert_records(evidence["selections"])[0]["state"] = "forged"
    assert_object(evidence["engine"])["version"] = "forged"
    assert observed == original
