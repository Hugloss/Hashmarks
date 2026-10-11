"""Freeze paired backend navigation observations for an external agent evaluator.

Evaluation-only: no agent, host transport, grader, semantic correspondence
resolver, benchmark verdict or product-side evidence routing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from hashmarks import CodeMap
from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)

SCHEMA = "hashmarks.backend-navigation-ablation.v1"
MANIFEST_SCHEMA = "hashmarks.backend-navigation-cases.v1"
MAX_CASES = 16
MAX_EXPORT_BYTES = 4_194_304


def _encode(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_encode(value)).hexdigest()


def _cases(manifest: object) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "cases"}:
        raise ValueError("backend case manifest must have exactly schema and cases")
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise ValueError("unsupported backend case manifest schema")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("backend case count must be 1..16")
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "id", "prompt", "paths", "model_fields", "environment_reads"
        }:
            raise ValueError("backend cases require five exact fields")
        case_id, prompt, paths = case["id"], case["prompt"], case["paths"]
        if (
            not isinstance(case_id, str)
            or not case_id.strip()
            or len(case_id) > 128
            or case_id in seen
            or not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > 2048
            or not isinstance(paths, list)
            or any(not isinstance(path, str) for path in paths)
        ):
            raise ValueError("invalid backend case id, prompt or path selection")
        if type(case["model_fields"]) is not bool or type(case["environment_reads"]) is not bool:
            raise ValueError("backend mode fields must be booleans")
        # Reuse product provider's exact source-path validation, not another parser.
        StaticPythonBackendDeclarations(
            paths=tuple(paths),
            include_model_fields=case["model_fields"],
            include_environment_reads=case["environment_reads"],
        )
        selected.append(case)
        seen.add(case_id)
    return sorted(selected, key=lambda case: case["id"])


def _source_facts(packet: dict[str, Any]) -> list[dict[str, object]]:
    """Compare source syntax independently of navigation and generated digests."""
    groups = packet["declarations"]["groups"]
    facts: list[dict[str, object]] = []
    for group in groups:
        if len(group["declarations"]) != 1:
            raise ValueError("backend ablation expected one direct declaration per group")
        declaration = group["declarations"][0]
        value = deepcopy(declaration["value"])
        value.pop("evidence_navigation", None)
        facts.append({
            "group_id": group["group_id"],
            "concept": group["concept"],
            "scope": group["scope"],
            "correspondence": group["correspondence"],
            "coverage": group["coverage"],
            "semantic_role": declaration["semantic_role"],
            "value_state": declaration["value_state"],
            "value": value,
            "producer": declaration["producer"],
            "evidence": declaration["evidence"],
        })
    return sorted(facts, key=lambda fact: str(fact["group_id"]))


def _provider_sources(packet: dict[str, Any]) -> dict[str, object]:
    providers = packet["providers"]
    if len(providers) != 1 or providers[0]["state"] != "collected":
        raise ValueError("backend ablation requires one collected source provider")
    provider = providers[0]
    return {"inputs": provider["inputs"], "enumerations": provider["enumerations"]}


def _arm(
    case: dict[str, Any], packet: dict[str, Any], *,
    navigation: bool, fact_identity: str
) -> dict[str, object]:
    arm = "navigation" if navigation else "syntax-only"
    observation = {
        "case_id": case["id"],
        "arm": arm,
        "prompt": case["prompt"],
        "provider_packet": packet,
        "fact_identity": fact_identity,
        "exposure": "exported-not-host-attested",
        "host_visible": "not-established",
        "agent_invoked": "not-established",
        "agent_used": "not-established",
        "agent_result": "not-measured",
    }
    return {
        **observation,
        "observation_identity": _digest(observation),
        "utf8_bytes": len(_encode(observation)),
    }


def export_cases(repo: Path, manifest: dict[str, object]) -> dict[str, object]:
    """Freeze both source-equivalent arms on one synced CodeMap snapshot."""
    cases = _cases(manifest)  # Fail malformed requests before index work.
    result: list[dict[str, object]] = []
    with CodeMap(repo) as codemap:
        codemap.sync()
        for case in cases:
            settings = {
                "paths": tuple(case["paths"]),
                "include_model_fields": case["model_fields"],
                "include_environment_reads": case["environment_reads"],
            }
            baseline = codemap.discover_repository_declarations([
                StaticPythonBackendDeclarations(**settings)
            ])
            treatment = codemap.discover_repository_declarations([
                StaticPythonBackendDeclarations(**settings, include_evidence_navigation=True)
            ])
            before, after = _source_facts(baseline), _source_facts(treatment)
            if before != after:
                raise ValueError("navigation changed the observed backend source facts")
            if _provider_sources(baseline) != _provider_sources(treatment):
                raise ValueError("navigation arms have divergent source revision binding")
            if baseline["repository"] != treatment["repository"]:
                raise ValueError("navigation arms have divergent repository authority")
            if any(
                "evidence_navigation" in row["value"] for row in before
            ) or any(
                "evidence_navigation" not in row["declarations"][0]["value"]
                for row in treatment["declarations"]["groups"]
            ):
                raise ValueError("ablation arms are not exact navigation off/on")
            identity = _digest({
                "repository": baseline["repository"],
                "sources": _provider_sources(baseline),
                "facts": before,
            })
            result.append({
                "case_id": case["id"],
                "source_facts_identity": identity,
                "source_group_count": len(before),
                "source_revision_binding": _provider_sources(baseline),
                "arms": [
                    _arm(case, baseline, navigation=False, fact_identity=identity),
                    _arm(case, treatment, navigation=True, fact_identity=identity),
                ],
                "inference": "no-agent-outcome-measured",
            })
    export: dict[str, object] = {
        "schema": SCHEMA,
        "cases": result,
        "pair_completeness": "two-frozen-arms-per-case",
        "authority": "source-bound-provider-observations-only",
        "agent_experiment_owner": "external-agentsCookbook",
        "model_delivery": "not-observed",
        "paired_correctness": "not-measured",
        "source_fact_equivalence": "checked",
    }
    if len(_encode(export)) > MAX_EXPORT_BYTES:
        raise ValueError("backend ablation exceeds 4 MiB exported packet bound")
    export["export_identity"] = _digest(export)
    return export


def validate_export(value: object) -> None:
    """Reject forged pairs, mismatched sources, and changed export identities."""
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("unsupported backend ablation export schema")
    if value.get("export_identity") != _digest({
        key: item for key, item in value.items() if key != "export_identity"
    }):
        raise ValueError("backend export identity mismatch")
    for case in value["cases"]:
        arms = case["arms"]
        if [arm["arm"] for arm in arms] != ["syntax-only", "navigation"]:
            raise ValueError("backend ablation requires exact paired arms")
        for arm in arms:
            observation = {
                key: item for key, item in arm.items()
                if key not in {"observation_identity", "utf8_bytes"}
            }
            if _digest(observation) != arm["observation_identity"]:
                raise ValueError("backend arm observation identity mismatch")
            if len(_encode(observation)) != arm["utf8_bytes"]:
                raise ValueError("backend arm size mismatch")
        before, after = arms[0]["provider_packet"], arms[1]["provider_packet"]
        if _source_facts(before) != _source_facts(after):
            raise ValueError("backend pair differs beyond navigation")
        if _provider_sources(before) != _provider_sources(after):
            raise ValueError("backend pair source binding differs")
        identity = _digest({
            "repository": before["repository"],
            "sources": _provider_sources(before),
            "facts": _source_facts(before),
        })
        if identity != case["source_facts_identity"] or any(
            arm["fact_identity"] != identity for arm in arms
        ):
            raise ValueError("backend source facts identity mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    export = export_cases(args.repo, manifest)
    validate_export(export)
    args.output.write_bytes(_encode(export) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
