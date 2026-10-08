from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_exact_member_occurrences_and_physical_source_shape(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_bytes(b"def example():\r\n    first = 'needle'\n    return 'needle'\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.source_observation(
            "example.py", literal="needle", long_line_threshold=10
        )
    assert packet["schema"] == "hashmarks.source-observation.v1"
    assert packet["member"]["state"] == "known-present"
    assert packet["availability"] == "observed"
    assert packet["observation_scope"] == "exact-admitted-repository-member"
    assert packet["observed_match_count"] == 2
    assert [item["line"] for item in packet["occurrences"]] == [2, 3]
    assert all(
        item["occurrence_kind"] == "string-literal" for item in packet["occurrences"]
    )
    assert all(
        item["member_revision"] == packet["member"]["member_revision"]
        for item in packet["occurrences"]
    )
    assert packet["source_shape"]["physical_lines"] == 3
    assert packet["source_shape"]["lf_terminators"] == 3
    assert packet["source_shape"]["crlf_terminators"] == 1
    assert packet["source_shape"]["long_line_count"] >= 1
    assert packet["completeness"] == "complete"
    assert packet["truncation"] == "complete"
    assert packet["negative_evidence"] == "not-admissible"


def test_truncated_occurrences_do_not_claim_complete_or_absent(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text(
        "def test():\n    return 'hit hit hit'\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.source_observation("example.py", literal="hit", limit=1)
        absent = codemap.source_observation("example.py", literal="unseen")
    assert packet["observed_match_count"] == 3
    assert len(packet["occurrences"]) == 1
    assert packet["truncation"] == "truncated"
    assert packet["completeness"] == "incomplete"
    assert packet["negative_evidence"] == "not-admissible"
    assert absent["observed_match_count"] == 0
    assert absent["completeness"] == "complete"
    if absent["freshness"] == "current":
        assert absent["negative_evidence"] == "admissible-within-exact-member"
    assert absent["observation_scope"] == "exact-admitted-repository-member"


def test_python_token_kinds_distinguish_comment_identifier_and_literal(
    tmp_path: Path,
) -> None:
    (tmp_path / "example.py").write_text(
        "def needle():\n    # needle\n    return 'needle'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        rows = codemap.source_observation("example.py", literal="needle")
    assert [row["occurrence_kind"] for row in rows["occurrences"]] == [
        "identifier",
        "comment",
        "string-literal",
    ]


def test_preflight_coverage_does_not_invent_pruned_member_counts(
    tmp_path: Path,
) -> None:
    (tmp_path / "example.py").write_text("x = 1\n", encoding="utf-8")
    excluded = tmp_path / "node_modules"
    excluded.mkdir()
    (excluded / "secret.js").write_text("ignored\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        packet = codemap.index_preflight()
    coverage = packet["observation_coverage"]
    assert coverage["scope"] == "discovered-policy-admitted-indexable-members"
    assert "node_modules" in coverage["known_pruned_directory_classes"]
    assert coverage["pruned_member_count"] is None
    assert coverage["repository_wide_completeness"] == "not-claimed"
    assert coverage["absence_outside_admitted_scope"] == "not-admissible"


def test_changed_unreconciled_member_never_returns_old_source_hits(
    tmp_path: Path,
) -> None:
    path = tmp_path / "example.py"
    path.write_text("def example(): return 'old'\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.source_observation("example.py", literal="old")
        path.write_text("def example(): return 'new'\n", encoding="utf-8")
        after = codemap.source_observation("example.py", literal="old")
    assert before["observed_match_count"] == 1
    assert after["availability"] == "unavailable"
    assert after["member"]["state"] == "unknown"
    assert after["occurrences"] == []
    assert after["negative_evidence"] == "not-admissible"


def test_denied_and_oversized_members_return_no_source(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=private\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("x = '" + "y" * 1024 + "'\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        denied = codemap.source_observation(".env", literal="private")
        oversized = codemap.source_observation("big.py", literal="y", max_bytes=32)
    assert denied["occurrences"] == []
    assert denied["source_shape"] is None
    assert denied["negative_evidence"] == "not-admissible"
    assert oversized["member"]["reason"] == "source-size-bound"
    assert oversized["observed_match_count"] is None
    assert oversized["negative_evidence"] == "not-admissible"


def test_binary_invalid_utf8_and_source_shape_are_distinct() -> None:
    shape = RepositoryDeltaMixin._source_shape(
        b"\xef\xbb\xbfA\r\n" + b"a" * 30, long_line_threshold=10
    )
    assert shape["utf8_bom"] is True
    assert shape["physical_lines"] == 2
    assert shape["crlf_terminators"] == 1
    assert shape["long_line_count"] == 1


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("literal", ""),
        ("literal", "line\nbreak"),
        ("limit", 0),
        ("max_bytes", 0),
        ("long_line_threshold", 0),
    ],
)
def test_source_observation_rejects_invalid_bounds(
    tmp_path: Path, argument: str, value: object
) -> None:
    with CodeMap(tmp_path) as codemap:
        with pytest.raises(ValueError):
            codemap.source_observation("source.py", **{argument: value})


def _observation(
    rows: list[dict[str, object]], *, collection: str = "fresh-complete"
) -> dict[str, object]:
    return RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        binding=RepositoryGenerationBinding(
            repository_identity="repo:fixture", codemap_generation=5
        ),
        diagnostics=rows,
        outcome="fail",
        collection_state=collection,
        scope_paths=["example.py"],
    )


def _diagnostic(line: int, message: str = "undefined") -> dict[str, object]:
    return {
        "tool": "pyright",
        "rule": "reportUndefinedVariable",
        "path": "example.py",
        "symbol": "example",
        "line": line,
        "column": 3,
        "message": message,
    }


def test_diagnostic_shift_is_candidate_not_proven_identity() -> None:
    before = _observation([_diagnostic(4)])
    after = _observation([_diagnostic(14)], collection="fresh-partial")
    delta = RepositoryDeltaMixin.diagnostic_observation_delta(
        before, after, changed_paths=["example.py"]
    )
    relocations = delta["diagnostics"]["possible_relocations"]
    assert len(relocations) == 1
    assert relocations[0]["state"] == "possible"
    assert relocations[0]["identity_authority"] is False
    assert relocations[0]["before_line"] == 4
    assert relocations[0]["after_line"] == 14
    assert len(delta["diagnostics"]["added"]) == 1
    assert len(delta["diagnostics"]["removed"]) == 1
    assert delta["collection"]["before"]["state"] == "fresh-complete"
    assert delta["collection"]["after"]["state"] == "fresh-partial"


def test_diagnostic_ambiguous_shift_is_not_correlated() -> None:
    before = _observation([_diagnostic(4), _diagnostic(5)])
    after = _observation([_diagnostic(14)])
    delta = RepositoryDeltaMixin.diagnostic_observation_delta(before, after)
    assert delta["diagnostics"]["possible_relocations"] == []


def test_diagnostic_collection_state_is_validated() -> None:
    with pytest.raises(ValueError, match="collection state"):
        _observation([_diagnostic(4)], collection="not-a-state")


def test_scoped_occurrences_have_exact_member_provenance_and_stable_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "alpha.py").write_text("needle = 1\n", encoding="utf-8")
    (tmp_path / "beta.py").write_text(
        "def needle():\n    return 'needle'\n", encoding="utf-8"
    )
    (tmp_path / "unrelated.py").write_text("needle = 3\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.scoped_source_occurrences(
            ["beta.py", "alpha.py", "alpha.py"], "needle"
        )
    assert packet["schema"] == "hashmarks.scoped-source-occurrences.v1"
    assert packet["paths"] == ["alpha.py", "beta.py"]
    assert packet["observation_scope"] == "explicit-member-set-only"
    assert packet["member_count"] == 2
    assert packet["source_coverage"] == "complete"
    assert packet["observed_match_count"] == 3
    assert packet["exact_match_count"] == 3
    assert packet["completeness"] == "complete"
    assert [row["path"] for row in packet["occurrences"]] == [
        "alpha.py",
        "beta.py",
        "beta.py",
    ]
    revisions = {
        row["path"]: row["member_revision"] for row in packet["member_observations"]
    }
    assert all(
        row["evidence_identity"].startswith("sha256:")
        and row["member_revision"] == revisions[row["path"]]
        for row in packet["occurrences"]
    )
    assert packet["observed_source_bytes"] > 0
    assert packet["negative_evidence"] == "not-admissible"


def test_scoped_absence_never_becomes_repository_wide_absence(
    tmp_path: Path,
) -> None:
    (tmp_path / "inside.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "outside.py").write_text("needle = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.scoped_source_occurrences(["inside.py"], "needle")
    assert packet["observed_match_count"] == 0
    assert packet["exact_match_count"] == 0
    assert packet["source_coverage"] == "complete"
    assert packet["observation_scope"] == "explicit-member-set-only"
    if packet["freshness"] == "current":
        assert packet["negative_evidence"] == "admissible-within-explicit-member-set"


def test_scoped_result_limit_does_not_change_exact_observed_counts(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("x = 'hit hit hit'\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 'hit hit'\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.scoped_source_occurrences(["a.py", "b.py"], "hit", limit=1)
    assert len(packet["occurrences"]) == 1
    assert packet["observed_match_count"] == 5
    assert packet["exact_match_count"] == 5
    assert packet["source_coverage"] == "complete"
    assert packet["truncation"] == "truncated"
    assert packet["completeness"] == "incomplete"
    assert packet["negative_evidence"] == "not-admissible"


def test_scoped_visibility_and_pruning_keep_coverage_unknown(tmp_path: Path) -> None:
    (tmp_path / "safe.py").write_text("needle = 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("needle=secret\n", encoding="utf-8")
    nested = tmp_path / "node_modules"
    nested.mkdir()
    (nested / "hidden.py").write_text("needle=hidden\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.scoped_source_occurrences(
            ["safe.py", ".env", "node_modules/hidden.py"], "needle"
        )
    assert packet["observed_match_count"] == 1
    assert packet["exact_match_count"] is None
    assert packet["source_coverage"] == "unknown"
    assert packet["completeness"] == "unknown"
    assert packet["negative_evidence"] == "not-admissible"
    denied = {row["path"]: row for row in packet["member_observations"]}
    assert denied[".env"]["availability"] == "unavailable"
    assert denied["node_modules/hidden.py"]["availability"] == "unavailable"


def test_scoped_total_byte_budget_fails_closed_without_reading_next_member(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("x = 'hit'\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 'hit'\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.scoped_source_occurrences(
            ["a.py", "b.py"], "hit", max_total_bytes=10
        )
    assert packet["observed_source_bytes"] == 10
    assert packet["observed_match_count"] == 1
    assert packet["exact_match_count"] is None
    assert packet["member_observations"][1]["reason"] == "scope-byte-budget-exhausted"
    assert packet["source_coverage"] == "unknown"
    assert packet["negative_evidence"] == "not-admissible"


def test_scoped_member_edit_fails_closed_before_reindex(tmp_path: Path) -> None:
    source = tmp_path / "changed.py"
    source.write_text("x = 'old'\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.scoped_source_occurrences(["changed.py"], "old")
        source.write_text("x = 'new'\n", encoding="utf-8")
        after = codemap.scoped_source_occurrences(["changed.py"], "old")
    assert before["exact_match_count"] == 1
    assert after["exact_match_count"] is None
    assert after["source_coverage"] == "unknown"
    assert after["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize("paths", [[], ["../outside.py"], ["x.py"] * 33])
def test_scoped_source_rejects_invalid_scope_before_observation(
    tmp_path: Path, paths: list[str]
) -> None:
    with CodeMap(tmp_path) as codemap:
        with pytest.raises(ValueError):
            codemap.scoped_source_occurrences(paths, "needle")


def test_scoped_scope_identity_is_stable_across_request_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("needle = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("needle = 2\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.scoped_source_occurrences(["b.py", "a.py"], "needle")
        second = codemap.scoped_source_occurrences(["a.py", "b.py"], "needle")
    assert first["observation_identity"] == second["observation_identity"]


def _qualified_observation(
    rows: list[dict[str, object]],
    *,
    collection: str = "fresh-complete",
    outcome: str = "fail",
    scope: tuple[str, ...] = ("example.py",),
    environment: str | None = "pyright:fixture",
    repository: str = "repo:fixture",
) -> dict[str, object]:
    return RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        binding=RepositoryGenerationBinding(repository, 5),
        diagnostics=rows,
        outcome=outcome,
        environment_identity=environment,
        collection_state=collection,
        scope_paths=scope,
    )


def test_diagnostic_qualified_removal_requires_complete_after_collection() -> None:
    before = _qualified_observation([_diagnostic(4)])
    after = _qualified_observation([], outcome="pass")
    delta = RepositoryDeltaMixin.diagnostic_observation_delta(before, after)
    proof = delta["diagnostics"]["qualification"]
    diagnostic_identity = before["diagnostics"][0]["identity"]
    assert len(delta["diagnostics"]["removed"]) == 1
    assert proof["qualified_removed_identities"] == [diagnostic_identity]
    assert proof["unqualified_removed_identities"] == []
    assert proof["shared_context"] is True
    assert proof["identity_authority"] is False


@pytest.mark.parametrize(
    "collection",
    ["fresh-partial", "timed-out", "unavailable", "source-mismatch", "unknown"],
)
def test_incomplete_diagnostic_collection_does_not_prove_absence(
    collection: str,
) -> None:
    before = _qualified_observation([_diagnostic(4)])
    after = _qualified_observation([], collection=collection, outcome="fail")
    delta = RepositoryDeltaMixin.diagnostic_observation_delta(before, after)
    proof = delta["diagnostics"]["qualification"]
    assert len(delta["diagnostics"]["removed"]) == 1
    assert proof["qualified_removed_identities"] == []
    assert proof["unqualified_removed_identities"] == [
        before["diagnostics"][0]["identity"]
    ]
    assert proof["collection_after"] == collection


def test_partial_after_collection_can_qualify_newly_seen_diagnostics() -> None:
    before = _qualified_observation([])
    after = _qualified_observation([_diagnostic(4)], collection="fresh-partial")
    delta = RepositoryDeltaMixin.diagnostic_observation_delta(before, after)
    proof = delta["diagnostics"]["qualification"]
    assert proof["qualified_added_identities"] == [after["diagnostics"][0]["identity"]]
    assert proof["unqualified_added_identities"] == []


def test_partial_before_collection_cannot_prove_new_diagnostic() -> None:
    before = _qualified_observation([], collection="fresh-partial")
    after = _qualified_observation([_diagnostic(4)])
    delta = RepositoryDeltaMixin.diagnostic_observation_delta(before, after)
    proof = delta["diagnostics"]["qualification"]
    assert proof["qualified_added_identities"] == []
    assert proof["unqualified_added_identities"] == [
        after["diagnostics"][0]["identity"]
    ]


@pytest.mark.parametrize(
    "different_after",
    [
        {"environment": "pyright:other"},
        {"environment": None},
        {"scope": ("other.py",)},
        {"repository": "repo:foreign"},
        {"outcome": "blocked-environment"},
    ],
)
def test_changed_producer_context_never_upgrades_diagnostic_absence(
    different_after: dict[str, object],
) -> None:
    before = _qualified_observation([_diagnostic(4)])
    after = _qualified_observation([], **different_after)
    delta = RepositoryDeltaMixin.diagnostic_observation_delta(before, after)
    proof = delta["diagnostics"]["qualification"]
    assert proof["qualified_removed_identities"] == []
    assert proof["unqualified_removed_identities"] == [
        before["diagnostics"][0]["identity"]
    ]


def test_missing_explicit_producer_scope_cannot_prove_absence() -> None:
    before = _qualified_observation([_diagnostic(4)], scope=())
    after = _qualified_observation([], scope=())
    proof = RepositoryDeltaMixin.diagnostic_observation_delta(before, after)[
        "diagnostics"
    ]["qualification"]
    assert proof["qualified_removed_identities"] == []
    assert len(proof["unqualified_removed_identities"]) == 1
