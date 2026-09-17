from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_RELEASE_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _config() -> dict[str, object]:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "tool"
    ]["hashmarks"]


def _release_tuple(value: str) -> tuple[int, int, int]:
    match = _RELEASE_RE.match(value.strip())
    if match is None:
        raise ValueError(f"unsupported version: {value!r}")
    return (
        int(match.group(1)),
        int(match.group(2) or 0),
        int(match.group(3) or 0),
    )


def _version_at_least(actual: str, minimum: str) -> bool:
    try:
        return _release_tuple(actual) >= _release_tuple(minimum)
    except ValueError:
        return False


def _pytest() -> int:
    from importlib.metadata import PackageNotFoundError, version

    qualification = _config()["qualification"]
    if not isinstance(qualification, dict):
        print("Hashmarks qualification configuration is invalid.", file=sys.stderr)  # noqa: T201 - intentional command output
        return 2
    minimum = str(qualification["pytest-min"])
    contract = f">={minimum}"
    try:
        actual = version("pytest")
    except PackageNotFoundError:
        print(  # noqa: T201 - intentional command output
            f"Hashmarks qualification requires project test group pytest {contract}; run: make init",
            file=sys.stderr,
        )
        return 2
    if not _version_at_least(actual, minimum):
        print(  # noqa: T201 - intentional command output
            f"Hashmarks qualification requires project test group pytest {contract}; environment provides {actual}.",
            file=sys.stderr,
        )
        return 2
    print(  # noqa: T201 - intentional command output
        f"qualification-runner pytest={actual} interpreter={sys.executable} contract={contract}"
    )
    return 0


def _ruff(*, floor: bool = False) -> int:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = project.get("dependency-groups", {}).get("lint", [])
    match = (
        re.fullmatch(r"ruff>=(\d+(?:\.\d+){1,2})", requirements[0])
        if len(requirements) == 1 and isinstance(requirements[0], str)
        else None
    )
    if match is None:
        print(  # noqa: T201 - intentional command output
            "Hashmarks lint group must declare one minimum-only Ruff requirement.",
            file=sys.stderr,
        )
        return 2
    minimum = match.group(1)
    contract = f">={minimum}"
    try:
        completed = subprocess.run(
            ["ruff", "--version"],
            cwd=_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print(  # noqa: T201 - intentional command output
            f"Hashmarks Ruff diagnostics require lint group ruff {contract}; ruff is absent.",
            file=sys.stderr,
        )
        return 2
    actual = completed.stdout.strip().removeprefix("ruff ")
    if completed.returncode != 0 or not _version_at_least(actual, minimum):
        print(  # noqa: T201 - intentional command output
            f"Hashmarks Ruff diagnostics require ruff {contract}; environment provides {actual or 'unusable'}.",
            file=sys.stderr,
        )
        return 2
    if floor and _release_tuple(actual) != _release_tuple(minimum):
        print(  # noqa: T201 - intentional command output
            f"Hashmarks Ruff floor check requires ruff {minimum}; environment provides {actual}.",
            file=sys.stderr,
        )
        return 2
    print(  # noqa: T201 - intentional command output
        f"diagnostic-runner ruff={actual} contract={contract} mode={'floor' if floor else 'supported'}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["pytest"]:
        return _pytest()
    if args == ["ruff"]:
        return _ruff()
    if args == ["ruff-floor"]:
        return _ruff(floor=True)
    print(  # noqa: T201 - intentional command output
        "usage: qualification_environment.py {pytest|ruff|ruff-floor}", file=sys.stderr
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
