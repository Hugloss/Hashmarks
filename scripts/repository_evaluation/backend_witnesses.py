"""Bind pure grading to retained API bytes and admitted source snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hashmarks.digest import FILE_DOMAIN, hash_file

from .backend_corpus import confined_file
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
    paths = sorted({label["path"] for label in rule["source_labels"][stage]})
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
    paths = sorted({label["path"] for label in rule["source_labels"][stage]})
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
        checks = rule.get(key)
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
                if checks:
                    witnesses.extend(
                        grade_fact_observation(packet, {"checks": checks}, context)[
                            "witnesses"
                        ]
                    )
                display_checks = (
                    rule.get("display_checks", {}).get(profile, {}).get(format)
                )
                if surface != "api" and format != "none" and display_checks:
                    observation = FactObservation(
                        "presentation",
                        workflow["id"],
                        stage,
                        profile,
                        surface,
                        format,
                        scope + f"/display_checks/{profile}/{format}",
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
