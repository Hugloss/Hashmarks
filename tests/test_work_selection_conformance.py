from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from hashmarks.test_shards import (
    ENVELOPE_SCHEMA,
    EXECUTION_LAYER_AUTHORITIES,
    HASHMARKS_AUTHORITIES,
    MEMBERSHIP_SCHEMA,
    SCHEMA,
    plan,
    selection_membership_identity,
    node_membership_identity,
    validate_test_shard_plan,
    validate_work_selection_envelope,
    validate_work_selection_repository_binding,
    work_selection_envelope,
)


def _write_repo(root: Path) -> None:
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_a.py").write_text(
        "def test_one(): pass\ndef test_two(): pass\ndef test_three(): pass\n",
        encoding="utf-8",
    )
    (tests / "test_b.py").write_text(
        "def test_four(): pass\ndef test_five(): pass\n",
        encoding="utf-8",
    )
    (root / "src.py").write_text("VALUE = 1\n", encoding="utf-8")


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _resign_plan(value: dict[str, object]) -> None:
    body = {
        "schema": value.get("schema"),
        "shard_count": value.get("shard_count"),
        "test_node_count": value.get("test_node_count"),
        "shards": value.get("shards"),
    }
    value["plan_identity"] = "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _resign_envelope(value: dict[str, object]) -> None:
    body = dict(value)
    body.pop("envelope_identity", None)
    digest = hashlib.sha256()
    digest.update(ENVELOPE_SCHEMA.encode("utf-8"))
    digest.update(b"\0")
    digest.update(_canonical_bytes(body))
    value["envelope_identity"] = "sha256:" + digest.hexdigest()


def test_membership_identity_is_grouping_and_order_independent() -> None:
    nodeids = ["tests/test_a.py::test_one", "tests/test_b.py::test_two", "tests/test_c.py::test_three"]
    expected = node_membership_identity(nodeids)
    assert expected.startswith("sha256:")
    assert node_membership_identity(list(reversed(nodeids))) == expected

    selection_a = {
        "shards": [
            {"nodeids": [nodeids[0], nodeids[1]]},
            {"nodeids": [nodeids[2]]},
        ]
    }
    selection_b = {
        "shards": [
            {"nodeids": [nodeids[2], nodeids[0]]},
            {"nodeids": [nodeids[1]]},
        ]
    }
    assert selection_membership_identity(selection_a) == expected
    assert selection_membership_identity(selection_b) == expected


def test_membership_identity_rejects_omission_and_duplicate() -> None:
    full = ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]
    assert node_membership_identity(full) != node_membership_identity(full[:1])
    with pytest.raises(ValueError, match="duplicate"):
        node_membership_identity([full[0], full[0]])


def test_generated_v3_plan_is_strictly_valid_and_exposes_membership_identity(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    payload = plan(tmp_path, 3)
    result = validate_test_shard_plan(payload)
    assert payload["schema"] == SCHEMA
    assert result["valid"] is True
    assert result["reasons"] == []
    assert result["missing_fields"] == []
    assert result["unexpected_fields"] == []
    assert result["membership_identity"] == selection_membership_identity(payload)


def test_plan_rejects_recomputed_identity_with_unknown_shard_field(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    payload = deepcopy(plan(tmp_path, 3))
    payload["shards"][0]["timeout_seconds"] = 10  # type: ignore[index]
    _resign_plan(payload)
    result = validate_test_shard_plan(payload)
    assert result["valid"] is False
    assert "unexpected-shard-field" in result["reasons"]
    assert "$.selection.shards[0].timeout_seconds" in result["unexpected_fields"]


def test_plan_rejects_duplicate_membership_even_if_identity_is_recomputed(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    payload = deepcopy(plan(tmp_path, 3))
    duplicate = payload["shards"][0]["nodeids"][0]  # type: ignore[index]
    payload["shards"][1]["nodeids"].append(duplicate)  # type: ignore[index]
    payload["test_node_count"] = len(
        {nodeid for row in payload["shards"] for nodeid in row["nodeids"]}  # type: ignore[index]
    )
    _resign_plan(payload)
    result = validate_test_shard_plan(payload)
    assert result["valid"] is False
    assert "duplicate-nodeid" in result["reasons"]
    assert result["membership_identity"] is None


def test_plan_rejects_unowned_isolation_requirement_even_if_resigned(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    payload = deepcopy(plan(tmp_path, 5))
    payload["shards"][0]["isolated_process"] = True  # type: ignore[index]
    _resign_plan(payload)
    result = validate_test_shard_plan(payload)
    assert result["valid"] is False
    assert "process-isolation-requirements-mismatch" in result["reasons"]


def test_envelope_enforces_exact_frozen_authority_declaration(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    envelope = deepcopy(work_selection_envelope(tmp_path, 3))
    assert envelope["authority"]["hashmarks"] == list(HASHMARKS_AUTHORITIES)  # type: ignore[index]
    assert envelope["authority"]["execution_layer"] == list(EXECUTION_LAYER_AUTHORITIES)  # type: ignore[index]

    envelope["authority"]["hashmarks"].append("process-launch")  # type: ignore[index]
    _resign_envelope(envelope)
    result = validate_work_selection_envelope(envelope)
    assert result["valid"] is False
    assert "hashmarks-authority-mismatch" in result["reasons"]


def test_envelope_rejects_unknown_or_execution_policy_fields_after_resign(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    envelope = deepcopy(work_selection_envelope(tmp_path, 3))
    envelope["timeout_seconds"] = 30
    _resign_envelope(envelope)
    result = validate_work_selection_envelope(envelope)
    assert result["valid"] is False
    assert "unexpected-envelope-field" in result["reasons"]
    assert "execution-policy-field-present" in result["reasons"]
    assert "$.timeout_seconds" in result["unexpected_fields"]
    assert "$.timeout_seconds" in result["forbidden_execution_policy_paths"]


def test_envelope_rejects_unknown_non_execution_extension_after_resign(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    envelope = deepcopy(work_selection_envelope(tmp_path, 3))
    envelope["future_hint"] = {"value": True}
    _resign_envelope(envelope)
    result = validate_work_selection_envelope(envelope)
    assert result["valid"] is False
    assert "unexpected-envelope-field" in result["reasons"]
    assert "$.future_hint" in result["unexpected_fields"]


def test_membership_schema_is_separate_from_shard_and_envelope_schema() -> None:
    assert MEMBERSHIP_SCHEMA == "hashmarks.test-shard-membership.v1"
    assert MEMBERSHIP_SCHEMA not in {SCHEMA, ENVELOPE_SCHEMA}


def test_repository_binding_reproof_accepts_current_exact_repository(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    envelope = work_selection_envelope(tmp_path, 3)
    result = validate_work_selection_repository_binding(tmp_path, envelope)
    assert result["valid"] is True
    assert result["repository_bound"] is True
    assert result["current_repository_content_identity"] == envelope["repository"]["content_identity"]
    assert result["current_plan_identity"] == envelope["selection"]["plan_identity"]


def test_repository_binding_reproof_rejects_stale_non_test_source(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    envelope = work_selection_envelope(tmp_path, 3)
    (tmp_path / "src.py").write_text("VALUE = 2\n", encoding="utf-8")
    result = validate_work_selection_repository_binding(tmp_path, envelope)
    assert result["valid"] is False
    assert result["repository_bound"] is False
    assert "repository-content-identity-mismatch" in result["reasons"]
    assert "selection-input-identity-mismatch" not in result["reasons"]
    assert "selection-does-not-reproduce" not in result["reasons"]


def test_repository_binding_reproof_rejects_resigned_forged_membership(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    envelope = deepcopy(work_selection_envelope(tmp_path, 3))
    first = envelope["selection"]["shards"][0]  # type: ignore[index]
    second = envelope["selection"]["shards"][1]  # type: ignore[index]
    moved = first["nodeids"].pop()
    second["nodeids"].append(moved)
    _resign_plan(envelope["selection"])  # type: ignore[arg-type]
    _resign_envelope(envelope)
    structural = validate_work_selection_envelope(envelope)
    assert structural["valid"] is True
    rebound = validate_work_selection_repository_binding(tmp_path, envelope)
    assert rebound["valid"] is False
    assert "selection-does-not-reproduce" in rebound["reasons"]
