"""Examples and the registered MCP tool consume the same provider contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest

from examples.make_shell_declarations import run_example as make_shell_example
from examples.python_uv_manifest_declarations import run_example as manifest_example
from hashmarks.codemap.repository_declaration_selection import (
    source_declaration_providers,
)
from hashmarks.mcp_sdk_server import close_sdk_server


def test_make_shell_example_reports_changed_and_incomplete_evidence(
    tmp_path: Path,
) -> None:
    result = make_shell_example(tmp_path)
    before, after = cast("dict", result["before"]), cast("dict", result["after"])
    assert before["observation_identity"] != after["observation_identity"]
    assert after["providers"][0]["provenance"]["missing_selected_paths"] == [
        "missing.sh"
    ]
    assert after["delta_from_previous"]["declarations"]["changed_groups"]


def test_manifest_example_retains_native_resolution_and_changed_source_mismatch(
    tmp_path: Path,
) -> None:
    result = manifest_example(tmp_path)
    dependencies = cast("dict", result["dependencies"])
    changed = cast("dict", result["dependencies_with_previous_inputs"])
    assert {row["source_equivalence"] for row in dependencies["repository_inputs"]} == {
        "proven"
    }
    mismatches = [
        row["path"]
        for row in changed["repository_inputs"]
        if row["source_equivalence"] == "mismatch"
    ]
    assert mismatches == ["packages/demo/pyproject.toml"]
    assert dependencies["selections"] == changed["selections"]


@pytest.mark.host_mcp_sdk
@pytest.mark.parametrize(
    "selection, expected",
    [
        (
            {"make_shell": {"make_paths": ["Makefile"], "shell_paths": ["demo.sh"]}},
            "make-shell-syntax",
        ),
        ({"python_uv_manifest_paths": ["pyproject.toml"]}, "python-uv-manifests"),
    ],
)
def test_registered_mcp_discovery_accepts_each_new_source_selector(
    tmp_path: Path,
    selection: dict,
    expected: str,
) -> None:
    pytest.importorskip("mcp")
    from mcp.types import CallToolResult

    from hashmarks.mcp_server import build_server

    (tmp_path / "Makefile").write_text("all:\n\techo fixture\n", encoding="utf-8")
    (tmp_path / "demo.sh").write_text("echo fixture\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\ndemo="pkg:main"\n', encoding="utf-8"
    )
    server = build_server(tmp_path, tool_names=("repository_declarations",))

    async def exercise() -> None:
        result = await server.call_tool(
            "repository_declarations",
            {
                "groups": [],
                "result_mode": "discovery",
                "source_selection": selection,
            },
        )
        assert isinstance(result, CallToolResult)
        assert result.is_error is not True
        packet = result.structured_content
        assert isinstance(packet, dict)
        assert packet["schema"] == "hashmarks.repository-declaration-discovery.v1"
        assert packet["providers"][0]["name"] == expected
        assert packet["declarations"]["groups"]
        assert all(row["member_revision"] for row in packet["providers"][0]["inputs"])

    try:
        asyncio.run(exercise())
    finally:
        close_sdk_server(server)


@pytest.mark.parametrize(
    "selection",
    [
        {"make_shell": {"shell_paths": ["../outside.sh"]}},
        {"make_shell": {"make_paths": ["Makefile"], "execute": True}},
        {"python_uv_manifest_paths": "pyproject.toml"},
    ],
)
def test_source_selection_rejects_scope_and_execution_expansion(
    selection: dict,
) -> None:
    with pytest.raises(ValueError):
        source_declaration_providers("discovery", selection)


def test_new_source_selection_requires_discovery_mode() -> None:
    with pytest.raises(ValueError, match="requires result_mode=discovery"):
        source_declaration_providers(
            "observe", {"python_uv_manifest_paths": ["pyproject.toml"]}
        )
