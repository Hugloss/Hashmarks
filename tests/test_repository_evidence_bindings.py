from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap
from hashmarks.client import RepositoryObservation
from hashmarks.observation import ObservationState

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
    assert first["observer"]["identity"].startswith("sha256:")
    assert "evidence-bindings" in first["observer"]["capabilities"]
    assert first["repository"]["source_identity"].startswith("sha256:")
    row = first["bindings"][0]
    assert row["binding_id"] == "consumer:a"
    assert row["evidence"][0]["state"] == "known-present"
    assert row["evidence"][0]["span_identity"].startswith("sha256:")
    assert len(row["evidence"][0]["member_revision"]) == 64


def test_span_identity_survives_unrelated_member_edit_while_member_revision_changes(
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
    assert old["member_revision"] != new["member_revision"]


def test_binding_reports_deleted_and_unsupported_members_without_policy_decision(
    tmp_path: Path,
) -> None:
    missing = [
        {
            "binding_id": "x",
            "evidence": [{"path": "gone.py", "start_line": 1, "end_line": 1}],
        }
    ]
    binary = tmp_path / "binary.dat"
    binary.write_bytes(b"\xff\xfe")
    unsupported = [
        {
            "binding_id": "y",
            "evidence": [{"path": "binary.dat", "start_line": 1, "end_line": 1}],
        }
    ]
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
                    {
                        "binding_id": "same",
                        "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
                    },
                    {
                        "binding_id": "same",
                        "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
                    },
                ]
            )
        with pytest.raises(ValueError, match="1 <= start_line"):
            codemap.repository_evidence_bindings(
                [
                    {
                        "binding_id": "bad",
                        "evidence": [{"path": "a.py", "start_line": 0, "end_line": 1}],
                    }
                ]
            )


def test_binding_vocabulary_does_not_encode_consumer_execution_policy(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            [
                {
                    "binding_id": "opaque",
                    "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
                }
            ]
        )
    rendered = repr(packet).lower()
    for forbidden in ("recertif", "capability suspension", "admission", "goon"):
        assert forbidden not in rendered


def test_span_identity_preserves_newline_bytes(tmp_path: Path) -> None:
    source = tmp_path / "a.py"
    source.write_bytes(b"one\r\ntwo\r\n")
    binding = [
        {
            "binding_id": "newline",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        crlf = codemap.repository_evidence_bindings(binding)
        source.write_bytes(b"one\ntwo\r\n")
        codemap.sync(["a.py"])
        lf = codemap.repository_evidence_bindings(binding)
    assert (
        crlf["bindings"][0]["evidence"][0]["span_identity"]
        != lf["bindings"][0]["evidence"][0]["span_identity"]
    )


def test_binding_rejects_symlinked_ancestor_evidence(tmp_path: Path) -> None:
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (outside / "secret.py").write_text("secret\n", encoding="utf-8")
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            [
                {
                    "binding_id": "escape",
                    "evidence": [
                        {"path": "linked/secret.py", "start_line": 1, "end_line": 1}
                    ],
                }
            ]
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
                [
                    {
                        "binding_id": "stable",
                        "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
                    }
                ]
            )
            assert (
                packet["repository"]["codemap_generation"] == codemap.store.generation()
            )


def test_dependency_change_is_separate_from_unchanged_direct_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    dependency = tmp_path / "dependency.py"
    source.write_text("stable\n", encoding="utf-8")
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "generic:binding",
            "evidence": [{"path": "source.py", "start_line": 1, "end_line": 1}],
        }
    ]
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
    assert changed["declared_dependencies"]["state"] == "affected"
    observations = changed["declared_dependencies"]["observations"]
    assert observations["state"] == "changed"
    assert observations["changes"][0]["path"] == "dependency.py"


def test_unrelated_change_does_not_affect_declared_dependency(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("stable\n", encoding="utf-8")
    (tmp_path / "dependency.py").write_text("VALUE = 1\n", encoding="utf-8")
    unrelated = tmp_path / "other.py"
    unrelated.write_text("OTHER = 1\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "generic:binding",
            "evidence": [{"path": "source.py", "start_line": 1, "end_line": 1}],
        }
    ]
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


def test_indexed_relationship_evidence_is_bounded_and_non_authoritative(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    dependency = tmp_path / "dependency.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    source.write_text(
        "from dependency import VALUE\nresult = VALUE\n", encoding="utf-8"
    )
    binding = [
        {
            "binding_id": "graph",
            "evidence": [{"path": "source.py", "start_line": 1, "end_line": 2}],
        }
    ]
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


def test_relationship_change_does_not_masquerade_as_direct_content_change(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("from alpha import VALUE\nKEEP = 1\n", encoding="utf-8")
    (tmp_path / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "beta.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "graph",
            "evidence": [{"path": "source.py", "start_line": 2, "end_line": 2}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("from beta import VALUE\nKEEP = 1\n", encoding="utf-8")
        codemap.sync(["source.py"])
        after = codemap.repository_evidence_bindings(binding)
        delta = codemap.repository_evidence_binding_delta(before, after)
    changed = delta["bindings"]["changed"][0]
    assert changed["direct_evidence"]["state"] == "preserved"
    relationships = changed["relationship_evidence"]
    assert relationships["state"] == "changed"
    assert relationships["comparability"] == "comparable"
    assert relationships["facts"]["state"] == "changed"
    assert relationships["completeness"] == "bounded-not-claimed"


def test_complete_change_set_can_prove_outside_declared_bindings(
    tmp_path: Path,
) -> None:
    (tmp_path / "bound.py").write_text("bound\n", encoding="utf-8")
    (tmp_path / "dependency.py").write_text("dep\n", encoding="utf-8")
    (tmp_path / "outside.py").write_text("outside\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "generic",
            "evidence": [{"path": "bound.py", "start_line": 1, "end_line": 1}],
        }
    ]
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
    assert coverage["classification"]["declared_dependencies_changed"] == [
        "dependency.py"
    ]
    assert coverage["classification"]["outside_declared_bindings"] == ["outside.py"]
    assert coverage["coverage"]["state"] == "complete"
    assert coverage["coverage"]["outside_classification"] == "known"


def test_incomplete_change_set_never_claims_unmapped_change(tmp_path: Path) -> None:
    (tmp_path / "bound.py").write_text("bound\n", encoding="utf-8")
    (tmp_path / "seen.py").write_text("seen\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "generic",
            "evidence": [{"path": "bound.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(bindings)
        coverage = codemap.repository_evidence_coverage(
            packet, changed_paths=["seen.py"], change_set_complete=False
        )
    assert coverage["classification"]["outside_declared_bindings"] == []
    assert coverage["classification"]["outside_declared_bindings_candidates"] == [
        "seen.py"
    ]
    assert coverage["coverage"]["state"] == "incomplete"
    assert coverage["coverage"]["outside_classification"] == "unknown"


def test_coverage_is_order_independent_and_identity_stable(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "generic",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        }
    ]
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


def test_coverage_distinguishes_bound_range_from_elsewhere_in_member(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("outside\nbound\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "range",
            "evidence": [{"path": "source.py", "start_line": 2, "end_line": 2}],
        }
    ]
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
    assert outside_range["classification"]["changed_elsewhere_in_bound_member"] == [
        "source.py"
    ]
    assert outside_range["classification"]["bound_member_precision_unknown"] == []
    assert inside_range["classification"]["changed_inside_bound_evidence"] == [
        "source.py"
    ]
    assert inside_range["classification"]["changed_elsewhere_in_bound_member"] == []
    assert inside_range["precision"]["bound_range"] == "known"


def test_path_only_coverage_refuses_to_infer_range_impact(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("a\nb\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "range",
            "evidence": [{"path": "source.py", "start_line": 2, "end_line": 2}],
        }
    ]
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


def test_relationship_projection_can_be_skipped_without_changing_evidence_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "cheap",
            "evidence": [{"path": "source.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    row = packet["bindings"][0]
    assert row["evidence"][0]["state"] == "known-present"
    assert row["relationships"]["state"] == "not-requested"
    assert row["relationships"]["completeness"] == "not-observed"


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ([{"binding_id": "", "evidence": []}], "binding_id must not be empty"),
        ([{"binding_id": "x", "evidence": "a.py"}], "evidence must be a sequence"),
        (
            [{"binding_id": "x", "evidence": [42]}],
            "each evidence item must be an object",
        ),
        (
            [
                {
                    "binding_id": "x",
                    "evidence": [
                        {"path": "../escape.py", "start_line": 1, "end_line": 1}
                    ],
                }
            ],
            "path",
        ),
    ],
)
def test_binding_contract_rejects_malformed_or_escaping_inputs(
    tmp_path: Path, payload: object, match: str
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises((TypeError, ValueError), match=match):
            codemap.repository_evidence_bindings(payload)  # type: ignore[arg-type]


def test_overlapping_and_duplicate_spans_remain_explicit_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("a\nb\nc\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "multi",
            "evidence": [
                {"path": "a.py", "start_line": 1, "end_line": 2},
                {"path": "a.py", "start_line": 2, "end_line": 3},
                {"path": "a.py", "start_line": 1, "end_line": 2},
            ],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = packet["bindings"][0]["evidence"]
    assert len(evidence) == 3
    identities = [str(row["span_identity"]) for row in evidence]
    assert len(set(identities)) == 2
    assert sorted(identities.count(identity) for identity in set(identities)) == [1, 2]


def test_deleted_bound_member_is_first_class_delta(tmp_path: Path) -> None:
    source = tmp_path / "a.py"
    source.write_text("a\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "deleted",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        source.unlink()
        codemap.sync(["a.py"])
        after = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["a.py"],
            change_set_complete=True,
            binding_delta=delta,
        )
    changed = delta["bindings"]["changed"][0]
    assert changed["direct_evidence"]["state"] == "preserved"
    assert changed["locator_evidence"]["state"] == "changed"
    member_change = changed["member_evidence"]["changes"][0]
    assert member_change["state"] == "removed"
    assert member_change["observation_state_changed"] is True
    assert after["bindings"][0]["evidence"][0]["state"] == "known-absent"
    assert coverage["classification"]["bound_members_removed"] == ["a.py"]
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "deleted",
            "reasons": ["bound-locator-changed", "bound-member-removed"],
        }
    ]


def test_exact_span_uses_physical_lf_lines_not_unicode_line_separators(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unicode.py"
    first_line = "alpha\u2028beta\n".encode()
    source.write_bytes(first_line + b"gamma\n")
    binding = [
        {
            "binding_id": "physical-lines",
            "evidence": [{"path": "unicode.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = packet["bindings"][0]["evidence"][0]
    assert evidence["state"] == "known-present"
    assert evidence["byte_length"] == len(first_line)


def test_exact_span_preserves_utf8_bom_as_repository_bytes(tmp_path: Path) -> None:
    source = tmp_path / "bom.py"
    source.write_bytes(b"\xef\xbb\xbfvalue = 1\n")
    binding = [
        {
            "binding_id": "bom",
            "evidence": [{"path": "bom.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    assert packet["bindings"][0]["evidence"][0]["byte_length"] == len(
        b"\xef\xbb\xbfvalue = 1\n"
    )


def test_binding_obeys_context_policy_source_disclosure(tmp_path: Path) -> None:
    hidden = tmp_path / "hidden.py"
    hidden.write_text("SECRET_VALUE = 'do-not-disclose'\n", encoding="utf-8")
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "hidden.py"\nvisibility = "deny"\n',
        encoding="utf-8",
    )
    binding = [
        {
            "binding_id": "hidden",
            "evidence": [{"path": "hidden.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = packet["bindings"][0]["evidence"][0]
    assert evidence["state"] == "unsupported"
    assert evidence["reason"] == "repository-evidence-denied"
    assert "do-not-disclose" not in repr(packet)


def test_outline_visibility_does_not_become_raw_source_binding(tmp_path: Path) -> None:
    source = tmp_path / "outline.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "outline.py"\nvisibility = "outline"\n',
        encoding="utf-8",
    )
    binding = [
        {
            "binding_id": "outline",
            "evidence": [{"path": "outline.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = packet["bindings"][0]["evidence"][0]
    assert evidence["state"] == "unsupported"
    assert evidence["reason"] == "source-evidence-not-visible"
    assert "span_identity" not in evidence


def test_unsignaled_member_edit_fails_closed_against_indexed_revision(
    tmp_path: Path,
) -> None:
    source = tmp_path / "owner.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "stable-read",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        source.write_text("VALUE = 2\n", encoding="utf-8")
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = packet["bindings"][0]["evidence"][0]
    assert evidence["state"] == "unknown"
    assert evidence["reason"] == "member-revision-mismatch"
    assert "span_identity" not in evidence


def test_binding_definition_change_is_not_relationship_content_change(
    tmp_path: Path,
) -> None:
    source = tmp_path / "owner.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "definition",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            binding, relationship_limit_per_path=8
        )
        after = codemap.repository_evidence_bindings(
            binding, relationship_limit_per_path=16
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    before_row = before["bindings"][0]
    after_row = after["bindings"][0]
    assert (
        before_row["binding_definition_identity"]
        != after_row["binding_definition_identity"]
    )
    changed = delta["bindings"]["changed"][0]
    assert changed["definition"]["state"] == "changed"
    relationships = changed["relationship_evidence"]
    assert relationships["state"] == "unknown"
    assert relationships["comparability"] == "observation-configuration-changed"
    assert relationships["facts"]["state"] == "unknown"
    assert relationships["locators"]["state"] == "unknown"
    assert relationships["observation"]["changed"] is True


def test_observer_proven_change_set_keeps_completeness_provenance(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "observer",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(binding)
        observation = RepositoryObservation(
            state=ObservationState.DIRTY,
            generation=7,
            dirty_paths=("owner.py",),
            paths_complete=True,
            dirty_path_count=1,
        )
        coverage = codemap.repository_evidence_coverage(
            packet,
            repository_observation=observation,
        )
    assert coverage["changed_paths"] == ["owner.py"]
    assert coverage["coverage"]["state"] == "complete"
    assert coverage["coverage"]["source"] == "repository-observer"
    assert coverage["change_set"]["generation"] == 7


def test_coverage_reports_binding_ids_and_stable_impact_reasons(tmp_path: Path) -> None:
    source = tmp_path / "owner.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "consumer:owner",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("VALUE = 2\n", encoding="utf-8")
        codemap.sync(["owner.py"])
        after = codemap.repository_evidence_bindings(binding)
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["owner.py"],
            change_set_complete=True,
            binding_delta=delta,
        )
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "consumer:owner",
            "reasons": [
                "bound-member-changed",
                "bound-range-content-changed",
            ],
        }
    ]


def test_whole_member_binding_supports_empty_and_binary_repository_members(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty.lock"
    binary = tmp_path / "payload.bin"
    empty.write_bytes(b"")
    binary.write_bytes(b"\xff\x00\xfe")
    binding = [
        {
            "binding_id": "whole-members",
            "evidence": [
                {"scope": "member", "path": "empty.lock"},
                {"scope": "member", "path": "payload.bin"},
            ],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )

    evidence = packet["bindings"][0]["evidence"]
    assert [row["scope"] for row in evidence] == ["member", "member"]
    assert all(row["state"] == "known-present" for row in evidence)
    assert all(len(str(row["member_revision"])) == 64 for row in evidence)
    assert all(row["index_state"] == "unindexed" for row in evidence)


def test_whole_member_change_is_direct_content_and_member_change(
    tmp_path: Path,
) -> None:
    member = tmp_path / "artifact.lock"
    member.write_bytes(b"one")
    binding = [
        {
            "binding_id": "whole",
            "evidence": [{"scope": "member", "path": "artifact.lock"}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        member.write_bytes(b"two")
        after = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["artifact.lock"],
            change_set_complete=True,
            binding_delta=delta,
        )

    changed = delta["bindings"]["changed"][0]
    assert changed["direct_evidence"]["state"] == "changed"
    assert changed["direct_evidence"]["changes"][0]["scope"] == "member"
    assert changed["member_evidence"]["state"] == "changed"
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "whole",
            "reasons": [
                "bound-member-changed",
                "bound-member-content-changed",
            ],
        }
    ]


def test_member_scope_rejects_line_bounds(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="must not declare line bounds"):
            codemap.repository_evidence_bindings(
                [
                    {
                        "binding_id": "bad-member",
                        "evidence": [
                            {
                                "scope": "member",
                                "path": "a.txt",
                                "start_line": 1,
                                "end_line": 1,
                            }
                        ],
                    }
                ]
            )


def test_binding_identity_is_order_independent_but_duplicates_remain_explicit(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("a\nb\n", encoding="utf-8")
    (tmp_path / "dep.py").write_text("dep\n", encoding="utf-8")
    left = [
        {
            "binding_id": "canonical",
            "evidence": [
                {"path": "a.py", "start_line": 2, "end_line": 2},
                {"path": "a.py", "start_line": 1, "end_line": 1},
                {"path": "a.py", "start_line": 1, "end_line": 1},
            ],
        }
    ]
    right = [
        {
            "binding_id": "canonical",
            "evidence": [
                {"path": "a.py", "start_line": 1, "end_line": 1},
                {"path": "a.py", "start_line": 1, "end_line": 1},
                {"path": "a.py", "start_line": 2, "end_line": 2},
            ],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.repository_evidence_bindings(
            left,
            dependency_paths={"canonical": ["dep.py"]},
            include_relationships=False,
        )
        second = codemap.repository_evidence_bindings(
            right,
            dependency_paths={"canonical": ["dep.py"]},
            include_relationships=False,
        )
    assert first == second
    assert len(first["bindings"][0]["evidence"]) == 3


def test_binding_contract_rejects_unknown_dependency_owner_and_unbounded_requests(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="unknown binding ids"):
            codemap.repository_evidence_bindings(
                [{"binding_id": "known", "evidence": []}],
                dependency_paths={"unknown": ["a.py"]},
            )
        with pytest.raises(ValueError, match="between 1 and"):
            codemap.repository_evidence_bindings(
                [{"binding_id": "known", "evidence": []}],
                relationship_limit_per_path=1001,
            )
        with pytest.raises(ValueError, match="bindings exceeds"):
            codemap.repository_evidence_bindings(
                [{"binding_id": f"b:{index}", "evidence": []} for index in range(257)]
            )


def test_binding_delta_preserves_duplicate_evidence_multiplicity(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    before_definition = [
        {
            "binding_id": "duplicates",
            "evidence": [
                {"path": "a.py", "start_line": 1, "end_line": 1},
                {"path": "a.py", "start_line": 1, "end_line": 1},
            ],
        }
    ]
    after_definition = [
        {
            "binding_id": "duplicates",
            "evidence": [
                {"path": "a.py", "start_line": 1, "end_line": 1},
            ],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            before_definition, include_relationships=False
        )
        after = codemap.repository_evidence_bindings(
            after_definition, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    changed = delta["bindings"]["changed"][0]
    assert changed["definition"]["state"] == "changed"
    assert changed["direct_evidence"]["state"] == "preserved"
    assert changed["direct_evidence"]["changes"] == []
    assert changed["locator_evidence"]["state"] == "preserved"
    assert changed["member_evidence"]["state"] == "preserved"


def test_coverage_rejects_tampered_binding_packet(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "coverage-authenticated",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(binding)
        packet["bindings"][0]["evidence"][0]["state"] = "known-absent"

        with pytest.raises(ValueError, match="bindings identity mismatch"):
            codemap.repository_evidence_coverage(
                packet,
                changed_paths=["a.py"],
                change_set_complete=True,
            )


def test_coverage_rejects_authenticated_foreign_repository_packet(
    tmp_path: Path,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    (right / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "coverage-repository-bound",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(left) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(binding)
    with CodeMap(right) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="repository-mismatch"):
            codemap.repository_evidence_coverage(
                packet,
                changed_paths=["owner.py"],
                change_set_complete=True,
            )


def test_coverage_rejects_delta_for_different_binding_packet(tmp_path: Path) -> None:
    source = tmp_path / "a.py"
    source.write_text("a\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "a",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        }
    ]
    other = [
        {
            "binding_id": "other",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("b\n", encoding="utf-8")
        codemap.sync(["a.py"])
        after = codemap.repository_evidence_bindings(binding)
        unrelated = codemap.repository_evidence_bindings(other)
        delta = codemap.repository_evidence_binding_delta(before, after)
        with pytest.raises(ValueError, match="after identity"):
            codemap.repository_evidence_coverage(
                unrelated,
                changed_paths=["a.py"],
                change_set_complete=True,
                binding_delta=delta,
            )


def test_coverage_rejects_tampered_binding_delta(tmp_path: Path) -> None:
    source = tmp_path / "a.py"
    source.write_text("a\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "delta-authenticated",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("b\n", encoding="utf-8")
        codemap.sync(["a.py"])
        after = codemap.repository_evidence_bindings(binding)
        delta = codemap.repository_evidence_binding_delta(before, after)
        delta["bindings"]["changed"].clear()

        with pytest.raises(ValueError, match="binding_delta identity mismatch"):
            codemap.repository_evidence_coverage(
                after,
                changed_paths=["a.py"],
                change_set_complete=True,
                binding_delta=delta,
            )


def test_whole_member_binding_cannot_bypass_pruned_analysis_scope(
    tmp_path: Path,
) -> None:
    pruned = tmp_path / "node_modules" / "pkg"
    pruned.mkdir(parents=True)
    (pruned / "package.json").write_text('{"name":"pkg"}\n', encoding="utf-8")
    binding = [
        {
            "binding_id": "pruned",
            "evidence": [{"scope": "member", "path": "node_modules/pkg/package.json"}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = packet["bindings"][0]["evidence"][0]
    assert evidence["state"] == "unsupported"
    assert evidence["reason"] == "repository-evidence-not-admitted"
    assert "member_revision" not in evidence


def test_relationship_locator_change_is_separate_from_relationship_fact_change(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    dependency = tmp_path / "dependency.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    source.write_text(
        "from dependency import VALUE\nPAD = 0\nKEEP = 1\n",
        encoding="utf-8",
    )
    binding = [
        {
            "binding_id": "relationship-locator",
            "evidence": [{"path": "source.py", "start_line": 3, "end_line": 3}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text(
            "PAD = 0\nfrom dependency import VALUE\nKEEP = 1\n",
            encoding="utf-8",
        )
        codemap.sync(["source.py"])
        after = codemap.repository_evidence_bindings(binding)
        delta = codemap.repository_evidence_binding_delta(before, after)

    changed = delta["bindings"]["changed"][0]
    assert changed["direct_evidence"]["state"] == "preserved"
    relationships = changed["relationship_evidence"]
    assert relationships["state"] == "changed"
    assert relationships["facts"]["state"] == "unchanged"
    assert relationships["facts"]["added"] == []
    assert relationships["facts"]["removed"] == []
    assert relationships["locators"]["state"] == "changed"
    assert len(relationships["locators"]["changes"]) >= 1


def test_range_definition_change_does_not_masquerade_as_repository_change(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("one\ntwo\n", encoding="utf-8")
    before_definition = [
        {
            "binding_id": "range-definition",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    after_definition = [
        {
            "binding_id": "range-definition",
            "evidence": [{"path": "owner.py", "start_line": 2, "end_line": 2}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            before_definition, include_relationships=False
        )
        after = codemap.repository_evidence_bindings(
            after_definition, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=[],
            change_set_complete=True,
            binding_delta=delta,
        )

    changed = delta["bindings"]["changed"][0]
    assert changed["definition"]["state"] == "changed"
    assert changed["direct_evidence"]["state"] == "preserved"
    assert changed["locator_evidence"]["state"] == "preserved"
    assert changed["member_evidence"]["state"] == "preserved"
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "range-definition",
            "reasons": ["binding-definition-changed"],
        }
    ]


def test_dependency_definition_change_is_not_dependency_observation_change(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("stable\n", encoding="utf-8")
    (tmp_path / "dependency.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "dependency-definition",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        after = codemap.repository_evidence_bindings(
            binding,
            dependency_paths={"dependency-definition": ["dependency.py"]},
            include_relationships=False,
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=[],
            change_set_complete=True,
            binding_delta=delta,
        )

    changed = delta["bindings"]["changed"][0]
    declared = changed["declared_dependencies"]
    assert declared["state"] == "definition-changed"
    assert declared["definition"] == {
        "state": "changed",
        "added": ["dependency.py"],
        "removed": [],
    }
    assert declared["observations"] == {"state": "unchanged", "changes": []}
    assert changed["definition"]["state"] == "changed"
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "dependency-definition",
            "reasons": ["binding-definition-changed"],
        }
    ]


def test_out_of_range_span_separates_member_presence_from_locator_state(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("one\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "locator",
            "evidence": [{"path": "owner.py", "start_line": 2, "end_line": 2}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )

    evidence = packet["bindings"][0]["evidence"][0]
    assert evidence["member_state"] == "known-present"
    assert evidence["state"] == "known-absent"
    assert evidence["locator_state"] == "outside-member"
    assert evidence["content_state"] == "known-absent"
    assert packet["completeness"]["state"] == "complete"


def test_cheap_binding_mode_does_not_query_relationship_lane(tmp_path: Path) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "cheap-economics",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.store.reset_read_counters()
        with codemap.decision_session():
            codemap.repository_evidence_bindings(binding, include_relationships=False)
            stats = codemap.decision_session_stats()
        counters = codemap.store.read_counters()

    assert stats.get("store_edges_for_paths_many", 0) == 0
    assert counters.get("edges_for_paths_many", 0) == 0


def test_bindings_are_language_neutral_for_typescript_and_config(
    tmp_path: Path,
) -> None:
    (tmp_path / "src.ts").write_text(
        "export const VALUE = 1;\nexport const KEEP = 2;\n",
        encoding="utf-8",
    )
    (tmp_path / "settings.json").write_text(
        '{"enabled": true}\n',
        encoding="utf-8",
    )
    bindings = [
        {
            "binding_id": "mixed-repository",
            "evidence": [
                {"path": "src.ts", "start_line": 2, "end_line": 2},
                {"scope": "member", "path": "settings.json"},
            ],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )

    evidence = packet["bindings"][0]["evidence"]
    assert [row["path"] for row in evidence] == ["src.ts", "settings.json"]
    assert all(row["state"] == "known-present" for row in evidence)
    assert packet["completeness"]["state"] == "complete"


def test_binding_delta_keeps_observer_change_separate_from_repository_change(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "observer-separation",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(binding)
        after = deepcopy(before)
        after["observer"] = {
            **after["observer"],
            "identity": "sha256:" + "a" * 64,
        }
        after["bindings_identity"] = "sha256:" + codemap._packet_digest(
            "hashmarks.repository-evidence-bindings.v1",
            {key: value for key, value in after.items() if key != "bindings_identity"},
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    assert delta["observer"]["changed"] is True
    assert delta["bindings"]["preserved"] == ["observer-separation"]
    assert delta["bindings"]["changed"] == []


def test_binding_delta_rejects_cross_repository_comparison(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    (right / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "repository-bound",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(left) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(binding)
    with CodeMap(right) as codemap:
        codemap.sync()
        after = codemap.repository_evidence_bindings(binding)
        with pytest.raises(ValueError, match="repository-mismatch"):
            codemap.repository_evidence_binding_delta(before, after)


def test_binding_delta_reports_added_and_removed_bindings_deterministically(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("B = 1\n", encoding="utf-8")
    before_definition = [
        {
            "binding_id": "z:removed",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        },
        {
            "binding_id": "stable",
            "evidence": [{"path": "b.py", "start_line": 1, "end_line": 1}],
        },
    ]
    after_definition = [
        {
            "binding_id": "a:added",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        },
        {
            "binding_id": "stable",
            "evidence": [{"path": "b.py", "start_line": 1, "end_line": 1}],
        },
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            before_definition, include_relationships=False
        )
        after = codemap.repository_evidence_bindings(
            after_definition, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    assert delta["bindings"] == {
        "added": ["a:added"],
        "removed": ["z:removed"],
        "preserved": ["stable"],
        "changed": [],
    }


def test_binding_delta_reports_previously_absent_member_as_added(
    tmp_path: Path,
) -> None:
    binding = [
        {
            "binding_id": "created-member",
            "evidence": [{"path": "created.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        (tmp_path / "created.py").write_text("VALUE = 1\n", encoding="utf-8")
        codemap.sync(["created.py"])
        after = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    changed = delta["bindings"]["changed"][0]
    member_change = changed["member_evidence"]["changes"][0]
    assert member_change["state"] == "added"
    assert member_change["before_state"] == "known-absent"
    assert member_change["after_state"] == "known-present"
    assert member_change["observation_state_changed"] is True


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"schema": "wrong"}, "before must be a repository evidence bindings packet"),
        ({"bindings_identity": None}, "before bindings identity mismatch"),
    ],
)
def test_binding_delta_rejects_malformed_before_packet(
    tmp_path: Path,
    mutation: dict[str, object],
    match: str,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "malformed",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(binding)
        before = {**packet, **mutation}
        with pytest.raises(ValueError, match=match):
            codemap.repository_evidence_binding_delta(before, packet)


def test_binding_delta_rejects_tampered_authenticated_packet(tmp_path: Path) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "authenticated",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(binding)
        before = deepcopy(packet)
        before["bindings"][0]["evidence"][0]["state"] = "known-absent"

        with pytest.raises(ValueError, match="before bindings identity mismatch"):
            codemap.repository_evidence_binding_delta(before, packet)


def test_binding_delta_reports_unsupported_member_becoming_present_as_state_change(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    binding = [
        {
            "binding_id": "state-transition",
            "evidence": [{"path": "linked/owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        linked.unlink()
        linked.mkdir()
        (linked / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
        codemap.sync(["linked/owner.py"])
        after = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    change = delta["bindings"]["changed"][0]["member_evidence"]["changes"][0]
    assert change["state"] == "state-changed"
    assert change["before_state"] == "unsupported"
    assert change["after_state"] == "known-present"
    assert change["observation_state_changed"] is True

def test_coverage_rejects_authenticated_delta_with_foreign_repository_claim(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "value",
            "evidence": [{"path": "source.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        source.write_text("value = 2\n", encoding="utf-8")
        codemap.sync(["source.py"])
        after = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        delta["repository"]["after"]["repository_identity"] = "sha256:foreign"
        payload = {
            key: value for key, value in delta.items() if key != "delta_identity"
        }
        delta["delta_identity"] = "sha256:" + codemap._packet_digest(
            "hashmarks.repository-evidence-binding-delta.v1", payload
        )

        with pytest.raises(ValueError, match="binding_delta repository-mismatch"):
            codemap.repository_evidence_coverage(
                after,
                changed_paths=["source.py"],
                change_set_complete=True,
                binding_delta=delta,
            )

