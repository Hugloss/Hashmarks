from __future__ import annotations

import argparse
import email
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path


def _log_command_output(*values: object) -> None:
    sys.stdout.write(" ".join(str(value) for value in values) + "\n")


SCHEMA = "hashmarks.release-artifact-manifest.v2"
PUBLICATION_SCHEMA = "hashmarks.release-publication-manifest.v1"
STANDALONE_FILENAME = "hashmarks-linux-x86_64"


def _project(root: Path) -> dict[str, object]:
    value = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    if not isinstance(value, dict):
        raise ValueError("[project] must be a table")
    return value


def _expected_tag(root: Path) -> str:
    return f"v{_project(root)['version']}"


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

    wheels = [dist / expected_wheel]
    sdists = [dist / expected_sdist]
    rows = [
        _distribution_row(wheels[0], kind="wheel"),
        _distribution_row(sdists[0], kind="sdist"),
    ]
    if rows[0]["filename"] != expected_wheel:
        raise ValueError(f"unexpected wheel filename: {rows[0]['filename']!r}")
    if rows[1]["filename"] != expected_sdist:
        raise ValueError(f"unexpected sdist filename: {rows[1]['filename']!r}")
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


def _standalone_row(path: Path, *, version: str) -> dict[str, object]:
    path = path.resolve()
    if path.name != STANDALONE_FILENAME:
        raise ValueError(
            "standalone release filename mismatch: "
            f"expected {STANDALONE_FILENAME!r}, got {path.name!r}"
        )
    if not path.is_file():
        raise ValueError(f"standalone release artifact is missing: {path}")

    try:
        completed = subprocess.run(
            [str(path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("standalone release version smoke test timed out") from exc
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

    return {
        "kind": "standalone",
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "platform": "linux",
        "architecture": "x86_64",
        "version": version,
    }


def publication_manifest(
    root: Path,
    dist: Path,
    standalone: Path,
    *,
    tag: str,
    source_sha: str,
) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError(
            "source_sha must be an exact lowercase 40-character commit SHA"
        )

    package = release_manifest(root, dist, tag=tag)
    version = str(package["version"])
    payload: dict[str, object] = {
        "schema": PUBLICATION_SCHEMA,
        "project": package["project"],
        "version": version,
        "tag": package["tag"],
        "source": {"commit_sha": source_sha},
        "distributions": package["distributions"],
        "standalone": _standalone_row(standalone, version=version),
        "qualification_dependency_resolution": package[
            "qualification_dependency_resolution"
        ],
        "package_qualification_identity": package["manifest_identity"],
        "publication_authority": package["publication_authority"],
    }
    payload["manifest_identity"] = _manifest_identity(PUBLICATION_SCHEMA, payload)
    return payload


def _write_sha256sums(manifest: dict[str, object], path: Path) -> None:
    rows = manifest["distributions"]
    assert isinstance(rows, list)
    checksum_rows = list(rows)
    standalone = manifest.get("standalone")
    if standalone is not None:
        assert isinstance(standalone, dict)
        checksum_rows.append(standalone)

    lines = []
    for row in checksum_rows:
        assert isinstance(row, dict)
        digest = str(row["sha256"]).removeprefix("sha256:")
        lines.append(f"{digest}  {row['filename']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_manifest(
    value: dict[str, object],
    *,
    output_path: str,
    sha256sums_path: str,
) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_sha256sums(value, Path(sha256sums_path))
    _log_command_output(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and bind Hashmarks release artifacts."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    tag = sub.add_parser("validate-tag")
    tag.add_argument("--root", default=".")
    tag.add_argument("--tag", required=True)

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

    publication = sub.add_parser("publication-manifest")
    publication.add_argument("--root", default=".")
    publication.add_argument("--dist", required=True)
    publication.add_argument("--standalone", required=True)
    publication.add_argument("--tag", required=True)
    publication.add_argument("--source-sha", required=True)
    publication.add_argument("--output", required=True)
    publication.add_argument("--sha256sums", required=True)

    verify_publication = sub.add_parser("verify-publication")
    verify_publication.add_argument("--root", default=".")
    verify_publication.add_argument("--dist", required=True)
    verify_publication.add_argument("--standalone", required=True)
    verify_publication.add_argument("--tag", required=True)
    verify_publication.add_argument("--source-sha", required=True)
    verify_publication.add_argument("--manifest", required=True)

    args = parser.parse_args(argv)
    try:
        return _run_command(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc


def _run_command(args) -> int:
    root = Path(args.root).resolve()
    if args.command == "validate-tag":
        expected = _expected_tag(root)
        if args.tag != expected:
            raise SystemExit(
                f"release tag mismatch: expected {expected!r}, got {args.tag!r}"
            )
        _log_command_output(f"Hashmarks release tag: PASS ({expected})")
        return 0

    if args.command in {"publication-manifest", "verify-publication"}:
        value = publication_manifest(
            root,
            Path(args.dist),
            Path(args.standalone),
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


if __name__ == "__main__":
    raise SystemExit(main())
