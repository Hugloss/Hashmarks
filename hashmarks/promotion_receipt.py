from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from ._version import __version__
from .qualification_units import (
    native_qualification_handoff as current_native_qualification_handoff,
)
from .qualification_units import (
    validate_native_qualification_handoff,
)
from .test_shards import repository_content_identity
from .validation_inputs import require_mapping_for_validation

if TYPE_CHECKING:
    from pathlib import Path

PROMOTION_GATE_SCHEMA = "hashmarks.promotion-gate.v2"
PROMOTION_RECEIPT_SCHEMA = "hashmarks.external-promotion-receipt.v2"
PROMOTION_MANIFEST_SCHEMA = "hashmarks.promotion-manifest.v3"

RUFF_TOOL = "ruff"
RUFF_MIN_VERSION = "0.12"
RUFF_VERSION_SPEC = f">={RUFF_MIN_VERSION}"
RUFF_RULES = (
    "E4",
    "E7",
    "E9",
    "F",
    "B",
    "I",
    "UP",
    "FAST",
    "SIM",
    "C4",
    "TID25",
    "T20",
    "G",
    "TC",
    "C901",
    "PLR0911",
    "PLR0912",
    "PLR0913",
    "PLR0914",
    "PLR0915",
    "PLR0916",
)
RUFF_COMMAND = ("make", "lint")
_REPOSITORY_IDENTITY = re.compile(r"^sha256:[0-9a-f]{64}:[0-9]+$")
_RELEASE_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _identity(domain: str, value: Mapping[str, object]) -> str:
    digest = hashlib.sha256(domain.encode("utf-8") + b"\0" + _canonical_bytes(value))
    return "sha256:" + digest.hexdigest()


def _release_tuple(value: str) -> tuple[int, int, int]:
    match = _RELEASE_RE.match(value.strip())
    if match is None:
        raise ValueError(value)
    major, minor, patch = match.groups()
    return int(major), int(minor or 0), int(patch or 0)


def _ruff_version_supported(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        actual = _release_tuple(value)
        minimum = _release_tuple(RUFF_MIN_VERSION)
    except ValueError:
        return False
    return actual >= minimum


def native_ruff_promotion_gate(root: Path) -> dict[str, object]:
    """Describe the retained native Ruff diagnostic contract.

    Ruff is diagnostic evidence only and is not a canonical-promotion
    prerequisite. The gate owns the minimum compatibility contract and exact rule
    contract; an external receipt records the concrete Ruff version that
    produced the evidence. Hashmarks does not execute Ruff or certify PASS.
    """
    root = root.resolve()
    payload: dict[str, object] = {
        "schema": PROMOTION_GATE_SCHEMA,
        "producer": {"name": "hashmarks", "version": __version__},
        "repository_identity": repository_content_identity(root),
        "gate": "ruff-diagnostic",
        "tool": {"name": RUFF_TOOL, "version_spec": RUFF_VERSION_SPEC},
        "rules": list(RUFF_RULES),
        "command": list(RUFF_COMMAND),
        "expected_result": "pass",
        "promotion_authority": "diagnostic-only",
        "execution_authority": "external",
        "result_authority": "external",
    }
    payload["gate_identity"] = _identity(PROMOTION_GATE_SCHEMA, payload)
    return payload


def _receipt_shape_reasons(receipt: Mapping[str, object]) -> list[str]:
    required = {
        "schema",
        "producer",
        "repository_identity",
        "gate_identity",
        "tool",
        "rules",
        "command",
        "evidence",
        "result",
        "result_authority",
    }
    reasons: list[str] = []
    if set(receipt) != required:
        reasons.append("receipt-fields-mismatch")
    if receipt.get("schema") != PROMOTION_RECEIPT_SCHEMA:
        reasons.append("unsupported-receipt-schema")
    if receipt.get("result_authority") != "external":
        reasons.append("result-authority-must-be-external")
    if receipt.get("result") != "pass":
        reasons.append("promotion-gate-not-passed")
    producer = receipt.get("producer")
    if not isinstance(producer, Mapping):
        reasons.append("invalid-receipt-producer")
    else:
        name = producer.get("name")
        try:
            _canonical_bytes(producer)
        except (TypeError, ValueError):
            reasons.append("invalid-receipt-producer")
        if not isinstance(name, str) or not name.strip():
            reasons.append("invalid-receipt-producer")
    tool = receipt.get("tool")
    if not isinstance(tool, Mapping):
        reasons.append("invalid-receipt-tool")
    else:
        if set(tool) != {"name", "version"}:
            reasons.append("invalid-receipt-tool")
        if tool.get("name") != RUFF_TOOL:
            reasons.append("invalid-receipt-tool")
        if not _ruff_version_supported(tool.get("version")):
            reasons.append("unsupported-tool-version")
    return reasons


def _gate_shape_reasons(gate: Mapping[str, object]) -> list[str]:
    required = {
        "schema",
        "producer",
        "repository_identity",
        "gate",
        "tool",
        "rules",
        "command",
        "expected_result",
        "promotion_authority",
        "execution_authority",
        "result_authority",
        "gate_identity",
    }
    reasons: list[str] = []
    if set(gate) != required:
        reasons.append("gate-fields-mismatch")
    if gate.get("schema") != PROMOTION_GATE_SCHEMA:
        reasons.append("unsupported-gate-schema")
    if gate.get("producer") != {"name": "hashmarks", "version": __version__}:
        reasons.append("invalid-gate-producer")
    repository_identity = gate.get("repository_identity")
    if not isinstance(repository_identity, str) or not _REPOSITORY_IDENTITY.fullmatch(
        repository_identity
    ):
        reasons.append("invalid-gate-repository-identity")
    if gate.get("gate") != "ruff-diagnostic":
        reasons.append("invalid-gate-name")
    if gate.get("tool") != {"name": RUFF_TOOL, "version_spec": RUFF_VERSION_SPEC}:
        reasons.append("invalid-gate-tool")
    if gate.get("rules") != list(RUFF_RULES):
        reasons.append("invalid-gate-rules")
    if gate.get("command") != list(RUFF_COMMAND):
        reasons.append("invalid-gate-command")
    if gate.get("expected_result") != "pass":
        reasons.append("invalid-gate-expected-result")
    if gate.get("promotion_authority") != "diagnostic-only":
        reasons.append("invalid-gate-promotion-authority")
    if gate.get("execution_authority") != "external":
        reasons.append("invalid-gate-execution-authority")
    if gate.get("result_authority") != "external":
        reasons.append("invalid-gate-result-authority")
    payload = {key: value for key, value in gate.items() if key != "gate_identity"}
    try:
        expected = _identity(PROMOTION_GATE_SCHEMA, payload)
    except (TypeError, ValueError):
        reasons.append("gate-not-canonical-json")
        expected = None
    if expected is None or gate.get("gate_identity") != expected:
        reasons.append("gate-identity-mismatch")
    return reasons


def _receipt_evidence_reasons(receipt: Mapping[str, object]) -> list[str]:
    evidence = receipt.get("evidence")
    if not isinstance(evidence, Mapping):
        return ["invalid-execution-evidence"]
    expected = {"exit_code", "tool_version_output", "output_sha256"}
    reasons: list[str] = []
    if set(evidence) != expected:
        reasons.append("execution-evidence-fields-mismatch")
    exit_code = evidence.get("exit_code")
    if type(exit_code) is not int:
        reasons.append("invalid-exit-code")
    elif exit_code != 0:
        reasons.append("nonzero-exit-code")
    tool = receipt.get("tool")
    tool_version = tool.get("version") if isinstance(tool, Mapping) else None
    if (
        not isinstance(tool_version, str)
        or evidence.get("tool_version_output") != f"ruff {tool_version}"
    ):
        reasons.append("tool-version-output-mismatch")
    output_sha256 = evidence.get("output_sha256")
    if (
        not isinstance(output_sha256, str)
        or len(output_sha256) != 71
        or not output_sha256.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in output_sha256[7:])
    ):
        reasons.append("invalid-output-identity")
    return reasons


def _receipt_binding_reasons(
    gate: Mapping[str, object],
    receipt: Mapping[str, object],
) -> list[str]:
    checks = (
        ("repository_identity", "repository-identity-mismatch"),
        ("gate_identity", "gate-identity-mismatch"),
        ("rules", "rule-set-mismatch"),
        ("command", "command-mismatch"),
    )
    reasons = [
        reason for field, reason in checks if receipt.get(field) != gate.get(field)
    ]
    gate_tool = gate.get("tool")
    receipt_tool = receipt.get("tool")
    if (
        not isinstance(gate_tool, Mapping)
        or not isinstance(receipt_tool, Mapping)
        or gate_tool.get("name") != receipt_tool.get("name")
    ):
        reasons.append("tool-identity-mismatch")
    return reasons


def validate_external_promotion_receipt(
    gate: Mapping[str, object],
    receipt: Mapping[str, object],
) -> dict[str, object]:
    gate, gate_root_reasons = require_mapping_for_validation(
        gate, reason="invalid-gate"
    )
    receipt, receipt_root_reasons = require_mapping_for_validation(
        receipt, reason="invalid-receipt"
    )
    reasons = [
        *gate_root_reasons,
        *receipt_root_reasons,
        *_gate_shape_reasons(gate),
        *_receipt_shape_reasons(receipt),
        *_receipt_evidence_reasons(receipt),
        *_receipt_binding_reasons(gate, receipt),
    ]
    return {
        "valid": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "authority": "validation-only",
    }


def _qualification_handoff_state(
    root: Path, handoff: Mapping[str, object]
) -> dict[str, object]:
    checked = validate_native_qualification_handoff(handoff)
    reasons = list(checked["reasons"])
    expected = current_native_qualification_handoff(root)
    fields = (
        "repository_identity",
        "membership_identity",
        "classification_identity",
        "classification_policy_identity",
        "plan_identity",
        "handoff_identity",
    )
    reasons.extend(
        f"qualification-{field.replace('_', '-')}-mismatch"
        for field in fields
        if handoff.get(field) != expected.get(field)
    )
    if handoff.get("producer") != expected.get("producer"):
        reasons.append("qualification-producer-mismatch")
    reasons = list(dict.fromkeys(reasons))
    return {
        "valid": not reasons,
        "reasons": reasons,
        "handoff_identity": handoff.get("handoff_identity"),
        "expected_handoff_identity": expected["handoff_identity"],
    }


def promotion_manifest(
    root: Path,
    *,
    native_qualification_handoff: Mapping[str, object],
    native_ruff_receipt: Mapping[str, object] | None = None,
) -> dict[str, object]:
    root = root.resolve()
    ruff_diagnostic = native_ruff_promotion_gate(root)
    receipt_state: dict[str, object] = {
        "present": native_ruff_receipt is not None,
        "valid": False,
        "reasons": ["missing-native-ruff-receipt"],
    }
    if native_ruff_receipt is not None:
        checked = validate_external_promotion_receipt(
            ruff_diagnostic, native_ruff_receipt
        )
        receipt_state = {
            "present": True,
            "valid": checked["valid"],
            "reasons": checked["reasons"],
        }

    qualification_state = _qualification_handoff_state(
        root, native_qualification_handoff
    )
    payload: dict[str, object] = {
        "schema": PROMOTION_MANIFEST_SCHEMA,
        "producer": {"name": "hashmarks", "version": __version__},
        "repository_identity": ruff_diagnostic["repository_identity"],
        "native_qualification_handoff": qualification_state,
        "required_native_gates": [],
        "ruff_diagnostic": ruff_diagnostic,
        "native_ruff_receipt": receipt_state,
        "manifest_valid": qualification_state["valid"],
        "manifest_scope": "hashmarks-evidence-binding-only",
        "release_authority": "external-release-process",
        "release_authorized": False,
    }
    payload["manifest_identity"] = _identity(PROMOTION_MANIFEST_SCHEMA, payload)
    return payload
