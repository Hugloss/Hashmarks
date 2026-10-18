"""Current repository binding stays with selection evidence, outside release policy."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from hashmarks.qualification_units import (
    HANDOFF_SCHEMA,
    _identity,
    native_qualification_handoff,
    validate_native_qualification_handoff,
    validate_native_qualification_repository_binding,
)
from scripts.qualification_handoff import main


def _repository(root: Path, *, value: int = 1) -> Path:
    (root / "tests").mkdir(parents=True)
    (root / "tests/test_sample.py").write_text("def test_sample(): pass\n")
    (root / "source.py").write_text(f"def sample(): return {value}\n")
    return root


def _rehash(handoff: dict[str, object]) -> None:
    handoff["handoff_identity"] = _identity(
        HANDOFF_SCHEMA,
        {key: value for key, value in handoff.items() if key != "handoff_identity"},
    )


def test_current_handoff_binding_has_only_repository_validation_authority(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    handoff = native_qualification_handoff(root)
    checked = validate_native_qualification_repository_binding(root, handoff)
    assert checked["valid"] is True
    assert checked["reasons"] == []
    assert checked["authority"] == "consumer-validation-only"
    assert checked["handoff_identity"] == handoff["handoff_identity"]
    assert {"release_authorized", "result", "tool", "rules"}.isdisjoint(checked)
    assert handoff["execution_authority"] == "external"
    assert handoff["result_authority"] == "external"
    assert handoff["certification_authority"] == "external"


def test_binding_detects_source_drift_even_when_selected_membership_is_unchanged(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    before = native_qualification_handoff(root)
    (root / "source.py").write_text("def sample(): return 2\n")
    after = native_qualification_handoff(root)
    assert before["membership_identity"] == after["membership_identity"]
    assert validate_native_qualification_handoff(before)["valid"] is True
    checked = validate_native_qualification_repository_binding(root, before)
    assert checked["valid"] is False
    assert "qualification-repository-identity-mismatch" in checked["reasons"]


def test_rehashed_foreign_handoff_does_not_gain_current_binding(tmp_path: Path) -> None:
    root = _repository(tmp_path / "current")
    foreign = _repository(tmp_path / "foreign", value=2)
    handoff = native_qualification_handoff(foreign)
    _rehash(handoff)
    assert validate_native_qualification_handoff(handoff)["valid"] is True
    checked = validate_native_qualification_repository_binding(root, handoff)
    assert checked["valid"] is False
    assert "qualification-repository-identity-mismatch" in checked["reasons"]


@pytest.mark.parametrize(
    "field", ["repository_identity", "classification_policy_identity"]
)
def test_self_consistent_rehashed_identity_drift_does_not_rebind_the_repository(
    tmp_path: Path, field: str
) -> None:
    from contract_assertions import assert_object

    root = _repository(tmp_path)
    handoff = native_qualification_handoff(root)
    handoff[field] = (
        "sha256:" + "a" * 64 + (":1" if field == "repository_identity" else "")
    )
    assert_object(handoff["provenance"])[field] = handoff[field]
    _rehash(handoff)
    assert validate_native_qualification_handoff(handoff)["valid"] is True
    checked = validate_native_qualification_repository_binding(root, handoff)
    assert checked["valid"] is False
    assert f"qualification-{field.replace('_', '-')}-mismatch" in checked["reasons"]


def test_binding_validation_does_not_mutate_comparison_input(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    handoff = native_qualification_handoff(root)
    before = deepcopy(handoff)
    validate_native_qualification_repository_binding(root, handoff)
    assert handoff == before


def test_binding_rejects_rehashed_execution_policy(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    handoff = native_qualification_handoff(root)
    handoff["workers"] = 8
    _rehash(handoff)
    checked = validate_native_qualification_repository_binding(root, handoff)
    assert checked["valid"] is False
    assert "handoff-fields-mismatch" in checked["reasons"]


def test_handoff_cli_renders_and_validates_without_result_or_promotion_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo")
    assert main(["--root", str(root)]) == 0
    handoff = json.loads(capsys.readouterr().out)
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(handoff))
    assert main(["--root", str(root), "--validate", str(path)]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["valid"] is True
    assert checked["authority"] == "consumer-validation-only"
    assert {"manifest_valid", "release_authorized", "native_ruff_receipt"}.isdisjoint(
        checked
    )
    (root / "source.py").write_text("def sample(): return 2\n")
    assert main(["--root", str(root), "--validate", str(path)]) == 3
    assert json.loads(capsys.readouterr().out)["valid"] is False


def test_handoff_cli_has_no_external_tool_result_receipt_option() -> None:
    with pytest.raises(SystemExit) as failure:
        main(["--receipt", "ruff-result.json"])
    assert failure.value.code == 2
