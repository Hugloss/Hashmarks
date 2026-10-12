"""Selected declaration source facts in the existing backend qualification ring.

These observations qualify caller-nominated source disclosure, not answer-blind
retrieval, runtime model validation, or verification sufficiency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from hashmarks.codemap import CodeMap
from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation

from .backend_corpus import confined_file
from .backend_transport import capture_cli, capture_mcp
from .common import write_json
from .fact_grading import grade_facts


def _source_bound(workspace: Path, packet: dict[str, Any], paths: list[str]) -> bool:
    inputs = [
        row
        for provider in packet.get("providers", [])
        for row in provider.get("inputs", [])
    ]
    expected = {
        path: hash_file(confined_file(workspace, path), domain=FILE_DOMAIN).hash
        for path in paths
    }
    bindings = (
        packet.get("declarations", {})
        .get("repository_evidence", {})
        .get("bindings", [])
    )
    return (
        bool(inputs)
        and bool(bindings)
        and {row["path"] for row in inputs} == set(paths)
        and all(
            row["state"] == "known-present"
            and row["member_revision"] == expected[row["path"]]
            for row in inputs
        )
        and all(
            bool(binding["evidence"])
            and all(
                evidence["path"] in expected
                and evidence["state"] == "known-present"
                and evidence["member_revision"] == expected[evidence["path"]]
                for evidence in binding["evidence"]
            )
            for binding in bindings
        )
    )


def _grade(
    workspace: Path, packet: dict[str, Any], rule: dict[str, Any], paths: list[str]
) -> dict[str, Any]:
    facts = grade_facts("declaration-source", {"packet": packet}, rule)
    return {
        "facts": facts["classification"] == "PASS",
        "authority": facts["authority_violations"] == 0,
        "revision": _source_bound(workspace, packet, paths),
        "checks": facts["checks"],
    }


def observe_declarations(
    workspace: Path,
    state: Path,
    inputs: dict[str, Any],
    rule: dict[str, Any],
    output: Path,
    transports: tuple[str, ...],
) -> dict[str, Any]:
    """Compose existing source/API/transport owners with independent fact checks."""
    paths = inputs["python_backend_paths"]
    with CodeMap(workspace, state_dir=state) as codemap:
        packet = cast(
            "dict[str, Any]",
            codemap.repository_declarations_operation(
                inputs["groups"],
                result_mode=inputs["result_mode"],
                providers=(
                    StaticPythonBackendDeclarations(
                        paths=tuple(paths),
                        include_class_fields=inputs["include_class_fields"],
                    ),
                ),
            ),
        )
    write_json(output / "api.json", packet)
    api = _grade(workspace, packet, rule, paths)
    results: dict[str, Any] = {"api": api}
    case = {"operation": "repository_declarations", "inputs": inputs}
    for transport, capture in (("cli", capture_cli), ("mcp", capture_mcp)):
        captures = capture(workspace, state, case) if transport in transports else []
        write_json(output / f"{transport}.json", captures)
        grades = []
        for row in captures:
            response = row["response"]
            native = response.get("result", response)
            graded = _grade(workspace, native, rule, paths)
            graded["parity"] = (
                row["format"] == "none"
                or validate_evidence_presentation(native, response["presentation"])[
                    "valid"
                ]
                is True
            )
            grades.append({"format": row["format"], **graded})
        complete = sorted(row["format"] for row in grades) == sorted(FORMATS)
        results[transport] = {
            "complete": complete if captures else None,
            "grades": grades,
        }
    results["gates"] = {
        name: api[name]
        and all(
            row[name]
            for transport in ("cli", "mcp")
            for row in results[transport]["grades"]
        )
        for name in ("facts", "authority", "revision")
    }
    for transport in ("cli", "mcp"):
        result = results[transport]
        results["gates"][transport] = (
            None
            if result["complete"] is None
            else result["complete"]
            and all(row["facts"] and row["parity"] for row in result["grades"])
        )
    return results
