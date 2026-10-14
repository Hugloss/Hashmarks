"""Explicit public observer operations for answer-blind evaluation cases."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hashmarks.codemap import CodeMap
from hashmarks.codemap.change_impact import ChangeImpactOptions
from hashmarks.codemap.repository_intelligence_query import (
    RepositoryIntelligenceQueryOptions,
)
from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)
from hashmarks.codemap.static_python_interface_declarations import (
    StaticPythonInterfaceDeclarations,
)


def _declarations(codemap: CodeMap, inputs: dict[str, Any]) -> dict[str, object]:
    """Only the two repository-owned source providers, never dynamic imports."""
    settings = dict(inputs)
    provider_name = settings.pop("provider", None)
    settings["paths"] = tuple(settings.get("paths", ()))
    providers = {
        "backend": StaticPythonBackendDeclarations,
        "interface": StaticPythonInterfaceDeclarations,
    }
    if provider_name not in providers:
        raise ValueError("evaluation declaration provider must be backend or interface")
    provider = providers[provider_name](**settings)
    return codemap.discover_repository_declarations([provider])


def _change_impact(codemap: CodeMap, inputs: dict[str, Any]) -> dict[str, object]:
    settings = dict(inputs)
    options = ChangeImpactOptions(**settings.pop("options", {}))
    return codemap.task_change_impact(**settings, options=options)


def _intelligence_query(codemap: CodeMap, inputs: dict[str, Any]) -> dict[str, object]:
    settings = dict(inputs)
    surface, task = settings.pop("surface_name"), settings.pop("task")
    paths = settings.pop("changed_paths", None) or ()
    return codemap.repository_intelligence_query(
        surface, task, paths, options=RepositoryIntelligenceQueryOptions(**settings)
    )


def observe_case(codemap: CodeMap, case: Mapping[str, object]) -> dict[str, object]:
    """Dispatch a closed set of read-only product calls, with no grader input."""
    operation = str(case.get("operation") or "")
    raw_inputs = case.get("inputs")
    inputs: dict[str, Any] = dict(raw_inputs) if isinstance(raw_inputs, dict) else {}
    operations = {
        "task_evidence": lambda: codemap.task_evidence(**inputs),
        "structural_locality": lambda: codemap.structural_locality(**inputs),
        "source_observation": lambda: codemap.source_observation(**inputs),
        "correlate_evidence": lambda: codemap.correlate_evidence(**inputs),
        "repository_declarations": lambda: _declarations(codemap, inputs),
        "change_impact": lambda: _change_impact(codemap, inputs),
        "post_change": lambda: codemap.task_post_change_delta(**inputs),
        "dependency_codemap": lambda: codemap.dependency_codemap(**inputs),
        "repository_intelligence_query": lambda: _intelligence_query(codemap, inputs),
    }
    if operation not in operations:
        raise ValueError(f"unsupported repository evaluation operation: {operation}")
    if not isinstance(case.get("inputs"), dict):
        raise ValueError("observer evaluation case requires an inputs object")
    return operations[operation]()
