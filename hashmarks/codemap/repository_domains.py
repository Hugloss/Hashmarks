from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import PurePosixPath

from .source_languages import SOURCE_SUFFIXES


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


_SOURCE_SUFFIXES = SOURCE_SUFFIXES

_CONFIG_SUFFIXES = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".conf"}
_SCRIPT_SUFFIXES = {".sh", ".bash", ".zsh", ".fish", ".ps1", ".cmd", ".bat"}


def _explicit_control_domains(
    name: str, parts: set[str]
) -> tuple[RepositoryDomain, ...]:
    """Recognize named ownership, build, and plan control surfaces."""
    domains: list[RepositoryDomain] = []
    if name in {"agents.md", "agents.override.md"} or name.endswith(".agents.md"):
        domains.extend(
            (
                RepositoryDomain.OWNERSHIP,
                RepositoryDomain.CONTRACT,
                RepositoryDomain.DOC,
            )
        )
    if name in {
        "makefile",
        "gnumakefile",
        "justfile",
        "taskfile",
        "taskfile.yml",
        "taskfile.yaml",
    }:
        domains.append(RepositoryDomain.BUILD)
    if "templates" in parts and ({"plans", "goons"} & parts):
        domains.extend((RepositoryDomain.PLAN, RepositoryDomain.CONFIG))
    if name in {"plan.yml", "plan.yaml", "goon.yml", "goon.yaml"}:
        domains.extend((RepositoryDomain.PLAN, RepositoryDomain.CONFIG))
    return tuple(dict.fromkeys(domains))


def _is_test_surface(name: str, parts: set[str]) -> bool:
    """Keep test role independent of test-shaped production source names."""
    if "test" in parts or "tests" in parts:
        return True
    if name.startswith("test_") and not parts.intersection({"src", "lib", "app"}):
        return True
    if "checks" in parts and name.endswith("_spec.py"):
        return True
    return name.endswith(
        (
            "_test.go",
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


def _document_contract_domains(
    lower: str, name: str, parts: set[str], suffix: str
) -> tuple[RepositoryDomain, ...]:
    """Classify repository contracts and explanatory documents in role order."""
    domains: list[RepositoryDomain] = []
    if any(term in lower for term in ("contract", "schema", "invariant", "policy")):
        domains.append(RepositoryDomain.CONTRACT)
    if "docs" in parts or suffix in {".md", ".rst", ".txt"}:
        domains.append(RepositoryDomain.DOC)
    if (
        "architecture" in lower
        or "development" in parts
        or name in {"readme.md", "architecture.md", "design.md"}
    ):
        domains.append(RepositoryDomain.ARCHITECTURE)
    return tuple(domains)


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
    suffix = rel.suffix.lower()
    domains: list[RepositoryDomain] = list(_explicit_control_domains(name, parts))
    if "scripts" in parts or suffix in _SCRIPT_SUFFIXES:
        domains.append(RepositoryDomain.SCRIPT)
    if suffix in _CONFIG_SUFFIXES:
        domains.append(RepositoryDomain.CONFIG)
    domains.extend(_document_contract_domains(lower, name, parts, suffix))
    if _is_test_surface(name, parts):
        domains.append(RepositoryDomain.TEST)
    if suffix in _SOURCE_SUFFIXES:
        domains.append(RepositoryDomain.SOURCE)
    return tuple(dict.fromkeys(domains))
