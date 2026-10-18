"""Qualify caller-selected physical source lines through existing public surfaces.

Development evidence only: source spelling never establishes runtime marker
binding, provider wiring, constructor compatibility or verification sufficiency.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hashmarks.codemap import CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_bytes

from .backend_gates import combine_required, fact_state, presentation_conformance
from .backend_grading import component_summary, validate_transport_capture
from .common import write_json
from .fact_grading import grade_facts


def source_request_lines(request: Mapping[str, Any]) -> tuple[str, list[int]]:
    """Admit the same bounded line-context request supported by CLI and MCP."""
    context = request.get("context_lines")
    paths = request.get("paths")
    if (
        set(request) != {"paths", "result_mode", "context_lines"}
        or request.get("result_mode") != "member"
        or not isinstance(paths, list)
        or len(paths) != 1
        or not isinstance(paths[0], str)
    ):
        raise ValueError("source observation requires one selected member")
    if (
        not isinstance(context, dict)
        or set(context) != {"lines", "radius"}
        or type(context["radius"]) is not int
        or context["radius"] != 1
    ):
        raise ValueError(
            "source observation requires one member and explicit line context"
        )
    lines = context["lines"]
    if (
        not isinstance(lines, list)
        or not 1 <= len(lines) <= 8
        or any(type(line) is not int or line < 1 for line in lines)
        or len(set(lines)) != len(lines)
    ):
        raise ValueError("source observation requires 1–8 distinct positive lines")
    return paths[0], lines


def source_lines_bound(
    workspace: Path, packet: dict[str, Any], rule: dict[str, Any]
) -> bool:
    """Re-prove current member and exact line bytes instead of trusting receipts."""
    from .backend_corpus import confined_file

    labels = rule["source_labels"]
    path = labels[0]["path"]
    raw = confined_file(workspace, path).read_bytes()
    revision = hash_bytes(raw, domain=FILE_DOMAIN).hash
    physical = raw.split(b"\n")
    anchors = packet.get("line_anchors", [])
    member = packet.get("member", {})
    expected = {label["start_line"] for label in labels}
    if (
        not isinstance(anchors, list)
        or not isinstance(member, dict)
        or any(not isinstance(row, dict) for row in anchors)
    ):
        return False
    return (
        packet.get("freshness") in {"current", "unknown"}
        and packet.get("availability") == "observed"
        and packet.get("completeness") == "complete"
        and packet.get("truncation") == "complete"
        and packet.get("line_coverage") == "complete"
        and member.get("path") == path
        and member.get("state") == "known-present"
        and member.get("index_state") == "indexed"
        and member.get("member_revision") == revision
        and len(anchors) == len(expected)
        and packet.get("requested_lines") == sorted(expected)
        and all(type(row.get("line")) is int for row in anchors)
        and {row.get("line") for row in anchors} == expected
        and all(
            row.get("state") == "observed"
            and type(row.get("line")) is int
            and 1 <= row["line"] <= len(physical)
            and row.get("path") == path
            and row.get("member_revision") == revision
            and row.get("line_sha256")
            == hashlib.sha256(
                b"hashmarks.source-line.v1\0" + physical[row["line"] - 1]
            ).hexdigest()
            for row in anchors
        )
    )


def grade_source(
    workspace: Path, packet: dict[str, Any], rule: dict[str, Any]
) -> dict[str, Any]:
    facts = grade_facts("source-lines", {"packet": packet}, rule)
    return {
        "facts": fact_state(facts["classification"]),
        "authority": facts["authority_violations"] == 0,
        "revision": source_lines_bound(workspace, packet, rule),
        "source_freshness": packet.get("freshness"),
        "checks": facts["checks"],
    }


def grade_source_transport(
    workspace: Path, capture: dict[str, Any], rule: dict[str, Any]
) -> dict[str, Any]:
    validate_transport_capture(capture)
    response = capture["response"]
    packet = response.get("result", response)
    graded = grade_source(workspace, packet, rule)
    graded["parity"] = (
        capture["format"] == "none"
        or presentation_conformance(packet, response["presentation"])["valid"] is True
    )
    display = rule.get("display_checks", {}).get(capture["format"])
    if capture["format"] != "none" and display:
        facts = grade_facts(
            "source-lines-display",
            {"packet": response["presentation"]},
            {"checks": display},
        )
        graded["facts"] = combine_required(
            [graded["facts"], fact_state(facts["classification"])]
        )
        graded["authority"] = graded["authority"] and facts["authority_violations"] == 0
    return {"format": capture["format"], **graded}


def observe_source(
    workspace: Path,
    state: Path,
    inputs: dict[str, Any],
    rule: dict[str, Any],
    output: Path,
    transports: tuple[str, ...],
) -> dict[str, Any]:
    from .backend_transport import capture_cli, capture_mcp

    path, lines = source_request_lines(inputs)
    with CodeMap(workspace, state_dir=state) as codemap:
        packet = codemap.source.observe(path, lines=lines, anchor_context_lines=1)
    write_json(output / "api.json", packet)
    api = grade_source(workspace, packet, rule)
    results = {}
    case = {"operation": "source_observation", "inputs": inputs}
    for name, capture in (("cli", capture_cli), ("mcp", capture_mcp)):
        rows = capture(workspace, state, case) if name in transports else []
        write_json(output / f"{name}.json", rows)
        results[name] = [grade_source_transport(workspace, row, rule) for row in rows]
    return component_summary(api, results)


def observe_source_stage(
    workspace: Path,
    state: Path,
    workflow: dict[str, Any],
    rule: dict[str, Any],
    output: Path,
    transports: tuple[str, ...],
) -> dict[str, Any] | None:
    """Compose the explicitly admitted source-line family for this revision."""
    inputs = workflow.get("source_observations", {}).get(rule["_stage"])
    oracle = rule.get("source_oracles", {}).get(rule["_stage"])
    if inputs is None or oracle is None:
        return None
    return observe_source(
        workspace, state, inputs, oracle, output / "source", transports
    )
