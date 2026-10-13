"""Bind pure grading to retained API bytes and admitted source snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hashmarks.digest import FILE_DOMAIN, hash_file

from .backend_corpus import confined_file
from .backend_grading import FactObservation, grade_fact_observation


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
