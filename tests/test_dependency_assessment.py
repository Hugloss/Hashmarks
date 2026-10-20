from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from contract_assertions import assert_object, assert_records
from test_dependency_derivation_explain import _snapshot

from hashmarks import CodeMap, hash_file
from hashmarks.file_store import UnstableFileError

RepositoryFixture = tuple[CodeMap, dict[str, object]]


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[RepositoryFixture]:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "dependency.lock").write_bytes(b"before\n")
    snapshot: dict[str, Any] = _snapshot()
    snapshot["repository_inputs"] = [
        {
            "path": "dependency.lock",
            "member_revision": hash_file(workspace / "dependency.lock").hash,
        }
    ]
    with CodeMap(workspace, state_dir=tmp_path / "state") as codemap:
        yield codemap, snapshot


def test_exact_input_freshness_does_not_require_global_index_freshness(
    repository: RepositoryFixture,
) -> None:
    codemap, raw_snapshot = repository
    snapshot = cast("dict[str, Any]", raw_snapshot)
    observation = codemap.dependencies.observe(snapshot)
    assessment = codemap.dependencies.assessment(observation)

    assert assessment["repository_freshness"] == "unknown"
    assert assert_object(assessment["source_scope"])["freshness"] == "current"
    assert assert_object(assessment["source_scope"])["source_equivalence"] == "proven"
    assert assert_object(assessment["source_scope"])["availability"] == "available"
    assert assert_object(assessment["resolved_inventory"])["completeness"] == "complete"
    assert (
        assert_object(assessment["resolved_inventory"])["negative_evidence"]
        == "admissible-within-declared-scope"
    )
    assert assessment["observation_identity"] == observation["observation_identity"]


def test_inventory_assessment_includes_uncovered_declared_context(
    repository: RepositoryFixture,
) -> None:
    codemap, raw_snapshot = repository
    snapshot = cast("dict[str, Any]", raw_snapshot)
    snapshot["contexts"].append("uncovered")
    assessment = codemap.dependencies.assessment(codemap.dependencies.observe(snapshot))

    assert assert_object(assessment["resolved_inventory"])["completeness"] == "unknown"
    contexts = {
        row["context"]: row
        for row in assert_records(
            assert_object(assessment["resolved_inventory"])["contexts"]
        )
    }
    assert contexts["runtime"]["completeness"] == "complete"
    assert contexts["uncovered"]["completeness"] == "unknown"
    assert contexts["uncovered"]["negative_evidence"] == "not-admissible"
    assert (
        assert_object(assessment["resolved_inventory"])["negative_evidence"]
        == "not-admissible"
    )


@pytest.mark.parametrize(
    ("completeness", "truncation", "expected"),
    [
        ("incomplete", "complete", "incomplete"),
        ("incomplete", "truncated", "incomplete"),
        ("unknown", "unknown", "unknown"),
    ],
)
def test_inventory_coverage_keeps_partial_and_truncated_evidence_unproven(
    repository: RepositoryFixture, completeness: str, truncation: str, expected: str
) -> None:
    codemap, raw_snapshot = repository
    snapshot = cast("dict[str, Any]", raw_snapshot)
    inventory = next(
        row for row in snapshot["coverage"] if row["kind"] == "resolved-inventory"
    )
    inventory.update(completeness=completeness, truncation=truncation)
    assessment = codemap.dependencies.assessment(codemap.dependencies.observe(snapshot))

    assert assert_object(assessment["source_scope"])["freshness"] == "current"
    assert assert_object(assessment["resolved_inventory"])["completeness"] == expected
    assert (
        assert_object(assessment["resolved_inventory"])["negative_evidence"]
        == "not-admissible"
    )


def test_missing_producer_revision_remains_unknown_with_current_native_source(
    repository: RepositoryFixture,
) -> None:
    codemap, raw_snapshot = repository
    snapshot = cast("dict[str, Any]", raw_snapshot)
    snapshot["repository_inputs"][0].pop("member_revision")
    assessment = codemap.dependencies.assessment(codemap.dependencies.observe(snapshot))

    assert assert_object(assessment["source_scope"])["freshness"] == "current"
    assert assert_object(assessment["source_scope"])["source_equivalence"] == "unknown"
    assert (
        assert_object(assessment["resolved_inventory"])["negative_evidence"]
        == "not-admissible"
    )


def test_mismatched_producer_claim_does_not_relabel_current_native_source(
    repository: RepositoryFixture,
) -> None:
    codemap, raw_snapshot = repository
    snapshot = cast("dict[str, Any]", raw_snapshot)
    snapshot["repository_inputs"][0]["member_revision"] = "0" * 64
    assessment = codemap.dependencies.assessment(codemap.dependencies.observe(snapshot))

    assert assert_object(assessment["source_scope"])["freshness"] == "current"
    assert assert_object(assessment["source_scope"])["source_equivalence"] == "mismatch"
    assert (
        assert_object(assessment["resolved_inventory"])["negative_evidence"]
        == "not-admissible"
    )


def test_matching_claim_does_not_repair_missing_retained_source_evidence(
    repository: RepositoryFixture,
) -> None:
    codemap, raw_snapshot = repository
    snapshot = cast("dict[str, Any]", raw_snapshot)
    member = codemap.workspace / "dependency.lock"
    member.unlink()
    observation = codemap.dependencies.observe(snapshot)
    member.write_bytes(b"before\n")
    assessment = codemap.dependencies.assessment(observation)

    assert assert_object(assessment["source_scope"])["source_equivalence"] == "proven"
    assert assert_object(assessment["source_scope"])["freshness"] == "unknown"
    assert (
        assert_object(assessment["resolved_inventory"])["negative_evidence"]
        == "not-admissible"
    )


@pytest.mark.parametrize("mutation", ["edit", "delete", "deny"])
def test_retained_inputs_are_reobserved_before_absence(
    repository: RepositoryFixture, mutation: str
) -> None:
    codemap, raw_snapshot = repository
    snapshot = cast("dict[str, Any]", raw_snapshot)
    observation = codemap.dependencies.observe(snapshot)
    member = codemap.workspace / "dependency.lock"
    if mutation == "edit":
        member.write_bytes(b"change\n")
    elif mutation == "delete":
        member.unlink()
    else:
        (codemap.workspace / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern="dependency.lock"\nindex=false\n'
        )
        codemap.index.sync()
    assessment = codemap.dependencies.assessment(observation)

    assert assert_object(assessment["source_scope"])["freshness"] == (
        "unknown" if mutation == "deny" else "stale"
    )
    assert (
        assert_object(assessment["resolved_inventory"])["negative_evidence"]
        == "not-admissible"
    )
    if mutation != "edit":
        assert (
            assert_object(assessment["source_scope"])["availability"] == "unavailable"
        )


def test_assessment_rejects_source_drift_during_multi_input_observation(
    repository: RepositoryFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    codemap, raw_snapshot = repository
    snapshot = cast("dict[str, Any]", raw_snapshot)
    second = codemap.workspace / "second.lock"
    second.write_bytes(b"second\n")
    snapshot["repository_inputs"].append(
        {"path": "second.lock", "member_revision": hash_file(second).hash}
    )
    observation = codemap.dependencies.observe(snapshot)
    original = codemap.source.observe
    calls = 0

    def observe(path: str, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        value = original(path, max_bytes=int(cast("int", kwargs["max_bytes"])))
        calls += 1
        if calls == 2:
            (codemap.workspace / "dependency.lock").write_bytes(b"change\n")
        return value

    monkeypatch.setattr(codemap.source, "observe", observe)
    with pytest.raises(UnstableFileError, match="inputs changed during assessment"):
        codemap.dependencies.assessment(observation)


def test_retained_dependency_packet_tampering_is_rejected_before_source_reads(
    repository: RepositoryFixture,
) -> None:
    codemap, raw_snapshot = repository
    snapshot = cast("dict[str, Any]", raw_snapshot)
    observation = codemap.dependencies.observe(snapshot)
    observation["inventory"] = []
    with pytest.raises(ValueError, match="identity mismatch|not normalized"):
        codemap.dependencies.assessment(observation)


def _git(workspace: Path, *arguments: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Observer Test",
            "-c",
            "user.email=observer@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *arguments,
        ],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )


def test_unrelated_git_commit_does_not_invalidate_exact_input_correspondence(
    repository: RepositoryFixture,
) -> None:
    codemap, snapshot = repository
    _git(codemap.workspace, "init")
    _git(codemap.workspace, "add", "dependency.lock")
    _git(codemap.workspace, "commit", "-m", "Initial input")
    observation = codemap.dependencies.observe(snapshot)
    (codemap.workspace / "unrelated.txt").write_text("unrelated change\n")
    _git(codemap.workspace, "add", "unrelated.txt")
    _git(codemap.workspace, "commit", "-m", "Unrelated change")

    assessment = codemap.dependencies.assessment(observation)

    assert assessment["repository_freshness"] == "stale"
    source = assert_object(assessment["source_scope"])
    assert source["freshness"] == "current"
    assert source["source_equivalence"] == "proven"
    inventory = assert_object(assessment["resolved_inventory"])
    assert inventory["negative_evidence"] == "admissible-within-declared-scope"
