from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class HostGateError(RuntimeError):
    pass


class HostGateEnvironmentBlocked(HostGateError):
    pass


def run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        input=input_text,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise HostGateError(
            f"command failed ({result.returncode}): {' '.join(argv)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def venv_executable(venv: Path, name: str) -> Path:
    if os.name == "nt":
        suffix = ".exe" if name in {"python", "hashmarks"} else ""
        return venv / "Scripts" / f"{name}{suffix}"
    return venv / "bin" / name


def package_versions(python: Path) -> dict[str, str]:
    code = (
        "import importlib.metadata as m,json;"
        "print(json.dumps({n:m.version(n) for n in ('hashmarks','mcp')},sort_keys=True))"
    )
    output = run([str(python), "-I", "-c", code], cwd=python.parent).stdout
    value = json.loads(output)
    return {str(key): str(version) for key, version in value.items()}


def build_installed_wheel(
    *,
    project_root: Path,
    tmp: Path,
    uv: str,
    python_selector: str,
) -> tuple[Path, Path, Path, dict[str, str]]:
    build_dir = tmp / "dist"
    build_dir.mkdir()
    run([uv, "build", "--out-dir", str(build_dir)], cwd=project_root)
    wheels = sorted(build_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise HostGateError(f"expected exactly one wheel, found {len(wheels)}")
    wheel = wheels[0]
    venv = tmp / "venv"
    run([uv, "venv", "--python", python_selector, str(venv)], cwd=project_root)
    python = venv_executable(venv, "python")
    hashmarks = venv_executable(venv, "hashmarks")
    run(
        [uv, "pip", "install", "--python", str(python), f"{wheel}[mcp]"],
        cwd=project_root,
    )
    return wheel, python, hashmarks, package_versions(python)


def installed_mcp_contract(
    python: Path,
    workspace: Path,
    *,
    expected_version: str | None = None,
) -> dict[str, Any]:
    output = run(
        [
            str(python),
            "-I",
            "-m",
            "hashmarks.mcp_contract",
            "--workspace",
            str(workspace),
        ],
        cwd=workspace,
    ).stdout
    try:
        value = json.loads(output)
    except json.JSONDecodeError as exc:
        raise HostGateError(
            f"installed Hashmarks MCP contract was not JSON: {output!r}"
        ) from exc
    if not isinstance(value, dict):
        raise HostGateError("installed Hashmarks MCP contract is not an object")
    if expected_version is not None and value.get("server_version") != expected_version:
        raise HostGateError(
            "installed Hashmarks package/MCP contract version differs: "
            f"package={expected_version!r} mcp={value.get('server_version')!r}"
        )
    return value


def write_fixture(repo: Path) -> None:
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


def parse_jsonl(text: str, *, host: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HostGateError(
                f"{host} emitted non-JSON stdout on line {line_number}: {line!r}"
            ) from exc
        if not isinstance(value, dict):
            raise HostGateError(f"{host} JSON event {line_number} is not an object")
        events.append(value)
    if not events:
        raise HostGateError(f"{host} emitted no JSON events")
    return events


def source_binding(project_root: Path, registration_path: Path) -> dict[str, Any]:
    from hashmarks.test_shards import repository_content_identity

    if not registration_path.is_file():
        raise HostGateError(f"project registration is missing: {registration_path}")
    return {
        "source_repository_identity": repository_content_identity(
            project_root,
            excluded_paths=(project_root / "dist",),
        ),
        "source_project_registration": {
            "path": registration_path.relative_to(project_root).as_posix(),
            "sha256": sha256(registration_path),
        },
    }


_BASIC_QUALIFICATION_REQUESTS: dict[str, dict[str, object]] = {
    "repository_context": {"max_areas": 8},
    "find": {"query": "flare041", "limit": 5},
}
_BASIC_QUALIFICATION_FIND_PATH = "src/feature.py"


def validate_basic_qualification_request(
    tool: str,
    value: object,
    *,
    host: str,
) -> dict[str, object]:
    expected = _BASIC_QUALIFICATION_REQUESTS.get(tool)
    if expected is None:
        raise HostGateError(f"{host} targeted unsupported qualification tool: {tool}")
    if not isinstance(value, dict):
        raise HostGateError(f"{host} qualification request for {tool} is not an object")
    if value != expected:
        raise HostGateError(
            f"{host} qualification request for {tool} differs from fixture contract: "
            f"expected={expected!r} got={value!r}"
        )
    return value


def _decode_json_payload(text: str, *, host: str, tool: str) -> dict[str, object]:
    stripped = text.strip()
    if not stripped:
        raise HostGateError(f"{host} MCP response for {tool} is empty")
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise HostGateError(
            f"{host} MCP response for {tool} is not an exact JSON object"
        ) from exc
    if not isinstance(decoded, dict):
        raise HostGateError(f"{host} MCP response for {tool} JSON is not an object")
    return decoded


def _decode_content_payload(
    value: list[object],
    *,
    host: str,
    tool: str,
) -> dict[str, object]:
    if len(value) != 1:
        raise HostGateError(
            f"{host} MCP response for {tool} must contain exactly one structured payload"
        )
    part = value[0]
    if not isinstance(part, dict):
        raise HostGateError(
            f"{host} MCP response content for {tool} contains a non-object part"
        )
    if part.get("type") != "text" or not isinstance(part.get("text"), str):
        raise HostGateError(
            f"{host} MCP response content for {tool} is not a text JSON payload"
        )
    return _decode_json_payload(part["text"], host=host, tool=tool)


def _decode_mapping_payload(
    value: dict[object, object],
    *,
    host: str,
    tool: str,
) -> dict[str, object]:
    structured = value.get("structured_content")
    if structured is None:
        structured = value.get("structuredContent")
    if structured is not None:
        if not isinstance(structured, dict):
            raise HostGateError(
                f"{host} structured MCP response for {tool} is not an object"
            )
        return structured
    if isinstance(value.get("schema"), str):
        return dict(value)
    if "content" in value:
        return _decode_mcp_payload(value["content"], host=host, tool=tool)
    raise HostGateError(
        f"{host} MCP response for {tool} has no structured Hashmarks payload"
    )


def _decode_mcp_payload(value: object, *, host: str, tool: str) -> dict[str, object]:
    if isinstance(value, dict):
        return _decode_mapping_payload(value, host=host, tool=tool)
    if isinstance(value, list):
        return _decode_content_payload(value, host=host, tool=tool)
    if isinstance(value, str):
        return _decode_json_payload(value, host=host, tool=tool)
    raise HostGateError(
        f"{host} MCP response for {tool} has unsupported payload type"
    )


def validate_basic_qualification_response(
    tool: str,
    value: object,
    *,
    host: str,
) -> dict[str, object]:
    from hashmarks.mcp_contract import validate_tool_response

    payload = _decode_mcp_payload(value, host=host, tool=tool)
    try:
        payload = validate_tool_response(tool, payload)
    except (RuntimeError, ValueError) as exc:
        raise HostGateError(
            f"{host} MCP response for {tool} failed canonical contract validation: {exc}"
        ) from exc
    if "BUILDING" in json.dumps(payload, sort_keys=True, default=str):
        raise HostGateError(f"transient BUILDING state escaped through {host}")
    if tool == "repository_context":
        generation = payload.get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool):
            raise HostGateError(
                f"{host} repository_context did not expose an integer generation"
            )
    elif tool == "find":
        results = payload.get("results")
        if not isinstance(results, list) or not any(
            isinstance(row, dict) and row.get("path") == _BASIC_QUALIFICATION_FIND_PATH
            for row in results
        ):
            raise HostGateError(
                f"{host} find did not return {_BASIC_QUALIFICATION_FIND_PATH}"
            )
    else:
        raise HostGateError(f"{host} targeted unsupported qualification tool: {tool}")
    return payload

def completed_at() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
