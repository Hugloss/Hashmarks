from __future__ import annotations

from pathlib import Path


def index_surface_for_path(path: str) -> str:
    """Classify one indexed repository path for measurement-only economics."""
    lower = path.lower()
    name = Path(lower).name
    suffix = Path(lower).suffix
    if name in {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "uv.lock",
        "poetry.lock",
        "cargo.lock",
        "go.sum",
    } or name.endswith(".lock"):
        return "lockfile"
    if "openapi" in name or "swagger" in name:
        return "openapi"
    if any(
        part in lower.split("/") for part in ("generated", "gen", "dist", "build")
    ) or name.endswith((".generated.ts", ".generated.js", "_generated.py")):
        return "generated"
    if "snapshot" in lower or suffix == ".snap":
        return "snapshot"
    if any(part in lower.split("/") for part in ("fixtures", "fixture", "testdata")):
        return "fixture"
    if any(
        part in lower.split("/")
        for part in ("locales", "locale", "i18n", "translations")
    ):
        return "translation"
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
