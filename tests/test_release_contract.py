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
from scripts.release_contract import (
    publication_manifest,
    release_manifest,
    standalone_qualification,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    hashmarks_build.build_wheel(str(dist))
    hashmarks_build.build_sdist(str(dist))
    return dist


def _artifact_payload(platform: str, *, version: str | None = None) -> bytes:
    reported = version or hashmarks.__version__
    if platform == "linux":
        return f"#!/bin/sh\nprintf '%s\\n' 'hashmarks version {reported}'\n".encode()
    return b"MZ\x00synthetic-windows-standalone"


def _standalone_filename(platform: str) -> str:
    if platform == "linux":
        return "hashmarks-linux-x86_64"
    return "hashmarks-windows-x86_64.exe"


def _bundle(
    tmp_path: Path,
    platform: str,
    *,
    version: str | None = None,
) -> Path:
    bundle = tmp_path / f"standalone-{platform}"
    bundle.mkdir(parents=True)
    artifact = bundle / _standalone_filename(platform)
    artifact.write_bytes(_artifact_payload(platform, version=version))
    if platform == "linux":
        artifact.chmod(0o755)
    checksum = bundle / f"{artifact.name}.sha256"
    checksum.write_text(
        f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}\n",
        encoding="utf-8",
    )
    qualification = standalone_qualification(
        _root(),
        artifact,
        checksum,
        platform=platform,
        architecture="x86_64",
        smoke=platform == "linux",
    )
    (bundle / release_contract.STANDALONE_QUALIFICATION_FILENAME).write_text(
        json.dumps(qualification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle


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


def test_standalone_qualification_binds_native_smoke_and_checksum(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path, "linux")
    qualification = json.loads(
        (bundle / release_contract.STANDALONE_QUALIFICATION_FILENAME).read_text(
            encoding="utf-8"
        )
    )

    assert qualification["schema"] == "hashmarks.standalone-qualification.v1"
    assert qualification["smoke"] == {
        "command": "--version",
        "reported_version": hashmarks.__version__,
        "status": "pass",
    }
    assert qualification["standalone"]["platform"] == "linux"
    assert qualification["standalone"]["architecture"] == "x86_64"
    assert str(qualification["qualification_identity"]).startswith("sha256:")


def test_standalone_qualification_rejects_native_version_drift(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "hashmarks-linux-x86_64"
    artifact.write_bytes(_artifact_payload("linux", version="999.0.0"))
    artifact.chmod(0o755)
    checksum = tmp_path / "hashmarks-linux-x86_64.sha256"
    checksum.write_text(
        f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="standalone release version mismatch"):
        standalone_qualification(
            _root(),
            artifact,
            checksum,
            platform="linux",
            architecture="x86_64",
        )


def test_publication_manifest_requires_linux_and_windows_qualifications(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="standalone publication set mismatch"):
        publication_manifest(
            _root(),
            _dist(tmp_path),
            [_bundle(tmp_path, "linux")],
            tag=f"v{hashmarks.__version__}",
            source_sha="a" * 40,
        )


def test_publication_manifest_binds_both_native_standalone_sets(
    tmp_path: Path,
) -> None:
    manifest = publication_manifest(
        _root(),
        _dist(tmp_path),
        [_bundle(tmp_path, "windows"), _bundle(tmp_path, "linux")],
        tag=f"v{hashmarks.__version__}",
        source_sha="b" * 40,
    )

    assert manifest["schema"] == "hashmarks.release-publication-manifest.v2"
    assert manifest["source"] == {"commit_sha": "b" * 40}
    assert [
        (row["platform"], row["architecture"], row["filename"])
        for row in manifest["standalones"]
    ] == [
        ("linux", "x86_64", "hashmarks-linux-x86_64"),
        ("windows", "x86_64", "hashmarks-windows-x86_64.exe"),
    ]
    assert [row["filename"] for row in manifest["installer_checksums"]] == [
        "hashmarks-linux-x86_64.sha256",
        "hashmarks-windows-x86_64.exe.sha256",
    ]
    assert all(
        str(row["qualification_identity"]).startswith("sha256:")
        for row in manifest["standalones"]
    )
    assert str(manifest["manifest_identity"]).startswith("sha256:")


def test_publication_manifest_rejects_duplicate_platform_qualification(
    tmp_path: Path,
) -> None:
    first = _bundle(tmp_path / "first", "linux")
    second = _bundle(tmp_path / "second", "linux")
    windows = _bundle(tmp_path, "windows")

    with pytest.raises(ValueError, match="duplicate standalone qualification"):
        publication_manifest(
            _root(),
            _dist(tmp_path),
            [first, second, windows],
            tag=f"v{hashmarks.__version__}",
            source_sha="c" * 40,
        )


def test_publication_manifest_rejects_tampered_qualified_windows_bytes(
    tmp_path: Path,
) -> None:
    linux = _bundle(tmp_path, "linux")
    windows = _bundle(tmp_path, "windows")
    artifact = windows / "hashmarks-windows-x86_64.exe"
    artifact.write_bytes(artifact.read_bytes() + b"tampered")

    with pytest.raises(
        ValueError,
        match="standalone installer checksum does not match qualified standalone bytes",
    ):
        publication_manifest(
            _root(),
            _dist(tmp_path),
            [linux, windows],
            tag=f"v{hashmarks.__version__}",
            source_sha="d" * 40,
        )


def test_publication_manifest_rejects_tampered_qualification_identity(
    tmp_path: Path,
) -> None:
    linux = _bundle(tmp_path, "linux")
    windows = _bundle(tmp_path, "windows")
    receipt = windows / release_contract.STANDALONE_QUALIFICATION_FILENAME
    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["qualification_identity"] = "sha256:" + "0" * 64
    receipt.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="qualification identity mismatch"):
        publication_manifest(
            _root(),
            _dist(tmp_path),
            [linux, windows],
            tag=f"v{hashmarks.__version__}",
            source_sha="e" * 40,
        )


def test_publication_manifest_rejects_extra_file_in_native_bundle(
    tmp_path: Path,
) -> None:
    linux = _bundle(tmp_path, "linux")
    windows = _bundle(tmp_path, "windows")
    (windows / "unqualified.exe").write_bytes(b"extra")

    with pytest.raises(ValueError, match="bundle must contain exactly"):
        publication_manifest(
            _root(),
            _dist(tmp_path),
            [linux, windows],
            tag=f"v{hashmarks.__version__}",
            source_sha="f" * 40,
        )


def test_publication_manifest_rejects_non_commit_source_identity(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="source_sha must be an exact"):
        publication_manifest(
            _root(),
            _dist(tmp_path),
            [_bundle(tmp_path, "linux"), _bundle(tmp_path, "windows")],
            tag=f"v{hashmarks.__version__}",
            source_sha="main",
        )


def test_publication_manifest_cli_writes_checksums_for_every_public_asset(
    tmp_path: Path,
) -> None:
    dist = _dist(tmp_path)
    linux = _bundle(tmp_path, "linux")
    windows = _bundle(tmp_path, "windows")
    output = tmp_path / "release-manifest.json"
    sums = tmp_path / "SHA256SUMS.txt"

    assert (
        release_contract.main(
            [
                "publication-manifest",
                "--root",
                str(_root()),
                "--dist",
                str(dist),
                "--standalone-bundle",
                str(linux),
                "--standalone-bundle",
                str(windows),
                "--tag",
                f"v{hashmarks.__version__}",
                "--source-sha",
                "1" * 40,
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
        f"hashmarks-{hashmarks.__version__}-py3-none-any.whl",
        f"hashmarks-{hashmarks.__version__}.tar.gz",
        "hashmarks-linux-x86_64",
        "hashmarks-windows-x86_64.exe",
        "hashmarks-linux-x86_64.sha256",
        "hashmarks-windows-x86_64.exe.sha256",
    ]


def test_publication_verification_rejects_post_manifest_mutation(
    tmp_path: Path,
) -> None:
    dist = _dist(tmp_path)
    linux = _bundle(tmp_path, "linux")
    windows = _bundle(tmp_path, "windows")
    output = tmp_path / "release-manifest.json"
    sums = tmp_path / "SHA256SUMS.txt"
    source_sha = "2" * 40
    args = [
        "--root",
        str(_root()),
        "--dist",
        str(dist),
        "--standalone-bundle",
        str(linux),
        "--standalone-bundle",
        str(windows),
        "--tag",
        f"v{hashmarks.__version__}",
        "--source-sha",
        source_sha,
    ]
    release_contract.main(
        [
            "publication-manifest",
            *args,
            "--output",
            str(output),
            "--sha256sums",
            str(sums),
        ]
    )
    windows_checksum = windows / "hashmarks-windows-x86_64.exe.sha256"
    windows_checksum.write_text(
        windows_checksum.read_text(encoding="utf-8") + "unexpected\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SystemExit,
        match="standalone installer checksum does not match qualified standalone bytes",
    ):
        release_contract.main(["verify-publication", *args, "--manifest", str(output)])


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
