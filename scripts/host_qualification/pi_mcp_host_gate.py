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

from mcp_host_gate_common import (
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
    "hashmarks_repository_context": "hashmarks.repository-capsule.v1",
    "hashmarks_find": "hashmarks.mcp-find.v1",
}


def _write_pi_config(repo: Path, hashmarks: Path) -> Path:
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
        "Hashmarks 1.0 Pi host qualification. Use only the Pi MCP proxy tool named mcp. "
        "First call mcp with tool='hashmarks_repository_context' and args={\"max_areas\":8}. "
        "Then call mcp with tool='hashmarks_find' and args={\"query\":\"flare041\",\"limit\":5}. "
        "Do not call any other tool. Reply exactly PI_HASHMARKS_HOST_GATE_COMPLETE after both calls."
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


def _validate_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    starts: dict[str, dict[str, Any]] = {}
    ends: dict[str, dict[str, Any]] = {}
    for event in events:
        event_type = event.get("type")
        if event_type == "tool_execution_start":
            tool_name = str(event.get("toolName"))
            if tool_name != "mcp":
                raise HostGateError(f"Pi used unexpected tool: {tool_name}")
            call_id = str(event.get("toolCallId"))
            starts[call_id] = event
        elif event_type == "tool_execution_end":
            tool_name = str(event.get("toolName"))
            if tool_name != "mcp":
                raise HostGateError(f"Pi used unexpected tool: {tool_name}")
            call_id = str(event.get("toolCallId"))
            ends[call_id] = event

    if len(starts) != 2 or len(ends) != 2 or set(starts) != set(ends):
        raise HostGateError(
            f"Pi did not execute exactly two MCP proxy calls: starts={len(starts)} ends={len(ends)}"
        )

    observed: dict[str, dict[str, Any]] = {}
    for call_id, start in starts.items():
        args = start.get("args")
        if not isinstance(args, dict):
            raise HostGateError("Pi MCP proxy call has no argument object")
        target = args.get("tool")
        if target not in EXPECTED:
            raise HostGateError(f"Pi MCP proxy targeted unexpected tool: {target!r}")
        if target in observed:
            raise HostGateError(f"Pi MCP proxy called tool more than once: {target}")
        end = ends[call_id]
        if end.get("isError") is True:
            raise HostGateError(f"Pi MCP proxy reported an error for {target}")
        result = end.get("result")
        schemas = _schemas_in(result)
        expected_schema = EXPECTED[str(target)]
        if expected_schema not in schemas:
            raise HostGateError(
                f"Pi MCP proxy result for {target} did not expose schema {expected_schema}"
            )
        if "BUILDING" in json.dumps(result, sort_keys=True, default=str):
            raise HostGateError("transient BUILDING state escaped through Pi")
        observed[str(target)] = end
    return observed


def _adapter_installed(pi: str, project_root: Path) -> bool:
    result = subprocess.run(
        [pi, "list"],
        cwd=project_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return False
    lines = [line.strip().lower() for line in f"{result.stdout}\n{result.stderr}".splitlines()]
    return any("pi-mcp-adapter" in line for line in lines)


def _gate(args: argparse.Namespace, project_root: Path) -> dict[str, Any]:
    if shutil.which(args.pi) is None:
        raise HostGateEnvironmentBlocked(f"{args.pi!r} is not installed")
    version = run([args.pi, "--version"], cwd=project_root).stdout.strip()
    if not _adapter_installed(args.pi, project_root):
        raise HostGateEnvironmentBlocked(
            "pi-mcp-adapter is not installed; run: pi install npm:pi-mcp-adapter"
        )
    source = source_binding(project_root, project_root / ".mcp.json")

    receipt_path = Path(args.receipt).resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    event_log = receipt_path.with_name(receipt_path.stem + "-events.jsonl")

    with tempfile.TemporaryDirectory(prefix="hashmarks-pi-host-gate-") as tmp_text:
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
        config_path = _write_pi_config(repo, hashmarks)

        argv = [
            args.pi,
            "--mode",
            "json",
            "--no-session",
            "--approve",
            "--no-builtin-tools",
            "--tools",
            "mcp",
            "--model",
            args.model,
            _prompt(),
        ]
        result = subprocess.run(
            argv,
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=900,
            check=False,
        )
        event_log.write_text(result.stdout, encoding="utf-8")
        if result.returncode != 0:
            raise HostGateError(
                f"Pi host process failed ({result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        events = parse_jsonl(result.stdout, host="Pi")
        observed = _validate_events(events)
        return {
            "schema": "hashmarks.pi-mcp-host-gate.v1",
            "status": "PASS",
            "completed_at": completed_at(),
            **source,
            "host": {"name": "pi", "version": version},
            "model": args.model,
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
    parser = argparse.ArgumentParser(description="Qualify the installed Hashmarks MCP wheel through Pi + pi-mcp-adapter.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--python", default="3.14")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--pi", default="pi")
    parser.add_argument("--receipt", default="dist/pi-mcp-host-gate.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    receipt_path = Path(args.receipt).resolve()
    try:
        receipt = _gate(args, project_root)
    except HostGateEnvironmentBlocked as exc:
        receipt = {
            "schema": "hashmarks.pi-mcp-host-gate.v1",
            "status": "ENVIRONMENT_BLOCKED",
            "error": str(exc),
        }
        code = 2
    except (HostGateError, OSError, subprocess.TimeoutExpired) as exc:
        receipt = {
            "schema": "hashmarks.pi-mcp-host-gate.v1",
            "status": "FAIL",
            "error": str(exc),
        }
        code = 1
    else:
        code = 0
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"HASHMARKS PI MCP HOST GATE: {receipt['status']}\nreceipt: {receipt_path}")
    if receipt["status"] != "PASS" and receipt.get("error"):
        print(receipt["error"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
