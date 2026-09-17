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
    "repository_context": "hashmarks.repository-capsule.v1",
    "find": "hashmarks.mcp-find.v1",
}


def _trust_override(repo: Path) -> str:
    path = json.dumps(str(repo.resolve()))
    return f'projects={{{path}={{trust_level="trusted"}}}}'


def _write_codex_config(repo: Path, hashmarks: Path) -> Path:
    path = repo / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    args = ["--workspace", str(repo), "mcp"]
    rendered_args = ", ".join(json.dumps(value) for value in args)
    path.write_text(
        "[mcp_servers.hashmarks]\n"
        f"command = {json.dumps(str(hashmarks))}\n"
        f"args = [{rendered_args}]\n"
        "enabled = true\n",
        encoding="utf-8",
    )
    return path


def _prompt() -> str:
    return (
        "Hashmarks 1.0 Codex host qualification. Use only the Hashmarks MCP server. "
        "Do not use shell, file, web, patch, or other built-in tools. "
        "Call hashmarks/repository_context exactly once with max_areas=8, then "
        "hashmarks/find exactly once with query='flare041' and limit=5. "
        "After the two calls reply exactly CODEX_HASHMARKS_HOST_GATE_COMPLETE."
    )


def _mcp_completed(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    forbidden = {"command_execution", "file_change", "web_search"}
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in forbidden:
            raise HostGateError(f"Codex used forbidden built-in tool surface: {item_type}")
        if item_type == "mcp_tool_call":
            completed.append(item)
    return completed


def _structured_payload(item: dict[str, Any], expected_schema: str) -> dict[str, Any]:
    if item.get("status") != "completed":
        raise HostGateError(
            f"Codex MCP call did not complete: {item.get('server')}/{item.get('tool')} status={item.get('status')!r}"
        )
    result = item.get("result")
    if not isinstance(result, dict):
        raise HostGateError("Codex MCP call has no structured result")
    payload = result.get("structured_content")
    if payload is None:
        payload = result.get("structuredContent")
    if not isinstance(payload, dict) or payload.get("schema") != expected_schema:
        raise HostGateError(
            f"Codex MCP call returned unexpected schema: {None if not isinstance(payload, dict) else payload.get('schema')!r}"
        )
    if "BUILDING" in json.dumps(payload, sort_keys=True):
        raise HostGateError("transient BUILDING state escaped through Codex")
    return payload


def _validate_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    calls = _mcp_completed(events)
    if len(calls) != len(EXPECTED):
        observed = [(row.get("server"), row.get("tool"), row.get("status")) for row in calls]
        raise HostGateError(f"Codex did not make exactly two required MCP calls: {observed}")
    by_tool: dict[str, dict[str, Any]] = {}
    for item in calls:
        if item.get("server") != "hashmarks":
            raise HostGateError(f"Codex used unexpected MCP server: {item.get('server')!r}")
        tool = str(item.get("tool"))
        if tool not in EXPECTED:
            raise HostGateError(f"Codex used unexpected Hashmarks MCP tool: {tool!r}")
        if tool in by_tool:
            raise HostGateError(f"Codex called Hashmarks MCP tool more than once: {tool}")
        by_tool[tool] = _structured_payload(item, EXPECTED[tool])
    if set(by_tool) != set(EXPECTED):
        raise HostGateError(f"Codex missing required Hashmarks MCP tools: {sorted(set(EXPECTED) - set(by_tool))}")
    found = by_tool["find"].get("results")
    if not isinstance(found, list) or not any(
        isinstance(row, dict) and row.get("path") == "src/feature.py" for row in found
    ):
        raise HostGateError("Codex-hosted Hashmarks find did not return src/feature.py")
    return by_tool


def _looks_like_headless_mcp_approval_block(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "user cancelled mcp tool call",
        "mcp tool call" ,
        "approval",
        "cancelled",
    )
    return "mcp" in lowered and any(marker in lowered for marker in markers)


def _gate(args: argparse.Namespace, project_root: Path) -> dict[str, Any]:
    if shutil.which(args.codex) is None:
        raise HostGateEnvironmentBlocked(f"{args.codex!r} is not installed")
    version = run([args.codex, "--version"], cwd=project_root).stdout.strip()
    source = source_binding(project_root, project_root / ".codex" / "config.toml")

    receipt_path = Path(args.receipt).resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    event_log = receipt_path.with_name(receipt_path.stem + "-events.jsonl")

    with tempfile.TemporaryDirectory(prefix="hashmarks-codex-host-gate-") as tmp_text:
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
        config_path = _write_codex_config(repo, hashmarks)

        argv = [args.codex, "-c", _trust_override(repo), "exec", "--json", "--skip-git-repo-check", "-C", str(repo)]
        if args.dangerous_bypass:
            argv.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            argv.extend(["--sandbox", "read-only"])
        if args.model:
            argv.extend(["-m", args.model])
        argv.append(_prompt())

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
            detail = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            if not args.dangerous_bypass and _looks_like_headless_mcp_approval_block(detail):
                raise HostGateEnvironmentBlocked(
                    "Codex exec blocked the MCP call in non-interactive read-only mode. "
                    "The gate does not bypass the sandbox by default. Rerun only if you accept the disposable-repo risk with CODEX_HOST_DANGEROUS=1."
                )
            raise HostGateError(f"Codex host process failed ({result.returncode})\n{detail}")

        events = parse_jsonl(result.stdout, host="Codex")
        payloads = _validate_events(events)
        return {
            "schema": "hashmarks.codex-mcp-host-gate.v1",
            "status": "PASS",
            "completed_at": completed_at(),
            **source,
            "host": {"name": "codex", "version": version},
            "model": args.model or "configured-default",
            "dangerous_bypass": bool(args.dangerous_bypass),
            "python_selector": args.python,
            "installed_versions": versions,
            "wheel": {"name": wheel.name, "sha256": sha256(wheel)},
            "qualified_registration": {
                "path": str(config_path.relative_to(repo)),
                "sha256": sha256(config_path),
            },
            "observed_tools": sorted(payloads),
            "event_log": {"path": str(event_log), "sha256": sha256(event_log)},
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Qualify the installed Hashmarks MCP wheel through Codex CLI.")
    parser.add_argument("--model", default="")
    parser.add_argument("--python", default="3.14")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--dangerous-bypass", action="store_true")
    parser.add_argument("--receipt", default="dist/codex-mcp-host-gate.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    receipt_path = Path(args.receipt).resolve()
    try:
        receipt = _gate(args, project_root)
    except HostGateEnvironmentBlocked as exc:
        receipt = {
            "schema": "hashmarks.codex-mcp-host-gate.v1",
            "status": "ENVIRONMENT_BLOCKED",
            "error": str(exc),
        }
        code = 2
    except (HostGateError, OSError, subprocess.TimeoutExpired) as exc:
        receipt = {
            "schema": "hashmarks.codex-mcp-host-gate.v1",
            "status": "FAIL",
            "error": str(exc),
        }
        code = 1
    else:
        code = 0
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"HASHMARKS CODEX MCP HOST GATE: {receipt['status']}\nreceipt: {receipt_path}")
    if receipt["status"] != "PASS" and receipt.get("error"):
        print(receipt["error"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
