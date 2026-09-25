from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import hashmarks
import hashmarks_build
from scripts import release_contract
from scripts.release_contract import release_manifest, verify_release_manifest


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    hashmarks_build.build_wheel(str(dist))
    hashmarks_build.build_sdist(str(dist))
    return dist


def test_release_manifest_binds_exact_distribution_bytes(tmp_path: Path) -> None:
    manifest = release_manifest(
        _root(), _dist(tmp_path), tag=f"v{hashmarks.__version__}"
    )
    assert manifest["schema"] == "hashmarks.release-artifact-manifest.v2"
    assert manifest["project"] == "hashmarks"
    assert manifest["version"] == hashmarks.__version__
    assert manifest["tag"] == f"v{hashmarks.__version__}"
    assert manifest["publication_authority"] == "external"
    assert manifest["qualification_dependency_resolution"] == {
        "path": "uv.lock",
        "sha256": "sha256:"
        + hashlib.sha256((_root() / "uv.lock").read_bytes()).hexdigest(),
    }
    rows = manifest["distributions"]
    assert [row["kind"] for row in rows] == ["wheel", "sdist"]
    assert all(str(row["sha256"]).startswith("sha256:") for row in rows)
    assert str(manifest["manifest_identity"]).startswith("sha256:")


def test_release_manifest_rejects_tag_version_drift(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="release tag mismatch"):
        release_manifest(_root(), _dist(tmp_path), tag="v999.0.0")


def test_release_manifest_rejects_extra_distribution(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    (dist / "extra.whl").write_bytes(b"not-a-wheel")
    with pytest.raises(ValueError, match="exactly the expected wheel and sdist"):
        release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")


def test_release_manifest_rejects_any_unexpected_publish_entry(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    (dist / "notes.txt").write_text("must not enter publish bundle", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly the expected wheel and sdist"):
        release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")


def test_release_contract_cli_translates_invalid_tag_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dist = _dist(tmp_path)
    manifest = release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit, match="release tag mismatch"):
        release_contract.main(
            [
                "verify",
                "--root",
                str(tmp_path / "source-tree-not-required"),
                "--dist",
                str(dist),
                "--tag",
                "v999.0.0",
                "--manifest",
                str(manifest_path),
            ]
        )
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err


def test_release_contract_verify_runs_without_source_or_installed_hashmarks(
    tmp_path: Path,
) -> None:
    dist = _dist(tmp_path)
    manifest = release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(_root() / "scripts" / "release_contract.py"),
            "verify",
            "--root",
            str(tmp_path / "source-tree-not-required"),
            "--dist",
            str(dist),
            "--tag",
            f"v{hashmarks.__version__}",
            "--manifest",
            str(manifest_path),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Hashmarks release artifact manifest: PASS" in result.stdout
    assert result.stderr == ""


def test_release_verifier_rejects_downloaded_distribution_byte_drift(
    tmp_path: Path,
) -> None:
    dist = _dist(tmp_path)
    manifest = release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")
    wheel = next(dist.glob("*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="downloaded distribution bytes"):
        verify_release_manifest(
            dist,
            tag=f"v{hashmarks.__version__}",
            recorded=manifest,
        )


def test_release_manifest_is_stable_for_unchanged_bytes(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    first = release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")
    second = release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
