"""Revision workflows in disposable copies of explicitly admitted repositories."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from hashmarks import CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation

from .backend_matrix import INITIAL_TOKEN_CEILING
from .backend_transport import capture_cli, capture_mcp
from .common import canonical_sha256, write_json
from .fact_grading import grade_facts


def _packet(response: dict[str, Any]) -> dict[str, Any]:
    return response.get("result", response)


def _transport_grade(
    captures: list[dict[str, Any]], rule: dict[str, Any]
) -> dict[str, Any]:
    grades = []
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
    }


def _observe_stage(
    workspace: Path,
    state: Path,
    workflow: dict[str, Any],
    rule: dict[str, Any],
    output: Path,
    transports: tuple[str, ...],
) -> dict[str, Any]:
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
    write_json(output / "cli.json", cli)
    write_json(output / "mcp.json", mcp)
    return {
        "packet": packet,
        "grade": grade,
        "revision_bound": _revision_bound(workspace, packet),
        "cli": _transport_grade(cli, rule)
        if cli
        else {"parity": None, "initial_budget": None, "grades": []},
        "mcp": _transport_grade(mcp, rule)
        if mcp
        else {"parity": None, "initial_budget": None, "grades": []},
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


def _freshness(codemap: CodeMap, paths: list[str]) -> dict[str, Any]:
    observations = [codemap.source_observation(path) for path in paths]
    passed = bool(observations) and all(
        row["freshness"] != "current" and row["negative_evidence"] == "not-admissible"
        for row in observations
    )
    return {"passed": passed, "observations": observations}


def _gates(
    before: dict[str, Any],
    after: dict[str, Any],
    stale: dict[str, Any],
    rule: dict[str, Any],
) -> dict[str, bool | None]:
    packets = [before["packet"], after["packet"]]
    owner_path = rule["expected_owner_path"]
    authority = all(
        packet["ownership"]["owner"] is None
        or packet["ownership"]["owner"]["path"] == owner_path
        for packet in packets
    )
    return {
        "facts": all(
            stage["grade"]["classification"] == "PASS" for stage in (before, after)
        ),
        "authority": authority,
        "revision": before["revision_bound"] and after["revision_bound"],
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
) -> dict[str, Any]:
    """Run one known source transition; no edits to the supplied source trees."""
    with tempfile.TemporaryDirectory(prefix="hashmarks-backend-") as scratch:
        workspace, state = Path(scratch) / "repo", Path(scratch) / "state"
        shutil.copytree(sources[workflow["before"]], workspace, symlinks=True)
        before = _observe_stage(
            workspace,
            state,
            workflow,
            {**rule, **rule.get("before", {})},
            output / "before",
            transports,
        )
        shutil.rmtree(workspace)
        shutil.copytree(sources[workflow["after"]], workspace, symlinks=True)
        with CodeMap(workspace, state_dir=state) as codemap:
            stale = _freshness(codemap, workflow["changed_paths"])
            write_json(output / "stale.json", stale)
            delta = codemap.task_post_change_delta(
                workflow["task"],
                workflow["changed_paths"],
                previous_evidence=before["packet"],
            )
            write_json(output / "delta.json", delta)
        after = _observe_stage(
            workspace,
            state,
            workflow,
            {**rule, **rule.get("after", {})},
            output / "after",
            transports,
        )
    gates = _gates(before, after, stale, rule)
    return {
        "id": workflow["id"],
        "gates": gates,
        "before": before["grade"],
        "after": after["grade"],
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
            }
        ),
    }
