"""Exact source revision provenance for externally collected diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def _diagnostic(
    *, source_revisions: Mapping[str, str] | None = None,
    scope: tuple[str, ...] = ("src.py",),
    diagnostics: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        binding=RepositoryGenerationBinding("repo:fixture", 5),
        environment_identity="lsp:fixture",
        outcome="fail",
        collection_state="fresh-complete",
        scope_paths=scope,
        diagnostics=(
            [{"tool": "pyright", "rule": "undefined", "path": "src.py", "line": 1}]
            if diagnostics is None
            else diagnostics
        ),
        source_revisions=source_revisions,
    )


def _source(tmp_path: Path) -> dict[str, object]:
    (tmp_path / "src.py").write_text("print(missing)\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        return codemap.source_observation("src.py")


def _project(diagnostic: Mapping[str, object], *sources: Mapping[str, object]) -> dict[str, object]:
    return RepositoryDeltaMixin.diagnostic_source_revision_evidence(
        diagnostic, list(sources)
    )


def test_exact_revision_match_preserves_producer_and_source_authority(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    digest = source["member"]["member_revision"]
    observed = _diagnostic(source_revisions={"src.py": digest})

    result = _project(observed, source)

    assert result["schema"] == "hashmarks.diagnostic-source-revision-evidence.v1"
    assert result["authority"] == "descriptive-source-revision-correspondence-only"
    assert result["execution_effect"] == "none"
    assert result["coverage"] == "complete-for-declared-members"
    assert (result["matching_count"], result["different_count"], result["unknown_count"]) == (
        1, 0, 0
    )
    row = result["rows"][0]
    assert row["state"] == "matching"
    assert row["reason"] == "producer-claim-matches-observed-member-revision"
    assert row["producer_claimed_member_revision"] == digest
    assert row["observed_member_revision"] == digest
    assert row["claim_authority"] == "producer-claimed"
    assert row["comparison_authority"] == "source-local-caller-supplied-observations"
    assert row["source_observation_identity"] == source["observation_identity"]


def test_diagnostic_identity_does_not_change_with_source_provenance(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    revision = source["member"]["member_revision"]
    first = _diagnostic()
    second = _diagnostic(source_revisions={"src.py": revision})
    assert "source_revisions" not in first
    assert second["source_revisions"] == {"src.py": revision}
    assert first["diagnostics"] == second["diagnostics"]


def test_changed_source_revision_is_not_reported_as_current(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    observed = _diagnostic(
        source_revisions={"src.py": source["member"]["member_revision"]}
    )
    (tmp_path / "src.py").write_text("print(changed)\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        current = codemap.source_observation("src.py")
    result = _project(observed, current)
    assert result["different_count"] == 1
    assert result["rows"][0]["state"] == "different"
    assert result["rows"][0]["reason"] == "claimed-and-observed-member-revisions-differ"
    assert result["rows"][0]["source_generation"] != observed["codemap_generation"] or (
        result["rows"][0]["generation_relation"] == "same"
    )


@pytest.mark.parametrize("freshness", ["stale", "unknown"])
def test_unqualified_source_freshness_never_validates_revision(
    tmp_path: Path, freshness: str
) -> None:
    source = _source(tmp_path)
    observation = _diagnostic(
        source_revisions={"src.py": source["member"]["member_revision"]}
    )
    weakened = {**source, "freshness": freshness}
    result = _project(observation, weakened)
    assert result["unknown_count"] == 1
    assert result["rows"][0]["reason"] == "source-observation-freshness-unproven"


def test_absent_and_duplicate_source_packets_are_not_negative_evidence(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    observation = _diagnostic(
        source_revisions={"src.py": source["member"]["member_revision"]}
    )
    missing = _project(observation)
    ambiguous = _project(observation, source, source)

    assert missing["coverage"] == "incomplete"
    assert missing["rows"][0]["reason"] == "source-observation-missing"
    assert ambiguous["rows"][0]["reason"] == "ambiguous-source-observations"
    assert ambiguous["unknown_count"] == 1
    assert ambiguous["matching_count"] == 0


def test_member_scope_and_partial_coverage_are_not_silently_expanded(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    observation = _diagnostic(
        source_revisions={"src.py": source["member"]["member_revision"]},
        scope=("src.py", "other.py"),
        diagnostics=[
            {"tool": "pyright", "path": "src.py", "rule": "A"},
            {"tool": "pyright", "path": "other.py", "rule": "B"},
        ],
    )
    result = _project(observation, source)

    assert result["matching_count"] == 1
    assert result["unclaimed_diagnostic_count"] == 1
    assert result["coverage"] == "complete-for-declared-members"


def test_empty_external_diagnostics_still_keep_declared_member_evidence(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    observation = _diagnostic(
        source_revisions={"src.py": source["member"]["member_revision"]},
        diagnostics=[],
    )
    result = _project(observation, source)
    assert result["matching_count"] == 1
    assert result["unclaimed_diagnostic_count"] == 0
    assert result["diagnostic_outcome"] == "fail"


def test_absent_revision_claim_never_infers_coverage(tmp_path: Path) -> None:
    source = _source(tmp_path)
    result = _project(_diagnostic(), source)
    assert result["coverage"] == "unknown"
    assert result["matching_count"] == 0
    assert result["unclaimed_diagnostic_count"] == 1
    assert result["ignored_source_observation_count"] == 1


def test_denied_or_unavailable_source_does_not_validate_claim(tmp_path: Path) -> None:
    source = _source(tmp_path)
    observation = _diagnostic(
        source_revisions={"src.py": source["member"]["member_revision"]}
    )
    unavailable = {
        **source,
        "availability": "unavailable",
        "member": {"path": "src.py", "state": "unknown"},
        "observation_identity": None,
    }
    result = _project(observation, unavailable)
    assert result["unknown_count"] == 1
    assert result["rows"][0]["reason"] == "source-member-not-revision-qualified"


def test_partial_literal_source_observation_does_not_prove_revision(
    tmp_path: Path,
) -> None:
    (tmp_path / "src.py").write_text("hit hit hit\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        source = codemap.source_observation("src.py", literal="hit", limit=1)
    observation = _diagnostic(
        source_revisions={"src.py": source["member"]["member_revision"]}
    )
    assert source["completeness"] == "incomplete"
    result = _project(observation, source)
    assert result["rows"][0]["reason"] == "source-member-not-revision-qualified"


def test_invalid_claims_fail_before_normalizing_diagnostic_rows() -> None:
    valid = "a" * 64
    wrong = "b" * 64
    for claims, scope in [
        ({"../../outside.py": valid}, ("src.py",)),
        ({"src.py": "sha256:" + valid}, ("src.py",)),
        ({"src.py": valid.upper()}, ("src.py",)),
        ({"src.py": ""}, ("src.py",)),
        ({"other.py": valid}, ("src.py",)),
        ({"src.py": valid, "./src.py": wrong}, ("src.py",)),
        ({str(i) + ".py": valid for i in range(33)}, ("src.py",)),
    ]:
        with pytest.raises(ValueError):
            _diagnostic(source_revisions=claims, scope=scope)


def test_exact_claims_have_stable_sorted_normalization() -> None:
    digest = "c" * 64
    observation = _diagnostic(
        scope=("b.py", "a.py"),
        source_revisions={"b.py": digest, "./a.py": digest},
        diagnostics=[],
    )
    assert list(observation["source_revisions"]) == ["a.py", "b.py"]


def test_wrong_observation_schema_or_invalid_source_input_is_not_accepted(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    observation = _diagnostic(
        source_revisions={"src.py": source["member"]["member_revision"]}
    )
    with pytest.raises(ValueError, match="diagnostic observation schema"):
        _project({**observation, "schema": "forged"}, source)
    with pytest.raises(ValueError, match="32 members"):
        _project(observation, *([source] * 33))
    with pytest.raises(ValueError, match="must contain mappings"):
        _project(observation, None)  # type: ignore[arg-type]


def test_unrelated_and_mismatched_path_source_packets_are_not_matched(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    observation = _diagnostic(
        source_revisions={"src.py": source["member"]["member_revision"]}
    )
    altered = {
        **source,
        "member": {**source["member"], "path": "outside.py"},
    }
    result = _project(observation, altered)
    assert result["unknown_count"] == 1
    assert result["ignored_source_observation_count"] == 1
    assert result["rows"][0]["reason"] == "source-observation-missing"
