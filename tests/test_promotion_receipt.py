from pathlib import Path

from hashmarks.promotion_receipt import (
    PROMOTION_GATE_SCHEMA,
    PROMOTION_RECEIPT_SCHEMA,
    RUFF_COMMAND,
    RUFF_MIN_VERSION,
    RUFF_RULES,
    RUFF_VERSION_SPEC,
    _identity,
    native_ruff_promotion_gate,
    promotion_manifest,
    validate_external_promotion_receipt,
)
from hashmarks.qualification_units import native_qualification_handoff


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _handoff() -> dict[str, object]:
    return native_qualification_handoff(_root())


def _receipt(gate: dict[str, object], *, version: str = RUFF_MIN_VERSION) -> dict[str, object]:
    return {
        "schema": PROMOTION_RECEIPT_SCHEMA,
        "producer": {"name": "native-release-host"},
        "repository_identity": gate["repository_identity"],
        "gate_identity": gate["gate_identity"],
        "tool": {"name": "ruff", "version": version},
        "rules": gate["rules"],
        "command": gate["command"],
        "evidence": {
            "exit_code": 0,
            "tool_version_output": f"ruff {version}",
            "output_sha256": "sha256:" + "a" * 64,
        },
        "result": "pass",
        "result_authority": "external",
    }


def test_native_ruff_gate_declares_minimum_compatibility_and_exact_rules() -> None:
    gate = native_ruff_promotion_gate(_root())
    assert gate["tool"] == {"name": "ruff", "version_spec": RUFF_VERSION_SPEC}
    assert RUFF_VERSION_SPEC == f">={RUFF_MIN_VERSION}"
    assert gate["rules"] == list(RUFF_RULES)
    assert gate["command"] == list(RUFF_COMMAND)
    assert gate["promotion_authority"] == "diagnostic-only"
    assert gate["execution_authority"] == "external"
    assert gate["result_authority"] == "external"


def test_external_native_ruff_receipt_records_exact_evidence_version() -> None:
    gate = native_ruff_promotion_gate(_root())
    assert validate_external_promotion_receipt(gate, _receipt(gate)) == {
        "valid": True,
        "reasons": [],
        "authority": "validation-only",
    }


def test_ruff_receipt_accepts_any_version_at_or_above_minimum() -> None:
    gate = native_ruff_promotion_gate(_root())
    for version in ("0.12.0", "0.14.1", "0.16.99", "0.17.0", "1.0.0", "9.0.0"):
        checked = validate_external_promotion_receipt(gate, _receipt(gate, version=version))
        assert checked == {"valid": True, "reasons": [], "authority": "validation-only"}


def test_ruff_receipt_rejects_versions_below_minimum_or_unparseable() -> None:
    gate = native_ruff_promotion_gate(_root())
    for version in ("0.11.99", "latest"):
        checked = validate_external_promotion_receipt(gate, _receipt(gate, version=version))
        assert checked["valid"] is False
        assert "unsupported-tool-version" in checked["reasons"]


def test_ruff_receipt_binds_reported_version_to_version_output() -> None:
    gate = native_ruff_promotion_gate(_root())
    receipt = _receipt(gate, version="0.12.0")
    receipt["evidence"]["tool_version_output"] = "ruff 0.16.6"
    checked = validate_external_promotion_receipt(gate, receipt)
    assert checked["valid"] is False
    assert "tool-version-output-mismatch" in checked["reasons"]


def test_external_native_ruff_receipt_rejects_tool_identity_drift() -> None:
    gate = native_ruff_promotion_gate(_root())
    wrong_tool = _receipt(gate)
    wrong_tool["tool"] = {"name": "not-ruff", "version": RUFF_MIN_VERSION}
    checked = validate_external_promotion_receipt(gate, wrong_tool)
    assert checked["valid"] is False
    assert "invalid-receipt-tool" in checked["reasons"]
    assert "tool-identity-mismatch" in checked["reasons"]

    failed = _receipt(gate)
    failed["result"] = "fail"
    assert "promotion-gate-not-passed" in validate_external_promotion_receipt(gate, failed)["reasons"]


def test_promotion_manifest_requires_current_qualification_handoff() -> None:
    manifest = promotion_manifest(_root(), native_qualification_handoff=_handoff())
    assert manifest["manifest_valid"] is True
    assert manifest["native_qualification_handoff"]["valid"] is True
    assert manifest["release_authorized"] is False
    assert manifest["release_authority"] == "external-release-process"
    assert manifest["manifest_scope"] == "hashmarks-evidence-binding-only"
    assert manifest["native_ruff_receipt"] == {
        "present": False,
        "valid": False,
        "reasons": ["missing-native-ruff-receipt"],
    }


def test_promotion_manifest_rejects_rehashed_stale_handoff() -> None:
    handoff = _handoff()
    handoff["repository_identity"] = "sha256:" + "a" * 64 + ":1"
    payload = {key: value for key, value in handoff.items() if key != "handoff_identity"}
    from hashmarks.qualification_units import HANDOFF_SCHEMA, _identity as qualification_identity

    handoff["handoff_identity"] = qualification_identity(HANDOFF_SCHEMA, payload)
    manifest = promotion_manifest(_root(), native_qualification_handoff=handoff)
    assert manifest["manifest_valid"] is False
    assert "qualification-repository-identity-mismatch" in manifest["native_qualification_handoff"]["reasons"]


def test_valid_ruff_receipt_is_optional_diagnostic_evidence() -> None:
    gate = native_ruff_promotion_gate(_root())
    manifest = promotion_manifest(
        _root(),
        native_qualification_handoff=_handoff(),
        native_ruff_receipt=_receipt(gate, version="0.12.0"),
    )
    assert manifest["manifest_valid"] is True
    assert manifest["release_authorized"] is False
    assert manifest["native_ruff_receipt"] == {
        "present": True,
        "valid": True,
        "reasons": [],
    }


def test_external_promotion_receipt_rejects_exit_code_scalar_coercion(tmp_path: Path) -> None:
    gate = native_ruff_promotion_gate(tmp_path)
    for value in (False, 0.0, -0.0):
        receipt = _receipt(gate)
        receipt["evidence"]["exit_code"] = value
        assert "invalid-exit-code" in validate_external_promotion_receipt(gate, receipt)["reasons"]


def test_external_promotion_receipt_requires_lowercase_hex_output_identity(tmp_path: Path) -> None:
    gate = native_ruff_promotion_gate(tmp_path)
    for value in ("sha256:" + "g" * 64, "sha256:" + " " * 64, "sha256:" + "A" * 64):
        receipt = _receipt(gate)
        receipt["evidence"]["output_sha256"] = value
        assert "invalid-output-identity" in validate_external_promotion_receipt(gate, receipt)["reasons"]


def test_external_promotion_receipt_rejects_rehashed_gate_authority_tampering(tmp_path: Path) -> None:
    gate = native_ruff_promotion_gate(tmp_path)
    gate["promotion_authority"] = "canonical"
    payload = {key: value for key, value in gate.items() if key != "gate_identity"}
    gate["gate_identity"] = _identity(PROMOTION_GATE_SCHEMA, payload)
    receipt = _receipt(gate)
    checked = validate_external_promotion_receipt(gate, receipt)
    assert checked["valid"] is False
    assert "invalid-gate-promotion-authority" in checked["reasons"]
