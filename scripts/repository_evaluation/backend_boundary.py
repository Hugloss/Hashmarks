"""Caller-nominated syntax observations in the existing backend revision ring.

These development measurements qualify source disclosure, not answer-blind
retrieval, runtime concurrency, or the sufficiency of a verification surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hashmarks.codemap import ChangeImpactOptions, CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS

from .backend_corpus import confined_file
from .backend_gates import combine_required, fact_state, presentation_conformance
from .backend_transport import capture_cli, capture_mcp
from .common import write_json
from .fact_grading import grade_facts


def _bound(workspace: Path, packet: dict[str, Any], paths: list[str]) -> bool:
    observations = packet.get("changed_line_evidence", {}).get("observations", [])
    return (
        bool(observations)
        and set(paths) == {row["path"] for row in observations}
        and all(
            row["member_revision"]
            == hash_file(confined_file(workspace, row["path"]), domain=FILE_DOMAIN).hash
            for row in observations
        )
    )


def _grade(
    workspace: Path, packet: dict[str, Any], rule: dict[str, Any], paths: list[str]
) -> dict[str, Any]:
    facts = grade_facts("function-boundary", {"packet": packet}, rule)
    return {
        "facts": fact_state(facts["classification"]),
        "authority": facts["authority_violations"] == 0,
        "revision": _bound(workspace, packet, paths),
        "checks": facts["checks"],
    }


def observe_boundary(
    workspace: Path,
    state: Path,
    inputs: dict[str, Any],
    rule: dict[str, Any],
    output: Path,
    transports: tuple[str, ...],
) -> dict[str, Any]:
    """Use public APIs/transports with inputs separate from the exact oracle."""
    paths = inputs["changed_paths"]
    with CodeMap(workspace, state_dir=state) as codemap:
        packet = codemap.task_change_impact(
            inputs["task"],
            paths,
            options=ChangeImpactOptions(
                max_depth=inputs["max_depth"],
                changed_line_spans=inputs["changed_line_spans"],
            ),
        )
    write_json(output / "api.json", packet)
    api = _grade(workspace, packet, rule, paths)
    results: dict[str, Any] = {"api": api}
    case = {"operation": "change_impact", "inputs": inputs}
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
                or presentation_conformance(native, response["presentation"])["valid"]
                is True
            )
            grades.append({"format": row["format"], **graded})
        complete = sorted(row["format"] for row in grades) == sorted(FORMATS)
        results[transport] = {
            "complete": complete if captures else None,
            "grades": grades,
        }
    results["gates"] = {
        name: combine_required(
            [
                api[name],
                *(
                    row[name]
                    for transport in ("cli", "mcp")
                    for row in results[transport]["grades"]
                ),
            ]
        )
        for name in ("facts", "authority", "revision")
    }
    for transport in ("cli", "mcp"):
        result = results[transport]
        results["gates"][transport] = combine_required(
            [
                True if result["complete"] is True else None,
                *(
                    combine_required([row["facts"], row["parity"]])
                    for row in result["grades"]
                ),
            ]
        )
    return results
