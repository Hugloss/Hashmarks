from __future__ import annotations

import argparse
import email
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path


def _log_command_output(*values: object) -> None:
    sys.stdout.write(" ".join(str(value) for value in values) + "\n")


SCHEMA = "hashmarks.release-artifact-manifest.v2"
PUBLICATION_SCHEMA = "hashmarks.release-publication-manifest.v3"
STANDALONE_QUALIFICATION_SCHEMA = "hashmarks.standalone-qualification.v1"
STANDALONE_QUALIFICATION_FILENAME = "standalone-qualification.json"
STANDALONE_SPECS = {
    ("linux", "x86_64"): "hashmarks-linux-x86_64",
    ("windows", "x86_64"): "hashmarks-windows-x86_64.exe",
}
REQUIRED_STANDALONES = frozenset(STANDALONE_SPECS)
BOOTSTRAP_INSTALLERS = {
    "linux-wsl": "install.sh",
    "windows": "install.ps1",
}


def _project(root: Path) -> dict[str, object]:
    value = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    if not isinstance(value, dict):
        raise ValueError("[project] must be a table")
    return value


def _expected_tag(root: Path) -> str:
    return f"v{_project(root)['version']}"


def validate_release_notes(root: Path, version: str) -> None:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ValueError(f"invalid release version: {version!r}")

    changelog = (root.resolve() / "CHANGELOG.md").read_text(encoding="utf-8")
    marker = f"## {version} — "
    if changelog.count(marker) != 1:
        raise ValueError(f"CHANGELOG.md must contain exactly one {version} heading")

    section = changelog.split(marker, 1)[1].split("\n## ", 1)[0]
    lines = section.splitlines()
    heading_label = lines[0].strip() if lines else ""
    if not heading_label or "development" in heading_label.lower():
        raise ValueError(f"CHANGELOG.md still marks {version} as Development")

    body = "\n".join(lines[1:]).strip()
    if not body:
        raise ValueError(f"CHANGELOG.md has no public release notes for {version}")
    if "replace this development placeholder" in body.lower():
        raise ValueError(
            f"CHANGELOG.md still contains the {version} release placeholder"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _manifest_identity(schema: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return "sha256:" + hashlib.sha256(schema.encode() + b"\0" + canonical).hexdigest()


def _wheel_metadata(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(names) != 1:
            raise ValueError("wheel must contain exactly one METADATA file")
        message = email.message_from_bytes(archive.read(names[0]))
    return str(message["Name"]), str(message["Version"])


def _sdist_metadata(path: Path) -> tuple[str, str]:
    with tarfile.open(path, "r:gz") as archive:
        candidates = [
            m for m in archive.getmembers() if m.name.endswith("/pyproject.toml")
        ]
        if len(candidates) != 1:
            raise ValueError("sdist must contain exactly one pyproject.toml")
        stream = archive.extractfile(candidates[0])
        if stream is None:
            raise ValueError("unable to read sdist pyproject.toml")
        project = tomllib.loads(stream.read().decode("utf-8"))["project"]
    return str(project["name"]), str(project["version"])


def _distribution_row(path: Path, *, kind: str) -> dict[str, object]:
    name, version = _wheel_metadata(path) if kind == "wheel" else _sdist_metadata(path)
    return {
        "kind": kind,
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "project": name,
        "version": version,
    }


def release_manifest(root: Path, dist: Path, *, tag: str) -> dict[str, object]:
    root = root.resolve()
    dist = dist.resolve()
    project = _project(root)
    name = str(project["name"])
    version = str(project["version"])
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise ValueError(
            f"release tag mismatch: expected {expected_tag!r}, got {tag!r}"
        )

    expected_wheel = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
    expected_sdist = f"{name}-{version}.tar.gz"
    entries = sorted(path.name for path in dist.iterdir())
    expected_entries = sorted((expected_wheel, expected_sdist))
    if entries != expected_entries:
        raise ValueError(
            "release dist must contain exactly the expected wheel and sdist; "
            f"expected {expected_entries!r}, got {entries!r}"
        )

    rows = [
        _distribution_row(dist / expected_wheel, kind="wheel"),
        _distribution_row(dist / expected_sdist, kind="sdist"),
    ]
    for row in rows:
        if row["project"] != name or row["version"] != version:
            raise ValueError(f"distribution metadata mismatch: {row['filename']}")

    if not (root / "uv.lock").is_file():
        raise ValueError("committed uv.lock is required for release qualification")

    payload: dict[str, object] = {
        "schema": SCHEMA,
        "project": name,
        "version": version,
        "tag": tag,
        "distributions": rows,
        "qualification_dependency_resolution": {
            "path": "uv.lock",
            "sha256": _sha256(root / "uv.lock"),
        },
        "publication_authority": "external",
    }
    payload["manifest_identity"] = _manifest_identity(SCHEMA, payload)
    return payload


def _standalone_filename(platform: str, architecture: str) -> str:
    filename = STANDALONE_SPECS.get((platform, architecture))
    if filename is None:
        raise ValueError(f"unsupported standalone platform: {platform}/{architecture}")
    return filename


def _standalone_row(
    path: Path,
    *,
    version: str,
    platform: str,
    architecture: str,
) -> dict[str, object]:
    path = path.resolve()
    expected_filename = _standalone_filename(platform, architecture)
    if path.name != expected_filename:
        raise ValueError(
            "standalone release filename mismatch: "
            f"expected {expected_filename!r}, got {path.name!r}"
        )
    if not path.is_file():
        raise ValueError(f"standalone release artifact is missing: {path}")
    return {
        "kind": "standalone",
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "platform": platform,
        "architecture": architecture,
        "version": version,
    }


def _standalone_checksum_row(
    path: Path,
    standalone: dict[str, object],
) -> dict[str, object]:
    path = path.resolve()
    artifact_name = str(standalone["filename"])
    expected_filename = f"{artifact_name}.sha256"
    if path.name != expected_filename:
        raise ValueError(
            "standalone checksum filename mismatch: "
            f"expected {expected_filename!r}, got {path.name!r}"
        )
    if not path.is_file():
        raise ValueError(f"standalone checksum artifact is missing: {path}")

    digest = str(standalone["sha256"]).removeprefix("sha256:")
    expected = f"{digest}  {artifact_name}\n"
    if path.read_text(encoding="utf-8").replace("\r\n", "\n") != expected:
        raise ValueError(
            "standalone installer checksum does not match qualified standalone bytes"
        )
    return {
        "kind": "installer-checksum",
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "for": artifact_name,
        "platform": standalone["platform"],
        "architecture": standalone["architecture"],
    }


def _smoke_standalone(path: Path, *, version: str) -> None:
    try:
        completed = subprocess.run(
            [str(path.resolve()), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("standalone release version smoke test failed") from exc
    expected = f"hashmarks version {version}"
    if completed.returncode != 0:
        raise ValueError(
            "standalone release version smoke test failed with "
            f"exit code {completed.returncode}"
        )
    if completed.stdout.strip() != expected:
        raise ValueError(
            "standalone release version mismatch: "
            f"expected {expected!r}, got {completed.stdout.strip()!r}"
        )


def standalone_qualification(
    root: Path,
    artifact: Path,
    checksum: Path,
    *,
    platform: str,
    architecture: str,
    smoke: bool = True,
) -> dict[str, object]:
    root = root.resolve()
    project = _project(root)
    name = str(project["name"])
    version = str(project["version"])
    standalone = _standalone_row(
        artifact,
        version=version,
        platform=platform,
        architecture=architecture,
    )
    installer_checksum = _standalone_checksum_row(checksum, standalone)
    if smoke:
        _smoke_standalone(artifact, version=version)

    payload: dict[str, object] = {
        "schema": STANDALONE_QUALIFICATION_SCHEMA,
        "project": name,
        "version": version,
        "standalone": standalone,
        "installer_checksum": installer_checksum,
        "smoke": {
            "command": "--version",
            "reported_version": version,
            "status": "pass",
        },
    }
    payload["qualification_identity"] = _manifest_identity(
        STANDALONE_QUALIFICATION_SCHEMA,
        payload,
    )
    return payload


def _validate_qualification_identity(value: dict[str, object]) -> None:
    recorded = str(value.get("qualification_identity") or "")
    payload = {
        key: item for key, item in value.items() if key != "qualification_identity"
    }
    expected = _manifest_identity(STANDALONE_QUALIFICATION_SCHEMA, payload)
    if recorded != expected:
        raise ValueError("standalone qualification identity mismatch")


def _read_standalone_qualification(bundle: Path) -> dict[str, object]:
    receipt_path = bundle / STANDALONE_QUALIFICATION_FILENAME
    if not receipt_path.is_file():
        raise ValueError(f"standalone qualification receipt is missing: {receipt_path}")
    value = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("standalone qualification receipt must be an object")
    if value.get("schema") != STANDALONE_QUALIFICATION_SCHEMA:
        raise ValueError("standalone qualification schema mismatch")
    _validate_qualification_identity(value)
    return value


def _qualification_parts(
    root: Path,
    value: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], str, str, str]:
    standalone = value.get("standalone")
    checksum = value.get("installer_checksum")
    smoke = value.get("smoke")
    if not isinstance(standalone, dict) or not isinstance(checksum, dict):
        raise ValueError("standalone qualification receipt is malformed")
    if not isinstance(smoke, dict) or smoke.get("status") != "pass":
        raise ValueError("standalone qualification smoke evidence is missing")

    project = _project(root)
    version = str(project["version"])
    if value.get("project") != project["name"] or value.get("version") != version:
        raise ValueError("standalone qualification project/version mismatch")
    if smoke.get("reported_version") != version:
        raise ValueError("standalone qualification smoke version mismatch")

    platform = str(standalone.get("platform") or "")
    architecture = str(standalone.get("architecture") or "")
    return standalone, checksum, platform, architecture, version


def _validate_standalone_bundle_members(
    bundle: Path,
    artifact_name: str,
) -> None:
    expected_entries = sorted(
        (
            artifact_name,
            f"{artifact_name}.sha256",
            STANDALONE_QUALIFICATION_FILENAME,
        )
    )
    entries = sorted(path.name for path in bundle.iterdir())
    if entries != expected_entries:
        raise ValueError(
            "standalone bundle must contain exactly artifact, checksum, and "
            f"qualification receipt; expected {expected_entries!r}, got {entries!r}"
        )


def _load_standalone_bundle(root: Path, bundle: Path) -> dict[str, object]:
    root = root.resolve()
    bundle = bundle.resolve()
    value = _read_standalone_qualification(bundle)
    standalone, checksum, platform, architecture, version = _qualification_parts(
        root, value
    )
    artifact_name = _standalone_filename(platform, architecture)
    _validate_standalone_bundle_members(bundle, artifact_name)
    observed_standalone = _standalone_row(
        bundle / artifact_name,
        version=version,
        platform=platform,
        architecture=architecture,
    )
    observed_checksum = _standalone_checksum_row(
        bundle / f"{artifact_name}.sha256",
        observed_standalone,
    )
    if standalone != observed_standalone or checksum != observed_checksum:
        raise ValueError("standalone qualification does not match current bundle bytes")
    return value


def _qualified_standalones(
    root: Path,
    bundles: list[Path],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    qualifications = [_load_standalone_bundle(root, bundle) for bundle in bundles]
    standalones: list[dict[str, object]] = []
    checksums: list[dict[str, object]] = []
    observed: set[tuple[str, str]] = set()
    for qualification in qualifications:
        standalone = dict(qualification["standalone"])
        checksum = dict(qualification["installer_checksum"])
        key = (str(standalone["platform"]), str(standalone["architecture"]))
        if key in observed:
            raise ValueError(f"duplicate standalone qualification: {key[0]}/{key[1]}")
        observed.add(key)
        identity = qualification["qualification_identity"]
        standalone["qualification_identity"] = identity
        checksum["qualification_identity"] = identity
        standalones.append(standalone)
        checksums.append(checksum)

    if observed != REQUIRED_STANDALONES:
        missing = sorted(REQUIRED_STANDALONES - observed)
        extra = sorted(observed - REQUIRED_STANDALONES)
        raise ValueError(
            f"standalone publication set mismatch: missing={missing!r} extra={extra!r}"
        )
    standalones.sort(key=lambda row: (str(row["platform"]), str(row["architecture"])))
    checksums.sort(key=lambda row: (str(row["platform"]), str(row["architecture"])))
    return standalones, checksums


def _bootstrap_installer_rows(root: Path) -> list[dict[str, object]]:
    rows = []
    for platform, filename in BOOTSTRAP_INSTALLERS.items():
        path = root.resolve() / filename
        if not path.is_file():
            raise ValueError(f"bootstrap installer is missing: {path}")
        rows.append(
            {
                "kind": "bootstrap-installer",
                "filename": filename,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "platform": platform,
            }
        )
    return rows


def publication_manifest(
    root: Path,
    dist: Path,
    standalone_bundles: list[Path],
    *,
    tag: str,
    source_sha: str,
) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError(
            "source_sha must be an exact lowercase 40-character commit SHA"
        )

    package = release_manifest(root, dist, tag=tag)
    standalones, installer_checksums = _qualified_standalones(
        root,
        standalone_bundles,
    )
    payload: dict[str, object] = {
        "schema": PUBLICATION_SCHEMA,
        "project": package["project"],
        "version": package["version"],
        "tag": package["tag"],
        "source": {"commit_sha": source_sha},
        "distributions": package["distributions"],
        "standalones": standalones,
        "installer_checksums": installer_checksums,
        "bootstrap_installers": _bootstrap_installer_rows(root),
        "qualification_dependency_resolution": package[
            "qualification_dependency_resolution"
        ],
        "package_qualification_identity": package["manifest_identity"],
        "publication_authority": package["publication_authority"],
    }
    payload["manifest_identity"] = _manifest_identity(PUBLICATION_SCHEMA, payload)
    return payload


def _validate_publication_identity(manifest: dict[str, object]) -> None:
    recorded = str(manifest.get("manifest_identity") or "")
    payload = {
        key: value for key, value in manifest.items() if key != "manifest_identity"
    }
    expected = _manifest_identity(PUBLICATION_SCHEMA, payload)
    if recorded != expected:
        raise ValueError("publication manifest identity mismatch")


def publication_asset_names(manifest: dict[str, object]) -> list[str]:
    if manifest.get("schema") != PUBLICATION_SCHEMA:
        raise ValueError("publication asset list requires a publication manifest")
    _validate_publication_identity(manifest)

    names = ["release-manifest.json", "SHA256SUMS.txt"]
    for key in (
        "distributions",
        "standalones",
        "installer_checksums",
        "bootstrap_installers",
    ):
        rows = manifest.get(key)
        if not isinstance(rows, list):
            raise ValueError(f"publication manifest {key} must be a list")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("filename"), str):
                raise ValueError(f"publication manifest {key} contains an invalid row")
            names.append(str(row["filename"]))

    if len(names) != len(set(names)):
        raise ValueError("publication manifest contains duplicate public asset names")
    return sorted(names)


def _standalone_publication_source(
    filename: str,
    standalone_bundles: list[Path],
) -> Path:
    matches = [
        bundle.resolve() / filename
        for bundle in standalone_bundles
        if (bundle.resolve() / filename).is_file()
    ]
    if len(matches) != 1:
        raise ValueError(
            f"qualified public asset {filename!r} must resolve in exactly one "
            "standalone bundle"
        )
    return matches[0]


def _publication_source_map(
    manifest: dict[str, object],
    *,
    root: Path,
    manifest_path: Path,
    sha256sums_path: Path,
    dist: Path,
    standalone_bundles: list[Path],
) -> dict[str, Path]:
    if sha256sums_path.read_text(encoding="utf-8").replace("\r\n", "\n") != (
        _sha256sums_text(manifest)
    ):
        raise ValueError("SHA256SUMS.txt does not match publication manifest")
    sources = {
        "release-manifest.json": manifest_path.resolve(),
        "SHA256SUMS.txt": sha256sums_path.resolve(),
    }
    for row in manifest["distributions"]:
        assert isinstance(row, dict)
        filename = str(row["filename"])
        sources[filename] = dist.resolve() / filename
    for key in ("standalones", "installer_checksums"):
        for row in manifest[key]:
            assert isinstance(row, dict)
            filename = str(row["filename"])
            sources[filename] = _standalone_publication_source(
                filename,
                standalone_bundles,
            )
    for row in manifest["bootstrap_installers"]:
        assert isinstance(row, dict)
        filename = str(row["filename"])
        sources[filename] = root.resolve() / filename
    return sources


def _publication_rows_by_name(
    manifest: dict[str, object],
) -> dict[str, dict[str, object]]:
    return {
        str(row["filename"]): row
        for key in (
            "distributions",
            "standalones",
            "installer_checksums",
            "bootstrap_installers",
        )
        for row in manifest[key]
        if isinstance(row, dict)
    }


def _copy_publication_sources(
    manifest: dict[str, object],
    sources: dict[str, Path],
    output_dir: Path,
) -> None:
    names = publication_asset_names(manifest)
    if set(sources) != set(names):
        raise ValueError("publication source set does not match manifest asset names")

    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("publication output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = _publication_rows_by_name(manifest)
    for name in names:
        source = sources[name]
        if not source.is_file():
            raise ValueError(f"qualified public asset is missing: {source}")
        row = rows.get(name)
        if row is not None and _sha256(source) != row["sha256"]:
            raise ValueError(f"qualified public asset digest mismatch: {name}")
        shutil.copyfile(source, output_dir / name)

    observed = sorted(path.name for path in output_dir.iterdir() if path.is_file())
    if observed != names:
        raise ValueError("materialized publication asset set mismatch")


def _sha256sums_text(manifest: dict[str, object]) -> str:
    checksum_rows = list(manifest["distributions"])
    checksum_rows.extend(manifest.get("standalones", []))
    checksum_rows.extend(manifest.get("installer_checksums", []))
    checksum_rows.extend(manifest.get("bootstrap_installers", []))

    lines = []
    for row in checksum_rows:
        assert isinstance(row, dict)
        digest = str(row["sha256"]).removeprefix("sha256:")
        lines.append(f"{digest}  {row['filename']}")
    return "\n".join(lines) + "\n"


def _write_sha256sums(manifest: dict[str, object], path: Path) -> None:
    path.write_text(_sha256sums_text(manifest), encoding="utf-8")


def _write_json(value: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_manifest(
    value: dict[str, object],
    *,
    output_path: str,
    sha256sums_path: str,
) -> None:
    _write_json(value, Path(output_path))
    _write_sha256sums(value, Path(sha256sums_path))
    _log_command_output(json.dumps(value, indent=2, sort_keys=True))


def _add_publication_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".")
    parser.add_argument("--dist", required=True)
    parser.add_argument(
        "--standalone-bundle",
        action="append",
        required=True,
        dest="standalone_bundles",
    )
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-sha", required=True)


def _add_validation_commands(sub) -> None:
    tag = sub.add_parser("validate-tag")
    tag.add_argument("--root", default=".")
    tag.add_argument("--tag", required=True)

    release_notes = sub.add_parser("validate-release-notes")
    release_notes.add_argument("--root", default=".")
    release_notes.add_argument("--version", required=True)


def _add_package_commands(sub) -> None:
    manifest = sub.add_parser("manifest")
    manifest.add_argument("--root", default=".")
    manifest.add_argument("--dist", required=True)
    manifest.add_argument("--tag", required=True)
    manifest.add_argument("--output", required=True)
    manifest.add_argument("--sha256sums", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--root", default=".")
    verify.add_argument("--dist", required=True)
    verify.add_argument("--tag", required=True)
    verify.add_argument("--manifest", required=True)


def _add_standalone_commands(sub) -> None:
    standalone = sub.add_parser("standalone-qualification")
    standalone.add_argument("--root", default=".")
    standalone.add_argument("--artifact", required=True)
    standalone.add_argument("--checksum", required=True)
    standalone.add_argument("--platform", choices=("linux", "windows"), required=True)
    standalone.add_argument("--architecture", choices=("x86_64",), required=True)
    standalone.add_argument("--output", required=True)

    verify = sub.add_parser("verify-standalone-qualification")
    verify.add_argument("--root", default=".")
    verify.add_argument("--bundle", required=True)


def _add_publication_commands(sub) -> None:
    publication = sub.add_parser("publication-manifest")
    _add_publication_arguments(publication)
    publication.add_argument("--output", required=True)
    publication.add_argument("--sha256sums", required=True)

    verify = sub.add_parser("verify-publication")
    _add_publication_arguments(verify)
    verify.add_argument("--manifest", required=True)

    assets = sub.add_parser("publication-assets")
    assets.add_argument("--manifest", required=True)
    assets.add_argument("--output", required=True)

    materialize = sub.add_parser("materialize-publication")
    materialize.add_argument("--root", default=".")
    materialize.add_argument("--manifest", required=True)
    materialize.add_argument("--sha256sums", required=True)
    materialize.add_argument("--dist", required=True)
    materialize.add_argument(
        "--standalone-bundle",
        action="append",
        required=True,
        dest="standalone_bundles",
    )
    materialize.add_argument("--output-dir", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and bind Hashmarks release artifacts."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _add_validation_commands(sub)
    _add_package_commands(sub)
    _add_standalone_commands(sub)
    _add_publication_commands(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run_command(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc


def _run_validate_tag(args, root: Path) -> int:
    expected = _expected_tag(root)
    if args.tag != expected:
        raise SystemExit(
            f"release tag mismatch: expected {expected!r}, got {args.tag!r}"
        )
    _log_command_output(f"Hashmarks release tag: PASS ({expected})")
    return 0


def _run_standalone_command(args, root: Path) -> int:
    if args.command == "standalone-qualification":
        value = standalone_qualification(
            root,
            Path(args.artifact),
            Path(args.checksum),
            platform=args.platform,
            architecture=args.architecture,
        )
        _write_json(value, Path(args.output))
        _log_command_output(json.dumps(value, indent=2, sort_keys=True))
        return 0
    _load_standalone_bundle(root, Path(args.bundle))
    _log_command_output("Hashmarks standalone qualification: PASS")
    return 0


def _run_publication_assets(args) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("publication manifest must be an object")
    names = publication_asset_names(manifest)
    Path(args.output).write_text("\n".join(names) + "\n", encoding="utf-8")
    _log_command_output("Hashmarks publication asset set: PASS")
    return 0


def _run_materialize_publication(args) -> int:
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("publication manifest must be an object")
    sources = _publication_source_map(
        manifest,
        root=Path(args.root),
        manifest_path=manifest_path,
        sha256sums_path=Path(args.sha256sums),
        dist=Path(args.dist),
        standalone_bundles=[Path(item) for item in args.standalone_bundles],
    )
    _copy_publication_sources(manifest, sources, Path(args.output_dir))
    _log_command_output("Hashmarks publication bundle materialization: PASS")
    return 0


def _run_publication_command(args, root: Path) -> int:
    value = publication_manifest(
        root,
        Path(args.dist),
        [Path(item) for item in args.standalone_bundles],
        tag=args.tag,
        source_sha=args.source_sha,
    )
    if args.command == "publication-manifest":
        _write_manifest(
            value,
            output_path=args.output,
            sha256sums_path=args.sha256sums,
        )
        return 0
    recorded = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if recorded != value:
        raise SystemExit(
            "release publication manifest does not match current artifact bytes"
        )
    _log_command_output("Hashmarks release publication manifest: PASS")
    return 0


def _run_package_command(args, root: Path) -> int:
    value = release_manifest(root, Path(args.dist), tag=args.tag)
    if args.command == "manifest":
        _write_manifest(
            value,
            output_path=args.output,
            sha256sums_path=args.sha256sums,
        )
        return 0
    recorded = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if recorded != value:
        raise SystemExit(
            "release artifact manifest does not match current distribution bytes"
        )
    _log_command_output("Hashmarks release artifact manifest: PASS")
    return 0


def _run_command(args) -> int:
    root = Path(getattr(args, "root", ".")).resolve()
    if args.command == "validate-tag":
        result = _run_validate_tag(args, root)
    elif args.command == "validate-release-notes":
        validate_release_notes(root, args.version)
        _log_command_output(f"Hashmarks release notes: PASS ({args.version})")
        result = 0
    elif args.command == "publication-assets":
        result = _run_publication_assets(args)
    elif args.command == "materialize-publication":
        result = _run_materialize_publication(args)
    elif args.command in {
        "standalone-qualification",
        "verify-standalone-qualification",
    }:
        result = _run_standalone_command(args, root)
    elif args.command in {"publication-manifest", "verify-publication"}:
        result = _run_publication_command(args, root)
    else:
        result = _run_package_command(args, root)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
