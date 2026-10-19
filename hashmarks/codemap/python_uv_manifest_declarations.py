"""Explicit Python/uv manifest syntax observations using declaration authority.

Authored intent stays distinct from dependency-resolution evidence. This
provider imports no project code and neither invokes uv nor interprets a lock.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

from hashmarks.codemap.uv_workspace import (
    uv_workspace_member,
    uv_workspace_patterns,
)
from hashmarks.paths import normalize_relative_path

from .repository_declaration_contract import MAX_GROUPS, json_value
from .repository_declaration_provider import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderResult,
)

MAX_MANIFEST_PATHS = 16
MAX_MANIFEST_BYTES = 262_144
MAX_MANIFEST_ENTRIES = 256
_SOURCE_KEYS = frozenset(
    {
        "git",
        "url",
        "path",
        "index",
        "workspace",
        "editable",
        "branch",
        "tag",
        "rev",
        "subdirectory",
        "marker",
        "extra",
        "group",
    }
)


def _table(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a TOML table")
    if len(value) > MAX_MANIFEST_ENTRIES:
        raise ValueError(f"{field} exceeds manifest entry bound")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _strings(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_MANIFEST_ENTRIES:
        raise ValueError(f"{field} must be a bounded array of strings")
    return [_text(item, field) for item in value]


def _manifest_group(
    path: str,
    key: tuple[str, ...],
    kind: str,
    value: dict[str, object],
    *,
    provider: str,
    evidence_paths: tuple[str, ...] = (),
) -> dict[str, object]:
    scope = {
        "manifest_path": path,
        "project_directory": PurePosixPath(path).parent.as_posix(),
        "toml_key": list(key),
    }
    return {
        "group_id": f"{path}:{'.'.join(key)}",
        "concept": {"kind": kind},
        "scope": scope,
        "correspondence": {
            "state": "unresolved",
            "basis": {"producer": provider, "reason": "authored-intent-only"},
        },
        "declarations": [
            {
                "declaration_id": "authored-manifest-syntax",
                "semantic_role": {"kind": "manifest-declaration"},
                "value_state": "resolved",
                "value": {
                    **value,
                    "authority": "authored-manifest-syntax",
                    "native_interpretation": "not-established",
                    "lock_correspondence": "unresolved",
                    "negative_evidence_admissible": False,
                },
                "producer": {"provider": provider, "parser": "tomllib"},
                "evidence": [
                    {"scope": "member", "path": item}
                    for item in sorted({path, *evidence_paths})
                ],
            }
        ],
        "coverage": {
            "state": "incomplete",
            "truncation": "complete",
            "expected_declaration_ids": [],
            "scope": scope,
            "provenance": {
                "producer": provider,
                "reason": "selected-manifests-and-supported-declaration-keys-only",
            },
        },
    }


def _project_metadata(project: Mapping[str, object]) -> dict[str, object]:
    result = {
        key: _text(project[key], f"project.{key}")
        for key in ("name", "version", "requires-python")
        if key in project
    }
    dynamic = _strings(project.get("dynamic", []), "project.dynamic")
    return {
        "declared": result,
        "dynamic": dynamic,
        "dynamic_metadata_values": "not-established",
        "project_role": "declared-project-not-transitive-dependency",
    }


def _requirement_entries(
    values: object,
    *,
    field: str,
    group_names: frozenset[str] | None = None,
) -> list[dict[str, object]]:
    if not isinstance(values, list) or len(values) > MAX_MANIFEST_ENTRIES:
        raise ValueError(f"{field} must be a bounded array")
    entries: list[dict[str, object]] = []
    for ordinal, value in enumerate(values):
        if isinstance(value, str):
            entry = {
                "raw_requirement": _text(value, field),
                "requirement_interpretation": "not-established",
                "marker_evaluation": "not-performed",
            }
        elif group_names is not None:
            include = _table(value, field)
            if set(include) != {"include-group"}:
                raise ValueError(f"{field} supports only include-group table entries")
            target = _text(include["include-group"], field)
            entry = {
                "include_group": target,
                "target_declared_in_this_manifest": target in group_names,
                "effective_requirements": "not-expanded",
            }
        else:
            raise ValueError(f"{field} requires requirement strings")
        entries.append({"ordinal": ordinal, **entry})
    return entries


def _dependency_groups(
    path: str, document: Mapping[str, object], *, provider: str
) -> list[dict[str, object]]:
    project = _table(document.get("project", {}), "project")
    groups: list[dict[str, object]] = []
    if "dependencies" in project:
        groups.append(
            _dependency_group(
                path,
                ("project", "dependencies"),
                project["dependencies"],
                provider=provider,
            )
        )
    optional = _table(
        project.get("optional-dependencies", {}), "project.optional-dependencies"
    )
    for extra, entries in sorted(optional.items()):
        groups.append(
            _dependency_group(
                path,
                ("project", "optional-dependencies", extra),
                entries,
                provider=provider,
            )
        )
    declared_groups = _table(document.get("dependency-groups", {}), "dependency-groups")
    for name, entries in sorted(declared_groups.items()):
        groups.append(
            _dependency_group(
                path,
                ("dependency-groups", name),
                entries,
                provider=provider,
                group_names=frozenset(declared_groups),
            )
        )
    return groups


def _dependency_group(
    path: str,
    key: tuple[str, ...],
    entries: object,
    *,
    provider: str,
    group_names: frozenset[str] | None = None,
) -> dict[str, object]:
    return _manifest_group(
        path,
        key,
        "python-dependency-declarations",
        {
            "entries": _requirement_entries(
                entries,
                field=".".join(key),
                group_names=group_names,
            ),
            "selected_versions": "not-established",
            "group_inclusion": "direct-references-only-no-recursive-expansion",
        },
        provider=provider,
    )


def _script_groups(
    path: str, project: Mapping[str, object], *, provider: str
) -> list[dict[str, object]]:
    scripts = _table(project.get("scripts", {}), "project.scripts")
    return [
        _manifest_group(
            path,
            ("project", "scripts", name),
            "python-script-entrypoint-declaration",
            {
                "name": _text(name, "script name"),
                "target": _text(target, f"project.scripts.{name}"),
                "runtime_importability": "not-established",
                "installed_launcher": "not-established",
            },
            provider=provider,
        )
        for name, target in sorted(scripts.items())
    ]


def _build_system(value: object) -> dict[str, object]:
    table = _table(value, "build-system")
    fields: dict[str, object] = {}
    for key in ("requires", "backend-path"):
        if key in table:
            fields[key] = _strings(table[key], f"build-system.{key}")
    if "build-backend" in table:
        fields["build-backend"] = _text(
            table["build-backend"], "build-system.build-backend"
        )
    return {"declared": fields, "backend_execution": "not-established"}


def _source_alternatives(value: object) -> list[dict[str, object]]:
    alternatives = value if isinstance(value, list) else [value]
    if not alternatives or len(alternatives) > MAX_MANIFEST_ENTRIES:
        raise ValueError(
            "tool.uv.sources alternatives must be a non-empty bounded array"
        )
    result: list[dict[str, object]] = []
    for source in alternatives:
        table = _table(source, "tool.uv.sources entry")
        result.append(
            {
                "declared": json_value(table, name="uv source declaration"),
                "unsupported_keys": sorted(set(table) - _SOURCE_KEYS),
                "effective_source": "not-established",
            }
        )
    return result


def _uv_groups(
    path: str, uv: Mapping[str, object], *, provider: str
) -> list[dict[str, object]]:
    sources = _table(uv.get("sources", {}), "tool.uv.sources")
    groups = [
        _manifest_group(
            path,
            ("tool", "uv", "sources", name),
            "uv-source-declaration",
            {
                "name": _text(name, "source name"),
                "alternatives": _source_alternatives(value),
            },
            provider=provider,
        )
        for name, value in sorted(sources.items())
    ]
    if "dev-dependencies" in uv:
        groups.append(
            _dependency_group(
                path,
                ("tool", "uv", "dev-dependencies"),
                uv["dev-dependencies"],
                provider=provider,
            )
        )
    return groups


def _workspace_group(
    path: str,
    workspace: object,
    candidates: tuple[str, ...],
    *,
    provider: str,
) -> dict[str, object]:
    table = _table(workspace, "tool.uv.workspace")
    members = _strings(table.get("members", []), "tool.uv.workspace.members")
    excludes = _strings(table.get("exclude", []), "tool.uv.workspace.exclude")
    parent = PurePosixPath(path).parent
    matches = [
        {
            "manifest_path": candidate,
            "matches_declared_patterns": uv_workspace_member(
                PurePosixPath(candidate),
                parent,
                uv_workspace_patterns(members),
                uv_workspace_patterns(excludes),
            )
            if "members" in table
            else None,
        }
        for candidate in candidates
    ]
    return _manifest_group(
        path,
        ("tool", "uv", "workspace"),
        "uv-workspace-declaration",
        {
            "members": members,
            "members_declared": "members" in table,
            "exclude": excludes,
            "static_candidate_matches": matches,
            "candidate_scope": "selected-present-manifests-only",
            "pattern_semantics": "hashmarks-existing-fnmatchcase-candidate-filter",
            "effective_workspace_membership": "not-established",
        },
        provider=provider,
        evidence_paths=candidates,
    )


def _document_groups(
    path: str,
    document: Mapping[str, object],
    candidates: tuple[str, ...],
    *,
    provider: str,
) -> list[dict[str, object]]:
    project = _table(document.get("project", {}), "project")
    groups = _dependency_groups(path, document, provider=provider)
    if "project" in document:
        groups.append(
            _manifest_group(
                path,
                ("project",),
                "python-project-declaration",
                _project_metadata(project),
                provider=provider,
            )
        )
    groups.extend(_script_groups(path, project, provider=provider))
    if "build-system" in document:
        groups.append(
            _manifest_group(
                path,
                ("build-system",),
                "python-build-system-declaration",
                _build_system(document["build-system"]),
                provider=provider,
            )
        )
    tool = _table(document.get("tool", {}), "tool")
    uv = _table(tool.get("uv", {}), "tool.uv")
    groups.extend(_uv_groups(path, uv, provider=provider))
    if "workspace" in uv:
        groups.append(
            _workspace_group(path, uv["workspace"], candidates, provider=provider)
        )
    return groups


@dataclass(frozen=True, slots=True)
class PythonUvManifestDeclarations:
    """Observe explicit pyproject manifests, preserving intent and native unknowns."""

    paths: tuple[str, ...]
    name: str = "python-uv-manifests"

    def __post_init__(self) -> None:
        if not 1 <= len(self.paths) <= MAX_MANIFEST_PATHS:
            raise ValueError("manifest provider requires 1..16 exact paths")
        for path in self.paths:
            if (
                not isinstance(path, str)
                or normalize_relative_path(path, allow_root=False) != path
                or PurePosixPath(path).name != "pyproject.toml"
            ):
                raise ValueError(
                    "manifest provider requires canonical pyproject.toml paths"
                )
        if len(set(self.paths)) != len(self.paths):
            raise ValueError("manifest provider paths must be unique")

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        # Selection declares applicability; missing selected inputs are reported.
        return True

    def discover(
        self, context: RepositoryDeclarationProviderContext
    ) -> RepositoryDeclarationProviderResult:
        documents: dict[str, Mapping[str, object]] = {}
        missing: list[str] = []
        for path in sorted(self.paths):
            if not context.exists(path):
                missing.append(path)
                continue
            raw = context.read_bytes(path)
            if len(raw) > MAX_MANIFEST_BYTES:
                raise ValueError("manifest exceeds bounded TOML input")
            documents[path] = tomllib.loads(raw.decode("utf-8"))
        groups: list[dict[str, object]] = []
        for path, document in documents.items():
            groups.extend(
                _document_groups(path, document, tuple(documents), provider=self.name)
            )
            if len(groups) > MAX_GROUPS:
                raise ValueError("manifest declarations exceed group bound")
        return RepositoryDeclarationProviderResult(
            groups=tuple(groups),
            provenance={
                "provider": self.name,
                "semantics": "hashmarks.python-uv-manifest-syntax.v1",
                "parser": "tomllib",
                "file_scope": sorted(self.paths),
                "missing_selected_paths": missing,
                "coverage": "selected-supported-declarations-only",
                "semantic_coverage": "incomplete",
                "native_workspace_membership": "not-established",
                "dependency_resolution": "not-performed",
                "negative_evidence_admissible": False,
            },
        )
