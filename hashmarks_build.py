"""Tiny stdlib-only PEP 517/660 backend for hashmarks.

The project intentionally has no runtime dependency and Linux/WSL daemon mode
must be runnable by uv without contacting a package index. Keeping the build
backend local removes the otherwise hidden setuptools bootstrap download.
"""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import os
import re
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _runtime_version() -> str:
    source = (ROOT / "hashmarks" / "_version.py").read_text(encoding="utf-8")
    match = re.search(
        r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', source, re.MULTILINE
    )
    if match is None:
        raise RuntimeError("hashmarks/_version.py does not declare __version__")
    return match.group(1)


def _project() -> tuple[str, str, str, tuple[str, ...]]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    version = str(project["version"])
    runtime_version = _runtime_version()
    if runtime_version != version:
        raise RuntimeError(
            f"release version mismatch: pyproject.toml={version!r}, hashmarks/_version.py={runtime_version!r}"
        )
    return (
        str(project["name"]),
        version,
        str(project.get("requires-python", ">=3.11")),
        tuple(sorted(project.get("optional-dependencies", {}).keys())),
    )


def _dist_info() -> str:
    name, version, _, _ = _project()
    return f"{name.replace('-', '_')}-{version}.dist-info"


def _project_metadata() -> dict[str, object]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return dict(data["project"])


def _header_value(value: object, *, field: str) -> str:
    text = str(value)
    if not text or "\n" in text or "\r" in text:
        raise RuntimeError(f"{field} must be a non-empty single-line value")
    return text


def _license_patterns(project: dict[str, object]) -> tuple[str, ...]:
    patterns = project.get("license-files")
    if patterns is None:
        return ()
    if not isinstance(patterns, list) or not all(
        isinstance(value, str) for value in patterns
    ):
        raise RuntimeError("project.license-files must be an array of strings")
    return tuple(patterns)


def _license_pattern_paths(pattern: str, root: Path) -> tuple[Path, ...]:
    if not pattern or "\\" in pattern:
        raise RuntimeError(
            "project.license-files patterns must use non-empty POSIX paths"
        )
    pattern_path = Path(pattern)
    if pattern_path.is_absolute() or ".." in pattern_path.parts:
        raise RuntimeError(
            "project.license-files patterns must remain below the project root"
        )
    files = [path for path in ROOT.glob(pattern) if path.is_file()]
    if not files:
        raise RuntimeError(
            f"project.license-files pattern matched no files: {pattern!r}"
        )
    relative_paths = []
    for path in files:
        try:
            relative = path.resolve().relative_to(root)
        except ValueError as exc:
            raise RuntimeError(
                "project.license-files resolved outside the project root"
            ) from exc
        path.resolve().read_text(encoding="utf-8")
        relative_paths.append(relative)
    return tuple(relative_paths)


def _license_file_paths(project: dict[str, object]) -> tuple[Path, ...]:
    root = ROOT.resolve()
    matched = {
        relative.as_posix(): relative
        for pattern in _license_patterns(project)
        for relative in _license_pattern_paths(pattern, root)
    }
    return tuple(matched[key] for key in sorted(matched))


def _publication_metadata_lines(project: dict[str, object]) -> list[str]:
    lines: list[str] = []
    license_expression = project.get("license")
    if license_expression is not None:
        if not isinstance(license_expression, str):
            raise RuntimeError("project.license must use the PEP 639 SPDX string form")
        lines.append(
            "License-Expression: "
            + _header_value(license_expression, field="project.license")
        )

    lines.extend(
        f"License-File: {path.as_posix()}" for path in _license_file_paths(project)
    )

    urls = project.get("urls")
    if urls is not None:
        if not isinstance(urls, dict):
            raise RuntimeError("project.urls must be a table")
        for label, value in sorted(urls.items()):
            label_text = _header_value(label, field="project.urls label")
            if len(label_text) > 32:
                raise RuntimeError("project.urls labels must be at most 32 characters")
            url = _header_value(value, field=f"project.urls.{label_text}")
            lines.append(f"Project-URL: {label_text}, {url}")
    return lines


def _metadata_bytes() -> bytes:
    name, version, requires_python, extras = _project()
    project = _project_metadata()
    lines = [
        "Metadata-Version: 2.4",
        f"Name: {name}",
        f"Version: {version}",
        f"Summary: {project.get('description', '')}",
        f"Requires-Python: {requires_python}",
        "Description-Content-Type: text/markdown",
    ]
    keywords = tuple(str(value) for value in project.get("keywords", ()))
    if keywords:
        lines.append(f"Keywords: {','.join(keywords)}")
    lines.extend(f"Classifier: {value}" for value in project.get("classifiers", ()))
    lines.extend(f"Provides-Extra: {extra}" for extra in extras)
    optional = project.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        raise RuntimeError("project.optional-dependencies must be a table")
    for extra in sorted(optional):
        requirements = optional[extra]
        if not isinstance(requirements, list) or not all(
            isinstance(value, str) and value.strip() for value in requirements
        ):
            raise RuntimeError(
                f"project.optional-dependencies.{extra} must be an array of non-empty requirement strings"
            )
        for requirement in requirements:
            lines.append(f'Requires-Dist: {requirement}; extra == "{extra}"')
    lines.extend(_publication_metadata_lines(project))
    description = (ROOT / "README.md").read_text(encoding="utf-8")
    return ("\n".join(lines) + "\n\n" + description + "\n").encode("utf-8")


def _wheel_bytes() -> bytes:
    return (
        b"Wheel-Version: 1.0\n"
        b"Generator: hashmarks-stdlib-backend\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n\n"
    )


def _entry_points_bytes() -> bytes:
    return b"[console_scripts]\nhashmarks = hashmarks.cli:main\n"


def _hash_record(data: bytes) -> tuple[str, str]:
    digest = (
        base64.urlsafe_b64encode(hashlib.sha256(data).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return f"sha256={digest}", str(len(data))


def _wheel_info(member: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def _wheel_members(
    name: str, version: str, dist_info: str, *, editable: bool
) -> dict[str, bytes]:
    members: dict[str, bytes] = {
        f"{dist_info}/METADATA": _metadata_bytes(),
        f"{dist_info}/WHEEL": _wheel_bytes(),
        f"{dist_info}/entry_points.txt": _entry_points_bytes(),
    }
    project = _project_metadata()
    for relative in _license_file_paths(project):
        members[f"{dist_info}/licenses/{relative.as_posix()}"] = (
            ROOT / relative
        ).read_bytes()

    if editable:
        pth_name = f"__editable__.{name.replace('-', '_')}-{version}.pth"
        members[pth_name] = (str(ROOT) + os.linesep).encode("utf-8")
    else:
        package = ROOT / "hashmarks"
        for path in sorted(package.rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            ):
                members[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    return members


def _record_bytes(members: dict[str, bytes], dist_info: str) -> tuple[str, bytes]:
    rows = []
    for member, data in sorted(members.items()):
        digest, size = _hash_record(data)
        rows.append((member, digest, size))
    record_name = f"{dist_info}/RECORD"
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    writer.writerow((record_name, "", ""))
    return record_name, buffer.getvalue().encode("utf-8")


def _write_wheel(wheel_directory: str, *, editable: bool) -> str:
    name, version, _, _ = _project()
    wheel_name = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
    target = Path(wheel_directory) / wheel_name
    target.parent.mkdir(parents=True, exist_ok=True)
    dist_info = _dist_info()
    members = _wheel_members(name, version, dist_info, editable=editable)

    record_name, record = _record_bytes(members, dist_info)
    members[record_name] = record

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for member, data in sorted(members.items()):
            zf.writestr(_wheel_info(member), data)
    return wheel_name


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_editable(config_settings=None):
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    dist_info = Path(metadata_directory) / _dist_info()
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_bytes(_metadata_bytes())
    (dist_info / "WHEEL").write_bytes(_wheel_bytes())
    (dist_info / "entry_points.txt").write_bytes(_entry_points_bytes())
    return dist_info.name


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):
    return prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _write_wheel(wheel_directory, editable=False)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    return _write_wheel(wheel_directory, editable=True)


def get_requires_for_build_sdist(config_settings=None):
    return []


_SDIST_FILES = (
    Path("pyproject.toml"),
    Path("hashmarks_build.py"),
    Path("README.md"),
    Path("CHANGELOG.md"),
    Path(".github/CONTRIBUTING.md"),
    Path(".github/SECURITY.md"),
)

_SDIST_DIRECTORIES = (
    Path("hashmarks"),
    Path("docs"),
    Path("examples"),
)

_SDIST_EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".hashmarks",
    ".venv",
    "dist",
    "build",
}


def _admitted_sdist_path(path: Path) -> Path | None:
    if not path.is_file():
        return None
    relative = path.relative_to(ROOT)
    if any(part in _SDIST_EXCLUDED_PARTS for part in relative.parts):
        return None
    if path.suffix in {".pyc", ".pyo"}:
        return None
    return relative


def _unique_paths(paths: list[Path]) -> list[Path]:
    result = []
    seen = set()
    for path in paths:
        key = path.as_posix()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _sdist_members() -> list[Path]:
    """Return the intentional public source-distribution surface.

    The sdist is a buildable public source release, not a mirror of the development
    checkout. Tests, benchmarks, qualification scripts/receipts, and contributor-agent
    instructions stay in the repository checkout but are not shipped through PyPI.
    Current user/reference documentation and
    examples remain available to people inspecting the sdist.
    """
    candidates = [relative for relative in _SDIST_FILES if (ROOT / relative).is_file()]
    for rel in _SDIST_DIRECTORIES:
        source = ROOT / rel
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*")):
            relative = _admitted_sdist_path(path)
            if relative is not None:
                candidates.append(relative)
    candidates.extend(_license_file_paths(_project_metadata()))
    return _unique_paths(candidates)


def _deterministic_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def build_sdist(sdist_directory, config_settings=None):
    name, version, _, _ = _project()
    normalized = name.replace("-", "_")
    root_name = f"{normalized}-{version}"
    filename = f"{root_name}.tar.gz"
    target = Path(sdist_directory) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
            ) as archive:
                for relative in _sdist_members():
                    archive.add(
                        ROOT / relative,
                        arcname=f"{root_name}/{relative.as_posix()}",
                        recursive=False,
                        filter=_deterministic_tar_info,
                    )
                metadata = _metadata_bytes()
                info = tarfile.TarInfo(name=f"{root_name}/PKG-INFO")
                info.size = len(metadata)
                info.mode = 0o644
                archive.addfile(_deterministic_tar_info(info), io.BytesIO(metadata))
    return filename
