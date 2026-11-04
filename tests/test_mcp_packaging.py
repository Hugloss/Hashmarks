from __future__ import annotations

import email
import tarfile
import zipfile
from pathlib import Path

import pytest
from packaging.requirements import Requirement

import hashmarks_build


def test_public_package_contains_apache_license_text() -> None:
    root = Path(__file__).resolve().parents[1]
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
        assert "Provides-Extra: syntax" in metadata
        syntax_requirement = next(
            line
            for line in metadata.splitlines()
            if line.startswith("Requires-Dist: tree-sitter-language-pack")
        )
        assert '; extra == "syntax"' in syntax_requirement
        assert any(
            name.endswith(".dist-info/licenses/LICENSE") for name in archive.namelist()
        )

    sdist_dir = tmp_path / "sdist"
    sdist_name = hashmarks_build.build_sdist(str(sdist_dir))
    with tarfile.open(sdist_dir / sdist_name, "r:gz") as archive:
        assert any(name.endswith("/LICENSE") for name in archive.getnames())


def _dependency_fixture(root: Path, dependencies: str) -> None:
    (root / "hashmarks").mkdir()
    (root / "hashmarks" / "__init__.py").write_text("", encoding="utf-8")
    (root / "hashmarks" / "_version.py").write_text(
        '__version__ = "1.0.0"\n', encoding="utf-8"
    )
    (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "hashmarks"\nversion = "1.0.0"\n'
        f"dependencies = {dependencies}\n",
        encoding="utf-8",
    )


def _artifact_metadata(directory: Path, kind: str) -> bytes:
    if kind == "sdist":
        name = hashmarks_build.build_sdist(directory)
        with tarfile.open(directory / name, "r:gz") as archive:
            member = next(item for item in archive if item.name.endswith("/PKG-INFO"))
            stream = archive.extractfile(member)
            assert stream is not None
            with stream:
                return stream.read()
    builder = (
        hashmarks_build.build_editable
        if kind == "editable"
        else hashmarks_build.build_wheel
    )
    name = builder(directory)
    with zipfile.ZipFile(directory / name) as archive:
        member = next(name for name in archive.namelist() if name.endswith("/METADATA"))
        return archive.read(member)


@pytest.mark.parametrize("kind", ["wheel", "sdist", "editable"])
def test_artifacts_preserve_required_dependency_and_environment_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    _dependency_fixture(
        tmp_path,
        """["runtime-support>=1", 'platform-tools>=2; python_version < "3.12"']""",
    )
    monkeypatch.setattr(hashmarks_build, "ROOT", tmp_path)
    message = email.message_from_bytes(_artifact_metadata(tmp_path / "out", kind))
    requirements = {
        item.name: item
        for value in message.get_all("Requires-Dist", [])
        if (item := Requirement(value))
    }
    assert set(requirements) == {"runtime-support", "platform-tools"}
    assert requirements["runtime-support"].marker is None
    marker = requirements["platform-tools"].marker
    assert marker is not None
    assert marker.evaluate({"python_version": "3.11", "extra": ""})
    assert not marker.evaluate({"python_version": "3.14", "extra": ""})


@pytest.mark.parametrize("declaration", ['"not-an-array"', "[1]", '[""]', '[" "]'])
def test_invalid_required_dependency_metadata_refuses_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, declaration: str
) -> None:
    _dependency_fixture(tmp_path, declaration)
    monkeypatch.setattr(hashmarks_build, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match=r"project\.dependencies"):
        hashmarks_build.build_wheel(tmp_path / "out")
