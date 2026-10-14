"""Bind pure grading to retained API bytes and admitted source snapshots."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from hashmarks.digest import FILE_DOMAIN, hash_file

from .backend_corpus import (
    confined_file,
    confined_path,
    task_source_labels,
    workflow_changed_paths,
)
from .backend_grading import (
    FactObservation,
    grade_fact_observation,
    validate_transport_capture,
)


def api_fact_witnesses(
    source: Path,
    output: Path,
    workflow: dict[str, Any],
    rule: dict[str, Any],
    packet: dict[str, Any],
) -> list[dict[str, Any]]:
    stage = rule["_stage"]
    paths = sorted({label["path"] for label in task_source_labels(rule, stage)})
    bindings = tuple(
        {
            "repository": workflow["repository"],
            "path": path,
            "revision": hash_file(confined_file(source, path), domain=FILE_DOMAIN).hash,
        }
        for path in paths
    )
    scope = f"/cases/{workflow['id']}"
    if "checks" in rule.get(stage, {}):
        scope += "/" + stage
    observation = FactObservation(
        "facts",
        workflow["id"],
        stage,
        "default",
        "api",
        "none",
        scope + "/checks",
        (stage + "/api.json", confined_file(output, "api.json").read_bytes()),
        bindings,
    )
    return grade_fact_observation(packet, rule, observation)["witnesses"]


def task_fact_witnesses(
    source: Path, output: Path, workflow: dict[str, Any], rule: dict[str, Any]
) -> list[dict[str, Any]]:
    """Retain separate native and display witnesses for every captured context."""
    stage = rule["_stage"]
    paths = sorted({label["path"] for label in task_source_labels(rule, stage)})
    bindings = tuple(
        {
            "repository": workflow["repository"],
            "path": path,
            "revision": hash_file(confined_file(source, path), domain=FILE_DOMAIN).hash,
        }
        for path in paths
    )
    witnesses = []
    for profile, prefix, key in (
        ("default", "", "checks"),
        ("initial", "initial/", "initial_checks"),
    ):
        scope = f"/cases/{workflow['id']}"
        if key in rule.get(stage, {}):
            scope += "/" + stage
        for surface in ("api", "cli", "mcp"):
            relative = prefix + surface + ".json"
            contents = confined_file(output, relative).read_bytes()
            decoded = json.loads(contents)
            rows = (
                [("none", decoded)]
                if surface == "api"
                else [(capture["format"], capture) for capture in decoded]
            )
            for format, row in rows:
                if surface != "api":
                    validate_transport_capture(row)
                    response = row["response"]
                    packet = response.get("result", response)
                else:
                    response = packet = row
                context = FactObservation(
                    "facts" if profile == "default" else "initial_evidence",
                    workflow["id"],
                    stage,
                    profile,
                    surface,
                    format,
                    scope + "/" + key,
                    (stage + "/" + relative, contents),
                    bindings,
                )
                witnesses.extend(_task_check_witnesses(packet, rule, context))
                display_checks = (
                    rule.get("display_checks", {}).get(profile, {}).get(format)
                )
                if surface != "api" and format != "none" and display_checks:
                    display_scope = f"/cases/{workflow['id']}"
                    if "display_checks" in rule.get(stage, {}):
                        display_scope += "/" + stage
                    observation = FactObservation(
                        "presentation",
                        workflow["id"],
                        stage,
                        profile,
                        surface,
                        format,
                        display_scope + f"/display_checks/{profile}/{format}",
                        (stage + "/" + relative, contents),
                        bindings,
                    )
                    witnesses.extend(
                        grade_fact_observation(
                            response["presentation"],
                            {"checks": display_checks},
                            observation,
                        )["witnesses"]
                    )
    return witnesses


def _task_check_witnesses(
    packet: dict[str, Any], rule: dict[str, Any], context: FactObservation
) -> list[dict[str, Any]]:
    witnesses = []
    key = "initial_checks" if context.profile == "initial" else "checks"
    for gate, check_key in ((context.gate, key), ("authority", "authority_checks")):
        if check_key not in rule:
            continue
        scope = f"/cases/{context.unit_id}"
        if check_key in rule.get(context.stage, {}):
            scope += "/" + context.stage
        observation = replace(
            context, gate=gate, oracle_pointer=scope + "/" + check_key
        )
        witnesses.extend(
            grade_fact_observation(packet, {"checks": rule[check_key]}, observation)[
                "witnesses"
            ]
        )
    return witnesses


def stage_fact_witnesses(
    source: Path, output: Path, workflow: dict[str, Any], rule: dict[str, Any]
) -> list[dict[str, Any]]:
    """One witness owner for task, selected boundary and declaration observations."""
    witnesses = task_fact_witnesses(source, output, workflow, rule)
    stage = rule["_stage"]
    for family, input_key, oracle_key, path_key in (
        (
            "boundary",
            "boundary_observations",
            "function_boundary_oracles",
            "changed_paths",
        ),
        (
            "declarations",
            "declaration_observations",
            "declaration_oracles",
            "python_backend_paths",
        ),
    ):
        inputs = workflow.get(input_key, {}).get(stage)
        oracle = rule.get(oracle_key, {}).get(stage)
        if inputs is None or oracle is None:
            continue
        bindings = tuple(
            {
                "repository": workflow["repository"],
                "path": path,
                "revision": hash_file(
                    confined_file(source, path), domain=FILE_DOMAIN
                ).hash,
            }
            for path in sorted(set(inputs[path_key]))
        )
        scope = f"/cases/{workflow['id']}/{oracle_key}/{stage}"
        context = FactObservation(
            family + "_facts",
            workflow["id"],
            stage,
            None,
            "api",
            "none",
            scope + "/checks",
            None,
            bindings,
        )
        witnesses.extend(
            captured_fact_witnesses(
                output,
                family,
                oracle,
                context,
            )
        )
    return witnesses


def captured_fact_witnesses(
    output: Path,
    family: str,
    rule: dict[str, Any],
    context: FactObservation,
) -> list[dict[str, Any]]:
    witnesses = []
    for surface in ("api", "cli", "mcp"):
        relative = (family + "/" if family else "") + surface + ".json"
        contents = confined_file(output, relative).read_bytes()
        decoded = json.loads(contents)
        captures = (
            [("none", decoded)]
            if surface == "api"
            else [(row["format"], row) for row in decoded]
        )
        for format, captured in captures:
            response = captured
            if surface != "api":
                validate_transport_capture(captured)
                response = captured["response"]
            packet = response.get("result", response)
            captured_context = replace(
                context,
                surface=surface,
                format=format,
                artifact=(context.stage + "/" + relative, contents),
            )
            witnesses.extend(
                grade_fact_observation(packet, rule, captured_context)["witnesses"]
            )
            display = rule.get("display_checks", {}).get(format)
            if surface != "api" and format != "none" and display:
                display_context = replace(
                    captured_context,
                    gate=context.gate.removesuffix("_facts") + "_presentation",
                    oracle_pointer=context.oracle_pointer.removesuffix("/checks")
                    + "/display_checks/"
                    + format,
                )
                witnesses.extend(
                    grade_fact_observation(
                        response["presentation"], {"checks": display}, display_context
                    )["witnesses"]
                )
    return witnesses


def delta_fact_witnesses(
    sources: dict[str, Path],
    output: Path,
    workflow: dict[str, Any],
    rule: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bind comparison facts to independently admitted before/after source bytes."""
    bindings = _comparison_source_bindings(sources, workflow, rule)
    contents = confined_file(output, "delta.json").read_bytes()
    context = FactObservation(
        "delta",
        workflow["id"],
        "delta",
        None,
        "api",
        "none",
        f"/cases/{workflow['id']}/delta_checks",
        ("delta.json", contents),
        bindings,
    )
    return grade_fact_observation(
        json.loads(contents), {"checks": rule["delta_checks"]}, context
    )["witnesses"]


def freshness_fact_witnesses(
    sources: dict[str, Path],
    output: Path,
    workflow: dict[str, Any],
    rule: dict[str, Any],
) -> list[dict[str, Any]]:
    """Regrade explicit stale checks; prior and present bindings stay separate."""
    if "freshness_checks" not in rule:
        return []
    contents = confined_file(output, "stale.json").read_bytes()
    context = FactObservation(
        "freshness",
        workflow["id"],
        "stale",
        None,
        "api",
        "none",
        f"/cases/{workflow['id']}/freshness_checks",
        ("stale.json", contents),
        _transition_source_bindings(sources, workflow),
    )
    return grade_fact_observation(
        json.loads(contents), {"checks": rule["freshness_checks"]}, context
    )["witnesses"]


def _transition_source_bindings(
    sources: dict[str, Path], workflow: dict[str, Any]
) -> tuple[dict[str, str], ...]:
    """Bind actual transition endpoints, independently of selected declarations."""
    return tuple(
        {
            "repository": workflow["repository"],
            "path": path,
            "stage": stage,
            "revision": hash_file(member, domain=FILE_DOMAIN).hash,
        }
        for stage in ("before", "after")
        for path in workflow_changed_paths(workflow)
        if (member := confined_path(sources[workflow[stage]], path)).is_file()
    )


def _comparison_source_bindings(
    sources: dict[str, Path], workflow: dict[str, Any], rule: dict[str, Any]
) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "repository": workflow["repository"],
            "path": path,
            "stage": stage,
            "revision": hash_file(
                confined_file(sources[workflow[stage]], path), domain=FILE_DOMAIN
            ).hash,
        }
        for stage in ("before", "after")
        for path in sorted({label["path"] for label in task_source_labels(rule, stage)})
    )
