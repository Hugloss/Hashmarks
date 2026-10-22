"""A nomination consumer never inherits source, policy or process authority."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_observation import evidence_identity
from hashmarks.verification_nomination_validation import (
    validate_verification_nomination,
)

if TYPE_CHECKING:
    from pathlib import Path


def _nomination(root: Path, *, available: bool = True) -> dict[str, object]:
    (root / "tests").mkdir()
    (root / "tests/test_sample.py").write_text(
        "def test_sample(): pass\n", encoding="utf-8"
    )
    with CodeMap(root) as codemap:
        codemap.index.sync()
        return dict(
            codemap.verification.nomination(
                "tests/test_sample.py" if available else "tests/no_such_test.py"
            )
        )


@pytest.mark.parametrize("available", [True, False])
def test_validator_accepts_canonical_producer_projection_without_admission(
    tmp_path: Path, available: bool
) -> None:
    nomination = _nomination(tmp_path, available=available)
    result = validate_verification_nomination(nomination)
    assert result["valid"] is True
    assert result["reasons"] == []
    assert result["nomination_identity"] == nomination["nomination_identity"]
    assert result["authority"] == "content-integrity-only"
    assert result["repository_binding"] == "not-checked"
    assert result["producer_authenticity"] == "not-checked"
    assert result["execution_authority"] == "external"


@pytest.mark.parametrize(
    "mutation",
    [
        "modified-digest",
        "forged-command",
        "forged-execution-authority",
        "noncanonical-target-path",
        "invalid-availability",
    ],
)
def test_validator_rejects_mutated_nomination_fields(
    tmp_path: Path, mutation: str
) -> None:
    changed = deepcopy(_nomination(tmp_path))
    if mutation == "modified-digest":
        changed["nomination_identity"] = "sha256:" + "0" * 64
    elif mutation == "forged-command":
        changed["argv"] = ["sh", "-c", "echo no"]
    elif mutation == "forged-execution-authority":
        changed["execution_authority"] = "hashmarks"
    elif mutation == "noncanonical-target-path":
        changed["verification_target"]["path"] = "tests/./test_sample.py"
    elif mutation == "invalid-availability":
        changed["available"] = 1
    result = validate_verification_nomination(changed)
    assert result["valid"] is False
    assert result["reasons"]
    assert result["nomination_identity"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        "absent-test-member",
        "duplicate-member",
        "invalid-source-revision",
        "extra-member-state",
        "reordered-test-member",
        "mismatched-source-revision",
    ],
)
def test_validator_rejects_mutated_nomination_ledger(
    tmp_path: Path, mutation: str
) -> None:
    changed = deepcopy(_nomination(tmp_path))
    members = changed["supporting_source_members"]
    if mutation == "absent-test-member":
        members[0] = {"path": members[0]["path"], "state": "known-absent"}
    elif mutation == "duplicate-member":
        members.append(deepcopy(members[0]))
    elif mutation == "invalid-source-revision":
        members[0]["member_revision"] = "unknown"
    elif mutation == "extra-member-state":
        members[0]["state"] = "unknown"
    elif mutation == "reordered-test-member":
        members.reverse()
    elif mutation == "mismatched-source-revision":
        changed["source_member_revision"] = "f" * 64
    result = validate_verification_nomination(changed)
    assert result["valid"] is False
    assert result["reasons"]
    assert result["nomination_identity"] is None


def test_resigned_malformed_packet_is_still_rejected(tmp_path: Path) -> None:
    changed = _nomination(tmp_path)
    changed["supporting_source_members"][0]["member_revision"] = "not-a-digest"
    without_identity = {
        key: value for key, value in changed.items() if key != "nomination_identity"
    }
    changed["nomination_identity"] = evidence_identity(
        changed["schema"], without_identity
    )
    result = validate_verification_nomination(changed)
    assert result["valid"] is False
    assert "invalid-source-member-revision" in result["reasons"]


@pytest.mark.parametrize("mutation", ["extra-command", "invalid-reason", "not-boolean"])
def test_unavailable_packet_cannot_gain_hidden_authority(
    tmp_path: Path, mutation: str
) -> None:
    changed = _nomination(tmp_path, available=False)
    if mutation == "extra-command":
        changed["command"] = ["python", "-m", "pytest"]
    elif mutation == "invalid-reason":
        changed["reason"] = ""
    elif mutation == "not-boolean":
        changed["available"] = "false"
    assert validate_verification_nomination(changed)["valid"] is False


@pytest.mark.parametrize("bad", [None, [], "", 7, True, {"schema": "wrong"}])
def test_validator_handles_malformed_root_without_throwing(bad: object) -> None:
    response = validate_verification_nomination(bad)
    assert response["valid"] is False
    assert response["reasons"]
    assert response["execution_authority"] == "external"


def test_validated_identity_is_not_current_repository_binding(tmp_path: Path) -> None:
    packet = _nomination(tmp_path)
    (tmp_path / "tests/test_sample.py").write_text(
        "def test_sample(): assert False\n", encoding="utf-8"
    )
    result = validate_verification_nomination(packet)
    assert result["valid"] is True
    assert result["repository_binding"] == "not-checked"



def test_validator_does_not_redecide_runner_or_scope_semantics(tmp_path: Path) -> None:
    """A resigned payload can be structurally sound without trusted provenance."""
    packet = _nomination(tmp_path)
    packet["runner_evidence"] = "future-repository-runner"
    packet["scope"] = "future-test-scope"
    payload = {key: value for key, value in packet.items() if key != "nomination_identity"}
    packet["nomination_identity"] = evidence_identity(packet["schema"], payload)
    state = validate_verification_nomination(packet)
    assert state["valid"] is True
    assert state["producer_authenticity"] == "not-checked"
    assert state["repository_binding"] == "not-checked"
