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
from scripts.release_contract import publication_manifest, release_manifest


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    hashmarks_build.build_wheel(str(dist))
    hashmarks_build.build_sdist(str(dist))
    return dist


def _standalone(
    tmp_path: Path,
    *,
    version: str | None = None,
    suffix: str = "",
) -> Path:
    standalone = tmp_path / "hashmarks-linux-x86_64"
    reported = version or hashmarks.__version__
    standalone.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' 'hashmarks version {reported}'\n"
        f"{suffix}",
        encoding="utf-8",
    )
    standalone.chmod(0o755)
    return standalone


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


def test_publication_manifest_binds_source_and_standalone_bytes(
    tmp_path: Path,
) -> None:
    standalone = _standalone(tmp_path)
    source_sha = "a" * 40
    manifest = publication_manifest(
        _root(),
        _dist(tmp_path),
        standalone,
        tag=f"v{hashmarks.__version__}",
        source_sha=source_sha,
    )

    assert manifest["schema"] == "hashmarks.release-publication-manifest.v1"
    assert manifest["source"] == {"commit_sha": source_sha}
    assert str(manifest["package_qualification_identity"]).startswith("sha256:")
    assert manifest["standalone"] == {
        "kind": "standalone",
        "filename": "hashmarks-linux-x86_64",
        "size_bytes": standalone.stat().st_size,
        "sha256": "sha256:" + hashlib.sha256(standalone.read_bytes()).hexdigest(),
        "platform": "linux",
        "architecture": "x86_64",
        "version": hashmarks.__version__,
    }
    assert str(manifest["manifest_identity"]).startswith("sha256:")


def test_publication_manifest_rejects_standalone_version_drift(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="standalone release version mismatch"):
        publication_manifest(
            _root(),
            _dist(tmp_path),
            _standalone(tmp_path, version="999.0.0"),
            tag=f"v{hashmarks.__version__}",
            source_sha="a" * 40,
        )


def test_publication_manifest_rejects_non_commit_source_identity(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="source_sha must be an exact"):
        publication_manifest(
            _root(),
            _dist(tmp_path),
            _standalone(tmp_path),
            tag=f"v{hashmarks.__version__}",
            source_sha="main",
        )


def test_publication_manifest_cli_writes_checksums_for_every_public_asset(
    tmp_path: Path,
) -> None:
    dist = _dist(tmp_path)
    standalone = _standalone(tmp_path)
    output = tmp_path / "release-manifest.json"
    sums = tmp_path / "SHA256SUMS.txt"
    source_sha = "b" * 40

    assert (
        release_contract.main(
            [
                "publication-manifest",
                "--root",
                str(_root()),
                "--dist",
                str(dist),
                "--standalone",
                str(standalone),
                "--tag",
                f"v{hashmarks.__version__}",
                "--source-sha",
                source_sha,
                "--output",
                str(output),
                "--sha256sums",
                str(sums),
            ]
        )
        == 0
    )

    names = [line.split("  ", 1)[1] for line in sums.read_text().splitlines()]
    assert names == [
        f"hashmarks_{hashmarks.__version__}-py3-none-any.whl",
        f"hashmarks-{hashmarks.__version__}.tar.gz",
        "hashmarks-linux-x86_64",
    ]
    recorded = json.loads(output.read_text(encoding="utf-8"))
    assert recorded["source"] == {"commit_sha": source_sha}


def test_publication_verification_rejects_post_manifest_standalone_mutation(
    tmp_path: Path,
) -> None:
    dist = _dist(tmp_path)
    standalone = _standalone(tmp_path)
    output = tmp_path / "release-manifest.json"
    sums = tmp_path / "SHA256SUMS.txt"
    source_sha = "c" * 40
    release_contract.main(
        [
            "publication-manifest",
            "--root",
            str(_root()),
            "--dist",
            str(dist),
            "--standalone",
            str(standalone),
            "--tag",
            f"v{hashmarks.__version__}",
            "--source-sha",
            source_sha,
            "--output",
            str(output),
            "--sha256sums",
            str(sums),
        ]
    )
    standalone.write_text(
        standalone.read_text(encoding="utf-8") + "# changed after qualification\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SystemExit,
        match="release publication manifest does not match current artifact bytes",
    ):
        release_contract.main(
            [
                "verify-publication",
                "--root",
                str(_root()),
                "--dist",
                str(dist),
                "--standalone",
                str(standalone),
                "--tag",
                f"v{hashmarks.__version__}",
                "--source-sha",
                source_sha,
                "--manifest",
                str(output),
            ]
        )


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


def test_release_contract_cli_runs_without_installed_hashmarks(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(_root() / "scripts" / "release_contract.py"),
            "validate-tag",
            "--root",
            str(_root()),
            "--tag",
            f"v{hashmarks.__version__}",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert f"Hashmarks release tag: PASS (v{hashmarks.__version__})" in result.stdout
    assert result.stderr == ""


def test_release_manifest_is_stable_for_unchanged_bytes(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    first = release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")
    second = release_manifest(_root(), dist, tag=f"v{hashmarks.__version__}")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
