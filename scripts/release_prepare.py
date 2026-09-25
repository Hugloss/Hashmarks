from __future__ import annotations

import argparse
import re
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


def prepare_release(root: Path, version: str) -> None:
    root = root.resolve()
    if _VERSION.fullmatch(version) is None:
        raise ValueError(f"invalid release version: {version!r}")

    current = _project_version(root)
    if current == version:
        raise ValueError(f"release version is already {version}")

    pyproject = root / "pyproject.toml"
    pyproject_text = pyproject.read_text(encoding="utf-8")
    pyproject_new = _replace_once(
        pyproject_text,
        rf'(?m)^version = "{re.escape(current)}"$',
        f'version = "{version}"',
        label="project version",
    )

    runtime = root / "hashmarks" / "_version.py"
    runtime_text = runtime.read_text(encoding="utf-8")
    runtime_new = _replace_once(
        runtime_text,
        rf'(?m)^__version__ = "{re.escape(current)}"$',
        f'__version__ = "{version}"',
        label="runtime version",
    )

    readme = root / "README.md"
    readme_text = readme.read_text(encoding="utf-8")
    readme_new = _replace_once(
        readme_text,
        rf"(?m)^Current package version: \*\*{re.escape(current)}\*\*\.$",
        f"Current package version: **{version}**.",
        label="README project version",
    )

    changelog = root / "CHANGELOG.md"
    changelog_text = changelog.read_text(encoding="utf-8")
    if re.search(rf"(?m)^## {re.escape(version)} — ", changelog_text):
        raise ValueError(f"CHANGELOG.md already contains release {version}")
    marker = "# Changelog\n\n"
    if not changelog_text.startswith(marker):
        raise ValueError("CHANGELOG.md must start with the canonical changelog heading")
    changelog_new = (
        marker
        + f"## {version} — Development\n\n"
        + "- Replace this development placeholder with substantive public release notes.\n\n"
        + changelog_text[len(marker) :]
    )

    request = root / ".github" / "release-request.toml"
    request_new = f'version = "{version}"\n'

    pyproject.write_text(pyproject_new, encoding="utf-8")
    runtime.write_text(runtime_new, encoding="utf-8")
    readme.write_text(readme_new, encoding="utf-8")
    changelog.write_text(changelog_new, encoding="utf-8")
    request.write_text(request_new, encoding="utf-8")


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
    print(
        f"Hashmarks release {args.version} prepared. "
        "Finalize CHANGELOG.md, refresh uv.lock, and run release preflight."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
