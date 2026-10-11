"""Initial disclosure preserves producer authority and accounts for omissions."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import initial_task_evidence
from hashmarks.evidence_presentation import FORMATS, presentation_response
from hashmarks.mcp_contract import tool_contract
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError


@pytest.mark.parametrize("ambiguous", [False, True])
def test_initial_profile_preserves_authority_and_source_identity(
    tmp_path: Path, ambiguous: bool
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/a.py").write_text("def widget():\n    return 1\n")
    if ambiguous:
        (tmp_path / "src/b.py").write_text("def widget():\n    return 2\n")
    (tmp_path / "tests/test_widget.py").write_text(
        "from src.a import widget\ndef test_widget():\n    assert widget() == 1\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        native = cast("dict[str, Any]", codemap.task_evidence("Fix widget"))
        before = deepcopy(native)
        initial = initial_task_evidence(native)
        api = cast(
            "dict[str, Any]",
            codemap.task_evidence("Fix widget", result_mode="initial"),
        )
    assert native == before
    assert api["schema"] == "hashmarks.task-evidence-initial.v1"
    assert initial["source_evidence_identity"] == native["evidence_packet_identity"]
    assert api["evidence_packet_identity"] != api["source_evidence_identity"]
    for key in ("status", "authority", "proof_scope", "proof_scope_complete", "basis"):
        assert initial["ownership"][key] == native["ownership"][key]
    assert (
        initial["ownership"]["ambiguity"]["ambiguous"]
        == (native["ownership"]["ambiguity"]["ambiguous"])
    )
    assert initial["freshness"] == native["freshness"]
    assert initial["provenance"] == native["provenance"]
    assert initial["verification"]["plan"] == native["verification"]["plan"]
    assert (
        initial["verification"]["relevance"]["task_matches"]
        == (native["verification"]["relevance"]["task_matches"])
    )
    if native["ownership"]["owner"] is None:
        assert initial["ownership"]["owner"] is None
    else:
        assert (
            initial["ownership"]["owner"]["path"]
            == (native["ownership"]["owner"]["path"])
        )
    assert initial["initial_projection"]["negative_evidence_from_omissions"] == (
        "not-admissible"
    )
    assert "/related" in initial["initial_projection"]["omissions"]["sections"]
    for mode in FORMATS:
        response = presentation_response(
            "task_evidence", api, result_mode="initial", format=mode
        )
        tool_contract("task_evidence").validate_response(
            response, result_mode="initial", presentation=mode
        )
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        observed = cast(
            "dict[str, Any]", surface.task_evidence("Fix widget", result_mode="initial")
        )
        assert observed["schema"] == api["schema"]
        assert observed["ownership"]["status"] == api["ownership"]["status"]
    finally:
        surface.close()


def test_initial_mode_rejects_unknown_mode_before_observation(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap, pytest.raises(ValueError, match="result_mode"):
        codemap.task_evidence("Fix widget", result_mode="invented")
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        with pytest.raises(McpSurfaceError, match="result_mode") as caught:
            surface.task_evidence("Fix widget", result_mode="invented")
        assert caught.value.reason == "invalid-request"
    finally:
        surface.close()
