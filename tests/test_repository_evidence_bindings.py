from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_array, assert_object, assert_records, assert_text

from hashmarks import CodeMap
from hashmarks.client import RepositoryObservation
from hashmarks.codemap.repository_observation import packet_digest
from hashmarks.observation import ObservationState

if TYPE_CHECKING:
    from pathlib import Path


def _first_binding(packet: Mapping[str, object]) -> dict[str, object]:
    return assert_object(assert_array(packet["bindings"])[0])


def _first_evidence(packet: Mapping[str, object]) -> dict[str, object]:
    return assert_object(assert_array(_first_binding(packet)["evidence"])[0])


def _changed_binding(packet: Mapping[str, object]) -> dict[str, object]:
    return assert_object(assert_array(assert_object(packet["bindings"])["changed"])[0])


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
        codemap.index.sync()
        first = codemap.repository_evidence_bindings(bindings)
        second = codemap.repository_evidence_bindings(bindings)

    assert first == second
    assert first["schema"] == "hashmarks.repository-evidence-bindings.v1"
    assert first["authority"] == "repository-intelligence-only"
    assert first["execution_effect"] == "none"
    assert assert_text(assert_object(first["observer"])["identity"]).startswith(
        "sha256:"
    )
    assert "evidence-bindings" in assert_array(
        assert_object(first["observer"])["capabilities"]
    )
    assert assert_text(
        assert_object(first["repository"])["source_identity"]
    ).startswith("sha256:")
    row = _first_binding(first)
    assert row["binding_id"] == "consumer:a"
    assert assert_object(assert_array(row["evidence"])[0])["state"] == "known-present"
    assert assert_text(
        assert_object(assert_array(row["evidence"])[0])["span_identity"]
    ).startswith("sha256:")
    assert (
        len(
            assert_text(
                assert_object(assert_array(row["evidence"])[0])["member_revision"]
            )
        )
        == 64
    )


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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("ONE\ntwo\nthree\n", encoding="utf-8")
        codemap.index.sync(["src.py"])
        after = codemap.repository_evidence_bindings(binding)

    old = _first_evidence(before)
    new = _first_evidence(after)
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
        codemap.index.sync()
        absent = codemap.repository_evidence_bindings(missing)
        nontext = codemap.repository_evidence_bindings(unsupported)
    assert _first_evidence(absent)["state"] == "known-absent"
    assert _first_evidence(nontext)["state"] == "unsupported"


def test_binding_rejects_duplicate_identity_and_invalid_range(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
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
        codemap.index.sync()
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
        codemap.index.sync()
        crlf = codemap.repository_evidence_bindings(binding)
        source.write_bytes(b"one\ntwo\r\n")
        codemap.index.sync(["a.py"])
        lf = codemap.repository_evidence_bindings(binding)
    assert (
        _first_evidence(crlf)["span_identity"] != _first_evidence(lf)["span_identity"]
    )


def test_binding_rejects_symlinked_ancestor_evidence(tmp_path: Path) -> None:
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (outside / "secret.py").write_text("secret\n", encoding="utf-8")
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
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
    row = _first_evidence(packet)
    assert row["state"] == "unsupported"
    assert row["reason"] == "symlink-evidence-not-observed"


def test_binding_observation_is_decision_session_scoped(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session():
            packet = codemap.repository_evidence_bindings(
                [
                    {
                        "binding_id": "stable",
                        "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
                    }
                ]
            )
            assert (
                assert_object(packet["repository"])["codemap_generation"]
                == codemap.store.generation()
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic:binding": ["dependency.py"]}
        )
        dependency.write_text("VALUE = 2\n", encoding="utf-8")
        codemap.index.sync(["dependency.py"])
        after = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic:binding": ["dependency.py"]}
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    changed = _changed_binding(delta)
    assert assert_object(changed["direct_evidence"])["state"] == "preserved"
    assert assert_object(changed["declared_dependencies"])["state"] == "affected"
    observations = assert_object(
        assert_object(changed["declared_dependencies"])["observations"]
    )
    assert observations["state"] == "changed"
    assert (
        assert_object(assert_array(observations["changes"])[0])["path"]
        == "dependency.py"
    )


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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic:binding": ["dependency.py"]}
        )
        unrelated.write_text("OTHER = 2\n", encoding="utf-8")
        codemap.index.sync(["other.py"])
        after = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic:binding": ["dependency.py"]}
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    assert assert_object(delta["bindings"])["preserved"] == ["generic:binding"]
    assert assert_object(delta["bindings"])["changed"] == []


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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, relationship_limit_per_path=8
        )
    relationships = assert_object(_first_binding(packet)["relationships"])
    assert relationships["state"] == "observed"
    assert relationships["completeness"] == "bounded-not-claimed"
    assert assert_object(relationships["bounds"])["limit_per_path"] == 8
    assert any(
        row.get("target") for row in assert_records(relationships["relationships"])
    )


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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("from beta import VALUE\nKEEP = 1\n", encoding="utf-8")
        codemap.index.sync(["source.py"])
        after = codemap.repository_evidence_bindings(binding)
        delta = codemap.repository_evidence_binding_delta(before, after)
    changed = _changed_binding(delta)
    assert assert_object(changed["direct_evidence"])["state"] == "preserved"
    relationships = assert_object(changed["relationship_evidence"])
    assert relationships["state"] == "changed"
    assert relationships["comparability"] == "comparable"
    assert assert_object(relationships["facts"])["state"] == "changed"
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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            bindings, dependency_paths={"generic": ["dependency.py"]}
        )
        coverage = codemap.repository_evidence_coverage(
            packet,
            changed_paths=["bound.py", "dependency.py", "outside.py"],
            change_set_complete=True,
        )
    assert assert_object(coverage["classification"])[
        "bound_member_precision_unknown"
    ] == ["bound.py"]
    assert assert_object(coverage["classification"])[
        "declared_dependencies_changed"
    ] == ["dependency.py"]
    assert assert_object(coverage["classification"])["outside_declared_bindings"] == [
        "outside.py"
    ]
    assert assert_object(coverage["coverage"])["state"] == "complete"
    assert assert_object(coverage["coverage"])["outside_classification"] == "known"


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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(bindings)
        coverage = codemap.repository_evidence_coverage(
            packet, changed_paths=["seen.py"], change_set_complete=False
        )
    assert assert_object(coverage["classification"])["outside_declared_bindings"] == []
    assert assert_object(coverage["classification"])[
        "outside_declared_bindings_candidates"
    ] == ["seen.py"]
    assert assert_object(coverage["coverage"])["state"] == "incomplete"
    assert assert_object(coverage["coverage"])["outside_classification"] == "unknown"


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
        codemap.index.sync()
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(bindings)
        source.write_text("OUTSIDE\nbound\n", encoding="utf-8")
        codemap.index.sync(["source.py"])
        after = codemap.repository_evidence_bindings(bindings)
        delta = codemap.repository_evidence_binding_delta(before, after)
        outside_range = codemap.repository_evidence_coverage(
            after,
            changed_paths=["source.py"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )
        source.write_text("OUTSIDE\nBOUND\n", encoding="utf-8")
        codemap.index.sync(["source.py"])
        latest = codemap.repository_evidence_bindings(bindings)
        direct_delta = codemap.repository_evidence_binding_delta(after, latest)
        inside_range = codemap.repository_evidence_coverage(
            latest,
            changed_paths=["source.py"],
            change_set_complete=True,
            binding_delta=direct_delta,
            binding_delta_before=after,
        )

    assert (
        assert_object(outside_range["classification"])["changed_inside_bound_evidence"]
        == []
    )
    assert assert_object(outside_range["classification"])[
        "changed_elsewhere_in_bound_member"
    ] == ["source.py"]
    assert (
        assert_object(outside_range["classification"])["bound_member_precision_unknown"]
        == []
    )
    assert assert_object(inside_range["classification"])[
        "changed_inside_bound_evidence"
    ] == ["source.py"]
    assert (
        assert_object(inside_range["classification"])[
            "changed_elsewhere_in_bound_member"
        ]
        == []
    )
    assert assert_object(inside_range["precision"])["bound_range"] == "known"


def test_path_only_coverage_refuses_to_infer_range_impact(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("a\nb\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "range",
            "evidence": [{"path": "source.py", "start_line": 2, "end_line": 2}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(bindings)
        coverage = codemap.repository_evidence_coverage(
            packet, changed_paths=["source.py"], change_set_complete=True
        )
    assert (
        assert_object(coverage["classification"])["changed_inside_bound_evidence"] == []
    )
    assert (
        assert_object(coverage["classification"])["changed_elsewhere_in_bound_member"]
        == []
    )
    assert assert_object(coverage["classification"])[
        "bound_member_precision_unknown"
    ] == ["source.py"]
    assert assert_object(coverage["precision"])["bound_range"] == "unknown"


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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    row = _first_binding(packet)
    assert assert_object(assert_array(row["evidence"])[0])["state"] == "known-present"
    assert assert_object(row["relationships"])["state"] == "not-requested"
    assert assert_object(row["relationships"])["completeness"] == "not-observed"


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
    tmp_path: Path, payload: list[dict[str, object]], match: str
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with pytest.raises((TypeError, ValueError), match=match):
            codemap.repository_evidence_bindings(payload)


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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = assert_records(_first_binding(packet)["evidence"])
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        source.unlink()
        codemap.index.sync(["a.py"])
        after = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["a.py"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )
    changed = _changed_binding(delta)
    assert assert_object(changed["direct_evidence"])["state"] == "preserved"
    assert assert_object(changed["locator_evidence"])["state"] == "changed"
    member_change = assert_object(
        assert_array(assert_object(changed["member_evidence"])["changes"])[0]
    )
    assert member_change["state"] == "removed"
    assert member_change["observation_state_changed"] is True
    assert _first_evidence(after)["state"] == "known-absent"
    assert assert_object(coverage["classification"])["bound_members_removed"] == [
        "a.py"
    ]
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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = _first_evidence(packet)
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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    assert _first_evidence(packet)["byte_length"] == len(b"\xef\xbb\xbfvalue = 1\n")


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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = _first_evidence(packet)
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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = _first_evidence(packet)
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
        codemap.index.sync()
        source.write_text("VALUE = 2\n", encoding="utf-8")
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = _first_evidence(packet)
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            binding, relationship_limit_per_path=8
        )
        after = codemap.repository_evidence_bindings(
            binding, relationship_limit_per_path=16
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    before_row = _first_binding(before)
    after_row = _first_binding(after)
    assert (
        before_row["binding_definition_identity"]
        != after_row["binding_definition_identity"]
    )
    changed = _changed_binding(delta)
    assert assert_object(changed["definition"])["state"] == "changed"
    relationships = assert_object(changed["relationship_evidence"])
    assert relationships["state"] == "unknown"
    assert relationships["comparability"] == "observation-configuration-changed"
    assert assert_object(relationships["facts"])["state"] == "unknown"
    assert assert_object(relationships["locators"])["state"] == "unknown"
    assert assert_object(relationships["observation"])["changed"] is True


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
        codemap.index.sync()
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
    assert assert_object(coverage["coverage"])["state"] == "complete"
    assert assert_object(coverage["coverage"])["source"] == "repository-observer"
    assert assert_object(coverage["change_set"])["generation"] == 7


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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("VALUE = 2\n", encoding="utf-8")
        codemap.index.sync(["owner.py"])
        after = codemap.repository_evidence_bindings(binding)
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["owner.py"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )

    evidence = assert_records(_first_binding(packet)["evidence"])
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
        codemap.index.sync()
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
            binding_delta_before=before,
        )

    changed = _changed_binding(delta)
    assert assert_object(changed["direct_evidence"])["state"] == "changed"
    assert (
        assert_object(
            assert_array(assert_object(changed["direct_evidence"])["changes"])[0]
        )["scope"]
        == "member"
    )
    assert assert_object(changed["member_evidence"])["state"] == "changed"
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
        codemap.index.sync()
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
        codemap.index.sync()
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
    assert len(assert_array(_first_binding(first)["evidence"])) == 3


def test_binding_contract_rejects_unknown_dependency_owner_and_unbounded_requests(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            before_definition, include_relationships=False
        )
        after = codemap.repository_evidence_bindings(
            after_definition, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    changed = _changed_binding(delta)
    assert assert_object(changed["definition"])["state"] == "changed"
    assert assert_object(changed["direct_evidence"])["state"] == "preserved"
    assert assert_object(changed["direct_evidence"])["changes"] == []
    assert assert_object(changed["locator_evidence"])["state"] == "preserved"
    assert assert_object(changed["member_evidence"])["state"] == "preserved"


def test_coverage_rejects_tampered_binding_packet(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "coverage-authenticated",
            "evidence": [{"path": "a.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(binding)
        _first_evidence(packet)["state"] = "known-absent"

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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(binding)
    with CodeMap(right) as codemap:
        codemap.index.sync()
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("b\n", encoding="utf-8")
        codemap.index.sync(["a.py"])
        after = codemap.repository_evidence_bindings(binding)
        unrelated = codemap.repository_evidence_bindings(other)
        delta = codemap.repository_evidence_binding_delta(before, after)
        with pytest.raises(ValueError, match="after identity"):
            codemap.repository_evidence_coverage(
                unrelated,
                changed_paths=["a.py"],
                change_set_complete=True,
                binding_delta=delta,
                binding_delta_before=before,
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text("b\n", encoding="utf-8")
        codemap.index.sync(["a.py"])
        after = codemap.repository_evidence_bindings(binding)
        delta = codemap.repository_evidence_binding_delta(before, after)
        assert_array(assert_object(delta["bindings"])["changed"]).clear()

        with pytest.raises(ValueError, match="binding_delta identity mismatch"):
            codemap.repository_evidence_coverage(
                after,
                changed_paths=["a.py"],
                change_set_complete=True,
                binding_delta=delta,
                binding_delta_before=before,
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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
    evidence = _first_evidence(packet)
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(binding)
        source.write_text(
            "PAD = 0\nfrom dependency import VALUE\nKEEP = 1\n",
            encoding="utf-8",
        )
        codemap.index.sync(["source.py"])
        after = codemap.repository_evidence_bindings(binding)
        delta = codemap.repository_evidence_binding_delta(before, after)

    changed = _changed_binding(delta)
    assert assert_object(changed["direct_evidence"])["state"] == "preserved"
    relationships = assert_object(changed["relationship_evidence"])
    assert relationships["state"] == "changed"
    assert assert_object(relationships["facts"])["state"] == "unchanged"
    assert assert_object(relationships["facts"])["added"] == []
    assert assert_object(relationships["facts"])["removed"] == []
    assert assert_object(relationships["locators"])["state"] == "changed"
    assert len(assert_array(assert_object(relationships["locators"])["changes"])) >= 1


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
        codemap.index.sync()
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
            binding_delta_before=before,
        )

    changed = _changed_binding(delta)
    assert assert_object(changed["definition"])["state"] == "changed"
    assert assert_object(changed["direct_evidence"])["state"] == "preserved"
    assert assert_object(changed["locator_evidence"])["state"] == "preserved"
    assert assert_object(changed["member_evidence"])["state"] == "preserved"
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
        codemap.index.sync()
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
            binding_delta_before=before,
        )

    changed = _changed_binding(delta)
    declared = assert_object(changed["declared_dependencies"])
    assert declared["state"] == "definition-changed"
    assert declared["definition"] == {
        "state": "changed",
        "added": ["dependency.py"],
        "removed": [],
    }
    assert declared["observations"] == {"state": "unchanged", "changes": []}
    assert assert_object(changed["definition"])["state"] == "changed"
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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )

    evidence = _first_evidence(packet)
    assert evidence["member_state"] == "known-present"
    assert evidence["state"] == "known-absent"
    assert evidence["locator_state"] == "outside-member"
    assert evidence["content_state"] == "known-absent"
    assert assert_object(packet["completeness"])["state"] == "complete"


def test_cheap_binding_mode_does_not_query_relationship_lane(tmp_path: Path) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "cheap-economics",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        codemap.store.reset_read_counters()
        with codemap.reads.session():
            codemap.repository_evidence_bindings(binding, include_relationships=False)
            stats = codemap.reads.stats()
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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )

    evidence = assert_records(_first_binding(packet)["evidence"])
    assert [row["path"] for row in evidence] == ["src.ts", "settings.json"]
    assert all(row["state"] == "known-present" for row in evidence)
    assert assert_object(packet["completeness"])["state"] == "complete"


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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(binding)
        after = deepcopy(before)
        after["observer"] = {
            **assert_object(after["observer"]),
            "identity": "sha256:" + "a" * 64,
        }
        after["bindings_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-bindings.v1",
            {key: value for key, value in after.items() if key != "bindings_identity"},
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    assert assert_object(delta["observer"])["changed"] is True
    assert assert_object(delta["bindings"])["preserved"] == ["observer-separation"]
    assert assert_object(delta["bindings"])["changed"] == []


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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(binding)
    with CodeMap(right) as codemap:
        codemap.index.sync()
        after = codemap.repository_evidence_bindings(binding)
        with pytest.raises(ValueError, match="repository-mismatch"):
            codemap.repository_evidence_binding_delta(before, after)


def test_binding_delta_rejects_foreign_packets_even_when_they_match_each_other(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    consumer = tmp_path / "consumer"
    source.mkdir()
    consumer.mkdir()
    (source / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    (consumer / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "repository-bound",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(source) as source_map:
        source_map.index.sync()
        packet = source_map.repository_evidence_bindings(binding)

    with CodeMap(consumer) as consumer_map:
        consumer_map.index.sync()
        with pytest.raises(ValueError, match="repository-mismatch"):
            consumer_map.repository_evidence_binding_delta(packet, deepcopy(packet))


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
        codemap.index.sync()
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        (tmp_path / "created.py").write_text("VALUE = 1\n", encoding="utf-8")
        codemap.index.sync(["created.py"])
        after = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    changed = _changed_binding(delta)
    member_change = assert_object(
        assert_array(assert_object(changed["member_evidence"])["changes"])[0]
    )
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
        codemap.index.sync()
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
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(binding)
        before = deepcopy(packet)
        _first_evidence(before)["state"] = "known-absent"

        with pytest.raises(ValueError, match="before bindings identity mismatch"):
            codemap.repository_evidence_binding_delta(before, packet)


def test_binding_delta_rejects_resigned_nested_binding_tamper(tmp_path: Path) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "authenticated",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(binding)
        before = deepcopy(packet)
        _first_evidence(before)["state"] = "known-absent"
        payload = {
            key: value for key, value in before.items() if key != "bindings_identity"
        }
        before["bindings_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-bindings.v1", payload
        )

        with pytest.raises(ValueError, match="binding observation identity mismatch"):
            codemap.repository_evidence_binding_delta(before, packet)


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        (
            "completeness",
            {"state": "incomplete", "scope": "explicit-declared-evidence"},
        ),
        ("storage", "persisted"),
        ("authority", "execution-authority"),
        ("execution_effect", "may-execute"),
    ],
)
def test_binding_delta_rejects_resigned_forged_packet_contract_claim(
    tmp_path: Path,
    field: str,
    forged_value: object,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "contract-bound",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(binding)
        before = deepcopy(packet)
        before[field] = forged_value
        payload = {
            key: value for key, value in before.items() if key != "bindings_identity"
        }
        before["bindings_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-bindings.v1", payload
        )

        with pytest.raises(ValueError, match=rf"{field} contract mismatch"):
            codemap.repository_evidence_binding_delta(before, packet)


def test_binding_delta_rejects_resigned_malformed_definition_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "definition-bound",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(binding)
        before = deepcopy(packet)
        _first_binding(before)["binding_definition_identity"] = "forged"
        payload = {
            key: value for key, value in before.items() if key != "bindings_identity"
        }
        before["bindings_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-bindings.v1", payload
        )

        with pytest.raises(ValueError, match="binding definition identity mismatch"):
            codemap.repository_evidence_binding_delta(before, packet)


def test_binding_delta_rejects_resigned_duplicate_binding_ids(tmp_path: Path) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "duplicate",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(binding)
        before = deepcopy(packet)
        assert_array(before["bindings"]).append(deepcopy(_first_binding(before)))
        payload = {
            key: value for key, value in before.items() if key != "bindings_identity"
        }
        before["bindings_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-bindings.v1", payload
        )

        with pytest.raises(ValueError, match="duplicate binding_id"):
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        linked.unlink()
        linked.mkdir()
        (linked / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
        codemap.index.sync(["linked/owner.py"])
        after = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)

    change = assert_object(
        assert_array(
            assert_object(_changed_binding(delta)["member_evidence"])["changes"]
        )[0]
    )
    assert change["state"] == "state-changed"
    assert change["before_state"] == "unsupported"
    assert change["after_state"] == "known-present"
    assert change["observation_state_changed"] is True


def test_coverage_rejects_resigned_duplicate_binding_packet(tmp_path: Path) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "duplicate",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.repository_evidence_bindings(binding)
        assert_array(packet["bindings"]).append(deepcopy(_first_binding(packet)))
        payload = {
            key: value for key, value in packet.items() if key != "bindings_identity"
        }
        packet["bindings_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-bindings.v1", payload
        )

        with pytest.raises(ValueError, match="duplicate binding_id"):
            codemap.repository_evidence_coverage(
                packet,
                changed_paths=["owner.py"],
                change_set_complete=True,
            )


def test_coverage_rejects_resigned_contradictory_binding_delta(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "value",
            "evidence": [{"path": "source.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        source.write_text("value = 2\n", encoding="utf-8")
        codemap.index.sync(["source.py"])
        after = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        assert_array(assert_object(delta["bindings"])["preserved"]).append("value")
        payload = {
            key: value for key, value in delta.items() if key != "delta_identity"
        }
        delta["delta_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-binding-delta.v1", payload
        )

        with pytest.raises(ValueError, match="classifications overlap"):
            codemap.repository_evidence_coverage(
                after,
                changed_paths=["source.py"],
                change_set_complete=True,
                binding_delta=delta,
                binding_delta_before=before,
            )


def test_coverage_rejects_resigned_forged_binding_delta_detail(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "value",
            "evidence": [{"path": "source.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(bindings)
        source.write_text("value = 2\n", encoding="utf-8")
        codemap.index.sync(["source.py"])
        after = codemap.repository_evidence_bindings(bindings)
        delta = codemap.repository_evidence_binding_delta(before, after)
        assert_object(_changed_binding(delta)["direct_evidence"])["state"] = "preserved"
        payload = {
            key: value for key, value in delta.items() if key != "delta_identity"
        }
        delta["delta_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-binding-delta.v1", payload
        )

        with pytest.raises(ValueError, match="semantic replay mismatch"):
            codemap.repository_evidence_coverage(
                after,
                changed_paths=["source.py"],
                change_set_complete=True,
                binding_delta=delta,
                binding_delta_before=before,
            )


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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        source.write_text("value = 2\n", encoding="utf-8")
        codemap.index.sync(["source.py"])
        after = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        assert_object(assert_object(delta["repository"])["after"])[
            "repository_identity"
        ] = "sha256:foreign"
        payload = {
            key: value for key, value in delta.items() if key != "delta_identity"
        }
        delta["delta_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-binding-delta.v1", payload
        )

        with pytest.raises(ValueError, match="binding_delta repository-mismatch"):
            codemap.repository_evidence_coverage(
                after,
                changed_paths=["source.py"],
                change_set_complete=True,
                binding_delta=delta,
                binding_delta_before=before,
            )


def test_coverage_rejects_authenticated_delta_with_foreign_before_repository_claim(
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
        codemap.index.sync()
        before = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        source.write_text("value = 2\n", encoding="utf-8")
        codemap.index.sync(["source.py"])
        after = codemap.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        assert_object(assert_object(delta["repository"])["before"])[
            "repository_identity"
        ] = "sha256:foreign"
        payload = {
            key: value for key, value in delta.items() if key != "delta_identity"
        }
        delta["delta_identity"] = "sha256:" + packet_digest(
            "hashmarks.repository-evidence-binding-delta.v1", payload
        )

        with pytest.raises(ValueError, match="binding_delta repository-mismatch"):
            codemap.repository_evidence_coverage(
                after,
                changed_paths=["source.py"],
                change_set_complete=True,
                binding_delta=delta,
                binding_delta_before=before,
            )
