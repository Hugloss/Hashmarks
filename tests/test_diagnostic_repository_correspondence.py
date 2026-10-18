"""Local producer claims retain ambiguity and old source identity after an edit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_object, assert_records, assert_text

from hashmarks import CodeMap
from hashmarks.codemap.diagnostic_observation import external_diagnostic_observation
from hashmarks.codemap.diagnostic_source_revision import (
    diagnostic_source_revision_evidence,
)
from hashmarks.codemap.repository_delta import RepositoryGenerationBinding

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[CodeMap]:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    for name in ("service", "alternative"):
        (root / "src" / f"{name}.py").write_text(
            "def handle_request():\n    return 'original'\n", encoding="utf-8"
        )
    with CodeMap(
        root, state_dir=tmp_path / "state", artifact_db=tmp_path / "artifacts.sqlite3"
    ) as codemap:
        codemap.index.sync()
        yield codemap


def _correlate(repository: CodeMap, anchor: dict[str, object]) -> dict[str, object]:
    return repository.correlation.observe(
        [
            {
                "bundle_id": "synthetic-diagnostic",
                "producer": {"kind": "example-test"},
                "scope": {"kind": "supplied-source-location"},
                "completeness": "unknown",
                "truncation": "unknown",
                "anchors": [anchor],
            }
        ],
        include_relationships=False,
    )


def test_ambiguous_diagnostic_preserves_both_repository_candidates(
    repository: CodeMap,
) -> None:
    packet = _correlate(
        repository,
        {
            "anchor_id": "ambiguous-location",
            "symbol": "handle_request",
            "metadata": {"message": "fictional assertion failed"},
        },
    )
    bundle = assert_records(packet["bundles"])[0]
    anchor = assert_records(bundle["anchors"])[0]
    resolution = assert_object(anchor["resolution"])

    assert resolution["state"] == "resolved-ambiguous"
    assert resolution["candidate_completeness"] == "complete"
    candidates = assert_records(resolution["candidates"])
    assert len(candidates) == 2
    assert {row["path"] for row in candidates} == {
        "src/service.py",
        "src/alternative.py",
    }
    assert "repository_path" not in resolution
    assert assert_object(anchor["source_equivalence"])["state"] == "unknown"
    assert (
        assert_object(packet["completeness"])["negative_evidence"] == "not-admissible"
    )
    assert packet["authority"] == "repository-intelligence-only"
    assert packet["interpretation_authority"] == "consumer-owned"
    assert packet["execution_effect"] == "none"
    assert packet["storage"] == "request-scoped-not-persisted"


def test_current_repository_does_not_rebind_diagnostic_to_edited_source(
    repository: CodeMap,
) -> None:
    before = repository.source.observe("src/service.py", lines=[2])
    original_revision = assert_text(assert_object(before["member"])["member_revision"])
    (repository.workspace / "src/service.py").write_text(
        "def handle_request():\n    return 'edited'\n", encoding="utf-8"
    )
    repository.index.sync()
    current = repository.source.observe("src/service.py", lines=[2])
    current_revision = assert_text(assert_object(current["member"])["member_revision"])
    assert current_revision != original_revision
    assert current["generation"] != before["generation"]

    packet = _correlate(
        repository,
        {
            "anchor_id": "old-source-location",
            "path": "src/service.py",
            "line": 2,
            "member_revision": original_revision,
        },
    )
    anchor = assert_records(assert_records(packet["bundles"])[0]["anchors"])[0]
    assert assert_object(anchor["resolution"])["state"] == "resolved-unique"
    assert assert_object(anchor["source_equivalence"])["state"] == "mismatch"
    assert assert_object(anchor["claims"])["member_revision"] == original_revision

    repository_evidence = assert_object(packet["repository_evidence"])
    identity = assert_object(repository_evidence["repository"])
    generation = before["generation"]
    assert isinstance(generation, int)
    diagnostic = external_diagnostic_observation(
        producer="example-test",
        binding=RepositoryGenerationBinding(
            assert_text(identity["repository_identity"]), generation
        ),
        diagnostics=[{"tool": "example-test", "path": "src/service.py", "line": 2}],
        outcome="fail",
        scope_paths=["src/service.py"],
        source_revisions={"src/service.py": original_revision},
    )
    comparison = diagnostic_source_revision_evidence(diagnostic, [current])
    row = assert_records(comparison["rows"])[0]
    assert row["state"] == "different"
    assert row["producer_claimed_member_revision"] == original_revision
    assert row["observed_member_revision"] == current_revision
    assert row["source_freshness"] == current["freshness"]
    assert row["generation_relation"] == "different"
    assert row["claim_authority"] == "producer-claimed"
    assert comparison["authority"] == "descriptive-source-revision-correspondence-only"
    assert comparison["execution_effect"] == "none"
