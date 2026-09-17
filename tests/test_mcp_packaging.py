from __future__ import annotations

import tarfile
import tomllib
import zipfile
from pathlib import Path

import hashmarks_build


def test_public_package_declares_apache_license_and_optional_mcp_extra() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]
    assert project["dependencies"] == []
    assert project["optional-dependencies"] == {"mcp": ["mcp>=2.2.0"]}
    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text


def test_build_metadata_projects_real_license_and_mcp_extra() -> None:
    metadata = hashmarks_build._metadata_bytes().decode("utf-8")
    assert "License-Expression: Apache-2.0" in metadata
    assert "License-File: LICENSE" in metadata
    assert "Provides-Extra: mcp" in metadata
    assert 'Requires-Dist: mcp>=2.2.0; extra == "mcp"' in metadata


def test_built_wheel_and_sdist_contain_apache_license_and_mcp_requirement(
    tmp_path: Path,
) -> None:
    wheel_dir = tmp_path / "wheel"
    wheel_name = hashmarks_build.build_wheel(str(wheel_dir))
    with zipfile.ZipFile(wheel_dir / wheel_name) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode("utf-8")
        assert "License-Expression: Apache-2.0" in metadata
        assert 'Requires-Dist: mcp>=2.2.0; extra == "mcp"' in metadata
        assert any(
            name.endswith(".dist-info/licenses/LICENSE") for name in archive.namelist()
        )

    sdist_dir = tmp_path / "sdist"
    sdist_name = hashmarks_build.build_sdist(str(sdist_dir))
    with tarfile.open(sdist_dir / sdist_name, "r:gz") as archive:
        assert any(name.endswith("/LICENSE") for name in archive.getnames())
