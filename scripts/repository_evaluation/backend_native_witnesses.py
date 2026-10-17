"""Source-bound facts from admitted native observations; no producer execution."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from hashmarks.digest import FILE_DOMAIN, hash_file

from .backend_corpus import confined_file
from .backend_gates import combine_required
from .backend_grading import FactObservation, grade_fact_observation
from .backend_witnesses import captured_fact_witnesses


def native_fact_witnesses(
    workflow: dict[str, Any],
    rule: dict[str, Any],
    sources: dict[str, Path],
    output: Path,
) -> list[dict[str, Any]]:
    if "native_oracles" not in rule:
        return []
    witnesses = [
        witness
        for stage in ("before", "after")
        for witness in _stage_witnesses(
            workflow, rule, sources[workflow[stage]], output / stage, stage
        )
    ]
    return [{**witness, "artifact_scope": "native"} for witness in witnesses]


def _stage_witnesses(
    workflow: dict[str, Any],
    rule: dict[str, Any],
    source: Path,
    output: Path,
    stage: str,
) -> list[dict[str, Any]]:
    oracles = rule.get("native_oracles", {}).get(stage, {})
    witnesses = []
    for ordinal, label in enumerate(rule["source_labels"][stage]):
        target = label["path"] + "::" + label["symbol"]
        if target not in oracles:
            continue
        directory = "" if ordinal == 0 else "targets/" + str(ordinal)
        pointer = target.replace("~", "~0").replace("/", "~1")
        context = FactObservation(
            "native_binding",
            workflow["id"] + "::" + target,
            stage,
            None,
            "api",
            "none",
            f"/cases/{workflow['id']}/native_oracles/{stage}/{pointer}/checks",
            None,
            _source_bindings(workflow, rule, source, stage),
        )
        witnesses.extend(
            captured_fact_witnesses(output, directory, oracles[target], context)
        )
        witnesses.extend(
            _definition_witnesses(output, directory, oracles[target], context)
        )
    return witnesses


def _source_bindings(
    workflow: dict[str, Any], rule: dict[str, Any], source: Path, stage: str
) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "repository": workflow["repository"],
            "path": path,
            "revision": hash_file(confined_file(source, path), domain=FILE_DOMAIN).hash,
        }
        for path in sorted({label["path"] for label in rule["source_labels"][stage]})
    )


def _definition_witnesses(
    output: Path,
    directory: str,
    oracle: dict[str, Any],
    context: FactObservation,
) -> list[dict[str, Any]]:
    if "definition_checks" not in oracle:
        return []
    relative = (directory + "/" if directory else "") + "definition-token.json"
    contents = confined_file(output, relative).read_bytes()
    observation = replace(
        context,
        gate="native_definition",
        oracle_pointer=context.oracle_pointer.removesuffix("/checks")
        + "/definition_checks",
        artifact=(context.stage + "/" + relative, contents),
    )
    return grade_fact_observation(
        json.loads(contents), {"checks": oracle["definition_checks"]}, observation
    )["witnesses"]


def native_witness_gate(witnesses: list[dict[str, Any]]) -> bool | None:
    states = {"PASS": True, "FAIL": False, "INCOMPLETE": None}
    return combine_required(states[row["state"]] for row in witnesses)
