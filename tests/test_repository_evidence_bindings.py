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


def test_span_identity_preserves_newline_bytes(tmp_path: Path) -> None:
    source = tmp_path / "a.py"
    source.write_bytes(b"one\r\ntwo\r\n")
    binding = [{"binding_id": "newline", "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        crlf = codemap.repository_evidence_bindings(binding)
        source.write_bytes(b"one\ntwo\r\n")
        codemap.sync(["a.py"])
        lf = codemap.repository_evidence_bindings(binding)
    assert crlf["bindings"][0]["evidence"][0]["span_identity"] != lf["bindings"][0]["evidence"][0]["span_identity"]


def test_binding_rejects_symlinked_ancestor_evidence(tmp_path: Path) -> None:
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (outside / "secret.py").write_text("secret\n", encoding="utf-8")
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            [{"binding_id": "escape", "evidence": [{"path": "linked/secret.py", "start_line": 1, "end_line": 1}]}]
        )
    row = packet["bindings"][0]["evidence"][0]
    assert row["state"] == "unsupported"
    assert row["reason"] == "symlink-evidence-not-observed"


def test_binding_observation_is_decision_session_scoped(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with codemap.decision_session():
            packet = codemap.repository_evidence_bindings(
                [{"binding_id": "stable", "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}]}]
            )
            assert packet["repository"]["codemap_generation"] == codemap.store.generation()


def test_dependency_change_is_separate_from_unchanged_direct_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    dependency = tmp_path / "dependency.py"
    source.write_text("stable\n", encoding="utf-8")
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    bindings = [{"binding_id": "generic:binding", "evidence": [{"path": "source.py", "start_line": 1, "end_line": 1}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic:binding": ["dependency.py"]}
        )
        dependency.write_text("VALUE = 2\n", encoding="utf-8")
        codemap.sync(["dependency.py"])
        after = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic:binding": ["dependency.py"]}
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    changed = delta["bindings"]["changed"][0]
    assert changed["direct_evidence"]["state"] == "preserved"
    assert changed["semantic_dependencies"]["state"] == "affected"
    assert changed["semantic_dependencies"]["changes"][0]["path"] == "dependency.py"


def test_unrelated_change_does_not_affect_declared_dependency(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("stable\n", encoding="utf-8")
    (tmp_path / "dependency.py").write_text("VALUE = 1\n", encoding="utf-8")
    unrelated = tmp_path / "other.py"
    unrelated.write_text("OTHER = 1\n", encoding="utf-8")
    bindings = [{"binding_id": "generic:binding", "evidence": [{"path": "source.py", "start_line": 1, "end_line": 1}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic:binding": ["dependency.py"]}
        )
        unrelated.write_text("OTHER = 2\n", encoding="utf-8")
        codemap.sync(["other.py"])
        after = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic:binding": ["dependency.py"]}
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    assert delta["bindings"]["preserved"] == ["generic:binding"]
    assert delta["bindings"]["changed"] == []


def test_indexed_relationship_evidence_is_bounded_and_non_authoritative(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    dependency = tmp_path / "dependency.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    source.write_text("from dependency import VALUE\nresult = VALUE\n", encoding="utf-8")
    binding = [{"binding_id": "graph", "evidence": [{"path": "source.py", "start_line": 1, "end_line": 2}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, relationship_limit_per_path=8
        )
    relationships = packet["bindings"][0]["relationships"]
    assert relationships["state"] == "observed"
    assert relationships["completeness"] == "bounded-not-claimed"
    assert relationships["bounds"]["limit_per_path"] == 8
    assert any(row.get("target") for row in relationships["relationships"])


def test_relationship_change_does_not_masquerade_as_direct_content_change(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("from alpha import VALUE\nKEEP = 1\n", encoding="utf-8")
    (tmp_path / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "beta.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [{"binding_id": "graph", "evidence": [{"path": "source.py", "start_line": 2, "end_line": 2}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("from beta import VALUE\nKEEP = 1\n", encoding="utf-8")
        codemap.sync(["source.py"])
        after = codemap.repository_evidence_bindings(binding)
        delta = codemap.repository_evidence_binding_delta(before, after)
    changed = delta["bindings"]["changed"][0]
    assert changed["direct_evidence"]["state"] == "preserved"
    assert changed["relationship_evidence"]["state"] == "changed"
    assert changed["relationship_evidence"]["completeness"] == "bounded-not-claimed"


def test_complete_change_set_can_prove_outside_declared_bindings(tmp_path: Path) -> None:
    (tmp_path / "bound.py").write_text("bound\n", encoding="utf-8")
    (tmp_path / "dependency.py").write_text("dep\n", encoding="utf-8")
    (tmp_path / "outside.py").write_text("outside\n", encoding="utf-8")
    bindings = [{"binding_id": "generic", "evidence": [{"path": "bound.py", "start_line": 1, "end_line": 1}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic": ["dependency.py"]}
        )
        coverage = codemap.repository_evidence_coverage(
            packet,
            changed_paths=["bound.py", "dependency.py", "outside.py"],
            change_set_complete=True,
        )
    assert coverage["classification"]["bound_member_precision_unknown"] == ["bound.py"]
    assert coverage["classification"]["dependency_affected"] == ["dependency.py"]
    assert coverage["classification"]["outside_declared_bindings"] == ["outside.py"]
    assert coverage["coverage"]["state"] == "complete"
    assert coverage["coverage"]["outside_classification"] == "known"


def test_incomplete_change_set_never_claims_unmapped_change(tmp_path: Path) -> None:
    (tmp_path / "bound.py").write_text("bound\n", encoding="utf-8")
    (tmp_path / "seen.py").write_text("seen\n", encoding="utf-8")
    bindings = [{"binding_id": "generic", "evidence": [{"path": "bound.py", "start_line": 1, "end_line": 1}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(bindings)
        coverage = codemap.repository_evidence_coverage(
            packet, changed_paths=["seen.py"], change_set_complete=False
        )
    assert coverage["classification"]["outside_declared_bindings"] == []
    assert coverage["classification"]["outside_declared_bindings_candidates"] == ["seen.py"]
    assert coverage["coverage"]["state"] == "incomplete"
    assert coverage["coverage"]["outside_classification"] == "unknown"


def test_coverage_is_order_independent_and_identity_stable(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b\n", encoding="utf-8")
    bindings = [{"binding_id": "generic", "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(bindings)
        first = codemap.repository_evidence_coverage(
            packet, changed_paths=["b.py", "a.py"], change_set_complete=True
        )
        second = codemap.repository_evidence_coverage(
            packet, changed_paths=["a.py", "b.py"], change_set_complete=True
        )
    assert first == second


def test_coverage_distinguishes_bound_range_from_elsewhere_in_member(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("outside\nbound\n", encoding="utf-8")
    bindings = [{"binding_id": "range", "evidence": [{"path": "source.py", "start_line": 2, "end_line": 2}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(bindings)
        source.write_text("OUTSIDE\nbound\n", encoding="utf-8")
        codemap.sync(["source.py"])
        after = codemap.repository_evidence_bindings(bindings)
        delta = codemap.repository_evidence_binding_delta(before, after)
        outside_range = codemap.repository_evidence_coverage(
            after,
            changed_paths=["source.py"],
            change_set_complete=True,
            binding_delta=delta,
        )
        source.write_text("OUTSIDE\nBOUND\n", encoding="utf-8")
        codemap.sync(["source.py"])
        latest = codemap.repository_evidence_bindings(bindings)
        direct_delta = codemap.repository_evidence_binding_delta(after, latest)
        inside_range = codemap.repository_evidence_coverage(
            latest,
            changed_paths=["source.py"],
            change_set_complete=True,
            binding_delta=direct_delta,
        )

    assert outside_range["classification"]["changed_inside_bound_evidence"] == []
    assert outside_range["classification"]["changed_elsewhere_in_bound_member"] == ["source.py"]
    assert outside_range["classification"]["bound_member_precision_unknown"] == []
    assert inside_range["classification"]["changed_inside_bound_evidence"] == ["source.py"]
    assert inside_range["classification"]["changed_elsewhere_in_bound_member"] == []
    assert inside_range["precision"]["bound_range"] == "known"


def test_path_only_coverage_refuses_to_infer_range_impact(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("a\nb\n", encoding="utf-8")
    bindings = [{"binding_id": "range", "evidence": [{"path": "source.py", "start_line": 2, "end_line": 2}]}]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(bindings)
        coverage = codemap.repository_evidence_coverage(
            packet, changed_paths=["source.py"], change_set_complete=True
        )
    assert coverage["classification"]["changed_inside_bound_evidence"] == []
    assert coverage["classification"]["changed_elsewhere_in_bound_member"] == []
    assert coverage["classification"]["bound_member_precision_unknown"] == ["source.py"]
    assert coverage["precision"]["bound_range"] == "unknown"
