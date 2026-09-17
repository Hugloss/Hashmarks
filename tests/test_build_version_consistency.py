import tarfile
import zipfile
from pathlib import Path

import pytest

import hashmarks_build


def _write_release(root: Path, *, metadata_version: str, runtime_version: str) -> None:
    (root / "hashmarks").mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "hashmarks"\n'
        f'version = "{metadata_version}"\n'
        'requires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    (root / "hashmarks" / "_version.py").write_text(
        f'__version__ = "{runtime_version}"\n', encoding="utf-8"
    )
    (root / "README.md").write_text(f"# Hashmarks {metadata_version}\n", encoding="utf-8")


def test_build_backend_accepts_matching_runtime_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_release(tmp_path, metadata_version="1.2.3", runtime_version="1.2.3")
    monkeypatch.setattr(hashmarks_build, "ROOT", tmp_path)
    assert hashmarks_build._project()[1] == "1.2.3"


def test_build_backend_rejects_runtime_version_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_release(tmp_path, metadata_version="1.2.3", runtime_version="1.2.2")
    monkeypatch.setattr(hashmarks_build, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="release version mismatch"):
        hashmarks_build._project()


def test_readme_release_surface_exposes_project_version_without_owning_h1() -> None:
    version = hashmarks_build._project()[1]
    lines = (hashmarks_build.ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Hashmarks — Repository intelligence and a local MCP server for coding agents"
    assert f"Current package version: **{version}**." in lines


def test_build_metadata_exposes_public_release_metadata() -> None:
    metadata = hashmarks_build._metadata_bytes().decode("utf-8")
    assert "Summary: Local repository intelligence and a read-only MCP server for coding agents:" in metadata
    keyword_line = next(line for line in metadata.splitlines() if line.startswith("Keywords: "))
    keywords = set(keyword_line.removeprefix("Keywords: ").split(","))
    assert {
        "repository-intelligence",
        "mcp",
        "mcp-server",
        "model-context-protocol",
        "coding-agents",
        "codebase-search",
        "code-navigation",
        "change-impact",
        "impact-analysis",
        "dependency-analysis",
    } <= keywords
    assert "Classifier: Programming Language :: Python :: 3.11" in metadata
    assert "Classifier: Programming Language :: Python :: 3.14" in metadata
    assert "Classifier: Typing :: Typed" in metadata
    assert "Metadata-Version: 2.4" in metadata
    assert "License-Expression: Apache-2.0" in metadata
    assert "License-File: LICENSE" in metadata
    assert "Provides-Extra: mcp" in metadata
    assert 'Requires-Dist: mcp>=2.2.0; extra == "mcp"' in metadata
    assert "Project-URL:" not in metadata


def test_build_backend_projects_pep639_license_and_project_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_release(tmp_path, metadata_version="1.2.3", runtime_version="1.2.3")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8")
        + 'license = "Apache-2.0"\n'
        + 'license-files = ["LICENSE"]\n'
        + "[project.urls]\n"
        + 'Repository = "https://github.com/example/hashmarks"\n'
        + 'Issues = "https://github.com/example/hashmarks/issues"\n',
        encoding="utf-8",
    )
    (tmp_path / "LICENSE").write_text("synthetic license text\n", encoding="utf-8")
    monkeypatch.setattr(hashmarks_build, "ROOT", tmp_path)

    metadata = hashmarks_build._metadata_bytes().decode("utf-8")
    assert "License-Expression: Apache-2.0" in metadata
    assert "License-File: LICENSE" in metadata
    assert "Project-URL: Issues, https://github.com/example/hashmarks/issues" in metadata
    assert "Project-URL: Repository, https://github.com/example/hashmarks" in metadata

    wheel_dir = tmp_path / "wheel-out"
    wheel_name = hashmarks_build.build_wheel(str(wheel_dir))
    with zipfile.ZipFile(wheel_dir / wheel_name) as archive:
        names = set(archive.namelist())
        assert "hashmarks-1.2.3.dist-info/licenses/LICENSE" in names
        assert archive.read("hashmarks-1.2.3.dist-info/licenses/LICENSE") == b"synthetic license text\n"

    sdist_dir = tmp_path / "sdist-out"
    sdist_name = hashmarks_build.build_sdist(str(sdist_dir))
    with tarfile.open(sdist_dir / sdist_name, "r:gz") as archive:
        names = set(archive.getnames())
        assert "hashmarks-1.2.3/LICENSE" in names
        pkg_info = archive.extractfile("hashmarks-1.2.3/PKG-INFO")
        assert pkg_info is not None
        assert b"License-Expression: Apache-2.0" in pkg_info.read()


def test_build_backend_rejects_missing_declared_license_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_release(tmp_path, metadata_version="1.2.3", runtime_version="1.2.3")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8") + 'license-files = ["LICENSE"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(hashmarks_build, "ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="matched no files"):
        hashmarks_build._metadata_bytes()


def test_public_readme_license_guidance_matches_release_metadata() -> None:
    readme = (hashmarks_build.ROOT / "README.md").read_text(encoding="utf-8")
    assert "Hashmarks is licensed under the [Apache License 2.0](LICENSE)." in readme
    assert "choose an explicit software license" not in readme
    assert "does not invent a license" not in readme
