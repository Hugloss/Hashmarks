from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from scripts.release_prepare import prepare_release


def _release_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "hashmarks").mkdir(parents=True)
    (root / ".github").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "hashmarks"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )
    (root / "hashmarks" / "_version.py").write_text(
        '__version__ = "1.2.3"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Hashmarks\n\nCurrent package version: **1.2.3**.\n",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.2.3 — Previous release\n\n- Previous notes.\n",
        encoding="utf-8",
    )
    (root / ".github" / "release-request.toml").write_text(
        'version = "1.2.3"\n'
        'source_sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
        "publication_attempt = 4\n",
        encoding="utf-8",
    )
    return root


def test_prepare_release_updates_mechanical_version_authorities(
    tmp_path: Path,
) -> None:
    root = _release_tree(tmp_path)

    prepare_release(root, "1.3.0")

    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert project["version"] == "1.3.0"
    assert (root / "hashmarks" / "_version.py").read_text(
        encoding="utf-8"
    ) == '__version__ = "1.3.0"\n'
    assert "Current package version: **1.3.0**." in (root / "README.md").read_text(
        encoding="utf-8"
    )

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.startswith(
        "# Changelog\n\n"
        "## 1.3.0 — Development\n\n"
        "- Replace this development placeholder with substantive public release notes.\n\n"
        "## 1.2.3 — Previous release\n"
    )


def test_prepare_release_resets_retry_authority_for_normal_release(
    tmp_path: Path,
) -> None:
    root = _release_tree(tmp_path)

    prepare_release(root, "1.3.0")

    request = tomllib.loads(
        (root / ".github" / "release-request.toml").read_text(encoding="utf-8")
    )
    assert request == {"version": "1.3.0"}


@pytest.mark.parametrize("version", ["1.2", "v1.3.0", "../1.3.0", "1.3.0rc1"])
def test_prepare_release_rejects_non_release_versions(
    tmp_path: Path,
    version: str,
) -> None:
    root = _release_tree(tmp_path)

    with pytest.raises(ValueError, match="invalid release version"):
        prepare_release(root, version)

    assert (
        tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
            "version"
        ]
        == "1.2.3"
    )


def test_prepare_release_rejects_existing_release_before_writing(
    tmp_path: Path,
) -> None:
    root = _release_tree(tmp_path)
    changelog = root / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "## 1.3.0 — Existing\n\n- Existing notes.\n\n"
        "## 1.2.3 — Previous release\n\n- Previous notes.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="already contains release 1.3.0"):
        prepare_release(root, "1.3.0")

    assert (
        tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
            "version"
        ]
        == "1.2.3"
    )
