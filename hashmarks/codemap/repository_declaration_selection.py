"""Translate explicit public source selections into existing declaration producers.

No discovery registry or source analysis lives here. Providers retain their
syntax, source bounds and authority; adapters share this request translation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NotRequired, TypedDict

from .make_shell_declarations import MakeShellDeclarations
from .python_uv_manifest_declarations import PythonUvManifestDeclarations
from .repository_declaration_provider import RepositoryDeclarationProvider
from .static_python_backend_declarations import StaticPythonBackendDeclarations
from .static_python_interface_declarations import StaticPythonInterfaceDeclarations


class _InterfaceArguments(TypedDict):
    paths: tuple[str, ...]
    route_objects: NotRequired[tuple[str, ...]]
    tool_objects: NotRequired[tuple[str, ...]]
    include_literal_shape_syntax: NotRequired[bool]
    include_input_contract_syntax: NotRequired[bool]


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be an array of strings")
    return tuple(value)


def _boolean(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be boolean")
    return value


def _interface_provider(selection: object) -> StaticPythonInterfaceDeclarations:
    if not isinstance(selection, Mapping):
        raise ValueError("python_interface must be an object")
    allowed = {
        "paths",
        "route_objects",
        "tool_objects",
        "include_literal_shape_syntax",
        "include_input_contract_syntax",
    }
    if "paths" not in selection or set(selection) - allowed:
        raise ValueError(
            "python_interface requires paths and only supported source options"
        )
    arguments: _InterfaceArguments = {"paths": _strings(selection["paths"], "paths")}
    if "route_objects" in selection:
        arguments["route_objects"] = _strings(
            selection["route_objects"], "route_objects"
        )
    if "tool_objects" in selection:
        arguments["tool_objects"] = _strings(selection["tool_objects"], "tool_objects")
    if "include_literal_shape_syntax" in selection:
        arguments["include_literal_shape_syntax"] = _boolean(
            selection["include_literal_shape_syntax"], "include_literal_shape_syntax"
        )
    if "include_input_contract_syntax" in selection:
        arguments["include_input_contract_syntax"] = _boolean(
            selection["include_input_contract_syntax"], "include_input_contract_syntax"
        )
    return StaticPythonInterfaceDeclarations(**arguments)


def _make_shell_provider(selection: object) -> MakeShellDeclarations:
    if not isinstance(selection, Mapping) or set(selection) - {
        "make_paths",
        "shell_paths",
    }:
        raise ValueError(
            "make_shell must be an object of selected make_paths/shell_paths"
        )
    return MakeShellDeclarations(
        make_paths=_strings(selection.get("make_paths", []), "make_paths"),
        shell_paths=_strings(selection.get("shell_paths", []), "shell_paths"),
    )


def _tool_providers(
    make_shell: object, manifests: object
) -> list[RepositoryDeclarationProvider]:
    providers: list[RepositoryDeclarationProvider] = []
    if make_shell is not None:
        providers.append(_make_shell_provider(make_shell))
    if manifests is not None:
        providers.append(
            PythonUvManifestDeclarations(
                paths=_strings(manifests, "python_uv_manifest_paths")
            )
        )
    return providers


def source_declaration_providers(
    mode: str,
    selection: Mapping[str, object] | None,
) -> list[RepositoryDeclarationProvider] | None:
    """Construct only the explicitly selected built-in source producers."""
    if selection is None:
        selection = {}
    if not isinstance(selection, Mapping) or set(selection) - {
        "python_backend_paths",
        "include_class_fields",
        "python_interface",
        "make_shell",
        "python_uv_manifest_paths",
    }:
        raise ValueError(
            "source_selection must be an object of supported source options"
        )
    paths, interface = (
        selection.get("python_backend_paths"),
        selection.get("python_interface"),
    )
    include_class_fields = _boolean(
        selection.get("include_class_fields", False), "include_class_fields"
    )
    make_shell = selection.get("make_shell")
    manifests = selection.get("python_uv_manifest_paths")
    if mode != "discovery":
        if include_class_fields or any(
            item is not None for item in (paths, interface, make_shell, manifests)
        ):
            raise ValueError("source selection requires result_mode=discovery")
        return None
    if include_class_fields and paths is None:
        raise ValueError("include_class_fields requires selected paths")
    providers: list[RepositoryDeclarationProvider] = []
    if paths is not None:
        providers.append(
            StaticPythonBackendDeclarations(
                paths=_strings(paths, "python_backend_paths"),
                include_class_fields=include_class_fields,
            )
        )
    if interface is not None:
        providers.append(_interface_provider(interface))
    providers.extend(_tool_providers(make_shell, manifests))
    return providers
