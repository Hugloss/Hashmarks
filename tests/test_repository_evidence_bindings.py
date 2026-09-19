from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def test_repository_evidence_bindings_are_generic_deterministic_repository_facts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src.py"
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "consumer:a",
            "evidence": [{"path": "src.py", "start_line": 2, "end_line": 2}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.repository_evidence_bindings(bindings)
        second = codemap.repository_evidence_bindings(bindings)

    assert first == second
    assert first["schema"] == "hashmarks.repository-evidence-bindings.v1"
    assert first["authority"] == "repository-intelligence-only"
    assert first["execution_effect"] == "none"
    row = first["bindings"][0]
    assert row["binding_id"] == "consumer:a"
    assert row["evidence"][0]["state"] == "known-present"
    assert row["evidence"][0]["span_identity"].startswith("sha256:")
    assert row["evidence"][0]["member_identity"].startswith("sha256:")


def test_span_identity_survives_unrelated_member_edit_while_member_identity_changes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src.py"
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "external-tool:fact",
            "evidence": [{"path": "src.py", "start_line": 2, "end_line": 2}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("ONE\ntwo\nthree\n", encoding="utf-8")
        codemap.sync(["src.py"])
        after = codemap.repository_evidence_bindings(binding)

    old = before["bindings"][0]["evidence"][0]
    new = after["bindings"][0]["evidence"][0]
    assert old["span_identity"] == new["span_identity"]
    assert old["member_identity"] != new["member_identity"]


def test_binding_reports_deleted_and_unsupported_members_without_policy_decision(
    tmp_path: Path,
) -> None:
    missing = [{"binding_id": "x", "evidence": [{"path": "gone.py", "start_line": 1, "end_line": 1}]}]
    binary = tmp_path / "binary.dat"
    binary.write_bytes(b"\xff\xfe")
    unsupported = [{"binding_id": "y", "evidence": [{"path": "binary.dat", "start_line": 1, "end_line": 1}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        absent = codemap.repository_evidence_bindings(missing)
        nontext = codemap.repository_evidence_bindings(unsupported)
    assert absent["bindings"][0]["evidence"][0]["state"] == "known-absent"
    assert nontext["bindings"][0]["evidence"][0]["state"] == "unsupported"


def test_binding_rejects_duplicate_identity_and_invalid_range(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="duplicate binding_id"):
            codemap.repository_evidence_bindings(
                [
                    {"binding_id": "same", "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}]},
                    {"binding_id": "same", "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}]},
                ]
            )
        with pytest.raises(ValueError, match="1 <= start_line"):
            codemap.repository_evidence_bindings(
                [{"binding_id": "bad", "evidence": [{"path": "a.py", "start_line": 0, "end_line": 1}]}]
            )


def test_binding_vocabulary_does_not_encode_consumer_execution_policy(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            [{"binding_id": "opaque", "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}]}]
        )
    rendered = repr(packet).lower()
    for forbidden in ("recertif", "capability suspension", "admission", "goon"):
        assert forbidden not in rendered
