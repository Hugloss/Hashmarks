import copy
from pathlib import Path

import pytest

from hashmarks.qualification_units import (
    COVERAGE_SCHEMA,
    PLAN_SCHEMA,
    UNIT_SCHEMA,
    _identity,
    external_qualification_result,
    qualification_coverage_provenance_identity,
    qualification_owner_plan,
    validate_external_qualification_coverage,
    validate_native_qualification_handoff,
)
from hashmarks.test_shards import _nodeids, node_membership_identity


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _coverage(plan: dict[str, object], unit: dict[str, object]) -> dict[str, object]:
    return {
        "schema": COVERAGE_SCHEMA,
        "producer": {"name": "external-test-executor"},
        "repository_identity": plan["repository_identity"],
        "plan_identity": plan["plan_identity"],
        "unit_identity": unit["unit_identity"],
        "membership_identity": unit["membership_identity"],
        "executed_nodeids": list(reversed(unit["nodeids"])),
        "producer_implementation_identity": plan["producer"]["implementation_identity"],
        "provenance_identity": qualification_coverage_provenance_identity(plan, unit),
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }


def test_owner_units_exactly_partition_repository_test_membership(
    repository_qualification_plan,
) -> None:
    root = _root()
    units = tuple(repository_qualification_plan["units"])
    actual = [nodeid for unit in units for nodeid in unit["nodeids"]]
    expected = [nodeid for nodeid, _weight in _nodeids(root)]
    assert len(actual) == len(set(actual))
    assert set(actual) == set(expected)
    assert node_membership_identity(actual) == node_membership_identity(expected)


def test_special_classifications_are_singleton_external_units(
    repository_qualification_plan,
) -> None:
    units = tuple(repository_qualification_plan["units"])
    special = [unit for unit in units if unit["kind"] != "release-correctness"]
    assert len([unit for unit in special if unit["kind"] == "process-sensitive"]) == 1
    assert len([unit for unit in special if unit["kind"] == "empirical-benchmark"]) == 6
    assert all(unit["preferred_granularity"] == "singleton" for unit in special)
    assert all(unit["execution_authority"] == "external" for unit in special)
    assert all(unit["result_authority"] == "external" for unit in special)
    assert all(unit["certification_authority"] == "external" for unit in special)


def test_release_correctness_units_prefer_file_granularity_without_runtime_policy(
    repository_qualification_plan,
) -> None:
    units = tuple(repository_qualification_plan["units"])
    correctness = [unit for unit in units if unit["kind"] == "release-correctness"]
    assert correctness
    assert all(unit["preferred_granularity"] == "file" for unit in correctness)
    forbidden = {"timeout", "retry", "workers", "concurrency", "argv", "command"}
    assert all(not forbidden.intersection(unit) for unit in units)


def test_owner_plan_is_deterministic_and_binds_exact_membership_classification_and_producer() -> (
    None
):
    first = qualification_owner_plan(_root())
    second = qualification_owner_plan(_root())
    assert first == second
    assert first["membership_identity"].startswith("sha256:")
    assert first["classification_identity"].startswith("sha256:")
    assert first["classification_policy_identity"].startswith("sha256:")
    assert first["producer"]["implementation_identity"].startswith("sha256:")
    assert first["test_node_count"] == len(_nodeids(_root()))
    assert first["authority"] == {
        "classification": "hashmarks",
        "execution": "external",
        "result": "external",
        "certification": "external",
    }


def test_external_coverage_validates_linkage_without_interpreting_pass_result(
    repository_qualification_plan,
) -> None:
    plan = repository_qualification_plan
    unit = plan["units"][0]
    coverage = _coverage(plan, unit)
    assert validate_external_qualification_coverage(plan, coverage) == {
        "coverage_valid": True,
        "reasons": [],
        "authority": "coverage-validation-only",
    }

    external_result = external_qualification_result(
        coverage_identity="sha256:" + "b" * 64,
        result="pass",
        producer={"name": "external-test-executor"},
    )
    assert external_result["result"] == "pass"
    assert external_result["result_authority"] == "external"
    assert external_result["certification_authority"] == "external"


def test_coverage_rejects_omission_duplicate_and_execution_policy(
    repository_qualification_plan,
) -> None:
    plan = repository_qualification_plan
    unit = next(row for row in plan["units"] if len(row["nodeids"]) >= 2)
    base = _coverage(plan, unit)

    omitted = dict(base, executed_nodeids=list(unit["nodeids"][:-1]))
    assert (
        "executed-membership-mismatch"
        in validate_external_qualification_coverage(plan, omitted)["reasons"]
    )

    duplicated = dict(base, executed_nodeids=[*unit["nodeids"], unit["nodeids"][0]])
    assert (
        "executed-membership-mismatch"
        in validate_external_qualification_coverage(plan, duplicated)["reasons"]
    )

    wrong_provenance = dict(base, provenance_identity="sha256:" + "f" * 64)
    assert (
        "provenance-linkage-mismatch"
        in validate_external_qualification_coverage(plan, wrong_provenance)["reasons"]
    )

    with_timeout = dict(base)
    with_timeout["timeout"] = 30
    checked = validate_external_qualification_coverage(plan, with_timeout)
    assert "coverage-fields-mismatch" in checked["reasons"]
    assert "execution-policy-present" in checked["reasons"]


def test_coverage_rejects_invalid_external_producer_metadata(
    repository_qualification_plan,
) -> None:
    plan = repository_qualification_plan
    unit = plan["units"][0]
    base = _coverage(plan, unit)

    invalid = (
        ([], "invalid-external-coverage-producer"),
        ({"name": ""}, "invalid-external-coverage-producer-name"),
        ({"name": True}, "invalid-external-coverage-producer-name"),
        (
            {"name": "executor", "metric": float("nan")},
            "external-coverage-producer-not-canonical-json",
        ),
        (
            {"name": "executor", "opaque": {1}},
            "external-coverage-producer-not-canonical-json",
        ),
    )
    for producer, expected_reason in invalid:
        coverage = dict(base, producer=producer)
        checked = validate_external_qualification_coverage(plan, coverage)
        assert checked["coverage_valid"] is False
        assert expected_reason in checked["reasons"]


def test_native_handoff_keeps_execution_result_and_certification_external(
    repository_qualification_handoff,
) -> None:
    handoff = repository_qualification_handoff
    assert handoff["execution_authority"] == "external"
    assert handoff["result_authority"] == "external"
    assert handoff["certification_authority"] == "external"
    assert handoff["may_regroup"] is True


def test_repository_identity_ignores_runtime_materialization_but_binds_source(
    tmp_path: Path,
) -> None:
    from hashmarks.test_shards import repository_content_identity

    a = tmp_path / "a"
    b = tmp_path / "b"
    for root in (a, b):
        (root / "src").mkdir(parents=True)
        (root / "src" / "x.py").write_text("VALUE = 1\n")
    (a / ".venv").mkdir()
    (a / ".venv" / "runtime.txt").write_text("host A")
    (b / ".pytest_cache").mkdir()
    (b / ".pytest_cache" / "runtime.txt").write_text("host B")

    assert repository_content_identity(a) == repository_content_identity(b)

    (b / "src" / "x.py").write_text("VALUE = 2\n")
    assert repository_content_identity(a) != repository_content_identity(b)


def test_repository_identity_can_exclude_declared_runtime_state_path(
    tmp_path: Path,
) -> None:
    from hashmarks.test_shards import repository_content_identity

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("VALUE = 1\n")
    runtime = tmp_path / "custom-runtime-state"
    runtime.mkdir()
    first = repository_content_identity(tmp_path, excluded_paths=(runtime,))
    (runtime / "state.sqlite3").write_bytes(
        b"runtime changes do not own source identity"
    )
    second = repository_content_identity(tmp_path, excluded_paths=(runtime,))
    assert first == second
    (tmp_path / "src" / "x.py").write_text("VALUE = 2\n")
    assert repository_content_identity(tmp_path, excluded_paths=(runtime,)) != first


def test_owner_plan_reuses_one_repository_classification_snapshot(monkeypatch) -> None:
    import hashmarks.qualification_units as qualification_units_module
    import hashmarks.test_shards as test_shards_module

    nodeid_calls = 0
    identity_calls = 0
    real_nodeids = qualification_units_module._nodeids
    real_identity = test_shards_module.repository_content_identity

    def counted_nodeids(root: Path):
        nonlocal nodeid_calls
        nodeid_calls += 1
        return real_nodeids(root)

    def counted_identity(root: Path, *, excluded_paths=()):
        nonlocal identity_calls
        identity_calls += 1
        return real_identity(root, excluded_paths=excluded_paths)

    monkeypatch.setattr(qualification_units_module, "_nodeids", counted_nodeids)
    monkeypatch.setattr(
        test_shards_module, "repository_content_identity", counted_identity
    )

    plan = qualification_units_module.qualification_owner_plan(_root())

    assert plan["test_node_count"] > 0
    assert nodeid_calls == 1
    assert identity_calls == 1


def test_repository_identity_prunes_runtime_trees_before_walk(
    tmp_path: Path, monkeypatch
) -> None:
    import hashmarks.test_shards as test_shards_module

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("VALUE = 1\n")
    (tmp_path / ".venv" / "lib" / "site-packages").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "site-packages" / "huge.py").write_text(
        "ignored = True\n"
    )

    visited: list[str] = []
    real_walk = test_shards_module.os.walk

    def observed_walk(*args, **kwargs):
        for row in real_walk(*args, **kwargs):
            visited.append(Path(row[0]).relative_to(tmp_path).as_posix())
            yield row

    monkeypatch.setattr(test_shards_module.os, "walk", observed_walk)
    identity = test_shards_module.repository_content_identity(tmp_path)

    assert identity.startswith("sha256:")
    assert not any(path == ".venv" or path.startswith(".venv/") for path in visited)


def test_external_result_rejects_nonportable_or_coerced_identity_state() -> None:
    import math

    with pytest.raises(ValueError):
        external_qualification_result(
            coverage_identity="sha256:" + "a" * 64,
            result="pass",
            producer={"name": "x", "metric": math.nan},
        )
    for identity in ("bad", "sha256:" + "G" * 64):
        with pytest.raises(ValueError):
            external_qualification_result(
                coverage_identity=identity, result="pass", producer={"name": "x"}
            )


def test_native_handoff_rejects_rehashed_unit_authority_tampering(
    repository_qualification_handoff,
) -> None:
    handoff = copy.deepcopy(repository_qualification_handoff)
    unit = handoff["units"][0]
    unit["execution_authority"] = "hashmarks"
    unit_payload = {key: value for key, value in unit.items() if key != "unit_identity"}
    unit["unit_identity"] = _identity(UNIT_SCHEMA, unit_payload)
    payload = {
        key: value for key, value in handoff.items() if key != "handoff_identity"
    }
    handoff["handoff_identity"] = _identity(
        "hashmarks.native-qualification-handoff.v1", payload
    )
    checked = validate_native_qualification_handoff(handoff)
    assert checked["valid"] is False
    assert (
        "qualification-unit-execution-authority-must-be-external" in checked["reasons"]
    )


def test_coverage_rejects_rehashed_semantically_corrupt_hashmarks_plan(
    repository_qualification_plan,
) -> None:
    original = repository_qualification_plan
    unit = original["units"][0]
    coverage = _coverage(original, unit)
    plan = copy.deepcopy(original)
    mutated_unit = plan["units"][0]
    mutated_unit["timeout"] = 30
    unit_payload = {
        key: value for key, value in mutated_unit.items() if key != "unit_identity"
    }
    mutated_unit["unit_identity"] = _identity(UNIT_SCHEMA, unit_payload)
    plan_payload = {key: value for key, value in plan.items() if key != "plan_identity"}
    plan["plan_identity"] = _identity(PLAN_SCHEMA, plan_payload)
    checked = validate_external_qualification_coverage(plan, coverage)
    assert checked["coverage_valid"] is False
    assert "qualification-unit-fields-mismatch" in checked["reasons"]
    assert "qualification-unit-execution-policy-present" in checked["reasons"]
