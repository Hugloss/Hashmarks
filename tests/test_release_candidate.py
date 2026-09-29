from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.release_contract import validate_release_candidate


def _candidate(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "candidate"
    (root / "hashmarks").mkdir(parents=True)
    (root / ".github").mkdir()
    project = root / "pyproject.toml"
    project.write_text('[project]\nname = "hashmarks"\nversion = "1.2.3"\n')
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "pyproject.toml"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        check=True,
    )
    base = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    project.write_text('[project]\nname = "hashmarks"\nversion = "1.3.0"\n')
    (root / "hashmarks" / "_version.py").write_text('__version__ = "1.3.0"\n')
    (root / "README.md").write_text("Current package version: **1.3.0**.\n")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.3.0 — Public release\n\n- Released update.\n"
    )
    (root / ".github" / "release-request.toml").write_text('version = "1.3.0"\n')
    return root, base


def test_normal_release_candidate_matches_reviewed_sources_and_increases(
    tmp_path: Path,
) -> None:
    root, base = _candidate(tmp_path)

    assert validate_release_candidate(root, base_ref=base, normal_only=True) == "1.3.0"


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (
            ".github/release-request.toml",
            'version = "1.4.0"\n',
            "request/version mismatch",
        ),
        ("hashmarks/_version.py", '__version__ = "1.2.3"\n', "runtime version"),
        (
            "README.md",
            "Current package version: **1.2.3**.\n",
            "README package version",
        ),
        (
            "CHANGELOG.md",
            "# Changelog\n\n## 1.3.0 — Development\n\n- Placeholder.\n",
            "still marks 1.3.0 as Development",
        ),
    ],
)
def test_normal_release_candidate_rejects_mismatched_sources(
    tmp_path: Path, path: str, replacement: str, message: str
) -> None:
    root, base = _candidate(tmp_path)
    (root / path).write_text(replacement)

    with pytest.raises(ValueError, match=message):
        validate_release_candidate(root, base_ref=base)


def test_normal_release_candidate_rejects_nonincreasing_base_version(
    tmp_path: Path,
) -> None:
    root, base = _candidate(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "hashmarks"\nversion = "1.2.3"\n'
    )
    (root / "hashmarks" / "_version.py").write_text('__version__ = "1.2.3"\n')
    (root / "README.md").write_text("Current package version: **1.2.3**.\n")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.2.3 — Public release\n\n- Released update.\n"
    )
    (root / ".github" / "release-request.toml").write_text('version = "1.2.3"\n')

    with pytest.raises(ValueError, match="must be greater than base 1.2.3"):
        validate_release_candidate(root, base_ref=base)


def test_retry_request_keeps_optional_fields_and_final_source_proof_in_publish(
    tmp_path: Path,
) -> None:
    root, base = _candidate(tmp_path)
    (root / ".github" / "release-request.toml").write_text(
        'version = "1.2.3"\npublication_attempt = 2\n'
    )

    assert validate_release_candidate(root, base_ref=base) == "1.2.3"
    with pytest.raises(ValueError, match="normal version-only release request"):
        validate_release_candidate(root, normal_only=True)
