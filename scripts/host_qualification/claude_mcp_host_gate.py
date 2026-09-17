from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from mcp_host_gate_common import (  # noqa: E402 - import follows standalone script path setup
    HostGateEnvironmentBlocked,
    HostGateError,
    build_installed_wheel,
    completed_at,
    parse_jsonl,
    run,
    sha256,
    source_binding,
    write_fixture,
)

EXPECTED = {
    "mcp__hashmarks__repository_context": "hashmarks.repository-capsule.v1",
    "mcp__hashmarks__find": "hashmarks.mcp-find.v1",
}


def _write_claude_config(repo: Path, hashmarks: Path) -> Path:
    path = repo / ".mcp.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "hashmarks": {
                        "command": str(hashmarks),
                        "args": ["--workspace", str(repo), "mcp"],
                    }
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _prompt() -> str:
    return (
        "Hashmarks 1.0 Claude Code host qualification. Use only the Hashmarks MCP tools. "
        "Do not use built-in file, shell, web, task, or edit tools. "
        "Call mcp__hashmarks__repository_context exactly once with max_areas=8, then "
        "mcp__hashmarks__find exactly once with query='flare041' and limit=5. "
        "After the two calls reply exactly CLAUDE_HASHMARKS_HOST_GATE_COMPLETE."
    )


def _schemas_in(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        schema = value.get("schema")
        if isinstance(schema, str):
            found.add(schema)
        for item in value.values():
            found.update(_schemas_in(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_schemas_in(item))
    elif isinstance(value, str):
        for schema in EXPECTED.values():
            if schema in value:
                found.add(schema)
    return found


def _init_catalog(events: list[dict[str, Any]]) -> tuple[bool, set[str]]:
    for event in events:
        if event.get("type") != "system" or event.get("subtype") != "init":
            continue
        servers = event.get("mcp_servers")
        connected = False
        if isinstance(servers, list):
            connected = any(
                isinstance(row, dict)
                and row.get("name") == "hashmarks"
                and str(row.get("status", "")).lower() == "connected"
                for row in servers
            )
        tools = event.get("tools")
        offered = {str(value) for value in tools} if isinstance(tools, list) else set()
        return connected, offered
    return False, set()


def _tool_uses(events: list[dict[str, Any]]) -> dict[str, str]:
    uses: dict[str, str] = {}
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name"))
            if name not in EXPECTED:
                raise HostGateError(f"Claude Code used unexpected tool: {name}")
            tool_id = str(block.get("id"))
            if name in uses:
                raise HostGateError(
                    f"Claude Code called Hashmarks tool more than once: {name}"
                )
            uses[name] = tool_id
    return uses


def _tool_results(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("type") != "user":
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_id = str(block.get("tool_use_id"))
            results[tool_id] = block
    return results


def _validate_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    connected, offered = _init_catalog(events)
    if not connected:
        raise HostGateEnvironmentBlocked(
            "Claude Code did not report the project Hashmarks MCP server connected"
        )
    missing_offered = set(EXPECTED) - offered
    if missing_offered:
        raise HostGateEnvironmentBlocked(
            "Claude Code connected to Hashmarks but did not expose required MCP tools in the model-visible catalog: "
            + ", ".join(sorted(missing_offered))
        )
    uses = _tool_uses(events)
    if set(uses) != set(EXPECTED):
        raise HostGateError(
            f"Claude Code did not call required Hashmarks tools: {sorted(set(EXPECTED) - set(uses))}"
        )
    results = _tool_results(events)
    validated: dict[str, dict[str, Any]] = {}
    for name, tool_id in uses.items():
        result = results.get(tool_id)
        if result is None:
            raise HostGateError(f"Claude Code emitted no tool_result for {name}")
        if result.get("is_error") is True:
            raise HostGateError(f"Claude Code reported an MCP error for {name}")
        expected_schema = EXPECTED[name]
        if expected_schema not in _schemas_in(result.get("content")):
            raise HostGateError(
                f"Claude Code result for {name} did not expose schema {expected_schema}"
            )
        if "BUILDING" in json.dumps(result, sort_keys=True, default=str):
            raise HostGateError("transient BUILDING state escaped through Claude Code")
        validated[name] = result
    return validated


def _gate(args: argparse.Namespace, project_root: Path) -> dict[str, Any]:
    if shutil.which(args.claude) is None:
        raise HostGateEnvironmentBlocked(f"{args.claude!r} is not installed")
    version = run([args.claude, "--version"], cwd=project_root).stdout.strip()
    source = source_binding(project_root, project_root / ".mcp.json")

    receipt_path = Path(args.receipt).resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    event_log = receipt_path.with_name(receipt_path.stem + "-events.jsonl")

    with tempfile.TemporaryDirectory(prefix="hashmarks-claude-host-gate-") as tmp_text:
        tmp = Path(tmp_text)
        wheel, _python, hashmarks, versions = build_installed_wheel(
            project_root=project_root,
            tmp=tmp,
            uv=args.uv,
            python_selector=args.python,
        )
        repo = tmp / "repo"
        repo.mkdir()
        write_fixture(repo)
        config_path = _write_claude_config(repo, hashmarks)

        argv = [
            args.claude,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "bypassPermissions",
            "--allowedTools",
            ",".join(EXPECTED),
        ]
        if args.model:
            argv.extend(["--model", args.model])
        result = subprocess.run(
            argv,
            cwd=repo,
            input=_prompt(),
            text=True,
            capture_output=True,
            timeout=900,
            check=False,
        )
        event_log.write_text(result.stdout, encoding="utf-8")
        if result.returncode != 0:
            raise HostGateError(
                f"Claude Code host process failed ({result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        events = parse_jsonl(result.stdout, host="Claude Code")
        observed = _validate_events(events)
        return {
            "schema": "hashmarks.claude-mcp-host-gate.v1",
            "status": "PASS",
            "completed_at": completed_at(),
            **source,
            "host": {"name": "claude", "version": version},
            "model": args.model or "configured-default",
            "python_selector": args.python,
            "installed_versions": versions,
            "wheel": {"name": wheel.name, "sha256": sha256(wheel)},
            "qualified_registration": {
                "path": str(config_path.relative_to(repo)),
                "sha256": sha256(config_path),
            },
            "observed_tools": sorted(observed),
            "event_log": {"path": str(event_log), "sha256": sha256(event_log)},
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Qualify the installed Hashmarks MCP wheel through Claude Code CLI."
    )
    parser.add_argument("--model", default="")
    parser.add_argument("--python", default="3.14")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--claude", default="claude")
    parser.add_argument("--receipt", default="dist/claude-mcp-host-gate.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    receipt_path = Path(args.receipt).resolve()
    try:
        receipt = _gate(args, project_root)
    except HostGateEnvironmentBlocked as exc:
        receipt = {
            "schema": "hashmarks.claude-mcp-host-gate.v1",
            "status": "ENVIRONMENT_BLOCKED",
            "error": str(exc),
        }
        code = 2
    except (HostGateError, OSError, subprocess.TimeoutExpired) as exc:
        receipt = {
            "schema": "hashmarks.claude-mcp-host-gate.v1",
            "status": "FAIL",
            "error": str(exc),
        }
        code = 1
    else:
        code = 0
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(  # noqa: T201 - intentional command output
        f"HASHMARKS CLAUDE MCP HOST GATE: {receipt['status']}\nreceipt: {receipt_path}"
    )
    if receipt["status"] != "PASS" and receipt.get("error"):
        print(receipt["error"])  # noqa: T201 - intentional command output
    return code


if __name__ == "__main__":
    raise SystemExit(main())
