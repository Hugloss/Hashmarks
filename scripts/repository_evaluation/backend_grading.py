"""Pure backend fact and task-gate grading shared by acquisition and revalidation.

This module observes supplied evidence only. It performs no source acquisition,
process launch, repository mutation, or execution/certification decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hashmarks.codemap.python_ast import estimate_tokens
from hashmarks.operation_contract import operation_schema

from .backend_gates import combine_required, fact_state
from .common import canonical_sha256
from .fact_grading import _json_equal, grade_facts


@dataclass(frozen=True)
class FactObservation:
    gate: str
    unit_id: str
    stage: str
    profile: str | None
    surface: str
    format: str
    oracle_pointer: str
    artifact: tuple[str, bytes] | None
    source_bindings: tuple[dict[str, str], ...]


def grade_fact_observation(
    packet: dict[str, Any], rule: dict[str, Any], observation: FactObservation
) -> dict[str, Any]:
    """Produce artifact-bound witnesses without trusting a supplied gate verdict."""
    graded = grade_facts(observation.unit_id, {"packet": packet}, rule)
    witnesses = []
    for ordinal, row in enumerate(graded["checks"]):
        state = row["classification"]
        check = rule["checks"][ordinal]
        if (
            state == "INCOMPLETE"
            and check.get("support") == "supported"
            and check["predicate"] != "excludes"
        ):
            state = "FAIL"
        reason = (
            "matched-reviewed-fact"
            if state == "PASS"
            else "supported-fact-not-returned"
            if state == "FAIL"
            else "observation-scope-unqualified"
        )
        if observation.artifact is None or not observation.source_bindings:
            state = "FAIL" if state == "FAIL" else "INCOMPLETE"
            reason = (
                "missing-artifact-binding"
                if observation.artifact is None
                else "missing-source-binding"
            )
        witnesses.append(
            {
                "gate": observation.gate,
                "unit_id": observation.unit_id,
                "stage": observation.stage,
                "profile": observation.profile,
                "surface": observation.surface,
                "format": observation.format,
                "check_id": row["id"],
                "state": state,
                "reason": reason,
                "artifact": observation.artifact[0]
                if observation.artifact is not None
                else None,
                "artifact_sha256": hashlib.sha256(observation.artifact[1]).hexdigest()
                if observation.artifact is not None
                else None,
                "reference_space": "decoded-initial-data"
                if packet.get("schema") == operation_schema("task_evidence", "initial")
                else "native-json",
                "observation_pointer": row["pointer"],
                "oracle_pointer": observation.oracle_pointer + "/" + str(ordinal),
                "expected": row["expected"],
                "observed": row["observed"],
                "source_bindings": [
                    dict(binding) for binding in observation.source_bindings
                ],
            }
        )
    value = combine_required(
        True if row["state"] == "PASS" else False if row["state"] == "FAIL" else None
        for row in witnesses
    )
    return {"gate": value, "witnesses": witnesses, "facts": graded}


def validate_transport_capture(capture: dict[str, Any]) -> None:
    """Bind graded records and size measurements to actual consumer-visible bytes."""
    visible = capture.get("consumer_visible_response")
    transport = capture.get("transport")
    if not isinstance(visible, str) or transport not in {"cli", "mcp"}:
        raise ValueError("backend capture lacks consumer-visible transport evidence")
    expected = {
        "utf8_bytes": len(visible.encode("utf-8")),
        "estimated_tokens": estimate_tokens(visible),
        "capture_identity": "sha256:"
        + canonical_sha256({"transport": transport, "text": visible}),
    }
    if any(not _json_equal(capture.get(key), value) for key, value in expected.items()):
        raise ValueError("backend transport measurement differs from visible bytes")
    wire = json.loads(visible)
    response = capture["response"]
    if transport == "cli":
        if not _json_equal(wire, response):
            raise ValueError("backend CLI response differs from visible bytes")
        return
    _validate_mcp_wire(wire, response, capture["format"])


def _validate_mcp_wire(
    wire: dict[str, Any], response: dict[str, Any], format: str
) -> None:
    native = response.get("result", response)
    initial = native.get("schema") == operation_schema("task_evidence", "initial")
    expected = native if initial else response
    texts = [
        part.get("text")
        for part in wire.get("content", [])
        if part.get("type") == "text"
    ]
    if (
        wire.get("isError") is True
        or len(texts) != 1
        or not _json_equal(wire.get("structuredContent"), expected)
    ):
        raise ValueError("backend MCP structured response differs from visible bytes")
    if not initial:
        displayed = json.loads(texts[0])
        expected = response
    elif format == "none":
        return
    elif format == "text":
        displayed = texts[0]
        expected = response["presentation"]["text"]
    else:
        displayed = json.loads(texts[0])
        expected = response["presentation"]
    if not _json_equal(displayed, expected):
        raise ValueError("backend MCP display differs from visible bytes")


def _packet(response: dict[str, Any]) -> dict[str, Any]:
    packet = response.get("result", response)
    if (
        packet.get("schema") == operation_schema("task_evidence", "initial")
        and "encoding" in packet
    ):
        from hashmarks.codemap.task_evidence_initial import decode_initial_packet

        return decode_initial_packet(packet)
    return packet


def _authority_safe(packet: dict[str, Any], rule: dict[str, Any]) -> bool | None:
    packet = _packet(packet)
    owner = packet["ownership"]["owner"]
    if owner is None:
        return True  # Unresolved ownership does not assert an exact owner.
    oracle = rule.get("owner_oracle")
    if oracle is None:
        # A legacy path label can disprove a wrong path, but cannot qualify an
        # exact symbol assertion. Preserve that missing proof explicitly.
        return False if owner["path"] != rule["expected_owner_path"] else None
    if oracle["resolution"] != "unique":
        return False
    if oracle["scope"] == "file" and owner.get("qualname"):
        # A reviewed file owner does not establish a more precise symbol.
        return False if owner["path"] != oracle["candidates"][0]["path"] else None
    fields = (
        ("path",)
        if oracle["scope"] == "file"
        else ("path", "qualname", "start_line", "end_line")
    )
    return all(owner.get(key) == oracle["candidates"][0][key] for key in fields)


def _gates(
    before: dict[str, Any],
    after: dict[str, Any],
    stale: dict[str, Any],
    rule: dict[str, Any],
    delta_grade: Mapping[str, Any],
) -> dict[str, bool | None]:
    authority = combine_required(
        [
            *(
                _authority_safe(stage["packet"], {**rule, **rule.get(label, {})})
                for label, stage in (("before", before), ("after", after))
            ),
            *(stage["grade"]["authority_violations"] == 0 for stage in (before, after)),
            *(
                _authority_safe(
                    stage["initial"]["packet"], {**rule, **rule.get(label, {})}
                )
                for label, stage in (("before", before), ("after", after))
            ),
            delta_grade["authority_violations"] == 0,
        ]
    )
    transport_rows = [
        profile[name]
        for stage in (before, after)
        for profile in (stage, stage["initial"])
        for name in ("cli", "mcp")
    ]
    initial_rows = [
        stage["initial"][name] for stage in (before, after) for name in ("cli", "mcp")
    ]

    def transport_gate(name: str) -> bool | None:
        return combine_required(
            profile[name]["parity"]
            for stage in (before, after)
            for profile in (stage, stage["initial"])
        )

    return {
        "facts": combine_required(
            fact_state(grade["classification"])
            for grade in (before["grade"], after["grade"], delta_grade)
        ),
        "authority": combine_required(
            [authority, *(row["authority"] for row in transport_rows)]
        ),
        "revision": combine_required(
            [
                before["revision_bound"],
                after["revision_bound"],
                before["initial"]["revision_bound"],
                after["initial"]["revision_bound"],
                *(row["revision"] for row in transport_rows),
            ]
        ),
        "freshness": stale["passed"],
        "cli": transport_gate("cli"),
        "mcp": transport_gate("mcp"),
        "presentation": combine_required(row["parity"] for row in transport_rows),
        "owner_top_three": combine_required(
            rule.get(label, {}).get("expected_owner_path", rule["expected_owner_path"])
            in {row["path"] for row in stage["packet"]["retrieval"]["results"][:3]}
            for label, stage in (("before", before), ("after", after))
        ),
        "initial_size": combine_required(row["initial_size"] for row in initial_rows),
        "initial_evidence": combine_required(
            row["initial_evidence"] for row in initial_rows
        ),
    }
