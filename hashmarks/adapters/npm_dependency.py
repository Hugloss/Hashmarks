"""Translate supplied npm lock inventory without resolving or inspecting packages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from hashmarks.paths import normalize_relative_path

_MAX_LOCK_BYTES = 4_194_304
_MAX_PACKAGES = 1000
_PACKAGE_NAME = re.compile(r"(?:@[A-Za-z0-9._~-]+/)?[A-Za-z0-9._~-]+\Z")
_SOURCE_ID = "npm:lock"
_CONTEXT = "lock"


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate npm lock field: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError(f"invalid npm lock JSON constant: {value}")


def _lock_document(lock: bytes) -> dict[str, object]:
    if not isinstance(lock, bytes) or len(lock) > _MAX_LOCK_BYTES:
        raise ValueError("npm lock requires at most 4194304 bytes")
    try:
        value = json.loads(
            lock.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid npm lock JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("npm lock must be an object")
    if type(value.get("lockfileVersion")) is not int or value[
        "lockfileVersion"
    ] not in {
        2,
        3,
    }:
        raise ValueError("npm lock requires lockfileVersion 2 or 3")
    return value


def _package_rows(
    document: Mapping[str, object],
) -> list[tuple[str, Mapping[str, object]]]:
    packages = document.get("packages")
    if not isinstance(packages, dict) or len(packages) > _MAX_PACKAGES:
        raise ValueError("npm lock requires a packages object of at most 1000 entries")
    if any(not isinstance(row, dict) for row in packages.values()):
        raise ValueError("npm lock package descriptors must be objects")
    return sorted(cast("dict[str, Mapping[str, object]]", packages).items())


def _install_namespace(location: str) -> str | None:
    if normalize_relative_path(location, allow_root=False) != location:
        raise ValueError("npm lock package locations must be canonical relative paths")
    tail = location.rsplit("node_modules/", 1)
    if len(tail) != 2 or (tail[0] and not tail[0].endswith("/")):
        return None
    namespace = tail[1]
    return namespace if _PACKAGE_NAME.fullmatch(namespace) else None


def _optional_text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field, "")
    if not isinstance(value, str):
        raise ValueError(f"npm lock package {field} must be a string")
    return value


def _unsupported_package(
    row: Mapping[str, object], namespace: str | None
) -> str | None:
    if type(row.get("link", False)) is not bool:
        raise ValueError("npm lock package link must be a boolean")
    if row.get("link"):
        return "linked-package-not-observed"
    if namespace is None:
        return "workspace-or-non-install-location-not-observed"
    if not _optional_text(row, "version"):
        return "package-version-unavailable"
    resolved = _optional_text(row, "resolved")
    if resolved.startswith(("file:", "link:", "./", "../", "/")):
        return "local-package-source-not-observed"
    return None


@dataclass(frozen=True)
class _Package:
    namespace: str
    name: str
    version: str
    source: str
    marker: str

    @property
    def node_id(self) -> str:
        identity = hashlib.sha256(self.source.encode()).hexdigest()[:24]
        return f"{self.name}:{self.version}:{identity}"


def _package(location: str, row: Mapping[str, object], namespace: str) -> _Package:
    name = _optional_text(row, "name") or namespace
    if not _PACKAGE_NAME.fullmatch(name):
        raise ValueError("npm lock package name is not a supported package identity")
    source = {
        "location": location,
        "resolved": _optional_text(row, "resolved"),
        "integrity": _optional_text(row, "integrity"),
    }
    marker = {
        key: row[key]
        for key in ("os", "cpu", "libc", "optional", "dev", "devOptional", "peer")
        if key in row
    }
    return _Package(
        namespace,
        name,
        _optional_text(row, "version"),
        json.dumps(source, sort_keys=True, separators=(",", ":")),
        json.dumps(marker, sort_keys=True, separators=(",", ":")) if marker else "",
    )


def _packages(
    document: Mapping[str, object],
) -> tuple[list[_Package], list[dict[str, str]]]:
    packages: list[_Package] = []
    omissions: list[dict[str, str]] = []
    for location, row in _package_rows(document):
        if not location:
            continue
        namespace = _install_namespace(location)
        reason = _unsupported_package(row, namespace)
        if reason is not None:
            omissions.append({"location": location, "reason": reason})
        else:
            packages.append(_package(location, row, cast("str", namespace)))
    return packages, omissions


def _facts(packages: Sequence[_Package]) -> dict[str, object]:
    components = {
        row.name: {"component_id": row.name, "name": row.name, "ecosystem": "npm"}
        for row in packages
    }
    owners: dict[str, list[str]] = {}
    for row in packages:
        owners.setdefault(row.namespace, []).append(row.node_id)
    return {
        "components": [components[name] for name in sorted(components)],
        "selections": [
            {
                "node_id": row.node_id,
                "component_id": row.name,
                "version": row.version,
                "source": row.source,
                "marker": row.marker,
                "contexts": [_CONTEXT],
                "evidence_sources": [_SOURCE_ID],
            }
            for row in packages
        ],
        "inventory": [
            {
                "node_id": row.node_id,
                "context": _CONTEXT,
                "evidence_sources": [_SOURCE_ID],
            }
            for row in packages
        ],
        "module_ownership": [
            {
                "module": namespace,
                "context": _CONTEXT,
                "owners": sorted(owners[namespace]),
                "completeness": "incomplete",
                "evidence_sources": [_SOURCE_ID],
            }
            for namespace in sorted(owners)
        ],
    }


def npm_lock_dependency_observation(
    *, lock: bytes, repository_inputs: Sequence[Mapping[str, object]] = ()
) -> dict[str, object]:
    """Translate explicit v2/v3 lock-recorded package slots, without a Node resolver.

    Native slot names establish positive namespace correspondence only.
    Aliases retain the separately declared component name. Nested slots remain
    separate selections; neither hoisting nor workspace/exports resolution is
    inferred. The caller owns capture and environment authenticity.
    """
    document = _lock_document(lock)
    packages, omissions = _packages(document)
    return {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {
            "kind": "npm-package-lock",
            "schema_version": str(document["lockfileVersion"]),
            "adapter_semantics": "hashmarks.npm-dependency-adapter.v1",
            "unsupported": omissions,
            "module_ownership_limits": [
                "positive-native-install-namespace-correspondence-only",
                "producer-and-environment-authority-caller-claimed",
                "actual-installation-and-runtime-loadability-not-observed",
                "workspace-links-and-local-package-sources-not-observed",
                "subpath-exports-conditions-and-runtime-resolution-not-observed",
                "dependency-edges-not-reconstructed",
            ],
        },
        "scope": {"package_scope": "lock-recorded-external-package-locations"},
        "contexts": [_CONTEXT],
        "roots": [],
        "relationships": [],
        "evidence_sources": [
            {
                "source_id": _SOURCE_ID,
                "kind": "npm-package-lock",
                "authorities": ["module-ownership", "resolved-inventory", "selection"],
                "context": _CONTEXT,
                "completeness": "complete",
                "truncation": "complete",
                "producer_digest": "sha256:" + hashlib.sha256(lock).hexdigest(),
            }
        ],
        "coverage": [
            {
                "context": _CONTEXT,
                "kind": kind,
                "completeness": "incomplete"
                if omissions or kind == "module-ownership"
                else "complete",
                "truncation": "complete",
                "evidence_sources": [_SOURCE_ID],
            }
            for kind in ("selection", "resolved-inventory", "module-ownership")
        ],
        "repository_inputs": [dict(row) for row in repository_inputs],
        **_facts(packages),
    }
