from copy import deepcopy
from pathlib import Path

from hashmarks import __version__
from hashmarks.producer_identity import native_producer_implementation_identity
from hashmarks.verification_selection import (
    VerificationSelectionEnvelopeState,
    downstream_consumption_contract,
    validate_downstream_consumption_contract,
    validate_verification_selection_envelope,
    verification_member,
    verification_membership,
    verification_selection_envelope,
)


def _envelope(identity: str) -> dict[str, object]:
    membership = verification_membership([verification_member("tests/test_a.py")])
    return verification_selection_envelope(
        VerificationSelectionEnvelopeState(
            repository_identity="git-tree:same",
            source_identity="sha256:" + "1" * 64,
            codemap_generation=1,
            identity_generation=1,
            stale=False,
            membership=membership,
            owner_evidence={"selected": "src/a.py"},
            evidence_hashes={"ownership": "sha256:" + "2" * 64},
            producer_implementation_identity=identity,
        )
    )


def test_same_version_different_implementation_bytes_cannot_cross_pair() -> None:
    a_id = "sha256:" + "a" * 64
    b_id = "sha256:" + "b" * 64
    a = _envelope(a_id)
    b = _envelope(b_id)
    a_contract = downstream_consumption_contract(a)
    b_contract = downstream_consumption_contract(b)

    assert a["producer"]["version"] == b["producer"]["version"] == __version__
    assert validate_downstream_consumption_contract(a, a_contract)["valid"] is True
    assert validate_downstream_consumption_contract(b, b_contract)["valid"] is True
    assert validate_downstream_consumption_contract(a, b_contract)["valid"] is False
    assert validate_downstream_consumption_contract(b, a_contract)["valid"] is False


def test_missing_or_tampered_implementation_identity_fails_closed() -> None:
    envelope = _envelope("sha256:" + "a" * 64)

    missing = deepcopy(envelope)
    del missing["producer"]["implementation_identity"]
    result = validate_verification_selection_envelope(missing)
    assert result["valid"] is False
    assert "missing-or-invalid-producer-implementation-identity" in result["reasons"]

    tampered = deepcopy(envelope)
    tampered["producer"]["implementation_identity"] = "sha256:" + "b" * 64
    result = validate_verification_selection_envelope(tampered)
    assert result["valid"] is False
    assert "envelope-identity-mismatch" in result["reasons"]


def test_evidence_claiming_other_same_version_producer_identity_fails() -> None:
    a = _envelope("sha256:" + "a" * 64)
    b = _envelope("sha256:" + "b" * 64)
    claimed = deepcopy(a)
    claimed["producer"]["implementation_identity"] = b["producer"][
        "implementation_identity"
    ]
    assert validate_verification_selection_envelope(claimed)["valid"] is False


def test_same_version_different_package_bytes_produce_different_native_identities(
    tmp_path: Path,
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "_version.py").write_text(f'__version__ = "{__version__}"\n')
    (b / "_version.py").write_text(f'__version__ = "{__version__}"\n')
    (a / "engine.py").write_text("VALUE = 1\n")
    (b / "engine.py").write_text("VALUE = 2\n")
    assert native_producer_implementation_identity(
        a
    ) != native_producer_implementation_identity(b)


def test_native_producer_identity_is_stable_across_repeated_calls() -> None:
    first = native_producer_implementation_identity()
    second = native_producer_implementation_identity()
    assert first == second
