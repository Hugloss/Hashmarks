from __future__ import annotations

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
        "source_change",
        "relationship_change",
        "dependency_change",
        "diagnostic_observation",
        "verification_evidence",
        "correspondence",
        "evidence_qualification",
    )
    assert groups["source_change"]["findings"][0]["assertion"] == "observed_change"
    assert (
        groups["correspondence"]["findings"][0]["assertion"]
        == "candidate_correspondence"
    )
    assert (
        groups["relationship_change"]["findings"][0]["kind"]
        == "dependency_edge_removed"
    )
    assert groups["evidence_qualification"]["count_observed_in_packet"] == 3
    assert result["source_evidence_identity"] == "test-identity"
    assert present_repository_evidence(delta, format="compact")["format"] == "compact"
    assert (
        "correspondence:" in present_repository_evidence(delta, format="text")["text"]
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
    assert groups[0]["family"] == "diagnostic_observation"
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
