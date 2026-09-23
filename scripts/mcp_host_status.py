from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_TOOLS = (
    "repository_context",
    "find",
    "task_evidence",
    "change_impact",
    "post_change",
)
EXPECTED_UV_ARGS = [
    "run",
    "--frozen",
    "--no-sync",
    "hashmarks",
    "--workspace",
    ".",
    "mcp",
]


@dataclass(frozen=True)
class Check:
    status: str
    detail: str = ""


@dataclass(frozen=True)
class HostStatus:
    installed: Check
    project_registration: Check
    registration_source: Check
    registration_ownership: Check
    global_hashmarks_registration: Check
    discovery: Check
    last_successful_mcp_call: Check


def _run(
    argv: list[str], *, cwd: Path, timeout: int = 20
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _version(binary: str, *, cwd: Path) -> Check:
    path = shutil.which(binary)
    if path is None:
        return Check("NOT INSTALLED")
    result = _run([binary, "--version"], cwd=cwd)
    text = (result.stdout or result.stderr).strip().splitlines()
    detail = text[0] if text else path
    return Check("PASS" if result.returncode == 0 else "MISCONFIGURED", detail)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_uv_registration(command: Any, args: Any = None) -> bool:
    if isinstance(command, list):
        return command == ["uv", *EXPECTED_UV_ARGS]
    return command == "uv" and args == EXPECTED_UV_ARGS


def _receipt_registration_check(
    data: dict[str, Any], workspace: Path, registration_path: Path
) -> Check | None:
    registration = data.get("source_project_registration")
    if not isinstance(registration, dict):
        return Check("STALE", "receipt predates project-registration binding")
    try:
        relative_path = registration_path.relative_to(workspace).as_posix()
    except ValueError:
        return Check("STALE", "registration path is outside workspace")
    if registration.get("path") != relative_path or not registration_path.is_file():
        return Check("STALE", "project registration changed")
    if registration.get("sha256") != _sha256(registration_path):
        return Check("STALE", "project registration bytes changed")
    return None


def _receipt_host_check(
    data: dict[str, Any], host: str, installed: Check
) -> Check | None:
    host_receipt = data.get("host")
    if not isinstance(host_receipt, dict) or host_receipt.get("name") != host:
        return Check("STALE", "receipt predates host-version binding")
    if installed.status == "PASS" and host_receipt.get("version") != installed.detail:
        return Check("STALE", "installed host version changed")
    return None


def _latest_receipt_call(
    workspace: Path,
    host: str,
    *,
    installed: Check,
    registration_path: Path,
    candidate_identity: str,
) -> Check:
    receipt = workspace / "dist" / f"{host}-mcp-host-gate.json"
    data = _read_json(receipt)
    if not data or data.get("status") != "PASS":
        return Check("NOT RECORDED")

    expected_schema = f"hashmarks.{host}-mcp-host-gate.v1"
    if data.get("schema") != expected_schema:
        return Check("STALE", "receipt schema is not current")
    if data.get("source_repository_identity") != candidate_identity:
        return Check("STALE", "candidate source identity changed")

    for check in (
        _receipt_registration_check(data, workspace, registration_path),
        _receipt_host_check(data, host, installed),
    ):
        if check is not None:
            return check

    completed_at = data.get("completed_at")
    if not isinstance(completed_at, str) or not completed_at.strip():
        return Check("STALE", "receipt has no completion timestamp")
    return Check("PASS", completed_at)


def _opencode_discovery_ok(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode != 0:
        return False
    lines = [
        line.strip().lower()
        for line in f"{result.stdout}\n{result.stderr}".splitlines()
    ]
    matching = [line for line in lines if "hashmarks" in line]
    if not matching:
        return False
    bad = ("fail", "error", "disconnected", "not connected", "disabled", "unavailable")
    return any(
        "connected" in line and not any(marker in line for marker in bad)
        for line in matching
    )


def _claude_discovery_ok(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode != 0:
        return False
    lines = [
        line.strip().lower()
        for line in f"{result.stdout}\n{result.stderr}".splitlines()
    ]
    matching = [line for line in lines if "hashmarks" in line]
    if not matching:
        return False
    bad = ("fail", "error", "not found", "disconnected", "disabled", "unavailable")
    return not any(any(marker in line for marker in bad) for line in matching)


def _codex_discovery_ok(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get("name") == "hashmarks"


def _opencode(workspace: Path, candidate_identity: str) -> HostStatus:
    installed = _version("opencode", cwd=workspace)
    candidates = [
        workspace / "opencode.json",
        workspace / ".opencode" / "opencode.json",
    ]
    path = next(
        (candidate for candidate in candidates if candidate.exists()), candidates[0]
    )
    data = _read_json(path)
    entry = None if data is None else (data.get("mcp") or {}).get("hashmarks")
    if not isinstance(entry, dict):
        registration = Check("NOT REGISTERED")
        ownership = Check("NOT CHECKED")
    elif (
        entry.get("type") == "local"
        and entry.get("enabled", True) is True
        and _is_uv_registration(entry.get("command"))
    ):
        registration = Check("PASS")
        ownership = Check("HASHMARKS")
    else:
        registration = Check("FOREIGN CONFIG")
        ownership = Check("USER")
    source = (
        Check("PASS", str(path.relative_to(workspace)))
        if path.exists()
        else Check("NOT REGISTERED")
    )
    discovery = Check("NOT CHECKED")
    if installed.status == "PASS" and registration.status == "PASS":
        result = _run(["opencode", "mcp", "list"], cwd=workspace)
        discovery = Check(
            "PASS" if _opencode_discovery_ok(result) else "FAIL",
            _summarize_failure(result) if result.returncode else "",
        )
    return HostStatus(
        installed,
        registration,
        source,
        ownership,
        Check("NOT REQUIRED", "Hashmarks registration is project-local"),
        discovery,
        _latest_receipt_call(
            workspace,
            "opencode",
            installed=installed,
            registration_path=path,
            candidate_identity=candidate_identity,
        ),
    )


def _claude(workspace: Path, candidate_identity: str) -> HostStatus:
    installed = _version("claude", cwd=workspace)
    path = workspace / ".mcp.json"
    data = _read_json(path)
    entry = None if data is None else (data.get("mcpServers") or {}).get("hashmarks")
    if not isinstance(entry, dict):
        registration = Check("NOT REGISTERED")
        ownership = Check("NOT CHECKED")
    elif _is_uv_registration(entry.get("command"), entry.get("args")):
        registration = Check("PASS")
        ownership = Check("HASHMARKS")
    else:
        registration = Check("FOREIGN CONFIG")
        ownership = Check("USER")
    source = Check("PASS", ".mcp.json") if path.exists() else Check("NOT REGISTERED")
    discovery = Check("NOT CHECKED")
    if installed.status == "PASS" and registration.status == "PASS":
        result = _run(["claude", "mcp", "get", "hashmarks"], cwd=workspace)
        discovery = Check(
            "PASS" if _claude_discovery_ok(result) else "FAIL",
            _summarize_failure(result) if result.returncode else "",
        )
    return HostStatus(
        installed,
        registration,
        source,
        ownership,
        Check("NOT REQUIRED", "Hashmarks registration is project-local"),
        discovery,
        _latest_receipt_call(
            workspace,
            "claude",
            installed=installed,
            registration_path=path,
            candidate_identity=candidate_identity,
        ),
    )


def _codex_trust_override(workspace: Path) -> str:
    # Codex disables project-local config until the repository is trusted. Probe the
    # exact same config non-destructively with a runtime trust override so status can
    # distinguish "registration is valid but trust is required" from a broken config.
    path = json.dumps(str(workspace.resolve()))
    return f'projects={{{path}={{trust_level="trusted"}}}}'


def _summarize_failure(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stderr or result.stdout).strip().replace("\n", " ")
    return text[:180]


def _probe_codex_discovery(
    workspace: Path, installed: Check, registration: Check
) -> Check:
    if installed.status != "PASS" or registration.status != "PASS":
        return Check("NOT CHECKED")
    result = _run(["codex", "mcp", "get", "hashmarks", "--json"], cwd=workspace)
    if _codex_discovery_ok(result):
        return Check("PASS")
    trusted = _run(
        [
            "codex",
            "-c",
            _codex_trust_override(workspace),
            "mcp",
            "get",
            "hashmarks",
            "--json",
        ],
        cwd=workspace,
    )
    if _codex_discovery_ok(trusted):
        return Check(
            "PROJECT TRUST REQUIRED",
            "registration is valid; open Codex in this repository and trust the project once",
        )
    detail = _summarize_failure(result) or _summarize_failure(trusted)
    return Check("FAIL", detail)


def _codex(workspace: Path, candidate_identity: str) -> HostStatus:
    installed = _version("codex", cwd=workspace)
    path = workspace / ".codex" / "config.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    entry = (
        (data.get("mcp_servers") or {}).get("hashmarks")
        if isinstance(data, dict)
        else None
    )
    if not isinstance(entry, dict):
        registration = Check("NOT REGISTERED")
        ownership = Check("NOT CHECKED")
    elif entry.get("enabled", True) is True and _is_uv_registration(
        entry.get("command"), entry.get("args")
    ):
        registration = Check("PASS")
        ownership = Check("HASHMARKS")
    else:
        registration = Check("FOREIGN CONFIG")
        ownership = Check("USER")
    source = (
        Check("PASS", ".codex/config.toml")
        if path.exists()
        else Check("NOT REGISTERED")
    )
    discovery = _probe_codex_discovery(workspace, installed, registration)
    return HostStatus(
        installed,
        registration,
        source,
        ownership,
        Check("NOT REQUIRED", "Hashmarks registration is project-local"),
        discovery,
        _latest_receipt_call(
            workspace,
            "codex",
            installed=installed,
            registration_path=path,
            candidate_identity=candidate_identity,
        ),
    )


def _pi(workspace: Path, candidate_identity: str) -> dict[str, Check]:
    installed = _version("pi", cwd=workspace)
    adapter = Check("NOT CHECKED")
    if installed.status == "PASS":
        result = _run(["pi", "list"], cwd=workspace)
        text = f"{result.stdout}\n{result.stderr}".lower()
        adapter = Check(
            "PASS"
            if result.returncode == 0 and "pi-mcp-adapter" in text
            else "ADAPTER REQUIRED"
        )
    path = workspace / ".mcp.json"
    data = _read_json(path)
    entry = None if data is None else (data.get("mcpServers") or {}).get("hashmarks")
    if isinstance(entry, dict) and _is_uv_registration(
        entry.get("command"), entry.get("args")
    ):
        registration = Check("PASS")
        ownership = Check("HASHMARKS")
    elif isinstance(entry, dict):
        registration = Check("FOREIGN CONFIG")
        ownership = Check("USER")
    else:
        registration = Check("NOT REGISTERED")
        ownership = Check("NOT CHECKED")
    discovery = Check("NOT CHECKED")
    if adapter.status == "PASS" and registration.status == "PASS":
        discovery = Check(
            "READY",
            "pi-mcp-adapter loads project .mcp.json; live tool call not executed by status",
        )
    return {
        "installed": installed,
        "native_mcp": Check("NO", "Pi core intentionally has no native MCP client"),
        "mcp_adapter": adapter,
        "project_registration": registration,
        "registration_source": Check("PASS", ".mcp.json")
        if path.exists()
        else Check("NOT REGISTERED"),
        "registration_ownership": ownership,
        "global_hashmarks_registration": Check(
            "NOT REQUIRED", "Hashmarks registration is project-local"
        ),
        "discovery": discovery,
        "last_successful_mcp_call": _latest_receipt_call(
            workspace,
            "pi",
            installed=installed,
            registration_path=path,
            candidate_identity=candidate_identity,
        ),
    }


def collect(workspace: Path) -> dict[str, Any]:
    from hashmarks.mcp_surface import HashmarksMcpSurface
    from hashmarks.test_shards import repository_content_identity

    candidate_identity = repository_content_identity(
        workspace,
        excluded_paths=(workspace / "dist",),
    )

    catalog_ok = all(
        callable(getattr(HashmarksMcpSurface, name, None)) for name in EXPECTED_TOOLS
    )
    core = {
        "mcp_server_executable": Check(
            "PASS"
            if (workspace / ".venv" / "bin" / "hashmarks").exists()
            or shutil.which("hashmarks")
            else "NOT INSTALLED"
        ),
        "mcp_sdk": Check(
            "PASS" if importlib.util.find_spec("mcp") is not None else "NOT INSTALLED"
        ),
        "mcp_tool_catalog": Check(
            "PASS" if catalog_ok else "FAIL", f"{len(EXPECTED_TOOLS)} tools"
        ),
    }

    def host_dict(value: HostStatus) -> dict[str, dict[str, str]]:
        return {
            "installed": asdict(value.installed),
            "project_registration": asdict(value.project_registration),
            "registration_source": asdict(value.registration_source),
            "registration_ownership": asdict(value.registration_ownership),
            "global_hashmarks_registration": asdict(
                value.global_hashmarks_registration
            ),
            "discovery": asdict(value.discovery),
            "last_successful_mcp_call": asdict(value.last_successful_mcp_call),
        }

    return {
        "schema": "hashmarks.mcp-host-status.v2",
        "workspace": str(workspace),
        "source_repository_identity": candidate_identity,
        "core": {key: asdict(value) for key, value in core.items()},
        "opencode": host_dict(_opencode(workspace, candidate_identity)),
        "claude": host_dict(_claude(workspace, candidate_identity)),
        "codex": host_dict(_codex(workspace, candidate_identity)),
        "pi": {
            key: asdict(value)
            for key, value in _pi(workspace, candidate_identity).items()
        },
    }


def _line(label: str, check: dict[str, str]) -> str:
    suffix = f" ({check['detail']})" if check.get("detail") else ""
    return f"  {label:.<31} {check['status']}{suffix}"


def render(report: dict[str, Any]) -> str:
    rows = ["Hashmarks integration status", "", "Core"]
    rows.append(
        _line("MCP server executable ", report["core"]["mcp_server_executable"])
    )
    rows.append(_line("MCP SDK ", report["core"]["mcp_sdk"]))
    rows.append(_line("MCP tool catalog ", report["core"]["mcp_tool_catalog"]))
    for title, key in (
        ("OpenCode", "opencode"),
        ("Claude Code", "claude"),
        ("Codex", "codex"),
    ):
        host = report[key]
        rows.extend(["", title])
        rows.append(_line(f"{title} installed ", host["installed"]))
        rows.append(_line("Project registration ", host["project_registration"]))
        rows.append(_line("Registration source ", host["registration_source"]))
        rows.append(_line("Registration ownership ", host["registration_ownership"]))
        rows.append(
            _line(
                "Global Hashmarks registration ", host["global_hashmarks_registration"]
            )
        )
        rows.append(_line("MCP discovery ", host["discovery"]))
        rows.append(
            _line("Last successful MCP call ", host["last_successful_mcp_call"])
        )
    pi = report["pi"]
    rows.extend(["", "Pi"])
    rows.append(_line("Pi installed ", pi["installed"]))
    rows.append(_line("Native MCP client ", pi["native_mcp"]))
    rows.append(_line("MCP adapter ", pi["mcp_adapter"]))
    rows.append(_line("Project registration ", pi["project_registration"]))
    rows.append(_line("Registration source ", pi["registration_source"]))
    rows.append(_line("Registration ownership ", pi["registration_ownership"]))
    rows.append(
        _line("Global Hashmarks registration ", pi["global_hashmarks_registration"])
    )
    rows.append(_line("MCP discovery ", pi["discovery"]))
    rows.append(_line("Last successful MCP call ", pi["last_successful_mcp_call"]))
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect project-local Hashmarks MCP host integrations"
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    report = collect(workspace)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render(report))  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
