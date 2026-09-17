from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_HASHMARKS_TOOLS = {
    "hashmarks_repository_context",
    "hashmarks_find",
    "hashmarks_task_evidence",
    "hashmarks_change_impact",
    "hashmarks_post_change",
}
TASK = "change flare041 behavior and verify it"
CHANGED_PATH = "src/feature.py"


class HostGateError(RuntimeError):
    pass


class HostGateEnvironmentBlocked(HostGateError):
    pass


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        command = " ".join(argv)
        raise HostGateError(
            f"command failed ({result.returncode}): {command}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _venv_executable(venv: Path, name: str) -> Path:
    if os.name == "nt":
        suffix = ".exe" if name in {"python", "hashmarks"} else ""
        return venv / "Scripts" / f"{name}{suffix}"
    return venv / "bin" / name


def _parse_jsonl(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HostGateError(f"OpenCode emitted non-JSON stdout on line {line_number}: {line!r}") from exc
        if not isinstance(value, dict):
            raise HostGateError(f"OpenCode JSON event {line_number} is not an object")
        events.append(value)
    if not events:
        raise HostGateError("OpenCode emitted no JSON events")
    return events


def _session_id(events: list[dict[str, Any]]) -> str:
    for event in events:
        session_id = event.get("sessionID")
        if isinstance(session_id, str) and session_id:
            return session_id
    raise HostGateError("OpenCode JSON events did not expose a sessionID")


def _tool_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "tool_use":
            continue
        part = event.get("part")
        if isinstance(part, dict) and part.get("type") == "tool":
            rows.append(part)
    return rows


def _assert_completed_tool_set(
    events: list[dict[str, Any]], expected: set[str]
) -> dict[str, dict[str, Any]]:
    tool_parts = _tool_events(events)
    observed_list = [str(part.get("tool")) for part in tool_parts]
    observed = set(observed_list)
    unexpected = observed - EXPECTED_HASHMARKS_TOOLS
    missing = expected - observed
    if unexpected:
        raise HostGateError(f"OpenCode used unexpected tools: {sorted(unexpected)}")
    if missing:
        raise HostGateError(f"OpenCode did not call required tools: {sorted(missing)}")
    duplicates = sorted(tool for tool in observed if observed_list.count(tool) > 1)
    if duplicates:
        raise HostGateError(f"OpenCode called qualification tools more than once: {duplicates}")
    extra_hashmarks = observed - expected
    if extra_hashmarks:
        raise HostGateError(f"OpenCode called Hashmarks tools outside this phase: {sorted(extra_hashmarks)}")
    completed: dict[str, dict[str, Any]] = {}
    for part in tool_parts:
        tool = str(part.get("tool"))
        state = part.get("state")
        if not isinstance(state, dict) or state.get("status") != "completed":
            raise HostGateError(f"OpenCode tool did not complete successfully: {tool}")
        completed[tool] = part
    return completed


def _decode_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            return None
        try:
            decoded, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            return None
    return decoded if isinstance(decoded, dict) else None


def _tool_payload(part: dict[str, Any], expected_schema: str) -> dict[str, Any]:
    state = part.get("state")
    if not isinstance(state, dict):
        raise HostGateError("OpenCode tool event has no state object")
    payload = _decode_json_object(state.get("output"))
    if payload is None:
        raise HostGateError(f"unable to decode structured output for {part.get('tool')}")
    if payload.get("schema") != expected_schema:
        raise HostGateError(
            f"unexpected schema from {part.get('tool')}: {payload.get('schema')!r}"
        )
    if "BUILDING" in json.dumps(payload, sort_keys=True):
        raise HostGateError(f"transient BUILDING state escaped through {part.get('tool')}")
    return payload


def _write_fixture(repo: Path) -> None:
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "feature.py").write_text(
        "def flare041(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_feature.py").write_text(
        "from src.feature import flare041\n\n"
        "def test_flare041():\n    assert flare041(1) == 2\n",
        encoding="utf-8",
    )


def _opencode_server_config(hashmarks: Path, repo: Path) -> dict[str, Any]:
    # Match the narrow OpenCode registration shape used by mature integrations:
    # one local command, explicitly enabled. Use an absolute workspace path so
    # correctness does not depend on the host subprocess working directory.
    return {
        "type": "local",
        "command": [str(hashmarks), "--workspace", str(repo), "mcp"],
        "enabled": True,
    }


def _write_opencode_project_config(repo: Path, hashmarks: Path) -> Path:
    # Use the root project config path supported by OpenCode 2.0.x and current releases.
    # This deliberately avoids OPENCODE_CONFIG/OPENCODE_CONFIG_CONTENT because
    # those override paths have changed across host versions and are not what a
    # normal user installation exercises.
    path = repo / "opencode.json"
    doc = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {"hashmarks": _opencode_server_config(hashmarks, repo)},
    }
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _configure_opencode_mcp(
    opencode: str,
    *,
    repo: Path,
    hashmarks: Path,
) -> tuple[subprocess.CompletedProcess[str], str, dict[str, str]]:
    config_path = _write_opencode_project_config(repo, hashmarks)
    env = os.environ.copy()
    # Force this gate to exercise natural project-config discovery. A caller's
    # runtime config override must not mask the config we are qualifying.
    env.pop("OPENCODE_CONFIG", None)
    env.pop("OPENCODE_CONFIG_CONTENT", None)
    result = _run([opencode, "mcp", "list"], cwd=repo, env=env, timeout=120)
    lines = [line.strip().lower() for line in f"{result.stdout}\n{result.stderr}".splitlines()]
    matching = [line for line in lines if "hashmarks" in line]
    bad = ("fail", "error", "disconnected", "not connected", "disabled", "unavailable")
    if any("connected" in line and not any(marker in line for marker in bad) for line in matching):
        return result, str(config_path.relative_to(repo)), env
    raise HostGateError(
        "OpenCode did not report the repo-local Hashmarks MCP registration as connected.\n"
        f"config: {config_path}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

def _phase1_prompt() -> str:
    return f"""Hashmarks 1.0 host qualification. Use only the Hashmarks MCP tools; built-in repository tools are forbidden.
Call these tools and do not edit any file:
1. hashmarks_repository_context with max_areas=12.
2. hashmarks_find with query=flare041 and limit=5.
3. hashmarks_task_evidence with task={TASK!r}, limit=20, per_role=3, token_budget=512.
4. hashmarks_change_impact with task={TASK!r}, changed_paths=[{CHANGED_PATH!r}], max_depth=4.
Do not call hashmarks_post_change yet. After the four calls, reply exactly HOST_GATE_PHASE1_COMPLETE.
"""


def _phase2_prompt(previous_evidence: dict[str, Any]) -> str:
    encoded = json.dumps(previous_evidence, separators=(",", ":"), ensure_ascii=False)
    return f"""Continue the Hashmarks 1.0 host qualification. The harness externally changed {CHANGED_PATH}; do not edit or read files with built-in tools.
Call hashmarks_post_change exactly once with task={TASK!r}, changed_paths=[{CHANGED_PATH!r}], token_budget=512, and previous_evidence equal to this exact JSON object:
{encoded}
Then call hashmarks_repository_context exactly once with max_areas=12.
Do not call any other tool. Reply exactly HOST_GATE_PHASE2_COMPLETE.
"""


def _opencode_run(
    opencode: str,
    *,
    repo: Path,
    model: str,
    prompt: str,
    env: dict[str, str],
    session_id: str | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [
        opencode,
        "run",
        "--dangerously-skip-permissions",
        "--dir",
        str(repo),
        "--model",
        model,
        "--format",
        "json",
    ]
    if session_id is None:
        argv.extend(["--title", "Hashmarks MCP 1.0 host gate"])
    else:
        argv.extend(["--session", session_id])
    argv.append(prompt)
    return _run(argv, cwd=repo, env=env, timeout=900)


def _package_versions(python: Path) -> dict[str, str]:
    code = (
        "import importlib.metadata as m,json;"
        "print(json.dumps({n:m.version(n) for n in ('hashmarks','mcp')},sort_keys=True))"
    )
    output = _run([str(python), "-I", "-c", code], cwd=python.parent).stdout
    value = json.loads(output)
    return {str(key): str(version) for key, version in value.items()}


def _opencode_version(version_text: str) -> tuple[int, int]:
    match = re.search(r"(?:^|\D)(\d+)\.(\d+)", version_text)
    if match is None:
        raise HostGateError(f"unable to parse OpenCode version from {version_text.strip()!r}")
    version = (int(match.group(1)), int(match.group(2)))
    if version < (1, 18):
        raise HostGateError(
            f"OpenCode 1.18 or newer is required for this host gate; found {version_text.strip()!r}"
        )
    return version


def _host_gate(args: argparse.Namespace, project_root: Path) -> dict[str, Any]:
    from hashmarks.test_shards import repository_content_identity

    if shutil.which(args.opencode) is None:
        raise HostGateEnvironmentBlocked(
            f"{args.opencode!r} is not installed; install OpenCode before running this gate"
        )
    opencode_version = _run([args.opencode, "--version"], cwd=project_root).stdout.strip()
    _opencode_version(opencode_version)
    source_registration = project_root / "opencode.json"
    if not source_registration.is_file():
        raise HostGateError("project opencode.json registration is missing")
    source_repository_identity = repository_content_identity(
        project_root,
        excluded_paths=(project_root / "dist",),
    )

    receipt_path = Path(args.receipt).resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    phase1_log = receipt_path.with_name(receipt_path.stem + "-phase1.jsonl")
    phase2_log = receipt_path.with_name(receipt_path.stem + "-phase2.jsonl")

    with tempfile.TemporaryDirectory(prefix="hashmarks-opencode-host-gate-") as tmp_text:
        tmp = Path(tmp_text)
        build_dir = tmp / "dist"
        build_dir.mkdir()
        _run([args.uv, "build", "--out-dir", str(build_dir)], cwd=project_root)
        wheels = sorted(build_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise HostGateError(f"expected exactly one wheel, found {len(wheels)}")
        wheel = wheels[0]

        venv = tmp / "venv"
        _run([args.uv, "venv", "--python", args.python, str(venv)], cwd=project_root)
        python = _venv_executable(venv, "python")
        hashmarks = _venv_executable(venv, "hashmarks")
        _run(
            [args.uv, "pip", "install", "--python", str(python), f"{wheel}[mcp]"],
            cwd=project_root,
        )
        versions = _package_versions(python)

        repo = tmp / "repo"
        repo.mkdir()
        _write_fixture(repo)
        mcp_list, mcp_config_path, opencode_env = _configure_opencode_mcp(
            args.opencode,
            repo=repo,
            hashmarks=hashmarks,
        )

        phase1 = _opencode_run(
            args.opencode,
            repo=repo,
            model=args.model,
            prompt=_phase1_prompt(),
            env=opencode_env,
        )
        phase1_log.write_text(phase1.stdout, encoding="utf-8")
        events1 = _parse_jsonl(phase1.stdout)
        session_id = _session_id(events1)
        tools1 = _assert_completed_tool_set(
            events1,
            {
                "hashmarks_repository_context",
                "hashmarks_find",
                "hashmarks_task_evidence",
                "hashmarks_change_impact",
            },
        )
        context1 = _tool_payload(tools1["hashmarks_repository_context"], "hashmarks.repository-capsule.v1")
        find1 = _tool_payload(tools1["hashmarks_find"], "hashmarks.mcp-find.v1")
        evidence = _tool_payload(tools1["hashmarks_task_evidence"], "hashmarks.task-evidence.v1")
        impact = _tool_payload(tools1["hashmarks_change_impact"], "hashmarks.task-change-impact.v1")
        found_paths = {str(row.get("path")) for row in find1.get("results", []) if isinstance(row, dict)}
        if CHANGED_PATH not in found_paths:
            raise HostGateError(f"OpenCode-hosted Hashmarks find did not return {CHANGED_PATH}")
        if evidence.get("edit") != CHANGED_PATH:
            raise HostGateError(f"task_evidence selected unexpected edit path: {evidence.get('edit')!r}")

        generation_before = context1.get("generation")
        receipt = evidence.get("evidence_receipt")
        if not isinstance(generation_before, int) or not isinstance(receipt, dict):
            raise HostGateError("phase 1 did not expose generation-bound evidence")
        if receipt.get("codemap_generation") != generation_before:
            raise HostGateError("task_evidence generation does not match repository_context")

        source = repo / CHANGED_PATH
        source.write_text(
            "def flare041(value: int) -> int:\n    return value + 2\n",
            encoding="utf-8",
        )

        phase2 = _opencode_run(
            args.opencode,
            repo=repo,
            model=args.model,
            prompt=_phase2_prompt(evidence),
            session_id=session_id,
        )
        phase2_log.write_text(phase2.stdout, encoding="utf-8")
        events2 = _parse_jsonl(phase2.stdout)
        if _session_id(events2) != session_id:
            raise HostGateError("OpenCode did not resume the phase 1 session")
        tools2 = _assert_completed_tool_set(
            events2,
            {"hashmarks_post_change", "hashmarks_repository_context"},
        )
        post = _tool_payload(tools2["hashmarks_post_change"], "hashmarks.task-post-change-delta.v1")
        context2 = _tool_payload(tools2["hashmarks_repository_context"], "hashmarks.repository-capsule.v1")
        generation_after = context2.get("generation")
        if post.get("status") != "changed":
            raise HostGateError(f"post_change status was not changed: {post.get('status')!r}")
        if post.get("generation_before") != generation_before:
            raise HostGateError("post_change generation_before does not match pre-edit generation")
        if not isinstance(generation_after, int) or generation_after <= generation_before:
            raise HostGateError("repository generation did not advance after external mutation")
        if post.get("generation_after") != generation_after:
            raise HostGateError("post_change generation_after does not match final repository_context")
        changes = post.get("path_changes")
        if not isinstance(changes, list) or not any(
            isinstance(row, dict) and row.get("path") == CHANGED_PATH and row.get("state") == "changed"
            for row in changes
        ):
            raise HostGateError("post_change did not report the externally changed path")

        return {
            "schema": "hashmarks.opencode-mcp-host-gate.v1",
            "status": "PASS",
            "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_repository_identity": source_repository_identity,
            "source_project_registration": {
                "path": source_registration.relative_to(project_root).as_posix(),
                "sha256": _sha256(source_registration),
            },
            "host": {"name": "opencode", "version": opencode_version},
            "opencode_version": opencode_version,
            "model": args.model,
            "python_selector": args.python,
            "installed_versions": versions,
            "wheel": {"name": wheel.name, "sha256": _sha256(wheel)},
            "mcp_list": mcp_list.stdout.strip() or mcp_list.stderr.strip(),
            "opencode_mcp_config_path": mcp_config_path,
            "session_id": session_id,
            "observed_tools": sorted(EXPECTED_HASHMARKS_TOOLS),
            "phase1": {
                "generation": generation_before,
                "find_paths": sorted(found_paths),
                "task_evidence_identity": receipt.get("evidence_identity"),
                "impact_schema": impact.get("schema"),
            },
            "phase2": {
                "generation_before": post.get("generation_before"),
                "generation_after": post.get("generation_after"),
                "status": post.get("status"),
                "invalidated": post.get("invalidated"),
                "path_changes": changes,
            },
            "logs": {
                "phase1": {"path": str(phase1_log), "sha256": _sha256(phase1_log)},
                "phase2": {"path": str(phase2_log), "sha256": _sha256(phase2_log)},
            },
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Qualify the installed Hashmarks MCP wheel through a real OpenCode host."
    )
    parser.add_argument("--model", required=True, help="OpenCode provider/model with tool calling")
    parser.add_argument("--python", default="3.14", help="Python selector for the isolated wheel environment")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--opencode", default="opencode")
    parser.add_argument("--receipt", default="dist/opencode-mcp-host-gate.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    receipt_path = Path(args.receipt).resolve()
    try:
        receipt = _host_gate(args, project_root)
    except HostGateEnvironmentBlocked as exc:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(
                {
                    "schema": "hashmarks.opencode-mcp-host-gate.v1",
                    "status": "ENVIRONMENT_BLOCKED",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"HASHMARKS OPENCODE MCP HOST GATE: ENVIRONMENT_BLOCKED\n{exc}", file=os.sys.stderr)
        return 2
    except (HostGateError, OSError, subprocess.TimeoutExpired) as exc:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(
                {
                    "schema": "hashmarks.opencode-mcp-host-gate.v1",
                    "status": "FAIL",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"HASHMARKS OPENCODE MCP HOST GATE: FAIL\n{exc}", file=os.sys.stderr)
        return 1

    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"HASHMARKS OPENCODE MCP HOST GATE: PASS\nreceipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
