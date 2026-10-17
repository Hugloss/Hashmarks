"""Capture real CLI and official MCP responses for development qualification."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from hashmarks.codemap.python_ast import estimate_tokens
from hashmarks.evidence_presentation import FORMATS
from hashmarks.mcp_contract import tool_contract
from hashmarks.mcp_launch import installed_mcp_command

from .common import canonical_sha256

_JSON_CLI_OPERATIONS = {
    "correlate_evidence": "correlate-evidence",
    "dependency_codemap": "dependency-codemap",
    "repository_intelligence_query": "repository-intelligence-query",
}


def _capture(response: dict[str, Any], text: str, *, transport: str) -> dict[str, Any]:
    return {
        "transport": transport,
        "response": response,
        "consumer_visible_response": text,
        "utf8_bytes": len(text.encode("utf-8")),
        "estimated_tokens": estimate_tokens(text),
        "capture_identity": "sha256:"
        + canonical_sha256({"transport": transport, "text": text}),
    }


def _change_cli_arguments(inputs: dict[str, Any]) -> list[str]:
    allowed = {"task", "changed_paths", "changed_line_spans", "max_depth"}
    if set(inputs) - allowed:
        raise ValueError("backend CLI change capture requires matching public inputs")
    args = ["change-impact", inputs["task"]]
    for path in inputs["changed_paths"]:
        args.extend(("--changed", path))
    for span in inputs.get("changed_line_spans", []):
        args.extend(
            (
                "--changed-line-span",
                f"{span['path']}:{span['start_line']}:{span['end_line']}",
            )
        )
    if "max_depth" in inputs:
        args.extend(("--max-depth", str(inputs["max_depth"])))
    return args


def _source_cli_arguments(inputs: dict[str, Any]) -> list[str]:
    if (
        set(inputs) - {"paths", "context_lines", "result_mode"}
        or len(inputs["paths"]) != 1
        or inputs.get("result_mode", "member") != "member"
    ):
        raise ValueError("backend CLI source capture requires one member")
    args = ["source-observation", inputs["paths"][0]]
    context = inputs.get("context_lines", 0)
    if isinstance(context, dict):
        if set(context) != {"lines", "radius"} or context["radius"] != 1:
            raise ValueError(
                "backend CLI source capture requires matching line context"
            )
        for line in context["lines"]:
            args.extend(("--line", str(line)))
    elif context != 0:
        raise ValueError("backend CLI source capture requires matching line context")
    return args


def _declaration_cli_arguments(inputs: dict[str, Any]) -> list[str]:
    if (
        set(inputs)
        - {"groups", "result_mode", "python_backend_paths", "include_class_fields"}
        or inputs.get("groups") != []
        or inputs.get("result_mode") != "discovery"
        or not inputs.get("python_backend_paths")
        or type(inputs.get("include_class_fields", False)) is not bool
    ):
        raise ValueError(
            "backend CLI declaration capture requires selected source discovery"
        )
    args = ["repository-declarations"]
    for path in inputs["python_backend_paths"]:
        args.extend(("--python-backend-path", path))
    if inputs.get("include_class_fields"):
        args.append("--include-class-fields")
    return args


def _cli_arguments(operation: str, inputs: dict[str, Any]) -> list[str]:
    if operation == "task_evidence":
        args = ["task-evidence", inputs["task"]]
        for key, flag in (
            ("limit", "--limit"),
            ("per_role", "--per-role"),
            ("token_budget", "--budget"),
            ("result_mode", "--result-mode"),
        ):
            if key in inputs:
                args.extend((flag, str(inputs[key])))
        if set(inputs) - {"task", "limit", "per_role", "token_budget", "result_mode"}:
            raise ValueError("backend CLI capture requires source-only task inputs")
        return args
    if operation == "structural_locality":
        if set(inputs) - {"target", "result_mode"}:
            raise ValueError(
                "backend CLI structural capture requires matching public inputs"
            )
        return [
            "structural-locality",
            inputs["target"],
            "--result-mode",
            inputs.get("result_mode", "default"),
        ]
    source_captures = {
        "change_impact": _change_cli_arguments,
        "source_observation": _source_cli_arguments,
        "repository_declarations": _declaration_cli_arguments,
    }
    if operation in source_captures:
        return source_captures[operation](inputs)
    raise ValueError(f"backend CLI transport is not available for {operation}")


def capture_cli(
    workspace: Path, state: Path, case: dict[str, Any]
) -> list[dict[str, Any]]:
    if case["operation"] not in _JSON_CLI_OPERATIONS:
        return _cli_captures(workspace, state, case)
    with tempfile.TemporaryDirectory(prefix="hashmarks-observation-request-") as raw:
        request = Path(raw) / "input.json"
        request.write_text(json.dumps(case["inputs"]), encoding="utf-8")
        return _cli_captures(workspace, state, case, request)


def _cli_captures(
    workspace: Path,
    state: Path,
    case: dict[str, Any],
    request_path: Path | None = None,
) -> list[dict[str, Any]]:
    args = (
        _cli_arguments(case["operation"], case["inputs"])
        if request_path is None
        else [
            _JSON_CLI_OPERATIONS[case["operation"]],
            "--input-json",
            str(request_path),
        ]
    )
    captures = []
    for presentation in FORMATS:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "hashmarks.cli",
                "--workspace",
                str(workspace),
                "--state-dir",
                str(state),
                *args,
                "--presentation",
                presentation,
            ],
            env={**os.environ, "HASHMARKS_NO_UPDATE_CHECK": "1", "PYTHONUTF8": "1"},
            capture_output=True,
            check=False,
            text=True,
        )
        if completed.returncode:
            raise ValueError(f"backend CLI capture failed: {completed.stderr[-2000:]}")
        captures.append(
            {
                "format": presentation,
                **_capture(
                    json.loads(completed.stdout), completed.stdout, transport="cli"
                ),
            }
        )
    return captures


async def _mcp_captures(
    workspace: Path, state: Path, case: dict[str, Any]
) -> list[dict[str, Any]]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command = installed_mcp_command(
        Path(sys.executable).with_name("hashmarks"), workspace, state_dir=state
    )
    parameters = StdioServerParameters(
        command=command[0],
        args=list(command[1:]),
        env={**os.environ, "HASHMARKS_NO_UPDATE_CHECK": "1"},
    )
    captures = []
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for presentation in FORMATS:
                reply = await session.call_tool(
                    tool_contract(case["operation"]).name,
                    {**case["inputs"], "presentation": presentation},
                )
                if reply.is_error:
                    raise ValueError(f"backend MCP returned an error: {reply.content}")
                texts = [part.text for part in reply.content if part.type == "text"]
                initial = (
                    case["operation"] == "task_evidence"
                    and case["inputs"].get("result_mode") == "initial"
                )
                response = reply.structured_content
                if len(texts) != 1 or not isinstance(response, dict):
                    raise ValueError(
                        "backend MCP must provide one text and a native object"
                    )
                if initial:
                    from hashmarks.codemap.task_evidence_initial import (
                        decode_initial_packet,
                    )
                    from hashmarks.evidence_presentation import (
                        present_repository_evidence,
                    )

                    decode_initial_packet(response)
                    if presentation != "none":
                        projection = present_repository_evidence(
                            response, format=presentation
                        )
                        displayed = (
                            projection["text"]
                            if presentation == "text"
                            else json.loads(texts[0])
                        )
                        expected = texts[0] if presentation == "text" else projection
                        if displayed != expected:
                            raise ValueError(
                                "backend MCP initial projection differs from native packet"
                            )
                        response = {"result": response, "presentation": projection}
                elif json.loads(texts[0]) != response:
                    raise ValueError("backend MCP text and structured content disagree")
                # Both fields are consumer-visible. Count their duplication;
                # measuring only the pretty projection would hide real cost.
                visible = reply.model_dump_json(by_alias=True, exclude_none=True)
                captures.append(
                    {
                        "format": presentation,
                        **_capture(response, visible, transport="mcp"),
                    }
                )
    return captures


def capture_mcp(
    workspace: Path, state: Path, case: dict[str, Any]
) -> list[dict[str, Any]]:
    try:
        return asyncio.run(_mcp_captures(workspace, state, case))
    except ExceptionGroup as error:
        leaf: BaseException = error
        while isinstance(leaf, BaseExceptionGroup) and len(leaf.exceptions) == 1:
            leaf = leaf.exceptions[0]
        if isinstance(leaf, ValueError):
            raise ValueError(str(leaf)) from error
        raise
