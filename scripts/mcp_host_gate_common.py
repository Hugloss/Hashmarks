from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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


def completed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
