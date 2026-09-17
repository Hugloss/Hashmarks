from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class PantsTargetData:
    address: str
    target_type: str
    dependencies: tuple[str, ...]
    sources: tuple[str, ...]
    goals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PantsSnapshot:
    executable: str | None
    targets: tuple[PantsTargetData, ...] = ()
    warnings: tuple[str, ...] = ()


def find_pants(workspace: Path) -> str | None:
    launcher = workspace / "pants"
    if launcher.is_file():
        return str(launcher)
    return shutil.which("pants")


def collect_pants_targets(
    workspace: Path, *, executable: str | None = None, timeout: float = 45.0
) -> PantsSnapshot:
    pants = executable or find_pants(workspace)
    if pants is None:
        return PantsSnapshot(
            None,
            warnings=(
                "pants.toml detected but Pants executable/launcher is unavailable",
            ),
        )
    env = dict(os.environ)
    try:
        completed = subprocess.run(
            [pants, "peek", "--exclude-defaults", "::"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return PantsSnapshot(pants, warnings=(f"pants peek failed: {exc}",))
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip().splitlines()[-1]
            if completed.stderr.strip()
            else f"exit {completed.returncode}"
        )
        return PantsSnapshot(pants, warnings=(f"pants peek failed: {detail}",))
    try:
        payload: Any = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return PantsSnapshot(pants, warnings=("pants peek returned invalid JSON",))
    if not isinstance(payload, list):
        return PantsSnapshot(pants, warnings=("pants peek JSON must be a list",))
    rows: list[PantsTargetData] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        address = str(raw.get("address") or "")
        if not address:
            continue
        dependencies = tuple(
            str(value)
            for value in raw.get("dependencies") or ()
            if isinstance(value, str)
        )
        sources = tuple(
            str(value).replace("\\", "/")
            for value in raw.get("sources") or ()
            if isinstance(value, str)
        )
        goals = tuple(
            str(value) for value in raw.get("goals") or () if isinstance(value, str)
        )
        rows.append(
            PantsTargetData(
                address=address,
                target_type=str(raw.get("target_type") or "target"),
                dependencies=dependencies,
                sources=sources,
                goals=goals,
            )
        )
    return PantsSnapshot(pants, tuple(rows))
