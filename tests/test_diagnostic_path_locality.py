"""Hermes-inspired post-edit diagnostic locality is descriptive only."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)
from hashmarks.evidence_presentation import present_repository_evidence

_DIRECT = "src/owner.py"
_OTHER = "src/consumer.py"


def _diagnostic(path: object, rule: str) -> dict[str, object]:
    return {
        "tool": "pyright",
        "rule": rule,
        "path": path,
        "line": 7,
        "message": "fixture diagnostic",
    }


def _observation(
    diagnostics: list[Mapping[str, object]],
    *,
    collection: str = "fresh-complete",
    scope: tuple[str, ...] = (_DIRECT, _OTHER),
) -> dict[str, object]:
    return RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        binding=RepositoryGenerationBinding("repository:fixture", 4),
        environment_identity="environment:fixture",
        diagnostics=diagnostics,
        outcome="fail",
        scope_paths=scope,
        collection_state=collection,
    )


def _delta(
    before: list[Mapping[str, object]],
    after: list[Mapping[str, object]],
    *,
    changed_paths: list[str] | None = None,
    before_collection: str = "fresh-complete",
    after_collection: str = "fresh-complete",
) -> dict[str, object]:
    return RepositoryDeltaMixin.diagnostic_observation_delta(
        _observation(before, collection=before_collection),
        _observation(after, collection=after_collection),
        changed_paths=changed_paths or [],
    )


def _rows(delta: Mapping[str, object]) -> list[dict[str, object]]:
    return delta["diagnostics"]["path_locality"]["rows"]


def test_direct_and_other_member_changes_preserve_both_delta_directions() -> None:
    before = [_diagnostic(_DIRECT, "old-direct"), _diagnostic(_OTHER, "old-other")]
    after = [_diagnostic(_DIRECT, "new-direct"), _diagnostic(_OTHER, "new-other")]
    delta = _delta(before, after, changed_paths=[_DIRECT])
    locality = delta["diagnostics"]["path_locality"]
    rows = _rows(delta)

    assert locality["schema"] == "hashmarks.diagnostic-path-locality.v1"
    assert locality["changed_paths"] == [_DIRECT]
    assert locality["change_scope"] == "caller-reported"
    assert locality["change_set_completeness"] == "unknown"
    assert locality["causality"] == "not-asserted"
    assert locality["authority"] == "descriptive-path-locality-only"
    assert locality["execution_effect"] == "none"
    assert len(delta["diagnostics"]["added"]) == 2
    assert len(delta["diagnostics"]["removed"]) == 2
    assert len(delta["diagnostics"]["added_in_changed_scope"]) == 1
    assert len(rows) == 4
    assert {(row["change_kind"], row["path"]): row["locality"] for row in rows} == {
        ("added", _DIRECT): "on-reported-changed-path",
        ("removed", _DIRECT): "on-reported-changed-path",
        ("added", _OTHER): "outside-reported-changed-paths",
        ("removed", _OTHER): "outside-reported-changed-paths",
    }
    assert all(row["collection_qualification"] == "qualified" for row in rows)
    assert all(row["causality"] == "not-asserted" for row in rows)
    assert locality["counts"]["added"] == {
        "on-reported-changed-path": 1,
        "outside-reported-changed-paths": 1,
        "unknown": 0,
    }
    assert locality["counts"]["removed"] == locality["counts"]["added"]
    assert {row["diagnostic_identity"] for row in rows} == {
        row["identity"]
        for row in [
            *delta["diagnostics"]["added"],
            *delta["diagnostics"]["removed"],
        ]
    }


def test_partial_changed_path_list_never_implies_other_file_unaffected() -> None:
    delta = _delta([], [_diagnostic(_OTHER, "new")], changed_paths=[_DIRECT])
    result = _rows(delta)[0]

    assert result["locality"] == "outside-reported-changed-paths"
    assert result["collection_qualification"] == "qualified"
    assert result["causality"] == "not-asserted"
    assert delta["diagnostics"]["path_locality"]["change_set_completeness"] == "unknown"


def test_empty_edit_scope_makes_all_diagnostic_locality_unknown() -> None:
    delta = _delta([], [_diagnostic(_OTHER, "new")])
    locality = delta["diagnostics"]["path_locality"]
    assert locality["changed_paths"] == []
    assert locality["change_scope"] == "unreported-or-empty"
    assert locality["counts"]["added"]["unknown"] == 1
    assert _rows(delta)[0]["locality"] == "unknown"


def test_unlocated_diagnostic_remains_unknown_without_invented_path() -> None:
    delta = _delta([], [_diagnostic(None, "anonymous")], changed_paths=[_DIRECT])
    row = _rows(delta)[0]

    assert row["path"] is None
    assert row["locality"] == "unknown"
    assert row["collection_qualification"] == "unqualified"


@pytest.mark.parametrize("path", ["../outside.py", "", "/tmp/absolute.py"])
def test_invalid_diagnostic_path_does_not_escape_reported_scope(path: str) -> None:
    delta = _delta([], [_diagnostic(path, "invalid")], changed_paths=[_DIRECT])
    assert _rows(delta)[0]["locality"] == "unknown"


def test_partial_after_collection_does_not_certify_removed_diagnostic() -> None:
    delta = _delta(
        [_diagnostic(_OTHER, "old")],
        [],
        changed_paths=[_DIRECT],
        after_collection="fresh-partial",
    )
    row = _rows(delta)[0]
    assert row["change_kind"] == "removed"
    assert row["locality"] == "outside-reported-changed-paths"
    assert row["collection_qualification"] == "unqualified"
    assert delta["diagnostics"]["qualification"]["qualified_removed_identities"] == []


def test_partial_before_collection_does_not_certify_new_diagnostic() -> None:
    delta = _delta(
        [],
        [_diagnostic(_OTHER, "new")],
        changed_paths=[_DIRECT],
        before_collection="fresh-partial",
    )
    assert _rows(delta)[0]["collection_qualification"] == "unqualified"


def test_repeat_observation_and_revision_only_delta_have_no_phantom_paths() -> None:
    row = _diagnostic(_DIRECT, "unchanged")
    delta = _delta([row], [row], changed_paths=[_DIRECT])

    assert delta["diagnostics"]["path_locality"]["rows"] == []
    assert delta["diagnostics"]["path_locality"]["counts"]["added"]["unknown"] == 0
    assert delta["diagnostics"]["unchanged_count"] == 1
    assert delta["diagnostics"]["added"] == []
    assert delta["diagnostics"]["removed"] == []


def test_path_aliases_are_normalized_but_outputs_remain_deterministic() -> None:
    first = _delta([], [_diagnostic(_DIRECT, "new")], changed_paths=["./src/owner.py"])
    second = _delta(
        [],
        [_diagnostic(_DIRECT, "new")],
        changed_paths=["src/owner.py", "./src/owner.py"],
    )
    assert (
        first["diagnostics"]["path_locality"] == second["diagnostics"]["path_locality"]
    )
    assert first["diagnostics"]["path_locality"]["changed_paths"] == [_DIRECT]


@pytest.mark.parametrize(
    "changed",
    [
        ["../escape.py"],
        ["/absolute.py"],
        ["src/x.py"] * 257,
        [None],
        "src/owner.py",
    ],
)
def test_invalid_reported_changed_paths_fail_before_locality_projection(
    changed: object,
) -> None:
    before = _observation([])
    after = _observation([_diagnostic(_DIRECT, "new")])
    with pytest.raises(ValueError, match="changed_paths|input path"):
        RepositoryDeltaMixin.diagnostic_observation_delta(
            before,
            after,
            changed_paths=changed,  # type: ignore[arg-type]
        )


def test_agent_native_presentation_preserves_original_and_locality_findings() -> None:
    delta = _delta(
        [],
        [_diagnostic(_OTHER, "new")],
        changed_paths=[_DIRECT],
    )
    structured = present_repository_evidence(delta, format="structured")
    compact = present_repository_evidence(delta, format="compact")
    for projection in (structured, compact):
        findings = [
            finding for group in projection["groups"] for finding in group["findings"]
        ]
        locality = [
            row for row in findings if row["kind"] == "diagnostic_path_locality"
        ]
        added = [row for row in findings if row["kind"] == "diagnostic_added"]
        assert len(added) == 1
        assert len(locality) == 1
        assert locality[0]["assertion"] == "producer_claim"
        assert locality[0]["source_refs"] == ["/diagnostics/path_locality"]
        assert locality[0]["details"] == delta["diagnostics"]["path_locality"]
        assert locality[0]["details"]["rows"][0]["locality"] == (
            "outside-reported-changed-paths"
        )
    text_view = present_repository_evidence(delta, format="text")
    assert "diagnostic_path_locality" in text_view["text"]
    assert "outside-reported-changed-paths" in text_view["text"]
