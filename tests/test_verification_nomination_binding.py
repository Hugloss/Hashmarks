"""Live nomination source binding reuses Hashmarks source observation only."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records, assert_text

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_observation import evidence_identity
from hashmarks.operation_contract import operation_schema
from hashmarks.verification_nomination_validation import (
    validate_verification_nomination,
)


def _repo(root: Path, *, with_manifest: bool = True) -> None:
    (root / "tests").mkdir()
    (root / "tests/test_demo.py").write_text(
        "def test_demo(): pass\n", encoding="utf-8"
    )
    if with_manifest:
        (root / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n", encoding="utf-8"
        )


def _assert_external(result: dict[str, object]) -> None:
    assert result["schema"] == operation_schema("verification_nomination_binding")
    assert result["authority"] == "current-source-correspondence-only"
    assert result["producer_authenticity"] == "not-checked"
    assert result["execution_authority"] == "external"
    assert result["result_authority"] == "external"
    assert result["certification_authority"] == "external"
    assert {"argv", "command", "safe", "execution_allowed"}.isdisjoint(result)


def test_live_binding_matches_qualified_source_members(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.verification.nomination("tests/test_demo.py")
        result = codemap.verification.observe_nomination_source_binding(packet)
    assert result["packet_valid"] is True
    assert result["nomination_identity"] == packet["nomination_identity"]
    assert result["source_binding_state"] == "matched"
    assert result["reasons"] == []
    checked_members = assert_records(result["checked_source_members"])
    assert [r["correspondence"] for r in checked_members] == [
        "matched",
        "matched",
    ]
    assert [r["recheck"] for r in checked_members] == [
        "stable",
        "stable",
    ]
    for claimed, checked in zip(
        assert_records(packet["supporting_source_members"]),
        checked_members,
        strict=True,
    ):
        observed = assert_object(checked["observed_member"])
        assert observed["path"] == claimed["path"]
        assert observed["state"] == claimed["state"]
        if claimed["state"] == "known-present":
            assert observed["member_revision"] == claimed["member_revision"]
        assert "reobserved_member" not in checked
    _assert_external(result)


def test_resigned_nomination_source_match_cannot_authenticate_semantic_claims(
    tmp_path: Path,
) -> None:
    """Current byte correspondence and packet integrity are independent of trust."""
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        original = codemap.verification.nomination("tests/test_demo.py")
        forged = deepcopy(original)
        forged["runner_evidence"] = "caller-invented-runner"
        forged["scope"] = "caller-invented-scope"
        forged["nomination_identity"] = evidence_identity(
            assert_text(forged["schema"]),
            {
                key: value
                for key, value in forged.items()
                if key != "nomination_identity"
            },
        )
        transported = validate_verification_nomination(forged)
        correlated = codemap.verification.observe_nomination_source_binding(forged)
    assert forged["nomination_identity"] != original["nomination_identity"]
    assert transported["valid"] is True
    assert transported["authority"] == "content-integrity-only"
    assert transported["repository_binding"] == "not-checked"
    assert transported["producer_authenticity"] == "not-checked"
    assert correlated["packet_valid"] is True
    assert correlated["source_binding_state"] == "matched"
    assert correlated["nomination_identity"] == forged["nomination_identity"]
    _assert_external(correlated)


@pytest.mark.parametrize("path", ["tests/test_demo.py", "pyproject.toml"])
def test_live_binding_detects_source_revision_drift(tmp_path: Path, path: str) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.verification.nomination("tests/test_demo.py")
        (tmp_path / path).write_text("changed\n", encoding="utf-8")
        codemap.index.sync()
        result = codemap.verification.observe_nomination_source_binding(packet)
    assert result["packet_valid"] is True
    assert result["source_binding_state"] == "mismatch"
    assert f"source-mismatch:{path}" in assert_array(result["reasons"])
    row = next(
        item
        for item in assert_records(result["checked_source_members"])
        if item["path"] == path
    )
    assert row["recheck"] == "stable"
    assert row["correspondence"] == "mismatch"
    assert assert_object(row["observed_member"])["state"] == "known-present"
    assert "reobserved_member" not in row
    _assert_external(result)


def test_known_absent_support_must_remain_absent(tmp_path: Path) -> None:
    _repo(tmp_path, with_manifest=False)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.verification.nomination("tests/test_demo.py")
        matched = codemap.verification.observe_nomination_source_binding(packet)
        assert matched["source_binding_state"] == "matched"
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n", encoding="utf-8"
        )
        codemap.index.sync()
        observed = codemap.verification.observe_nomination_source_binding(packet)
    assert observed["source_binding_state"] == "mismatch"
    assert "source-mismatch:pyproject.toml" in assert_array(observed["reasons"])


def test_denied_source_cannot_be_claimed_as_absent(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.verification.nomination("tests/test_demo.py")
        (tmp_path / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "pyproject.toml"\nindex = false\n',
            encoding="utf-8",
        )
        codemap.files.refresh_policy()
        codemap.index.sync()
        observed = codemap.verification.observe_nomination_source_binding(packet)
    assert observed["packet_valid"] is True
    assert observed["source_binding_state"] == "unknown"
    assert "source-unknown:pyproject.toml" in assert_array(observed["reasons"])
    row = assert_records(observed["checked_source_members"])[1]
    assert assert_object(row["observed_member"])["state"] == "unsupported"
    assert row["recheck"] == "stable"


def test_structurally_invalid_packet_does_not_read_any_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.verification.nomination("tests/test_demo.py")
        invalid = deepcopy(packet)
        invalid["argv"] = ["python", "-m", "pytest"]

        def forbidden(_path: str) -> dict[str, object]:
            raise AssertionError("invalid packet attempted a source observation")

        monkeypatch.setattr(
            codemap.verification, "_observe_nomination_source_member", forbidden
        )
        result = codemap.verification.observe_nomination_source_binding(invalid)
    assert result["source_binding_state"] == "invalid-packet"
    assert result["packet_valid"] is False
    assert result["checked_source_members"] == []
    _assert_external(result)


def test_unavailable_nomination_is_not_a_current_absence_claim(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.verification.nomination("tests/test_missing.py")
        result = codemap.verification.observe_nomination_source_binding(packet)
    assert packet["available"] is False
    assert result["packet_valid"] is True
    assert result["source_binding_state"] == "not-applicable"
    assert result["checked_source_members"] == []
    _assert_external(result)


def test_intervening_source_change_yields_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.verification.nomination("tests/test_demo.py")
        native = codemap.verification._observe_nomination_source_member
        counts: dict[str, int] = {}

        def changed(path: str) -> dict[str, object]:
            counts[path] = counts.get(path, 0) + 1
            original = native(path)
            if path == "tests/test_demo.py" and counts[path] == 2:
                return {**original, "state": "unknown"}
            return original

        monkeypatch.setattr(
            codemap.verification, "_observe_nomination_source_member", changed
        )
        result = codemap.verification.observe_nomination_source_binding(packet)
    assert result["source_binding_state"] == "unknown"
    assert "source-changed-during-observation:tests/test_demo.py" in assert_array(
        result["reasons"]
    )
    row = assert_records(result["checked_source_members"])[0]
    assert row["correspondence"] == "unknown"
    assert row["recheck"] == "changed"
    assert assert_object(row["observed_member"])["state"] == "known-present"
    assert assert_object(row["reobserved_member"])["state"] == "unknown"
    assert "source-unknown:tests/test_demo.py" not in assert_array(result["reasons"])
    _assert_external(result)


def test_intervening_change_overrides_stale_initial_mismatch_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When evidence changes during replay, the final reason is unknown."""
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.verification.nomination("tests/test_demo.py")
        (tmp_path / "tests/test_demo.py").write_text(
            "def test_demo(): assert True\n", encoding="utf-8"
        )
        codemap.index.sync()
        original = codemap.verification._observe_nomination_source_member
        calls: dict[str, int] = {}

        def second_read_unknown(path: str) -> dict[str, object]:
            calls[path] = calls.get(path, 0) + 1
            observed = original(path)
            if path == "tests/test_demo.py" and calls[path] == 2:
                return {**observed, "state": "unknown"}
            return observed

        monkeypatch.setattr(
            codemap.verification,
            "_observe_nomination_source_member",
            second_read_unknown,
        )
        result = codemap.verification.observe_nomination_source_binding(packet)

    row = assert_records(result["checked_source_members"])[0]
    assert assert_object(row["observed_member"])["state"] == "known-present"
    assert assert_object(row["reobserved_member"])["state"] == "unknown"
    assert row["recheck"] == "changed"
    assert row["correspondence"] == "unknown"
    assert result["source_binding_state"] == "unknown"
    reasons = assert_array(result["reasons"])
    assert "source-changed-during-observation:tests/test_demo.py" in reasons
    assert "source-mismatch:tests/test_demo.py" not in reasons
    _assert_external(result)
