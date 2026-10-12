"""Revision workflows in disposable copies of explicitly admitted repositories."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from hashmarks.codemap import CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation
from hashmarks.test_shards import repository_content_identity

from .backend_boundary import observe_boundary
from .backend_declarations import observe_declarations
from .backend_matrix import INITIAL_TOKEN_CEILING
from .backend_transport import capture_cli, capture_mcp
from .common import canonical_sha256, write_json
from .fact_grading import grade_facts


def _packet(response: dict[str, Any]) -> dict[str, Any]:
    return response.get("result", response)


def _transport_grade(
    captures: list[dict[str, Any]], rule: dict[str, Any], workspace: Path
) -> dict[str, Any]:
    grades: list[dict[str, Any]] = []
    for capture in captures:
        response = capture["response"]
        packet = _packet(response)
        graded = grade_facts(capture["format"], {"packet": packet}, rule)
        parity = graded["classification"] == "PASS"
        if capture["format"] != "none":
            parity &= (
                validate_evidence_presentation(packet, response["presentation"])[
                    "valid"
                ]
                is True
            )
        grades.append(
            {
                "format": capture["format"],
                "parity": parity,
                "estimated_tokens": capture["estimated_tokens"],
                "checks": graded["checks"],
                "authority": _authority_safe(packet, rule)
                and graded["authority_violations"] == 0,
                "revision": _revision_bound(workspace, packet),
            }
        )
    complete = sorted(row["format"] for row in grades) == sorted(FORMATS)
    initial = [row for row in grades if row["format"] in {"compact", "text"}]
    return {
        "parity": complete and all(row["parity"] for row in grades),
        "initial_budget": complete
        and len(initial) == 2
        and all(
            row["parity"] and row["estimated_tokens"] <= INITIAL_TOKEN_CEILING
            for row in initial
        ),
        "grades": grades,
        "authority": complete and all(row["authority"] for row in grades),
        "revision": complete and all(row["revision"] for row in grades),
    }


def _authority_safe(packet: dict[str, Any], rule: dict[str, Any]) -> bool:
    owner = packet["ownership"]["owner"]
    return owner is None or owner["path"] == rule["expected_owner_path"]


def _missing_transport() -> dict[str, Any]:
    return {
        "parity": None,
        "initial_budget": None,
        "grades": [],
        "authority": None,
        "revision": None,
    }


def _observe_stage(
    workspace: Path,
    state: Path,
    workflow: dict[str, Any],
    rule: dict[str, Any],
    output: Path,
    transports: tuple[str, ...],
) -> dict[str, Any]:
    snapshot = repository_content_identity(workspace)
    with CodeMap(workspace, state_dir=state) as codemap:
        codemap.sync()
        packet = codemap.task_evidence(workflow["task"])
    # Independent public consumers must not contend with an open writer held
    # by this evaluator. Reopening retains the same durable observation owner.
    grade = grade_facts(workflow["id"], {"packet": packet}, rule)
    case = {"operation": "task_evidence", "inputs": {"task": workflow["task"]}}
    write_json(output / "api.json", packet)
    cli = capture_cli(workspace, state, case) if "cli" in transports else []
    mcp = capture_mcp(workspace, state, case) if "mcp" in transports else []
    boundary_inputs = workflow.get("boundary_observations", {}).get(rule["_stage"])
    boundary_rule = rule.get("function_boundary_oracles", {}).get(rule["_stage"])
    boundary = (
        observe_boundary(
            workspace,
            state,
            boundary_inputs,
            boundary_rule,
            output / "boundary",
            transports,
        )
        if boundary_inputs is not None and boundary_rule is not None
        else None
    )
    declaration_inputs = workflow.get("declaration_observations", {}).get(
        rule["_stage"]
    )
    declaration_rule = rule.get("declaration_oracles", {}).get(rule["_stage"])
    declarations = (
        observe_declarations(
            workspace,
            state,
            declaration_inputs,
            declaration_rule,
            output / "declarations",
            transports,
        )
        if declaration_inputs is not None and declaration_rule is not None
        else None
    )
    # A sequence of public observations must belong to one stable repository
    # snapshot, including producer and transport reads after the writer closes.
    _check_snapshot(workspace, snapshot)
    write_json(output / "cli.json", cli)
    write_json(output / "mcp.json", mcp)
    return {
        "packet": packet,
        "grade": grade,
        "revision_bound": _revision_bound(workspace, packet),
        "cli": _transport_grade(cli, rule, workspace) if cli else _missing_transport(),
        "mcp": _transport_grade(mcp, rule, workspace) if mcp else _missing_transport(),
        "boundary": boundary,
        "declarations": declarations,
    }


def _revision_bound(workspace: Path, packet: dict[str, Any]) -> bool:
    candidate = packet["ownership"].get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("path"):
        return False
    path = (workspace / candidate["path"]).resolve()
    if not path.is_relative_to(workspace.resolve()) or not path.is_file():
        return False
    return (
        packet["provenance"].get("revision") == hash_file(path, domain=FILE_DOMAIN).hash
    )


def _freshness(
    codemap: CodeMap, paths: list[str], before_revisions: dict[str, str]
) -> dict[str, Any]:
    observations = [
        cast("dict[str, Any]", codemap.source_observation(path)) for path in paths
    ]
    passed = bool(observations) and all(
        row["freshness"] != "current"
        and row["negative_evidence"] == "not-admissible"
        and row["member"]["state"] == "unknown"
        and row["member"]["reason"] == "member-revision-mismatch"
        and row["member"]["member_revision"] == before_revisions[path]
        for path, row in zip(paths, observations, strict=True)
    )
    return {"passed": passed, "observations": observations}


def _gates(
    before: dict[str, Any],
    after: dict[str, Any],
    stale: dict[str, Any],
    rule: dict[str, Any],
    delta_grade: dict[str, Any],
) -> dict[str, bool | None]:
    packets = [before["packet"], after["packet"]]
    owner_path = rule["expected_owner_path"]
    authority = all(_authority_safe(packet, rule) for packet in packets)
    authority &= (
        all(stage["grade"]["authority_violations"] == 0 for stage in (before, after))
        and delta_grade["authority_violations"] == 0
    )
    transport_rows = [
        stage[name] for stage in (before, after) for name in ("cli", "mcp")
    ]
    authority &= all(row["authority"] is not False for row in transport_rows)
    return {
        "facts": all(
            stage["grade"]["classification"] == "PASS" for stage in (before, after)
        )
        and delta_grade["classification"] == "PASS",
        "authority": authority,
        "revision": before["revision_bound"]
        and after["revision_bound"]
        and all(row["revision"] is not False for row in transport_rows),
        "freshness": stale["passed"],
        "cli": before["cli"]["parity"] and after["cli"]["parity"],
        "mcp": before["mcp"]["parity"] and after["mcp"]["parity"],
        "presentation": before["cli"]["parity"]
        and before["mcp"]["parity"]
        and after["cli"]["parity"]
        and after["mcp"]["parity"],
        "owner_top_three": owner_path
        in {row["path"] for row in before["packet"]["retrieval"]["results"][:3]},
        "initial_evidence": before["cli"]["initial_budget"]
        and before["mcp"]["initial_budget"],
    }


def execute_workflow(
    workflow: dict[str, Any],
    rule: dict[str, Any],
    sources: dict[str, Path],
    output: Path,
    *,
    transports: tuple[str, ...] = ("cli", "mcp"),
    source_identities: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one known source transition; no edits to the supplied source trees."""
    identities = (
        source_identities
        if source_identities is not None
        else {
            workflow[stage]: repository_content_identity(sources[workflow[stage]])
            for stage in ("before", "after")
        }
    )
    with tempfile.TemporaryDirectory(prefix="hashmarks-backend-") as scratch:
        workspace, state = Path(scratch) / "repo", Path(scratch) / "state"
        shutil.copytree(sources[workflow["before"]], workspace, symlinks=True)
        _check_snapshot(workspace, identities[workflow["before"]])
        before_revisions = {
            path: hash_file(workspace / path, domain=FILE_DOMAIN).hash
            for path in workflow["changed_paths"]
        }
        before = _observe_stage(
            workspace,
            state,
            workflow,
            {**rule, **rule.get("before", {}), "_stage": "before"},
            output / "before",
            transports,
        )
        shutil.rmtree(workspace)
        shutil.copytree(sources[workflow["after"]], workspace, symlinks=True)
        _check_snapshot(workspace, identities[workflow["after"]])
        with CodeMap(workspace, state_dir=state) as codemap:
            stale = _freshness(codemap, workflow["changed_paths"], before_revisions)
            write_json(output / "stale.json", stale)
            delta = codemap.task_post_change_delta(
                workflow["task"],
                workflow["changed_paths"],
                previous_evidence=before["packet"],
            )
            write_json(output / "delta.json", delta)
            delta_grade = grade_facts(
                workflow["id"], {"packet": delta}, {"checks": rule["delta_checks"]}
            )
        after = _observe_stage(
            workspace,
            state,
            workflow,
            {**rule, **rule.get("after", {}), "_stage": "after"},
            output / "after",
            transports,
        )
    gates = _gates(before, after, stale, rule, delta_grade)
    for stage in (before, after):
        for component in (stage["boundary"], stage["declarations"]):
            if component is None:
                continue
            for key, value in component["gates"].items():
                gates[key] = (
                    False
                    if gates[key] is False or value is False
                    else None
                    if gates[key] is None or value is None
                    else True
                )
            gates["presentation"] = gates["cli"] and gates["mcp"]
    return {
        "id": workflow["id"],
        "gates": gates,
        "before": before["grade"],
        "after": after["grade"],
        "delta": delta_grade,
        "boundary_observations": {
            "before": before["boundary"],
            "after": after["boundary"],
        },
        "declaration_observations": {
            "before": before["declarations"],
            "after": after["declarations"],
        },
        "transport_grades": {
            "before": {key: before[key] for key in ("cli", "mcp")},
            "after": {key: after[key] for key in ("cli", "mcp")},
        },
        "observation_identity": "sha256:"
        + canonical_sha256(
            {
                "before": before["packet"],
                "after": after["packet"],
                "stale": stale,
                "delta": delta,
                "boundary": [before["boundary"], after["boundary"]],
                "declarations": [before["declarations"], after["declarations"]],
            }
        ),
    }


def _check_snapshot(workspace: Path, expected_identity: str) -> None:
    if repository_content_identity(workspace) != expected_identity:
        raise ValueError(
            "backend source changed while materializing the observation snapshot"
        )
