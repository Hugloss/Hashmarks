from __future__ import annotations

import hashlib
import subprocess
import sys
import tarfile
from pathlib import Path

import hashmarks_build

FORBIDDEN_SDIST_ROOTS = {
    ".codex",
    ".gitignore",
    ".mcp.json",
    "AGENTS.md",
    "Makefile",
    "benchmarks",
    "opencode.json",
    "qualification-classification.json",
    "scripts",
    "tests",
}

EXPECTED_SDIST_ROOTS = {
    ".github",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "docs",
    "examples",
    "hashmarks",
    "hashmarks_build.py",
    "pyproject.toml",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sdist_members_are_the_deliberate_public_source_surface() -> None:
    members = hashmarks_build._sdist_members()
    roots = {path.parts[0] for path in members}
    assert roots == EXPECTED_SDIST_ROOTS
    assert not (roots & FORBIDDEN_SDIST_ROOTS)
    assert all(
        path != Path("docs/development")
        and Path("docs/development") not in path.parents
        for path in members
    )
    assert Path(".github/CONTRIBUTING.md") in members
    assert Path(".github/SECURITY.md") in members
    assert Path("docs/GETTING_STARTED.md") in members
    assert Path("docs/reference/PRODUCT_BOUNDARY.md") in members
    assert Path("examples/basic.py") in members
    assert Path("hashmarks/cli.py") in members


def test_sdist_archive_does_not_reintroduce_repository_only_material(
    tmp_path: Path,
) -> None:
    name = hashmarks_build.build_sdist(str(tmp_path))
    with tarfile.open(tmp_path / name, "r:gz") as archive:
        root = name.removesuffix(".tar.gz")
        relative = {
            Path(member).relative_to(root)
            for member in archive.getnames()
            if member != root and member != f"{root}/PKG-INFO"
        }
    roots = {path.parts[0] for path in relative}
    assert roots == EXPECTED_SDIST_ROOTS
    assert not any(
        path == Path("docs/development") or Path("docs/development") in path.parents
        for path in relative
    )


def test_extracted_sdist_rebuilds_the_direct_wheel_byte_identically(
    tmp_path: Path,
) -> None:
    direct_dir = tmp_path / "direct"
    sdist_dir = tmp_path / "sdist"
    extracted_dir = tmp_path / "extracted"
    rebuilt_dir = tmp_path / "rebuilt"
    direct_name = hashmarks_build.build_wheel(str(direct_dir))
    sdist_name = hashmarks_build.build_sdist(str(sdist_dir))

    with tarfile.open(sdist_dir / sdist_name, "r:gz") as archive:
        archive.extractall(extracted_dir, filter="data")
    root = extracted_dir / sdist_name.removesuffix(".tar.gz")

    code = """
import importlib.util
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
spec = importlib.util.spec_from_file_location("sdist_hashmarks_build", root / "hashmarks_build.py")
if spec is None or spec.loader is None:
    raise SystemExit("unable to load extracted build backend")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.build_wheel(str(out)))
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code, str(root), str(rebuilt_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    rebuilt_name = completed.stdout.strip()
    assert rebuilt_name == direct_name
    assert _sha256(rebuilt_dir / rebuilt_name) == _sha256(direct_dir / direct_name)


def test_shipped_markdown_relative_links_stay_inside_sdist() -> None:
    import re

    members = set(hashmarks_build._sdist_members())
    markdown = sorted(path for path in members if path.suffix.lower() == ".md")
    failures: list[str] = []
    for source in markdown:
        text = (hashmarks_build.ROOT / source).read_text(encoding="utf-8")
        for raw in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            target = raw.split("#", 1)[0].strip()
            if (
                not target
                or target == "..."
                or "://" in target
                or target.startswith("mailto:")
            ):
                continue
            resolved = source.parent / target
            try:
                normalized = (
                    Path(resolved).resolve().relative_to(hashmarks_build.ROOT.resolve())
                )
            except ValueError:
                failures.append(f"{source}: escapes sdist root -> {raw}")
                continue
            absolute = hashmarks_build.ROOT / normalized
            if absolute.is_file() and normalized not in members:
                failures.append(f"{source}: linked file not shipped -> {normalized}")
            elif absolute.is_dir() and not any(
                normalized == member or normalized in member.parents
                for member in members
            ):
                failures.append(
                    f"{source}: linked directory not shipped -> {normalized}"
                )
            elif not absolute.exists():
                failures.append(f"{source}: broken relative link -> {raw}")
    assert failures == []
