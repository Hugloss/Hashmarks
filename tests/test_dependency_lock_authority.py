from __future__ import annotations

import tomllib
from pathlib import Path, PureWindowsPath
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def test_uv_lock_local_sources_are_repository_portable() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    violations: list[str] = []
    for package in lock.get("package", []):
        source = package.get("source")
        if not isinstance(source, dict):
            continue
        for key in ("directory", "editable", "path", "url"):
            value = source.get(key)
            if not isinstance(value, str):
                continue
            if urlparse(value).scheme == "file":
                violations.append(f"{package.get('name', '?')}:{key}={value}")
                continue
            if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
                violations.append(f"{package.get('name', '?')}:{key}={value}")

    assert violations == [], (
        "uv.lock contains machine-absolute local dependency sources: "
        + ", ".join(violations)
    )
