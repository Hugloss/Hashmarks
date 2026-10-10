"""Real CLI processes and official MCP calls over genuine producer evidence."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from native_evidence_support import (
    TASK,
    dependency_capture,
    input_revisions,
    materialize_dependency,
    materialize_scip,
)

from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import FORMATS


def _cli(root: Path, state: Path, *command: str) -> Any:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hashmarks.cli",
            "--workspace",
            str(root),
            "--state-dir",
            str(state),
            *command,
        ],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "HASHMARKS_NO_UPDATE_CHECK": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_native_scip_cli_change_roundtrips_exact_packets(
    tmp_path: Path, native_scip_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    endpoints = []
    for endpoint in ("before", "after"):
        source = native_scip_corpus / "typescript" / endpoint
        materialize_scip(root, source)
        _cli(root, state, "map", "sync")
        _cli(
            root,
            state,
            "map",
            "import-scip",
            str(source / "index.json"),
            "--provenance",
            str(source / "provenance.json"),
        )
        packet = _cli(
            root,
            state,
            "structural-locality",
            "src/engine.ts::Engine",
            "--result-mode",
            "relationships",
        )
        saved = tmp_path / f"{endpoint}.json"
        saved.write_text(json.dumps(packet))
        endpoints.append(saved)
    response = _cli(
        root,
        state,
        "structural-locality-delta",
        "--before",
        str(endpoints[0]),
        "--after",
        str(endpoints[1]),
        "--result-mode",
        "relationships",
        "--presentation",
        "text",
    )
    delta = response["result"]
    assert delta["comparable"] is True
    assert len(delta["producer_deltas"][0]["facts"]["removed"]) == 1
    assert "- qualified producer claim:" in response["presentation"]["text"]
    assert response["presentation"]["text"].startswith("Subject:")


def test_native_python_cli_post_change_does_not_replay_index(
    tmp_path: Path, native_scip_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_scip_corpus / "python" / "before"
    materialize_scip(root, source)
    _cli(root, state, "map", "sync")
    _cli(
        root,
        state,
        "map",
        "import-scip",
        str(source / "index.json"),
        "--provenance",
        str(source / "provenance.json"),
    )
    response = _cli(root, state, "task-evidence", TASK, "--presentation", "text")
    previous = tmp_path / "task.json"
    previous.write_text(json.dumps(response["result"]))
    materialize_scip(root, native_scip_corpus / "python" / "after")
    response = _cli(
        root,
        state,
        "post-change",
        TASK,
        "--changed",
        "src/engine.py",
        "--previous-evidence",
        str(previous),
        "--presentation",
        "text",
    )
    assert response["result"]["semantic_relationships"]["after"] is None
    assert (
        "after: unavailable in task projection (unknown)"
        in response["presentation"]["text"]
    )
    assert "semantic_relationships" not in _cli(root, state, "task-evidence", TASK)


@pytest.mark.host_mcp_sdk
def test_native_dependency_mcp_comparison_formats_keep_version_change(
    tmp_path: Path, native_dependency_corpus: Path
) -> None:
    pytest.importorskip("mcp.server")
    from hashmarks.mcp_server import build_server

    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_dependency_corpus / "uv" / "v1"
    paths = materialize_dependency(root, source)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        before = cm.dependency_resolution_evidence(
            dependency_capture("uv", source, input_revisions(root, paths))
        )
    source = native_dependency_corpus / "uv" / "v2"
    paths = materialize_dependency(root, source)
    raw = dependency_capture("uv", source, input_revisions(root, paths))
    server: Any = build_server(root, state_dir=state)

    async def exercise() -> None:
        for format in FORMATS:
            reply = await server.call_tool(
                "dependency_codemap",
                {
                    "snapshot": raw,
                    "previous_observation": before,
                    "result_mode": "compare",
                    "presentation": format,
                },
            )
            assert reply.is_error is not True
            response = reply.structured_content
            native = response if format == "none" else response["result"]
            assert native["comparability"] == "comparable"
            transition = native["component_selection_transitions"][0]
            assert transition["removed"][0]["version"] == "1.0.0"
            assert transition["added"][0]["version"] == "2.0.0"
            if format == "text":
                assert response["presentation"]["text"].startswith(
                    "Dependency comparison: comparable\n"
                )
                assert '"version":"2.0.0"' in response["presentation"]["text"]

    try:
        asyncio.run(exercise())
    finally:
        server._hashmarks_surface.close()


def test_native_lsp_cli_stdout_keeps_unproven_body_query(
    tmp_path: Path, native_lsp_corpus: Path
) -> None:
    from native_evidence_support import lsp_capture

    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_lsp_corpus / "python" / "before"
    materialize_scip(root, source)
    _cli(root, state, "map", "sync")
    capture = tmp_path / "captured.json"
    capture.write_text(
        json.dumps({"observations": [lsp_capture(root, source, "body-definition")]})
    )
    for format in FORMATS:
        response = _cli(
            root,
            state,
            "structural-locality",
            "src/caller.py::caller",
            "--result-mode",
            "relationships",
            "--supplied-observations",
            str(capture),
            "--presentation",
            format,
        )
        native = response if format == "none" else response["result"]
        (claim,) = native["observations"][0]["claims"]
        assert claim["source"]["resolution"]["state"] == "unresolved"
        assert (
            claim["target"]["resolution"]["candidates"][0]["symbol_id"]
            == "src/callee.py::target"
        )
        assert native["producer_correspondence"]["unresolved_claims"] == 1


def _copy_dependency_inputs(root: Path, source: Path) -> list[str]:
    inputs = []
    for path in source.rglob("*"):
        if path.name in {"pyproject.toml", "uv.lock"}:
            name = path.relative_to(source).as_posix()
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(path.read_bytes())
            inputs.append(name)
    return inputs


@pytest.mark.host_mcp_sdk
def test_native_mcp_stdio_lsp_and_dependency_comparison_keep_semantic_facts(
    tmp_path: Path, native_lsp_corpus: Path, native_dependency_corpus: Path
) -> None:
    from native_evidence_support import lsp_capture

    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root, state = tmp_path / "repo", tmp_path / "state"
    lsp_source = native_lsp_corpus / "python" / "before"
    materialize_scip(root, lsp_source)
    source = native_dependency_corpus / "uv" / "v1"
    # Dependency files are additional inputs; preserve the LSP fixture's files.
    inputs = _copy_dependency_inputs(root, source)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        before = cm.dependency_resolution_evidence(
            dependency_capture("uv", source, input_revisions(root, inputs))
        )
    source = native_dependency_corpus / "uv" / "v2"
    inputs = _copy_dependency_inputs(root, source)
    raw = dependency_capture("uv", source, input_revisions(root, inputs))

    async def exercise() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "hashmarks.mcp_server",
                "--workspace",
                str(root),
                "--state-dir",
                str(state),
            ],
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for format in FORMATS:
                    reply = await session.call_tool(
                        "structural_locality",
                        {
                            "target": "src/callee.py::target",
                            "result_mode": "relationships",
                            "supplied_observations": [
                                lsp_capture(root, lsp_source, "incoming")
                            ],
                            "presentation": format,
                        },
                    )
                    assert reply.is_error is not True
                    response: Any = reply.structured_content
                    native = response if format == "none" else response["result"]
                    (claim,) = native["observations"][0]["claims"]
                    assert claim["basis"]["direction"] == "result-to-query"
                    assert (
                        claim["source"]["resolution"]["candidates"][0]["symbol_id"]
                        == "src/caller.py::caller"
                    )
                    assert (
                        claim["target"]["resolution"]["candidates"][0]["symbol_id"]
                        == "src/callee.py::target"
                    )
                    reply = await session.call_tool(
                        "dependency_codemap",
                        {
                            "snapshot": raw,
                            "previous_observation": before,
                            "result_mode": "compare",
                            "presentation": format,
                        },
                    )
                    assert reply.is_error is not True
                    response = reply.structured_content
                    native = response if format == "none" else response["result"]
                    (transition,) = native["component_selection_transitions"]
                    assert transition["component_id"] == "dummy-dep"
                    assert transition["removed"][0]["version"] == "1.0.0"
                    assert transition["added"][0]["version"] == "2.0.0"
                    if format != "none":
                        group = next(
                            group
                            for group in response["presentation"]["groups"]
                            if group["family"] == "dependency"
                        )
                        assert group["findings"][1]["details"] == transition

    asyncio.run(exercise())
