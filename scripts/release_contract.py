from __future__ import annotations

import argparse
import email
import hashlib
import json
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path


def _log_command_output(*values: object) -> None:
    sys.stdout.write(" ".join(str(value) for value in values) + "\n")


SCHEMA = "hashmarks.release-artifact-manifest.v2"


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
    payload["manifest_identity"] = _manifest_identity(payload)
    return payload


def _manifest_identity(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return "sha256:" + hashlib.sha256(SCHEMA.encode() + b"\0" + canonical).hexdigest()


def verify_release_manifest(
    dist: Path,
    *,
    tag: str,
    recorded: dict[str, object],
) -> None:
    expected_keys = {
        "schema",
        "project",
        "version",
        "tag",
        "distributions",
        "qualification_dependency_resolution",
        "publication_authority",
        "manifest_identity",
    }
    if set(recorded) != expected_keys:
        raise ValueError("release artifact manifest has unexpected fields")
    if recorded["schema"] != SCHEMA:
        raise ValueError("release artifact manifest schema mismatch")

    name = str(recorded["project"])
    version = str(recorded["version"])
    if recorded["tag"] != tag or tag != f"v{version}":
        raise ValueError(
            f"release tag mismatch: manifest={recorded['tag']!r}, requested={tag!r}"
        )
    if recorded["publication_authority"] != "external":
        raise ValueError("release publication authority mismatch")

    lock = recorded["qualification_dependency_resolution"]
    if not isinstance(lock, dict) or set(lock) != {"path", "sha256"}:
        raise ValueError("release dependency-resolution identity is malformed")
    if lock["path"] != "uv.lock":
        raise ValueError("release dependency-resolution path mismatch")
    lock_digest = str(lock["sha256"])
    if (
        not lock_digest.startswith("sha256:")
        or len(lock_digest) != len("sha256:") + 64
        or any(char not in "0123456789abcdef" for char in lock_digest[7:])
    ):
        raise ValueError("release dependency-resolution digest is malformed")

    dist = dist.resolve()
    expected_wheel = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
    expected_sdist = f"{name}-{version}.tar.gz"
    expected_entries = sorted((expected_wheel, expected_sdist))
    entries = sorted(path.name for path in dist.iterdir())
    if entries != expected_entries:
        raise ValueError(
            "release dist must contain exactly the manifest wheel and sdist; "
            f"expected {expected_entries!r}, got {entries!r}"
        )

    rows = [
        _distribution_row(dist / expected_wheel, kind="wheel"),
        _distribution_row(dist / expected_sdist, kind="sdist"),
    ]
    if recorded["distributions"] != rows:
        raise ValueError(
            "release artifact manifest does not match downloaded distribution bytes"
        )

    payload = dict(recorded)
    identity = str(payload.pop("manifest_identity"))
    if identity != _manifest_identity(payload):
        raise ValueError("release artifact manifest identity mismatch")


def _write_sha256sums(manifest: dict[str, object], path: Path) -> None:
    rows = manifest["distributions"]
    assert isinstance(rows, list)
    lines = []
    for row in rows:
        assert isinstance(row, dict)
        digest = str(row["sha256"]).removeprefix("sha256:")
        lines.append(f"{digest}  {row['filename']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

    if args.command == "verify":
        recorded = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        if not isinstance(recorded, dict):
            raise ValueError("release artifact manifest must be a JSON object")
        verify_release_manifest(Path(args.dist), tag=args.tag, recorded=recorded)
        _log_command_output("Hashmarks release artifact manifest: PASS")
        return 0

    value = release_manifest(root, Path(args.dist), tag=args.tag)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_sha256sums(value, Path(args.sha256sums))
    _log_command_output(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
