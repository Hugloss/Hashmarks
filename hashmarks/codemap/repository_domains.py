from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import PurePosixPath


class RepositoryDomain(str, Enum):
    SOURCE = "source"
    TEST = "test"
    ARCHITECTURE = "architecture"
    OWNERSHIP = "ownership"
    BUILD = "build"
    PLAN = "plan"
    CONFIG = "config"
    SCRIPT = "script"
    CONTRACT = "contract"
    DOC = "doc"


_SOURCE_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".sql",
}
_CONFIG_SUFFIXES = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".conf"}
_SCRIPT_SUFFIXES = {".sh", ".bash", ".zsh", ".fish", ".ps1", ".cmd", ".bat"}


@lru_cache(maxsize=32768)
def is_test_path(path: str) -> bool:
    """Return pure path-only test classification with bounded process-local reuse."""
    name = path.rsplit("/", 1)[-1]
    lowered = path.lower()
    return (
        lowered.startswith("tests/")
        or "/tests/" in lowered
        or name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
    )


@lru_cache(maxsize=32768)
def classify_repository_path(path: str) -> tuple[RepositoryDomain, ...]:
    """Return deterministic, non-exclusive consumer-facing repository domains.

    This is derived retrieval metadata only.  It never grants visibility or
    authority and deliberately allows one path to serve several roles.
    """
    rel = PurePosixPath(path)
    lower = rel.as_posix().lower()
    name = rel.name.lower()
    parts = {part.lower() for part in rel.parts}
    domains: list[RepositoryDomain] = []

    def add(domain: RepositoryDomain) -> None:
        if domain not in domains:
            domains.append(domain)

    if name in {"agents.md", "agents.override.md"} or name.endswith(".agents.md"):
        add(RepositoryDomain.OWNERSHIP)
        add(RepositoryDomain.CONTRACT)
        add(RepositoryDomain.DOC)
    if name in {
        "makefile",
        "gnumakefile",
        "justfile",
        "taskfile",
        "taskfile.yml",
        "taskfile.yaml",
    }:
        add(RepositoryDomain.BUILD)
    if "templates" in parts and ({"plans", "goons"} & parts):
        add(RepositoryDomain.PLAN)
        add(RepositoryDomain.CONFIG)
    if name in {"plan.yml", "plan.yaml", "goon.yml", "goon.yaml"}:
        add(RepositoryDomain.PLAN)
        add(RepositoryDomain.CONFIG)
    if "scripts" in parts or rel.suffix.lower() in _SCRIPT_SUFFIXES:
        add(RepositoryDomain.SCRIPT)
    if rel.suffix.lower() in _CONFIG_SUFFIXES:
        add(RepositoryDomain.CONFIG)
    if (
        "contract" in lower
        or "schema" in lower
        or "invariant" in lower
        or "policy" in lower
    ):
        add(RepositoryDomain.CONTRACT)
    if "docs" in parts or rel.suffix.lower() in {".md", ".rst", ".txt"}:
        add(RepositoryDomain.DOC)
    if (
        "architecture" in lower
        or "development" in parts
        or name in {"readme.md", "architecture.md", "design.md"}
    ):
        add(RepositoryDomain.ARCHITECTURE)
    source_tree = bool(parts.intersection({"src", "lib", "app"}))
    if (
        "test" in parts
        or "tests" in parts
        or (name.startswith("test_") and not source_tree)
        or ("checks" in parts and name.endswith("_spec.py"))
        or name.endswith("_test.go")
        or name.endswith(
            (
                ".test.js",
                ".test.jsx",
                ".test.mjs",
                ".test.cjs",
                ".test.ts",
                ".test.tsx",
                ".test.mts",
                ".test.cts",
                ".spec.js",
                ".spec.jsx",
                ".spec.mjs",
                ".spec.cjs",
                ".spec.ts",
                ".spec.tsx",
                ".spec.mts",
                ".spec.cts",
            )
        )
    ):
        add(RepositoryDomain.TEST)
    if rel.suffix.lower() in _SOURCE_SUFFIXES:
        add(RepositoryDomain.SOURCE)
    return tuple(domains)
