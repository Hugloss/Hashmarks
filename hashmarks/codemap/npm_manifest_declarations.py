"""Observe selected npm manifest and lock-bin syntax without selecting executables."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

from hashmarks.paths import normalize_relative_path

from .repository_declaration_provider import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderResult,
)

MAX_NPM_PATHS = 16
MAX_NPM_BYTES = 4 * 1024 * 1024
MAX_NPM_ENTRIES = 1024
_DEPENDENCY_FIELDS = ("dependencies", "devDependencies", "optionalDependencies")


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate npm document key: {name}")
        result[name] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"invalid npm JSON constant: {value}")


def _table(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or len(value) > MAX_NPM_ENTRIES:
        raise ValueError(f"{field} must be a bounded object")
    return value


def _string_table(value: object, field: str) -> dict[str, str]:
    entries = _table(value, field)
    if any(not isinstance(item, str) for item in entries.values()):
        raise ValueError(f"{field} must contain string values")
    return {name: str(item) for name, item in entries.items()}


def _bin(value: object, field: str) -> str | dict[str, str]:
    # A string is preserved as authored. Native npm alone decides its effective
    # command name and installation; no slot-name-derived default is invented.
    return value if isinstance(value, str) else _string_table(value, field)


def _metadata(document: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in ("name", "version", "integrity"):
        if name in document:
            value = document[name]
            if not isinstance(value, str):
                raise ValueError(f"npm {name} must be a string")
            result[name] = value
    if "bin" in document:
        result["bin"] = _bin(document["bin"], "npm bin")
    if "link" in document:
        if type(document["link"]) is not bool:
            raise ValueError("npm link must be a boolean")
        result["link"] = document["link"]
    return result


def _manifest(document: Mapping[str, object]) -> dict[str, object]:
    sections = ("scripts", *_DEPENDENCY_FIELDS)
    return {
        **_metadata(document),
        "declared_fields": sorted(
            name for name in (*sections, "bin") if name in document
        ),
        "scripts": _string_table(document.get("scripts", {}), "npm scripts"),
        "dependency_declarations": {
            name: _string_table(document[name], f"npm {name}")
            for name in _DEPENDENCY_FIELDS
            if name in document
        },
        "script_shell": "native-npm-owned",
        "dependency_resolution": "not-performed",
    }


def _lock(document: Mapping[str, object]) -> dict[str, object]:
    version = document.get("lockfileVersion")
    if type(version) is not int or version not in {2, 3}:
        raise ValueError("npm lock bin declarations require lockfileVersion 2 or 3")
    packages = _table(document.get("packages"), "npm lock packages")
    slots: list[dict[str, object]] = []
    for location, descriptor in packages.items():
        package = _table(descriptor, "npm lock package")
        if "bin" in package:
            slots.append({"package_location": location, **_metadata(package)})
    return {
        "lockfile_version": version,
        "bin_declarations": slots,
        "package_locations": "authored-lock-keys-not-resolved-installation",
        "dependency_resolution": "native-npm-owned",
        "effective_bin_names": "not-established",
    }


def _group(path: str, value: dict[str, object], *, provider: str) -> dict[str, object]:
    lock = PurePosixPath(path).name == "package-lock.json"
    scope = {
        "manifest_path": path,
        "project_directory": PurePosixPath(path).parent.as_posix(),
    }
    return {
        "group_id": path,
        "concept": {
            "kind": "npm-lock-bin-declarations" if lock else "npm-project-declarations"
        },
        "scope": scope,
        "correspondence": {
            "state": "unresolved",
            "basis": {"producer": provider, "reason": "authored-syntax-only"},
        },
        "declarations": [
            {
                "declaration_id": "selected-npm-syntax",
                "semantic_role": {"kind": "manifest-declaration"},
                "value_state": "resolved",
                "value": {
                    **value,
                    "authority": "authored-npm-syntax",
                    "native_interpretation": "not-established",
                    "installation": "not-observed",
                    "execution": "not-established",
                    "negative_evidence_admissible": False,
                },
                "producer": {"provider": provider, "parser": "json"},
                "evidence": [{"scope": "member", "path": path}],
            }
        ],
        "coverage": {
            "state": "incomplete",
            "truncation": "complete",
            "expected_declaration_ids": [],
            "scope": scope,
            "provenance": {
                "producer": provider,
                "reason": "selected-supported-fields-only",
            },
        },
    }


@dataclass(frozen=True, slots=True)
class NpmManifestDeclarations:
    """Read explicit npm source fields; never choose a script or bin provider."""

    paths: tuple[str, ...]
    name: str = "npm-manifests"
    fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= len(self.paths) <= MAX_NPM_PATHS or len(set(self.paths)) != len(
            self.paths
        ):
            raise ValueError("npm manifest provider requires 1..16 unique exact paths")
        if any(
            not isinstance(path, str)
            or normalize_relative_path(path, allow_root=False) != path
            or PurePosixPath(path).name not in {"package.json", "package-lock.json"}
            for path in self.paths
        ):
            raise ValueError(
                "npm manifest provider requires canonical npm manifest paths"
            )
        if len(self.fields) > 16 or len(set(self.fields)) != len(self.fields):
            raise ValueError("npm selected root fields must be unique and bounded")
        if any(not isinstance(name, str) or not name for name in self.fields):
            raise ValueError("npm selected root fields require non-empty names")

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self, context: RepositoryDeclarationProviderContext
    ) -> RepositoryDeclarationProviderResult:
        groups: list[dict[str, object]] = []
        missing: list[str] = []
        for path in sorted(self.paths):
            if not context.exists(path):
                missing.append(path)
                continue
            raw = context.read_bytes(path, max_bytes=MAX_NPM_BYTES)
            if len(raw) > MAX_NPM_BYTES:
                raise ValueError("npm manifest exceeds bounded JSON input")
            document = _table(
                json.loads(
                    raw, object_pairs_hook=_object, parse_constant=_invalid_constant
                ),
                "npm document",
            )
            value = (
                _lock(document)
                if PurePosixPath(path).name == "package-lock.json"
                else _manifest(document)
            )
            # Explicit opaque field transport lets consumers read their own
            # configuration without a second JSON parse or producer policy.
            value["selected_fields"] = {
                name: document[name] for name in self.fields if name in document
            }
            groups.append(_group(path, value, provider=self.name))
        return RepositoryDeclarationProviderResult(
            groups=tuple(groups),
            provenance={
                "provider": self.name,
                "semantics": "hashmarks.npm-manifest-syntax.v1",
                "parser": "json",
                "file_scope": sorted(self.paths),
                "selected_root_fields": list(self.fields),
                "missing_selected_paths": missing,
                "coverage": "selected-supported-fields-only",
                "semantic_coverage": "incomplete",
                "native_interpretation": "not-established",
                "execution": "not-performed",
                "negative_evidence_admissible": False,
            },
        )
