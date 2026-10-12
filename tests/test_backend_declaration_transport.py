"""Selected-source discovery retains input closure through public transports."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any, cast

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError
from scripts.repository_evaluation import backend_transport
from scripts.repository_evaluation.backend_transport import capture_cli, capture_mcp


def _source(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    (tmp_path / "backend.py").write_text(
        'raise RuntimeError("source must not execute")\n'
        "def factory():\n"
        "    class Payload(BaseModel):\n"
        "        value: str = Field(default_factory=str)\n"
        "    class Derived(Payload):\n"
        "        other: int\n"
    )
    state = tmp_path / "state"
    with CodeMap(tmp_path, state_dir=state) as cm:
        cm.sync()
        packet = cast(
            "dict[str, Any]",
            cm.repository_declarations_operation(
                [],
                result_mode="discovery",
                providers=(
                    StaticPythonBackendDeclarations(
                        paths=("backend.py",), include_class_fields=True
                    ),
                ),
            ),
        )
    return state, packet


def _assert_source_facts(packet: dict[str, Any], root: Path) -> None:
    assert packet["schema"] == "hashmarks.repository-declaration-discovery.v1"
    revision = hash_file(root / "backend.py", domain=FILE_DOMAIN).hash
    inputs = packet["providers"][0]["inputs"]
    assert len(inputs) == 1
    assert inputs[0]["path"] == "backend.py"
    assert inputs[0]["member_revision"] == revision
    assert inputs[0]["state"] == "known-present"
    groups = {g["scope"]["class_line"]: g for g in packet["declarations"]["groups"]}
    assert set(groups) == {3, 5}
    model = groups[3]["declarations"][0]["value"]
    derived = groups[5]["declarations"][0]["value"]
    assert model["fields"][0]["name"] == "value"
    assert model["fields"][0]["line"] == 4
    assert model["fields"][0]["default"]["keyword_names"] == ["default_factory"]
    assert derived["base_expressions"][0]["text"] == "Payload"
    assert [f["name"] for f in derived["fields"]] == ["other"]
    assert derived["inherited_fields"] == "not-established"
    assert derived["runtime_field_roles"] == "unknown"
    for group in groups.values():
        value = group["declarations"][0]["value"]
        assert value["runtime_binding"] == "not-established"
        assert value["negative_evidence_admissible"] is False
        assert group["correspondence"]["state"] == "unresolved"
        assert group["absence"]["state"] == "unknown"
    for binding in packet["declarations"]["repository_evidence"]["bindings"]:
        assert all(e["member_revision"] == revision for e in binding["evidence"])


def _request() -> dict[str, Any]:
    return {
        "operation": "repository_declarations",
        "inputs": {
            "groups": [],
            "result_mode": "discovery",
            "python_backend_paths": ["backend.py"],
            "include_class_fields": True,
        },
    }


def _assert_captures(
    captures: list[dict[str, Any]], packet: dict[str, Any], root: Path
) -> None:
    assert {c["format"] for c in captures} == {"none", "structured", "compact", "text"}
    for capture in captures:
        response = capture["response"]
        native = response.get("result", response)
        assert native == packet
        _assert_source_facts(native, root)
        if "presentation" in response:
            assert validate_evidence_presentation(native, response["presentation"])[
                "valid"
            ]
            refs = [
                ref
                for group in response["presentation"]["groups"]
                for finding in group["findings"]
                for ref in finding["source_refs"]
            ]
            assert any(ref.startswith("/declarations/groups/") for ref in refs)
            assert "/providers/0" in refs


def test_cli_selected_declarations_keep_bindings_in_every_format(
    tmp_path: Path,
) -> None:
    state, packet = _source(tmp_path)
    _assert_captures(capture_cli(tmp_path, state, _request()), packet, tmp_path)


@pytest.mark.host_mcp_sdk
def test_official_mcp_selected_declarations_keep_bindings_in_every_format(
    tmp_path: Path,
) -> None:
    state, packet = _source(tmp_path)
    _assert_captures(capture_mcp(tmp_path, state, _request()), packet, tmp_path)


@pytest.mark.host_mcp_sdk
def test_public_transports_reject_invalidated_source_before_refresh(
    tmp_path: Path,
) -> None:
    state, _ = _source(tmp_path)
    (tmp_path / "backend.py").write_text(
        "class Payload(BaseModel):\n    current: str\n"
    )
    for capture in (capture_cli, capture_mcp):
        with pytest.raises(ValueError, match="input changed"):
            capture(tmp_path, state, _request())


def test_discovery_rejects_mixed_claims_and_source_options_in_claim_mode(
    tmp_path: Path,
) -> None:
    state, _ = _source(tmp_path)
    with closing(HashmarksMcpSurface(str(tmp_path), state_dir=str(state))) as surface:
        with pytest.raises(McpSurfaceError, match="empty caller-supplied groups"):
            surface.repository_declarations(
                [{}], result_mode="discovery", python_backend_paths=["backend.py"]
            )
        with pytest.raises(McpSurfaceError, match="source selection requires"):
            surface.repository_declarations([], python_backend_paths=["backend.py"])
        with pytest.raises(McpSurfaceError, match="requires selected paths"):
            surface.repository_declarations(
                [], result_mode="discovery", include_class_fields=True
            )
        with pytest.raises(McpSurfaceError, match="boolean"):
            surface.repository_declarations(
                [], result_mode="discovery", include_class_fields=cast(Any, 1)
            )
        with pytest.raises(McpSurfaceError, match="must not contain"):
            surface.repository_declarations(
                [], result_mode="discovery", python_backend_paths=["../outside.py"]
            )


def test_discovery_previous_packet_cannot_restore_unselected_provider(
    tmp_path: Path,
) -> None:
    state, before = _source(tmp_path)
    with closing(HashmarksMcpSurface(str(tmp_path), state_dir=str(state))) as surface:
        empty = surface.repository_declarations(
            [], result_mode="discovery", previous_observation=before
        )
        assert empty["providers"] == []
        assert cast("dict", empty["declarations"])["groups"] == []
        current = surface.repository_declarations(
            [],
            result_mode="discovery",
            python_backend_paths=["backend.py"],
            include_class_fields=True,
        )
    assert current == before


def test_mcp_capture_keeps_multiple_transport_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failures = ExceptionGroup(
        "transport failed",
        [ValueError("response invalid"), RuntimeError("reader closed")],
    )

    async def failed_capture(*_args):
        raise failures

    monkeypatch.setattr(backend_transport, "_mcp_captures", failed_capture)
    with pytest.raises(ExceptionGroup) as raised:
        capture_mcp(tmp_path, tmp_path / "state", _request())
    assert raised.value is failures
