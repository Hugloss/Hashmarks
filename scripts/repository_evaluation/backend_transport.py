"""Capture real CLI and official MCP responses for development qualification."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from hashmarks.codemap.python_ast import estimate_tokens
from hashmarks.evidence_presentation import FORMATS
from hashmarks.mcp_contract import tool_contract
from hashmarks.mcp_launch import installed_mcp_command

from .common import canonical_sha256


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


def _cli_arguments(operation: str, inputs: dict[str, Any]) -> list[str]:
    if operation == "task_evidence":
        args = ["task-evidence", inputs["task"]]
        for key, flag in (
            ("limit", "--limit"),
            ("per_role", "--per-role"),
            ("token_budget", "--budget"),
        ):
            if key in inputs:
                args.extend((flag, str(inputs[key])))
        if set(inputs) - {"task", "limit", "per_role", "token_budget"}:
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
    raise ValueError(f"backend CLI transport is not available for {operation}")


def capture_cli(
    workspace: Path, state: Path, case: dict[str, Any]
) -> list[dict[str, Any]]:
    args = _cli_arguments(case["operation"], case["inputs"])
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
                if len(texts) != 1 or json.loads(texts[0]) != reply.structured_content:
                    raise ValueError("backend MCP text and structured content disagree")
                # Both fields are consumer-visible. Count their duplication;
                # measuring only the pretty projection would hide real cost.
                visible = reply.model_dump_json(by_alias=True, exclude_none=True)
                captures.append(
                    {
                        "format": presentation,
                        **_capture(reply.structured_content, visible, transport="mcp"),
                    }
                )
    return captures


def capture_mcp(
    workspace: Path, state: Path, case: dict[str, Any]
) -> list[dict[str, Any]]:
    return asyncio.run(_mcp_captures(workspace, state, case))
