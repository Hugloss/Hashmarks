from __future__ import annotations

import json
from pathlib import Path

import pytest

import hashmarks
import hashmarks_build
from scripts import release_contract
from scripts.release_contract import release_manifest


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
    assert manifest["schema"] == "hashmarks.release-artifact-manifest.v1"
    assert manifest["project"] == "hashmarks"
    assert manifest["version"] == hashmarks.__version__
    assert manifest["tag"] == f"v{hashmarks.__version__}"
    assert manifest["publication_authority"] == "external"
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
    with pytest.raises(SystemExit, match="release tag mismatch"):
        release_contract.main(
            [
                "verify",
                "--root",
                str(_root()),
                "--dist",
                str(dist),
                "--tag",
                "v999.0.0",
                "--manifest",
                str(tmp_path / "missing.json"),
            ]
        )
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err


def test_release_manifest_is_stable_for_unchanged_bytes(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    first = release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")
    second = release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
