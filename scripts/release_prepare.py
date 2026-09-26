from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _replace_once(text: str, pattern: str, replacement: str, *, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"unable to locate exactly one {label}")
    return updated


def _project_version(root: Path) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    return str(project["version"])


def _prepared_version_files(
    root: Path,
    current: str,
    version: str,
) -> dict[Path, str]:
    pyproject = root / "pyproject.toml"
    runtime = root / "hashmarks" / "_version.py"
    readme = root / "README.md"
    return {
        pyproject: _replace_once(
            pyproject.read_text(encoding="utf-8"),
            rf'^version = "{re.escape(current)}"$',
            f'version = "{version}"',
            label="project version",
        ),
        runtime: _replace_once(
            runtime.read_text(encoding="utf-8"),
            rf'^__version__ = "{re.escape(current)}"$',
            f'__version__ = "{version}"',
            label="runtime version",
        ),
        readme: _replace_once(
            readme.read_text(encoding="utf-8"),
            rf"^Current package version: \*\*{re.escape(current)}\*\*\.$",
            f"Current package version: **{version}**.",
            label="README project version",
        ),
    }


def _prepared_changelog(root: Path, version: str) -> str:
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if re.search(rf"(?m)^## {re.escape(version)} — ", changelog):
        raise ValueError(f"CHANGELOG.md already contains release {version}")
    marker = "# Changelog\n\n"
    if not changelog.startswith(marker):
        raise ValueError("CHANGELOG.md must start with the canonical changelog heading")
    return (
        marker
        + f"## {version} — Development\n\n"
        + "- Replace this development placeholder with substantive public release notes.\n\n"
        + changelog[len(marker) :]
    )


def prepare_release(root: Path, version: str) -> None:
    root = root.resolve()
    if _VERSION.fullmatch(version) is None:
        raise ValueError(f"invalid release version: {version!r}")

    current = _project_version(root)
    if current == version:
        raise ValueError(f"release version is already {version}")

    prepared = _prepared_version_files(root, current, version)
    prepared[root / "CHANGELOG.md"] = _prepared_changelog(root, version)
    prepared[root / ".github" / "release-request.toml"] = f'version = "{version}"\n'

    for path, value in prepared.items():
        path.write_text(value, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the mechanical source edits for a normal Hashmarks release."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    try:
        prepare_release(Path(args.root), args.version)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    sys.stdout.write(
        f"Hashmarks release {args.version} prepared. "
        "Finalize CHANGELOG.md, refresh uv.lock, and run release preflight.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
