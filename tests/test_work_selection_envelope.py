from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks._version import __version__
from hashmarks.test_shards import (
    ENVELOPE_SCHEMA,
    SCHEMA,
    plan,
    validate_work_selection_envelope,
    work_selection_envelope,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_repo(root: Path) -> None:
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_a.py").write_text(
        "def test_one(): pass\ndef test_two(): pass\n",
        encoding="utf-8",
    )
    (root / "src.py").write_text("VALUE = 1\n", encoding="utf-8")


def test_envelope_binds_v3_plan_repository_and_producer_without_execution_policy(
    tmp_path: Path,
) -> None:
    _write_repo(tmp_path)
    artifact = "sha256:" + "a" * 64
    envelope = work_selection_envelope(tmp_path, 2, producer_artifact_identity=artifact)

    assert envelope["schema"] == ENVELOPE_SCHEMA
    assert envelope["selection"]["schema"] == SCHEMA
    assert envelope["selection"] == plan(tmp_path, 2)
    assert envelope["producer"]["version"] == __version__
    assert envelope["producer"]["artifact_identity"] == artifact
    assert envelope["producer"]["implementation_identity"].startswith("sha256:")
    assert envelope["repository"]["content_identity"].startswith("sha256:")
    assert envelope["repository"]["selection_input_identity"].startswith("sha256:")
    assert envelope["envelope_identity"].startswith("sha256:")
    assert validate_work_selection_envelope(envelope)["valid"] is True

    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    forbidden_keys = {
        "timeout",
        "retry_count",
        "workers",
        "concurrency",
        "schedule",
        "machine",
        "argv",
    }
    assert forbidden_keys.isdisjoint(set(keys(envelope)))


def test_non_test_repository_change_invalidates_outer_envelope_not_inner_membership(
    tmp_path: Path,
) -> None:
    _write_repo(tmp_path)
    before = work_selection_envelope(tmp_path, 2)
    before_plan = before["selection"]
    before_input = before["repository"]["selection_input_identity"]

    (tmp_path / "src.py").write_text("VALUE = 2\n", encoding="utf-8")
    after = work_selection_envelope(tmp_path, 2)

    assert after["selection"] == before_plan
    assert after["repository"]["selection_input_identity"] == before_input
    assert (
        after["repository"]["content_identity"]
        != before["repository"]["content_identity"]
    )
    assert after["envelope_identity"] != before["envelope_identity"]


def test_test_source_change_invalidates_selection_input_and_plan_identity(
    tmp_path: Path,
) -> None:
    _write_repo(tmp_path)
    before = work_selection_envelope(tmp_path, 2)
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_one(): pass\ndef test_two(): pass\ndef test_three(): pass\n",
        encoding="utf-8",
    )
    after = work_selection_envelope(tmp_path, 2)

    assert (
        after["repository"]["selection_input_identity"]
        != before["repository"]["selection_input_identity"]
    )
    assert after["selection"]["plan_identity"] != before["selection"]["plan_identity"]
    assert after["envelope_identity"] != before["envelope_identity"]


def test_envelope_validation_rejects_tampered_shard_membership(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    envelope = work_selection_envelope(tmp_path, 2)
    envelope["selection"]["shards"][0]["nodeids"] = ["tests/test_a.py::test_changed"]
    result = validate_work_selection_envelope(envelope)
    assert result["valid"] is False
    assert "envelope-identity-mismatch" in result["reasons"]
    assert "selection-plan-identity-mismatch" in result["reasons"]


def test_envelope_rejects_invalid_artifact_identity(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    with pytest.raises(ValueError, match="producer_artifact_identity"):
        work_selection_envelope(
            tmp_path, 2, producer_artifact_identity="sha256:not-a-digest"
        )
