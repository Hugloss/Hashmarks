from __future__ import annotations

from copy import deepcopy

import pytest

from hashmarks import __version__
from hashmarks.verification_selection import (
    VerificationSelectionEnvelopeState,
    downstream_consumption_contract,
    validate_verification_membership,
    validate_verification_selection_envelope,
    verification_member,
    verification_membership,
    verification_selection_envelope,
)


def test_membership_identity_is_order_independent_and_member_ids_are_stable() -> None:
    a = verification_member("tests/test_a.py", test_symbol="test_a")
    b = verification_member("tests/test_b.py")
    first = verification_membership([a, b])
    second = verification_membership([b, a])

    assert first["membership_identity"] == second["membership_identity"]
    assert first["members"] == second["members"]
    assert first["members"][0]["member_id"].startswith("sha256:")
    assert first["member_count"] == 2


def test_membership_identity_changes_on_omission_and_duplicate_fails_closed() -> None:
    a = verification_member("tests/test_a.py", test_symbol="test_a")
    b = verification_member("tests/test_b.py")
    full = verification_membership([a, b])
    reduced = verification_membership([a])

    assert full["membership_identity"] != reduced["membership_identity"]

    try:
        verification_membership([a, a])
    except ValueError as exc:
        assert "duplicate verification member" in str(exc)
    else:
        raise AssertionError("duplicate verification member was accepted")


def test_selection_envelope_binds_repository_source_owner_and_evidence_hashes() -> None:
    membership = verification_membership(
        [
            verification_member("tests/test_a.py", test_symbol="test_a"),
        ]
    )
    envelope = verification_selection_envelope(
        VerificationSelectionEnvelopeState(
            repository_identity="git-tree:abc",
            source_identity="sha256:" + "1" * 64,
            codemap_generation=7,
            identity_generation=3,
            stale=False,
            membership=membership,
            owner_evidence={"selected": "src/a.py", "via": "import"},
            evidence_hashes={
                "ownership": "sha256:" + "2" * 64,
                "verification_plan": "sha256:" + "3" * 64,
            },
        )
    )

    assert (
        envelope["selection"]["membership_identity"]
        == membership["membership_identity"]
    )
    assert envelope["repository"]["repository_identity"] == "git-tree:abc"
    assert envelope["repository"]["source_identity"].startswith("sha256:")
    assert envelope["producer"]["name"] == "hashmarks"
    assert envelope["envelope_identity"].startswith("sha256:")
    assert validate_verification_selection_envelope(envelope)["valid"] is True


def test_selection_validator_rejects_nonportable_owner_and_invalid_hash_entries() -> (
    None
):
    membership = verification_membership([verification_member("tests/test_a.py")])
    envelope = verification_selection_envelope(
        VerificationSelectionEnvelopeState(
            repository_identity="git-tree:abc",
            source_identity="sha256:" + "1" * 64,
            codemap_generation=7,
            identity_generation=None,
            stale=False,
            membership=membership,
            owner_evidence={},
            evidence_hashes={},
        )
    )
    envelope["owner_evidence"] = {"unportable": object()}
    envelope["evidence_hashes"] = {42: "bad"}

    reasons = validate_verification_selection_envelope(envelope)["reasons"]
    assert "invalid-owner-evidence" in reasons
    assert "invalid-evidence-hash-key" in reasons
    assert "invalid-evidence-hash" in reasons
    assert "nonportable-envelope-payload" in reasons


def test_membership_validator_rejects_member_schema_drift() -> None:
    membership = verification_membership([verification_member("tests/test_a.py")])
    membership["members"][0]["schema"] = "unsupported"

    reasons = validate_verification_membership(membership)["reasons"]
    assert "unsupported-member-schema" in reasons
    assert "member-payload-identity-mismatch" in reasons


def test_selection_envelope_rejects_membership_and_provenance_tampering() -> None:
    membership = verification_membership(
        [
            verification_member("tests/test_a.py"),
            verification_member("tests/test_b.py"),
        ]
    )
    envelope = verification_selection_envelope(
        VerificationSelectionEnvelopeState(
            repository_identity="git-tree:abc",
            source_identity="sha256:" + "1" * 64,
            codemap_generation=7,
            identity_generation=None,
            stale=False,
            membership=membership,
            owner_evidence={"selected": "src/a.py"},
            evidence_hashes={"ownership": "sha256:" + "2" * 64},
        )
    )

    tampered_member = deepcopy(envelope)
    tampered_member["selection"]["members"].pop()
    validation = validate_verification_selection_envelope(tampered_member)
    assert validation["valid"] is False
    assert "membership-identity-mismatch" in validation["reasons"]
    assert "envelope-identity-mismatch" in validation["reasons"]

    tampered_source = deepcopy(envelope)
    tampered_source["repository"]["source_identity"] = "sha256:" + "9" * 64
    validation = validate_verification_selection_envelope(tampered_source)
    assert validation["valid"] is False
    assert "envelope-identity-mismatch" in validation["reasons"]


def test_downstream_contract_is_compact_and_execution_layout_independent() -> None:
    membership = verification_membership(
        [
            verification_member("tests/test_a.py"),
            verification_member("tests/test_b.py"),
        ]
    )
    envelope = verification_selection_envelope(
        VerificationSelectionEnvelopeState(
            repository_identity="git-tree:abc",
            source_identity="sha256:" + "1" * 64,
            codemap_generation=7,
            identity_generation=3,
            stale=False,
            membership=membership,
            owner_evidence={"selected": "src/a.py"},
            evidence_hashes={"ownership": "sha256:" + "2" * 64},
        )
    )
    contract = downstream_consumption_contract(envelope)

    assert contract["schema"] == "hashmarks.downstream-verification-contract.v2"
    assert contract["repository_identity"] == "git-tree:abc"
    assert contract["source_identity"] == "sha256:" + "1" * 64
    assert contract["hashmarks_identity"] == f"hashmarks:{__version__}"
    assert (
        contract["producer_implementation_identity"]
        == envelope["producer"]["implementation_identity"]
    )
    assert contract["selected_membership_identity"] == membership["membership_identity"]
    assert contract["envelope_identity"] == envelope["envelope_identity"]
    assert contract["contract_identity"].startswith("sha256:")
    assert contract["authority"] == "repository-intelligence-only"
    assert contract["execution_layout"] == "external"


def test_external_batch_layouts_do_not_change_membership_identity() -> None:
    members = [
        verification_member(f"tests/test_{name}.py") for name in ("a", "b", "c", "d")
    ]
    layouts = [
        [members],
        [members[:2], members[2:]],
        [[member] for member in reversed(members)],
    ]

    identities = {
        verification_membership([member for group in layout for member in group])[
            "membership_identity"
        ]
        for layout in layouts
    }
    assert len(identities) == 1


def test_membership_validator_rejects_tampered_member_id_even_when_outer_membership_identity_is_unchanged() -> (
    None
):
    membership = verification_membership(
        [verification_member("tests/test_a.py", test_symbol="test_a")]
    )
    tampered = dict(membership)
    tampered["members"] = [dict(membership["members"][0])]
    tampered["members"][0]["member_id"] = "sha256:" + "f" * 64
    result = validate_verification_membership(tampered)
    assert result["valid"] is False
    assert "member-payload-identity-mismatch" in result["reasons"]


def test_generation_domain_and_identity_types_fail_closed() -> None:
    from hashmarks.generation_domain import MAX_PORTABLE_GENERATION

    membership = verification_membership([verification_member("tests/test_a.py")])

    def state(**changes):
        values = {
            "repository_identity": "git-tree:abc",
            "source_identity": "sha256:" + "1" * 64,
            "codemap_generation": 1,
            "identity_generation": 1,
            "stale": False,
            "membership": membership,
            "owner_evidence": {},
            "evidence_hashes": {},
        }
        values.update(changes)
        return VerificationSelectionEnvelopeState(**values)

    for field, value in (
        ("codemap_generation", True),
        ("codemap_generation", False),
        ("codemap_generation", -1),
        ("codemap_generation", MAX_PORTABLE_GENERATION + 1),
        ("identity_generation", True),
        ("identity_generation", -1),
        ("identity_generation", MAX_PORTABLE_GENERATION + 1),
        ("repository_identity", True),
        ("source_identity", 1.0),
    ):
        try:
            verification_selection_envelope(state(**{field: value}))
        except ValueError:
            pass
        else:
            raise AssertionError(f"producer accepted {field}={value!r}")

    assert (
        verification_selection_envelope(state(codemap_generation=0))["repository"][
            "codemap_generation"
        ]
        == 0
    )
    assert (
        verification_selection_envelope(
            state(codemap_generation=MAX_PORTABLE_GENERATION)
        )["repository"]["codemap_generation"]
        == MAX_PORTABLE_GENERATION
    )
    assert (
        verification_selection_envelope(state(identity_generation=None))["repository"][
            "identity_generation"
        ]
        is None
    )


def test_unknown_freshness_fails_closed_as_stale() -> None:
    membership = verification_membership([verification_member("tests/test_a.py")])
    envelope = verification_selection_envelope(
        VerificationSelectionEnvelopeState(
            repository_identity="git-tree:abc",
            source_identity="sha256:" + "1" * 64,
            codemap_generation=1,
            identity_generation=None,
            stale=None,
            membership=membership,
            owner_evidence={},
            evidence_hashes={},
        )
    )
    assert envelope["repository"]["stale"] is True
    contract = downstream_consumption_contract(envelope)
    from hashmarks.consumer_conformance import validate_native_consumer_bundle

    checked = validate_native_consumer_bundle(envelope, contract, require_fresh=True)
    assert checked["valid"] is False
    assert "fresh-evidence-required" in checked["reasons"]


def test_membership_member_count_rejects_python_numeric_equality_aliases() -> None:
    membership = verification_membership([verification_member("tests/test_a.py")])
    for invalid in (True, 1.0):
        tampered = deepcopy(membership)
        tampered["member_count"] = invalid
        result = validate_verification_membership(tampered)
        assert result["valid"] is False
        assert "member-count-mismatch" in result["reasons"]


def test_envelope_rejects_invalid_membership_before_identity_formation():
    with pytest.raises(ValueError, match="membership is invalid"):
        verification_selection_envelope(
            VerificationSelectionEnvelopeState(
                repository_identity="repo",
                source_identity="source",
                codemap_generation=1,
                identity_generation=1,
                stale=False,
                membership={
                    "schema": "bad",
                    "members": [],
                    "membership_identity": "sha256:x",
                    "member_count": 0,
                },
                owner_evidence={},
                evidence_hashes={},
            )
        )


def test_envelope_rejects_nonportable_owner_evidence_before_identity_formation():
    membership = verification_membership([verification_member("tests/test_x.py")])
    with pytest.raises(ValueError, match="strict JSON-portable"):
        verification_selection_envelope(
            VerificationSelectionEnvelopeState(
                repository_identity="repo",
                source_identity="source",
                codemap_generation=1,
                identity_generation=1,
                stale=False,
                membership=membership,
                owner_evidence={"metric": float("nan")},
                evidence_hashes={},
            )
        )


def test_envelope_rejects_coerced_evidence_hash_before_identity_formation():
    membership = verification_membership([verification_member("tests/test_x.py")])
    with pytest.raises(ValueError, match="evidence hashes"):
        verification_selection_envelope(
            VerificationSelectionEnvelopeState(
                repository_identity="repo",
                source_identity="source",
                codemap_generation=1,
                identity_generation=1,
                stale=False,
                membership=membership,
                owner_evidence={},
                evidence_hashes={"ownership": True},
            )
        )


def test_envelope_validator_rejects_identity_bound_invalid_evidence_hashes() -> None:
    import hashmarks.verification_selection as selection_module

    membership = selection_module.verification_membership([{"path": "tests/test_x.py"}])
    envelope = selection_module.verification_selection_envelope(
        selection_module.VerificationSelectionEnvelopeState(
            repository_identity="repo",
            source_identity="source",
            codemap_generation=0,
            identity_generation=None,
            stale=False,
            membership=membership,
            owner_evidence={},
            evidence_hashes={},
        )
    )
    envelope["evidence_hashes"] = {"ownership": "not-a-sha256"}
    payload = {
        key: value for key, value in envelope.items() if key != "envelope_identity"
    }
    envelope["envelope_identity"] = selection_module._identity(
        selection_module.SELECTION_ENVELOPE_SCHEMA, payload
    )

    state = selection_module.validate_verification_selection_envelope(envelope)
    assert state["valid"] is False
    assert "invalid-evidence-hash" in state["reasons"]


def test_envelope_validator_fails_closed_on_nonportable_owner_evidence() -> None:
    import hashmarks.verification_selection as selection_module

    membership = selection_module.verification_membership([{"path": "tests/test_x.py"}])
    envelope = selection_module.verification_selection_envelope(
        selection_module.VerificationSelectionEnvelopeState(
            repository_identity="repo",
            source_identity="source",
            codemap_generation=0,
            identity_generation=None,
            stale=False,
            membership=membership,
            owner_evidence={},
            evidence_hashes={},
        )
    )
    envelope["owner_evidence"] = {"metric": float("nan")}

    state = selection_module.validate_verification_selection_envelope(envelope)
    assert state["valid"] is False
    assert "invalid-owner-evidence" in state["reasons"]
    assert "nonportable-envelope-payload" in state["reasons"]
