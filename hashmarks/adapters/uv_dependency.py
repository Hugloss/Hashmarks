from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Mapping, Sequence

_SCHEMA = "hashmarks.dependency-resolution.v3"
_CONTEXT = "lock"


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _source(raw: object) -> str:
    if not isinstance(raw, Mapping) or not raw:
        raise ValueError("uv lock package source must be a non-empty object")
    return json.dumps(dict(raw), sort_keys=True, separators=(",", ":"))


def _node_id(name: str, version: str, source: str) -> str:
    source_identity = hashlib.sha256(source.encode()).hexdigest()[:16]
    return f"{name}:{version}@{source_identity}"


def _marker_list(document: Mapping[str, object], field: str) -> list[str]:
    raw = document.get(field, [])
    if not isinstance(raw, list) or any(
        not isinstance(marker, str) or not marker.strip() for marker in raw
    ):
        raise ValueError(f"uv lock {field} must be a list of strings")
    markers = [marker.strip() for marker in raw]
    if len(set(markers)) != len(markers):
        raise ValueError(f"uv lock contains duplicate values in {field}")
    return markers


def _dependency_target(
    dependency: Mapping[str, object],
    packages_by_name: Mapping[str, list[dict[str, object]]],
) -> dict[str, object]:
    name = str(dependency.get("name") or "").strip()
    if not name:
        raise ValueError("uv lock dependency name must not be empty")
    candidates = list(packages_by_name.get(name, ()))
    version = str(dependency.get("version") or "").strip()
    if version:
        candidates = [row for row in candidates if row["version"] == version]
    source_raw = dependency.get("source")
    if source_raw is not None:
        source = _source(source_raw)
        candidates = [row for row in candidates if row["source"] == source]
    if len(candidates) != 1:
        raise ValueError(
            f"uv lock dependency target must resolve uniquely: {name} "
            f"({len(candidates)} candidates)"
        )
    return candidates[0]


def uv_lock_dependency_observation(  # noqa: C901, PLR0912, PLR0914, PLR0915
    *,
    lock: bytes,
    repository_inputs: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Translate already-produced uv.lock bytes into dependency-resolution v3.

    The adapter is execution-free. It reads the lock as producer evidence and never
    invokes uv, resolves packages, reads dependency source, or parses pyproject.toml
    as resolved truth.
    """
    try:
        document = tomllib.loads(lock.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("invalid uv lock TOML") from exc

    lock_version = document.get("version")
    if lock_version != 1:
        raise ValueError(f"unsupported uv lock schema version: {lock_version}")
    resolution_markers = _marker_list(document, "resolution-markers")
    supported_environments = sorted(_marker_list(document, "supported-markers"))
    required_environments = sorted(_marker_list(document, "required-markers"))
    if document.get("conflicts"):
        raise ValueError("uv lock conflicts are not modeled")

    raw_packages = document.get("package", ())
    if not isinstance(raw_packages, list) or not raw_packages:
        raise ValueError("uv lock must contain at least one package")

    source_id = "uv:lock"
    packages: list[dict[str, object]] = []
    packages_by_name: dict[str, list[dict[str, object]]] = {}
    for raw in raw_packages:
        if not isinstance(raw, Mapping):
            raise ValueError("uv lock package must be an object")
        if raw.get("resolution-markers"):
            raise ValueError("uv package resolution forks are not modeled")
        name = str(raw.get("name") or "").strip()
        version = str(raw.get("version") or "").strip()
        if not name or not version:
            raise ValueError("uv lock package requires name and version")
        source_raw = raw.get("source")
        source = _source(source_raw)
        if (
            isinstance(source_raw, Mapping)
            and any(key in source_raw for key in ("virtual", "editable", "directory"))
            and sum(key in source_raw for key in ("virtual", "editable", "directory"))
            > 1
        ):
            raise ValueError(
                f"uv lock package has ambiguous local source identity: {name}"
            )
        row = {
            "name": name,
            "version": version,
            "source": source,
            "node_id": _node_id(name, version, source),
            "raw": raw,
        }
        packages.append(row)
        packages_by_name.setdefault(name, []).append(row)

    node_ids = [str(row["node_id"]) for row in packages]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("uv lock contains duplicate package selection identity")

    roots = [
        row
        for row in packages
        if isinstance(row["raw"].get("source"), Mapping)
        and any(
            str(row["raw"]["source"].get(kind) or "") == "."
            for kind in ("virtual", "editable", "directory")
        )
    ]
    if not roots:
        raise ValueError(
            "uv.lock alone does not identify a project root; "
            "workspace membership evidence is required"
        )

    relationships: list[dict[str, object]] = []
    for row in packages:
        raw = row["raw"]
        dependency_groups = [("", raw.get("dependencies", []))]
        for field, prefix in (
            ("optional-dependencies", "extra"),
            ("dev-dependencies", "dev"),
        ):
            groups = raw.get(field, {})
            if not isinstance(groups, Mapping):
                raise ValueError(f"uv lock {field} must be a table: {row['name']}")
            for group, dependencies in groups.items():
                if not isinstance(group, str) or not group or group != group.strip():
                    raise ValueError(f"uv lock {field} group name is invalid")
                dependency_groups.append((f"{prefix}:{group}", dependencies))
        for effective_scope, dependencies in dependency_groups:
            if not isinstance(dependencies, list):
                raise ValueError(f"uv lock dependencies must be a list: {row['name']}")
            for dependency in dependencies:
                if not isinstance(dependency, Mapping):
                    raise ValueError(
                        f"uv lock dependency must be an object: {row['name']}"
                    )
                target = _dependency_target(dependency, packages_by_name)
                relationships.append(
                    {
                        "source": row["node_id"],
                        "target": target["node_id"],
                        "kind": "dependency",
                        "context": _CONTEXT,
                        "effective_scope": effective_scope,
                        "marker": str(dependency.get("marker") or ""),
                        "evidence_sources": [source_id],
                    }
                )

    root_ids = {str(row["node_id"]) for row in roots}
    components: dict[str, dict[str, object]] = {}
    for row in packages:
        component_id = str(row["name"])
        component = {
            "component_id": component_id,
            "name": component_id,
            "ecosystem": "pypi",
        }
        previous = components.setdefault(component_id, component)
        if previous != component:
            raise ValueError(f"conflicting uv component identity: {component_id}")
    selections = [
        {
            "node_id": row["node_id"],
            "component_id": row["name"],
            "version": row["version"],
            "source": row["source"],
            "marker": "",
            "contexts": [_CONTEXT],
            "evidence_sources": [source_id],
        }
        for row in packages
    ]
    inventory = [
        {
            "node_id": row["node_id"],
            "context": _CONTEXT,
            "evidence_sources": [source_id],
        }
        for row in packages
        if str(row["node_id"]) not in root_ids
    ]
    producer_digest = _digest(lock)
    evidence_sources = [
        {
            "source_id": source_id,
            "kind": "uv-lock",
            "authorities": [
                "resolution-graph",
                "resolved-inventory",
                "selection",
            ],
            "context": _CONTEXT,
            "completeness": "complete",
            "truncation": "complete",
            "producer_digest": producer_digest,
        }
    ]

    return {
        "schema": _SCHEMA,
        "producer": {
            "kind": "uv-lock",
            "schema_version": str(document.get("version") or ""),
            "revision": str(document.get("revision") or ""),
            "resolution_markers": resolution_markers,
        },
        "scope": {
            **(
                {"requires_python": str(document["requires-python"])}
                if document.get("requires-python")
                else {}
            ),
            **(
                {"supported_environments": supported_environments}
                if supported_environments
                else {}
            ),
            **(
                {"required_environments": required_environments}
                if required_environments
                else {}
            ),
        },
        "contexts": [_CONTEXT],
        "roots": sorted(
            (
                {
                    "node_id": row["node_id"],
                    "context": _CONTEXT,
                    "evidence_sources": [source_id],
                }
                for row in roots
            ),
            key=lambda row: str(row["node_id"]),
        ),
        "evidence_sources": evidence_sources,
        "components": sorted(components.values(), key=lambda row: row["component_id"]),
        "selections": sorted(selections, key=lambda row: str(row["node_id"])),
        "inventory": sorted(inventory, key=lambda row: str(row["node_id"])),
        "relationships": sorted(
            relationships,
            key=lambda row: (
                str(row["source"]),
                str(row["target"]),
                str(row["effective_scope"]),
                str(row["marker"]),
            ),
        ),
        "coverage": [
            {
                "context": _CONTEXT,
                "kind": "resolution-graph",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": [source_id],
            },
            {
                "context": _CONTEXT,
                "kind": "resolved-inventory",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": [source_id],
            },
            {
                "context": _CONTEXT,
                "kind": "selection",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": [source_id],
            },
        ],
        "repository_inputs": [dict(row) for row in repository_inputs],
        "module_ownership": [],
    }
