from __future__ import annotations

from pathlib import Path


def _special_index_surface(
    lower: str, name: str, suffix: str, parts: set[str]
) -> str | None:
    """Classify artifact surfaces that take precedence over file roles."""
    if name in {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "uv.lock",
        "poetry.lock",
        "cargo.lock",
        "go.sum",
    } or name.endswith(".lock"):
        surface = "lockfile"
    elif "openapi" in name or "swagger" in name:
        surface = "openapi"
    elif parts.intersection({"generated", "gen", "dist", "build"}) or name.endswith(
        (".generated.ts", ".generated.js", "_generated.py")
    ):
        surface = "generated"
    elif "snapshot" in lower or suffix == ".snap":
        surface = "snapshot"
    elif parts.intersection({"fixtures", "fixture", "testdata"}):
        surface = "fixture"
    elif parts.intersection({"locales", "locale", "i18n", "translations"}):
        surface = "translation"
    else:
        surface = None
    return surface


def index_surface_for_path(path: str) -> str:
    """Classify one indexed repository path for measurement-only economics."""
    lower = path.lower()
    name = Path(lower).name
    suffix = Path(lower).suffix
    parts = set(lower.split("/"))
    special = _special_index_surface(lower, name, suffix, parts)
    if special is not None:
        return special
    if (
        lower.startswith(("tests/", "test/"))
        or "/tests/" in lower
        or name.startswith("test_")
        or name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    ):
        return "test"
    if (
        suffix in {".md", ".rst", ".adoc"}
        or lower.startswith("docs/")
        or "/docs/" in lower
    ):
        return "docs"
    if name in {
        "pyproject.toml",
        "package.json",
        "tsconfig.json",
        "makefile",
    } or suffix in {".toml", ".yaml", ".yml"}:
        return "config"
    if suffix in {
        ".py",
        ".pyi",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".kts",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
    }:
        return "source"
    return "other"
