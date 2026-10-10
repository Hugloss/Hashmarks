from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import FAMILIES, present_repository_evidence
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "alpha.py").write_text(
        "def target(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    return repo


def test_findings_separate_observation_move_candidate_and_capability_change() -> None:
    delta = {
        "schema": "hashmarks.repository-intelligence-delta.v1",
        "delta_identity": "test-identity",
        "semantic": {
            "symbols_added": [{"path": "src/alpha.py", "name": "target"}],
            "dependencies_removed": [{"path": "src/alpha.py", "name": "old"}],
            "possible_symbol_moves": [{"name": "target", "from": "a.py", "to": "b.py"}],
            "verification_changed": True,
            "freshness_changed": True,
        },
        "observer": {"changed": True},
        "completeness": {"changed": True},
    }
    result = present_repository_evidence(delta, format="structured")
    groups = {g["family"]: g for g in result["groups"]}
    assert tuple(FAMILIES) == (
        "source",
        "relationship",
        "dependency",
        "diagnostic",
        "verification",
        "correspondence",
        "qualification",
        "repository_structure",
        "retrieval_evidence",
        "ownership_evidence",
        "evidence_measurement",
    )
    assert groups["source"]["findings"][0]["assertion"] == "observed_change"
    assert (
        groups["correspondence"]["findings"][0]["assertion"]
        == "candidate_correspondence"
    )
    assert groups["relationship"]["findings"][0]["kind"] == "dependency_edge_removed"
    assert groups["qualification"]["count_observed_in_packet"] == 3
    assert result["source_evidence_identity"] == "test-identity"
    assert present_repository_evidence(delta, format="compact")["format"] == "compact"
    assert (
        "correspondence:" in present_repository_evidence(delta, format="text")["text"]
    )
    assert (
        "candidate_correspondence"
        in present_repository_evidence(delta, format="text")["text"]
    )


def test_diagnostic_disappearance_remains_only_a_producer_claim() -> None:
    packet = {
        "schema": "hashmarks.diagnostic-observation-delta.v1",
        "diagnostics": {
            "removed": [{"path": "src/alpha.py", "message": "fail"}],
            "possible_relocations": [{"from": "old", "to": "new"}],
        },
    }
    groups = present_repository_evidence(packet, format="structured")["groups"]
    assert groups[0]["family"] == "diagnostic"
    assert groups[0]["findings"][0]["kind"] == "diagnostic_missing_after"
    assert groups[0]["findings"][0]["assertion"] == "producer_claim"
    assert groups[1]["family"] == "correspondence"
    assert groups[1]["findings"][0]["assertion"] == "candidate_correspondence"


def test_presentation_rejects_unknown_modes_and_preserves_unknown_schema() -> None:
    with pytest.raises(ValueError, match="presentation must be"):
        present_repository_evidence({}, format="unsupported")
    result = present_repository_evidence({"schema": "new-schema"}, format="text")
    assert result["supported"] is False
    assert result["groups"] == []
    assert result["coverage"] == "unsupported"


def test_mcp_exposes_existing_authoritative_source_and_query_evidence(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        member = surface.source_observation(["src/alpha.py"], literal="target")
        assert member["schema"] == "hashmarks.source-observation.v1"
        assert member["observed_match_count"] == 1
        scoped = surface.source_observation(
            ["src/alpha.py"], literal="target", result_mode="scope"
        )
        assert scoped["schema"] == "hashmarks.scoped-source-occurrences.v1"
        profile = surface.repository_intelligence_query(
            "profile", "Explain target", ["src/alpha.py"]
        )
        assert profile["schema"] == "hashmarks.repository-intelligence-query.v1"
        assert profile["presentation"]["supported"]
        assert (
            profile["presentation"]["source_schema"] == "hashmarks.evidence-profile.v1"
        )
        with pytest.raises(McpSurfaceError, match="requires exactly one"):
            surface.source_observation(
                ["src/alpha.py", "src/beta.py"], literal="target"
            )
        with pytest.raises(McpSurfaceError, match="requires a literal"):
            surface.source_observation(["src/alpha.py"], result_mode="scope")
        with pytest.raises(McpSurfaceError, match="result_mode must be"):
            surface.source_observation(["src/alpha.py"], result_mode="invalid")
        with pytest.raises(McpSurfaceError, match="presentation must be"):
            surface.repository_intelligence_query(
                "profile",
                "Explain target",
                ["src/alpha.py"],
                presentation="unsafe",
            )
    finally:
        surface.close()


def test_core_presentation_does_not_replace_snapshot_or_mutate_producer(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    with CodeMap(repo) as codemap:
        codemap.sync()
        snapshot = codemap.repository_intelligence_snapshot(
            "Explain target", ["src/alpha.py"]
        )
        rendered = present_repository_evidence(snapshot, format="structured")
        assert snapshot["schema"] == "hashmarks.repository-intelligence-snapshot.v1"
        assert rendered["source_evidence_identity"] == snapshot["snapshot_identity"]
        assert rendered["authority"] == "descriptive-only"
        assert rendered == present_repository_evidence(snapshot, format="structured")


def test_mcp_evidence_binding_and_coverage_reuse_core_qualification(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        binding = surface.repository_evidence(
            {
                "bindings": [
                    {
                        "binding_id": "case:alpha",
                        "evidence": [{"scope": "member", "path": "src/alpha.py"}],
                    }
                ],
                "include_relationships": False,
            }
        )
        assert binding["schema"] == "hashmarks.repository-evidence-bindings.v1"
        coverage = surface.repository_evidence(
            {
                "bindings_packet": binding,
                "changed_paths": ["src/alpha.py"],
                "change_set_complete": False,
            },
            result_mode="coverage",
        )
        assert coverage["schema"] == "hashmarks.repository-evidence-coverage.v1"
        assert coverage["coverage"]["state"] == "incomplete"
        assert surface.repository_findings(["src/alpha.py"])["schema"] == (
            "hashmarks.repository-findings.v1"
        )
        with pytest.raises(McpSurfaceError, match="result_mode must be"):
            surface.repository_evidence({}, result_mode="unsupported")
    finally:
        surface.close()


def test_task_evidence_projection_exposes_source_owner_and_verifier_separately() -> (
    None
):
    native = {
        "schema": "hashmarks.task-evidence.v5",
        "retrieval": {
            "results": [{"path": "src/archive.py", "name": "write_archive"}],
            "bounds": {"canonical_completeness": "incomplete"},
        },
        "ownership": {
            "status": "resolved",
            "authority": "repository-ownership-only",
            "proof_scope_complete": True,
            "owner": {"path": "src/archive.py", "name": "write_archive"},
            "candidate": None,
            "source_evidence": {
                "representation": "source-range",
                "start_line": 12,
                "end_line": 21,
                "content": "ZipInfo(filename)",
            },
            "next_read": None,
        },
        "verification": {
            "selected": {
                "path": "tests/test_archive.py",
                "name": "test_write_archive",
            },
            "plan": {"argv": ["python", "-m", "pytest", "-q", "tests/test_archive.py"]},
            "authority": "repository-verification-evidence-only",
        },
        "evidence_receipt": {"freshness": "current"},
        "freshness": {"state": "current", "reason": None},
    }
    before = deepcopy(native)
    projection = present_repository_evidence(native, format="compact")
    groups = {group["family"]: group for group in projection["groups"]}
    source = groups["source"]["findings"][0]
    assert source["kind"] == "owner_source_evidence"
    assert source["source_refs"] == ["/ownership/source_evidence"]
    assert source["source_context"]["task_ownership"]["owner_path"] == "src/archive.py"
    assert source["details"]["content"] == "ZipInfo(filename)"
    ownership = groups["ownership_evidence"]["findings"]
    assert ownership[0]["kind"] == "qualified_owner"
    assert (
        ownership[0]["source_context"]["task_ownership"]["freshness_state"] == "current"
    )
    assert ownership[0]["source_refs"] == ["/ownership/owner"]
    verifiers = groups["verification"]["findings"]
    assert [row["kind"] for row in verifiers[:2]] == [
        "selected_verifier",
        "verification_plan",
    ]
    assert verifiers[0]["source_refs"] == ["/verification/selected"]
    assert verifiers[1]["source_refs"] == ["/verification/plan"]
    assert all(row["assertion"] == "producer_claim" for row in verifiers[:2])
    assert projection["authority"] == "descriptive-only"
    assert native == before
    assert (
        "owner_source_evidence"
        in present_repository_evidence(native, format="text")["text"]
    )


def test_task_evidence_ambiguous_next_read_remains_non_authoritative() -> None:
    native = {
        "schema": "hashmarks.task-evidence.v5",
        "retrieval": {"results": [], "bounds": {"canonical_truncation": "truncated"}},
        "ownership": {
            "status": "ambiguous",
            "authority": "repository-ownership-only",
            "proof_scope_complete": False,
            "owner": None,
            "candidate": {"path": "src/archive.py"},
            "source_evidence": None,
            "next_read": {
                "path": "src/archive.py",
                "reason": "ownership-ambiguity-discrimination",
                "authority": "non-authoritative-discrimination",
            },
        },
        "verification": {"selected": None, "plan": {}, "authority": ""},
        "evidence_receipt": {},
    }
    groups = {
        group["family"]: group
        for group in present_repository_evidence(native, format="structured")["groups"]
    }
    rows = groups["ownership_evidence"]["findings"]
    assert "qualified_owner" not in {row["kind"] for row in rows}
    assert rows[0]["kind"] == "owner_candidate"
    next_read = next(row for row in rows if row["kind"] == "discrimination_read")
    assert next_read["assertion"] == "producer_claim"
    assert next_read["source_context"]["task_ownership"]["status"] == "ambiguous"
    assert next_read["details"]["authority"] == "non-authoritative-discrimination"


def test_compact_source_hits_precede_member_inventory() -> None:
    native = {
        "schema": "hashmarks.scoped-source-occurrences.v1",
        "member_observations": [
            {"path": f"src/member_{number}.py", "state": "known-present"}
            for number in range(8)
        ],
        "occurrences": [
            {
                "path": "src/member_7.py",
                "line": 9,
                "column": 4,
                "literal": "ZipInfo",
                "occurrence_kind": "identifier",
            }
        ],
        "completeness": "incomplete",
        "truncation": "complete",
        "negative_evidence": "not-admissible",
    }
    projection = present_repository_evidence(native, format="compact")
    sources = next(
        group for group in projection["groups"] if group["family"] == "source"
    )
    assert sources["count_observed_in_packet"] == 9
    assert sources["omitted_from_presentation"] == 4
    assert sources["findings"][0]["kind"] == "occurrences"
    assert sources["findings"][0]["source_refs"] == ["/occurrences/0"]
    assert sources["findings"][0]["path"] == "src/member_7.py"
    assert projection["coverage"] == "projection-only"
    assert projection["source_context"][0]["details"]["negative_evidence"] == (
        "not-admissible"
    )


def test_literal_set_mcp_surface_preserves_modes_and_presentation(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "src" / "alpha.py").write_text(
        "def ZipInfo():\n    return ZIP_DEFLATED\n", encoding="utf-8"
    )
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        response = surface.source_observation(
            ["src/alpha.py"],
            literals=["ZIP_DEFLATED", "ZipInfo", "not-here"],
            result_mode="literals",
            limit=2,
        )
        assert response["schema"] == "hashmarks.scoped-source-literal-set.v1"
        assert response["observed_match_count"] == 2
        assert response["exact_match_count"] == 2
        presentation = present_repository_evidence(response, format="compact")
        groups = {group["family"]: group for group in presentation["groups"]}
        hits = groups["source"]["findings"]
        assert [row["details"]["literal"] for row in hits[:2]] == [
            "ZIP_DEFLATED",
            "ZipInfo",
        ]
        qualifications = groups["qualification"]["findings"]
        assert len(qualifications) == 3
        assert all(
            row["source_refs"] == [f"/literal_observations/{index}"]
            for index, row in enumerate(qualifications)
        )
        assert presentation["coverage"] == "projection-only"
        assert presentation["authority"] == "descriptive-only"
        with pytest.raises(McpSurfaceError, match="forbids literal"):
            surface.source_observation(
                ["src/alpha.py"],
                literal="ZipInfo",
                literals=["ZIP_DEFLATED"],
                result_mode="literals",
            )
        with pytest.raises(McpSurfaceError, match="requires literals result_mode"):
            surface.source_observation(
                ["src/alpha.py"], literals=["ZipInfo"], result_mode="member"
            )
        with pytest.raises(McpSurfaceError, match="distinct"):
            surface.source_observation(
                ["src/alpha.py"],
                literals=["ZipInfo", "ZipInfo"],
                result_mode="literals",
            )
        with pytest.raises(McpSurfaceError, match="exact single-line"):
            surface.source_observation(
                ["src/alpha.py"], literals=["bad\nquery"], result_mode="literals"
            )
    finally:
        surface.close()
