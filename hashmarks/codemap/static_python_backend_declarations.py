"""Explicit selected-file backend model-field and environment-read syntax.

A RepositoryDeclarationProvider: no ambient scanner, framework runtime,
config precedence authority, schema inference, or cross-artifact matching.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from hashmarks.paths import normalize_relative_path

from .handler_input_syntax import _annotation, _default
from .repository_declaration_provider import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderResult,
)

MAX_BACKEND_SOURCE_BYTES = 262_144
MAX_BACKEND_PATHS = 16
MAX_BACKEND_GROUPS = 64
MAX_MODEL_FIELDS = 24
MAX_ENV_KEY_CHARS = 128

_MODEL_BASE_NAMES = frozenset({"BaseModel", "BaseSettings"})


def _model_base(node: ast.expr) -> dict[str, object] | None:
    if isinstance(node, ast.Name) and node.id in _MODEL_BASE_NAMES:
        return {"state": "direct-name-syntax", "name": node.id}
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.attr in _MODEL_BASE_NAMES
    ):
        return {
            "state": "direct-member-syntax",
            "receiver": node.value.id,
            "name": node.attr,
        }
    return None


def _class_field(node: ast.AnnAssign) -> dict[str, object] | None:
    if not isinstance(node.target, ast.Name):
        return None
    if len(node.target.id) > 128:
        raise ValueError("model field identifier exceeds direct syntax bound")
    return {
        "name": node.target.id,
        "line": node.lineno,
        "end_line": node.end_lineno or node.lineno,
        "annotation": _annotation(node.annotation),
        "default": _default(node.value),
        "runtime_requiredness": "unknown",
        "runtime_validation": "not-established",
    }


def _group(
    group_id: str,
    concept: dict[str, object],
    scope: dict[str, object],
    value: dict[str, object],
    evidence: list[dict[str, object]],
    *,
    name: str,
) -> dict[str, object]:
    return {
        "group_id": group_id,
        "concept": concept,
        "scope": scope,
        "correspondence": {
            "state": "unresolved",
            "basis": {
                "producer": name,
                "reason": "source-syntax-is-not-runtime-contract",
            },
        },
        "declarations": [
            {
                "declaration_id": "direct-source-syntax",
                "semantic_role": {"kind": "syntax-only-observation"},
                "value_state": "resolved",
                "value": {
                    **value,
                    "authority": "direct-static-syntax-only",
                    "coverage": "incomplete",
                    "runtime_binding": "not-established",
                    "cross_artifact_correspondence": "unresolved",
                    "negative_evidence_admissible": False,
                },
                "producer": {
                    "provider": name,
                    "parser": "python-ast",
                    "authority": "direct-static-syntax-only",
                },
                "evidence": evidence,
            }
        ],
        "coverage": {
            "state": "incomplete",
            "truncation": "complete",
            "expected_declaration_ids": [],
            "scope": scope,
            "provenance": {
                "producer": name,
                "reason": "caller-selected-files-and-recognized-syntax-only",
            },
        },
    }


def _model_group(
    path: str, node: ast.ClassDef, *, name: str
) -> dict[str, object] | None:
    bases = [_model_base(base) for base in node.bases]
    nominated = [base for base in bases if base is not None]
    if not nominated:
        return None
    fields: list[dict[str, object]] = []
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign):
            field = _class_field(statement)
            if field is not None:
                fields.append(field)
                if len(fields) > MAX_MODEL_FIELDS:
                    raise ValueError("backend model field syntax exceeds 24 fields")
    scope = {
        "path": path,
        "class_name_syntax": node.name,
        "class_line": node.lineno,
    }
    return _group(
        f"{path}:model:{node.lineno}:{node.name}",
        {"kind": "python-model-class-syntax", "syntax": "python-ast"},
        scope,
        {
            "class_name_syntax": node.name,
            "model_base_syntax": nominated,
            "field_count": len(fields),
            "fields": fields,
            "model_identity": "not-established",
            "field_requiredness": "unknown",
            "schema_compatibility": "not-established",
        },
        [
            {"path": path, "start_line": node.lineno, "end_line": node.lineno},
            *[
                {"path": path, "start_line": f["line"], "end_line": f["end_line"]}
                for f in fields
            ],
        ],
        name=name,
    )


def _env_callee(node: ast.expr) -> str | None:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
        and node.attr == "getenv"
    ):
        return "os.getenv"
    if isinstance(node, ast.Attribute) and node.attr == "get":
        receiver = node.value
        if (
            isinstance(receiver, ast.Attribute)
            and isinstance(receiver.value, ast.Name)
            and receiver.value.id == "os"
            and receiver.attr == "environ"
        ):
            return "os.environ.get"
    return None


def _environ_subscript(node: ast.Subscript) -> bool:
    target = node.value
    return (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "os"
        and target.attr == "environ"
    )


def _env_key(node: ast.expr | None) -> dict[str, object]:
    if node is None:
        return {"state": "not-supplied"}
    if not isinstance(node, ast.Constant) or type(node.value) is not str:
        return {"state": "dynamic-or-unsupported"}
    if len(node.value) > MAX_ENV_KEY_CHARS:
        return {"state": "over-bound"}
    return {"state": "literal-key-syntax", "value": node.value}


def _env_site(node: ast.AST) -> dict[str, object] | None:
    if isinstance(node, ast.Call):
        callee = _env_callee(node.func)
        if callee is None:
            return None
        key_kw = next((kw.value for kw in node.keywords if kw.arg == "key"), None)
        default_kw = next((kw.value for kw in node.keywords if kw.arg == "default"), None)
        key = node.args[0] if node.args else key_kw
        default = node.args[1] if len(node.args) > 1 else default_kw
        return {
            "callee_syntax": callee,
            "key": _env_key(key),
            "default": _default(default),
            "positional_count": len(node.args),
            "has_argument_expansion": any(
                isinstance(arg, ast.Starred) for arg in node.args
            )
            or any(kw.arg is None for kw in node.keywords),
            "runtime_env_read": "not-established",
        }
    if isinstance(node, ast.Subscript) and _environ_subscript(node):
        return {
            "callee_syntax": "os.environ[...]",
            "key": _env_key(node.slice),
            "default": {"state": "not-supplied"},
            "runtime_env_read": "not-established",
        }
    return None


def _direct_assignment_targets(tree: ast.Module) -> dict[int, list[str]]:
    """Capture only a direct RHS name assignment, not runtime dataflow."""
    targets: dict[int, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if names:
                targets[id(node.value)] = names[:8]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                targets[id(node.value)] = [node.target.id]
    return targets


def _config_groups(
    path: str, tree: ast.Module, *, name: str
) -> list[dict[str, object]]:
    sites: list[tuple[int, int, ast.AST, dict[str, object]]] = []
    direct_targets = _direct_assignment_targets(tree)
    for node in ast.walk(tree):
        observation = _env_site(node)
        if observation is not None:
            observation["direct_assignment_names"] = direct_targets.get(id(node), [])
            observation["runtime_assignment_binding"] = "not-established"
            sites.append((node.lineno, node.col_offset, node, observation))
            if len(sites) > MAX_BACKEND_GROUPS:
                raise ValueError("backend environment syntax exceeds group bound")
    rows: list[dict[str, object]] = []
    for line, column, node, value in sorted(sites, key=lambda x: x[:2]):
        scope = {"path": path, "line": line, "column": column}
        rows.append(
            _group(
                f"{path}:env:{line}:{column}",
                {"kind": "python-env-access-syntax", "syntax": "python-ast"},
                scope,
                value,
                [
                    {
                        "path": path,
                        "start_line": line,
                        "end_line": node.end_lineno or line,
                    }
                ],
                name=name,
            )
        )
    return rows


@dataclass(frozen=True, slots=True)
class StaticPythonBackendDeclarations:
    """Explicit Python source observer for model classes and env access sites."""

    paths: tuple[str, ...]
    name: str = "static-python-backend"
    include_model_fields: bool = True
    include_environment_reads: bool = True

    def __post_init__(self) -> None:
        if not 1 <= len(self.paths) <= MAX_BACKEND_PATHS:
            raise ValueError("backend provider requires 1..16 exact paths")
        if any(
            not isinstance(path, str)
            or not path.endswith(".py")
            or normalize_relative_path(path, allow_root=False) != path
            for path in self.paths
        ):
            raise ValueError("backend provider requires canonical Python paths")
        if len(set(self.paths)) != len(self.paths):
            raise ValueError("backend provider paths must be unique")
        if (
            type(self.include_model_fields) is not bool
            or type(self.include_environment_reads) is not bool
        ):
            raise ValueError("backend provider switches must be boolean")
        if not self.include_model_fields and not self.include_environment_reads:
            raise ValueError("backend provider requires an enabled observation")

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return any(context.exists(path) for path in self.paths)

    def _source_groups(self, path: str, source: str) -> list[dict[str, object]]:
        if len(source.encode("utf-8")) > MAX_BACKEND_SOURCE_BYTES:
            raise ValueError("backend source exceeds bounded syntax input")
        tree = ast.parse(source, filename=path)
        groups: list[dict[str, object]] = []
        if self.include_model_fields:
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    group = _model_group(path, node, name=self.name)
                    if group is not None:
                        groups.append(group)
                        if len(groups) > MAX_BACKEND_GROUPS:
                            raise ValueError("backend declarations exceed group bound")
        if self.include_environment_reads:
            groups.extend(_config_groups(path, tree, name=self.name))
        return groups

    def discover(
        self, context: RepositoryDeclarationProviderContext
    ) -> RepositoryDeclarationProviderResult:
        groups: list[dict[str, object]] = []
        missing: list[str] = []
        for path in sorted(self.paths):
            if not context.exists(path):
                missing.append(path)
                continue
            groups.extend(self._source_groups(path, context.read_text(path)))
            if len(groups) > MAX_BACKEND_GROUPS:
                raise ValueError("backend declarations exceed group bound")
        return RepositoryDeclarationProviderResult(
            groups=tuple(groups),
            provenance={
                "provider": self.name,
                "parser": "python-ast",
                "file_scope": sorted(self.paths),
                "missing_selected_paths": missing,
                "model_fields": self.include_model_fields,
                "environment_reads": self.include_environment_reads,
                "semantics": "direct-selected-source-syntax-not-runtime-binding",
            },
        )
