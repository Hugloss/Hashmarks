"""Revalidate retained task observations without launching an observer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hashmarks.digest import FILE_DOMAIN, hash_file

from .backend_boundary import _grade as _boundary_grade
from .backend_corpus import confined_file, confined_path, workflow_changed_paths
from .backend_declarations import _grade as _declaration_grade
from .backend_gates import combine_required, presentation_conformance
from .backend_grading import _gates, component_summary, validate_transport_capture
from .backend_witnesses import (
    delta_fact_witnesses,
    freshness_fact_witnesses,
    stage_fact_witnesses,
)
from .backend_workflows import _invalidated_member, _revision_bound, _transport_grade
from .fact_grading import _json_equal, grade_facts


def _read(root: Path, relative: str) -> object:
    result = json.loads(confined_file(root, relative).read_bytes())
    if Path(relative).name in {"cli.json", "mcp.json"}:
        for capture in result:
            validate_transport_capture(capture)
    return result


def _stage(
    root: Path, source: Path, workflow: dict[str, object], rule: dict[str, object]
) -> dict[str, object]:
    packet = _read(root, "api.json")
    initial = _read(root, "initial/api.json")
    profiles = {}
    for name, native, prefix in (
        ("default", packet, ""),
        ("initial", initial, "initial/"),
    ):
        profiles[name] = {
            "packet": native,
            "revision_bound": _revision_bound(source, native),
            **{
                transport: _transport_grade(
                    _read(root, prefix + transport + ".json"),
                    rule,
                    source,
                    initial=name == "initial",
                    source_identity=packet["evidence_packet_identity"],
                )
                for transport in ("cli", "mcp")
            },
        }
    return {
        **profiles["default"],
        "initial": profiles["initial"],
        "grade": grade_facts(workflow["id"], {"packet": packet}, rule),
    }


def _freshness(
    root: Path, workflow: dict[str, object], sources: dict[str, Path]
) -> dict[str, object]:
    retained = _read(root, "stale.json")
    paths = workflow_changed_paths(workflow)
    rows = retained["observations"]
    if len(rows) != len(paths):
        raise ValueError("backend stale observations differ from changed membership")
    values = []
    for path, row in zip(paths, rows, strict=True):
        prior = confined_path(sources[workflow["before"]], path)
        present = confined_path(sources[workflow["after"]], path).is_file()
        revision = (
            hash_file(prior, domain=FILE_DOMAIN).hash if prior.is_file() else None
        )
        # Membership must bind each result to its own selected source path.
        if row.get("member", {}).get("path") != path:
            raise ValueError("backend stale observation has wrong source membership")
        values.append(_invalidated_member(row, revision, present))
    return {"passed": combine_required(values), "observations": rows}


def regrade_task_workflow(
    root: Path,
    workflow: dict[str, object],
    rule: dict[str, object],
    sources: dict[str, Path],
) -> dict[str, object]:
    """Recompute task and composed component gates from retained observations."""
    before = _stage(
        root / "before",
        sources[workflow["before"]],
        workflow,
        {**rule, **rule.get("before", {})},
    )
    after = _stage(
        root / "after",
        sources[workflow["after"]],
        workflow,
        {**rule, **rule.get("after", {})},
    )
    delta = grade_facts(
        workflow["id"],
        {"packet": _read(root, "delta.json")},
        {"checks": rule["delta_checks"]},
    )
    gates = _gates(before, after, _freshness(root, workflow, sources), rule, delta)
    components: dict[str, dict[str, object]] = {
        family: {stage: None for stage in ("before", "after")}
        for family in ("boundary", "declarations")
    }
    for stage in ("before", "after"):
        for family, input_key, oracle_key in (
            ("boundary", "boundary_observations", "function_boundary_oracles"),
            ("declarations", "declaration_observations", "declaration_oracles"),
        ):
            if input_key not in workflow:
                continue
            component = _component(
                root / stage / family,
                sources[workflow[stage]],
                workflow[input_key][stage],
                rule[oracle_key][stage],
                family,
            )
            components[family][stage] = component
            for name, value in component["gates"].items():
                gates[name] = combine_required([gates[name], value])
            gates["presentation"] = combine_required([gates["cli"], gates["mcp"]])
    return {
        "gates": gates,
        "before": before["grade"],
        "after": after["grade"],
        "delta": delta,
        "boundary_observations": components["boundary"],
        "declaration_observations": components["declarations"],
        "transport_grades": {
            stage: {key: observed[key] for key in ("cli", "mcp")}
            for stage, observed in (("before", before), ("after", after))
        },
        "initial_transport_grades": {
            stage: {key: observed["initial"][key] for key in ("cli", "mcp")}
            for stage, observed in (("before", before), ("after", after))
        },
    }


def verify_task_summary(
    root: Path,
    workflow: dict[str, object],
    rule: dict[str, object],
    sources: dict[str, Path],
    outcome: dict[str, object],
) -> None:
    expected = regrade_task_workflow(root, workflow, rule, sources)
    witnesses = [
        witness
        for stage in ("before", "after")
        for witness in stage_fact_witnesses(
            sources[workflow[stage]],
            root / stage,
            workflow,
            {**rule, **rule.get(stage, {}), "_stage": stage},
        )
    ]
    witnesses.extend(delta_fact_witnesses(sources, root, workflow, rule))
    witnesses.extend(freshness_fact_witnesses(sources, root, workflow, rule))
    if not _json_equal(outcome.get("gate_witnesses"), witnesses):
        raise ValueError("backend workflow witnesses differ from artifact proof")
    if outcome.get("gates", {}).keys() != expected["gates"].keys():
        raise ValueError("backend workflow has unexpected or missing gate claims")
    for name, value in expected.items():
        if not _json_equal(outcome.get(name), value):
            raise ValueError(
                f"backend workflow {name} summary differs from artifact proof"
            )


def _component(
    root: Path,
    source: Path,
    inputs: dict[str, object],
    rule: dict[str, object],
    family: str,
) -> dict[str, object]:
    grader = _boundary_grade if family == "boundary" else _declaration_grade
    paths = (
        inputs["changed_paths"]
        if family == "boundary"
        else inputs["python_backend_paths"]
    )
    api = grader(source, _read(root, "api.json"), rule, paths)
    observations = {}
    for transport in ("cli", "mcp"):
        captures = _read(root, transport + ".json")
        rows = []
        for capture in captures:
            response = capture["response"]
            packet = response.get("result", response)
            row = grader(source, packet, rule, paths)
            row["parity"] = (
                capture["format"] == "none"
                or presentation_conformance(packet, response["presentation"])["valid"]
                is True
            )
            rows.append(row)
        observations[transport] = [
            {"format": capture["format"], **row}
            for capture, row in zip(captures, rows, strict=True)
        ]
    return component_summary(api, observations)
