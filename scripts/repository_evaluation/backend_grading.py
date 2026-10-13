"""Pure backend fact and task-gate grading shared by acquisition and revalidation.

This module observes supplied evidence only. It performs no source acquisition,
process launch, repository mutation, or execution/certification decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from hashmarks.codemap.python_ast import estimate_tokens
from hashmarks.evidence_presentation import FORMATS
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

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value
            for value in (self.gate, self.unit_id, self.oracle_pointer)
        ) or not self.oracle_pointer.startswith("/"):
            raise ValueError("backend witness requires gate, unit and oracle identity")
        _observation_context(self.stage, self.profile, self.surface, self.format)
        if self.artifact is not None:
            path, contents = self.artifact
            _relative_reference(path)
            if not isinstance(contents, bytes):
                raise ValueError("backend witness artifact requires exact bytes")
        identities = set()
        for binding in self.source_bindings:
            if any(
                not isinstance(binding.get(key), str) or not binding[key]
                for key in ("repository", "path", "revision")
            ):
                raise ValueError("backend witness requires complete source identity")
            _relative_reference(binding["path"])
            stage = binding.get("stage")
            if stage is not None and stage not in {"before", "after"}:
                raise ValueError("backend source binding has invalid revision stage")
            identity = (binding["repository"], binding["path"], stage)
            if identity in identities:
                raise ValueError("backend witness contains duplicate source bindings")
            identities.add(identity)


def _relative_reference(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or PurePosixPath(value).is_absolute()
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("backend witness references must be confined relative paths")


def _observation_context(
    stage: object, profile: object, surface: object, format: object
) -> None:
    dimensions = (
        (stage, ("before", "after", "stale", "delta", "transition")),
        (profile, (None, "default", "initial")),
        (surface, ("api", "cli", "mcp")),
        (format, FORMATS),
    )
    if any(value not in allowed for value, allowed in dimensions) or (
        surface == "api" and format != "none"
    ):
        raise ValueError("backend witness has invalid observation context")


WITNESS_CONTEXT = (
    "gate",
    "unit_id",
    "stage",
    "profile",
    "surface",
    "format",
    "check_id",
)


def witness_identity(row: Mapping[str, Any]) -> tuple[object, ...]:
    if any(key not in row for key in WITNESS_CONTEXT):
        raise ValueError("backend witness requires complete observation context")
    if any(
        not isinstance(row[key], str) or not row[key]
        for key in ("gate", "unit_id", "check_id")
    ):
        raise ValueError("backend witness requires nonempty semantic identity")
    _observation_context(row["stage"], row["profile"], row["surface"], row["format"])
    return tuple(row[key] for key in WITNESS_CONTEXT)


def grade_fact_observation(
    packet: dict[str, Any], rule: dict[str, Any], observation: FactObservation
) -> dict[str, Any]:
    """Produce artifact-bound witnesses without trusting a supplied gate verdict."""
    graded = grade_facts(observation.unit_id, {"packet": packet}, rule)
    witnesses = []
    for ordinal, row in enumerate(graded["checks"]):
        state = row["classification"]
        check = rule["checks"][ordinal]
        paths = check.get("source_paths")
        if paths is not None and (
            not isinstance(paths, list)
            or not paths
            or any(not isinstance(path, str) or not path for path in paths)
            or len(set(paths)) != len(paths)
        ):
            raise ValueError("backend fact requires distinct source binding paths")
        bindings = [
            dict(binding)
            for binding in observation.source_bindings
            if paths is None or binding["path"] in paths
        ]
        binding_complete = bool(bindings) and (
            paths is None or set(paths) == {binding["path"] for binding in bindings}
        )
        reason = (
            "matched-reviewed-fact"
            if state == "PASS"
            else "supported-fact-not-returned"
            if state == "FAIL"
            else "observation-scope-unqualified"
        )
        if observation.artifact is None or not binding_complete:
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
                "source_bindings": bindings,
                "alternative_records": row["alternative_records"],
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
        if texts[0] != "Initial repository evidence is available in structuredContent.":
            raise ValueError("backend initial MCP none display differs from contract")
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


def _declaration_locators(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    from hashmarks.codemap.task_evidence_initial import decode_initial_collection

    candidates = []
    for family in ("class_declarations", "enclosing_declarations"):
        context = row.get(family)
        if not isinstance(context, dict):
            continue
        qualifiers = {
            "authority": "indexed-lexical-declarations-only",
            "ownership_authority": False,
            "negative_evidence_admissible": False,
        }
        if not all(
            _json_equal(context.get(key), value) for key, value in qualifiers.items()
        ) or not context.get("source_revision"):
            continue
        declarations = context.get("declarations", [])
        if isinstance(context.get("declarations_encoding"), dict):
            declarations = decode_initial_collection(
                declarations, context["declarations_encoding"]
            )
        candidates.extend(declarations)
    return candidates


def _owner_top_three(packet: dict[str, Any], rule: dict[str, Any]) -> bool | None:
    """Measure reviewed locator presence without assigning ownership authority."""
    packet = _packet(packet)
    oracle = rule.get("owner_oracle")
    if oracle is None or oracle["resolution"] != "unique":
        return None
    expected = oracle["candidates"][0]
    rows = packet["retrieval"]["results"][:3]
    if oracle["scope"] == "file":
        return any(row.get("path") == expected["path"] for row in rows)
    for row in rows:
        for candidate in (row, *_declaration_locators(row)):
            actual = {
                "path": candidate.get("path"),
                "qualname": candidate.get("qualname", candidate.get("symbol")),
                "start_line": candidate.get("start_line"),
                "end_line": candidate.get("end_line"),
            }
            if _json_equal(actual, expected):
                return True
    return False


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
            _owner_top_three(stage["packet"], {**rule, **rule.get(label, {})})
            for label, stage in (("before", before), ("after", after))
        ),
        "initial_size": combine_required(row["initial_size"] for row in initial_rows),
        "initial_evidence": combine_required(
            row["initial_evidence"] for row in initial_rows
        ),
    }


def component_summary(
    api: dict[str, Any], transports: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    """One pure composition owner for boundary/declaration capture and regrading."""
    result: dict[str, Any] = {"api": api}
    for transport in ("cli", "mcp"):
        rows = transports[transport]
        formats = [row["format"] for row in rows]
        if len(set(formats)) != len(formats) or set(formats) - set(FORMATS):
            raise ValueError("backend component formats must be distinct and supported")
        result[transport] = {
            "complete": set(formats) == set(FORMATS) if rows else None,
            "grades": rows,
        }
    gates = {
        name: combine_required(
            [api[name], *(row[name] for rows in transports.values() for row in rows)]
        )
        for name in ("facts", "authority", "revision")
    }
    for transport in ("cli", "mcp"):
        gates[transport] = combine_required(
            [
                True if result[transport]["complete"] is True else None,
                *(
                    combine_required([row["facts"], row["parity"]])
                    for row in transports[transport]
                ),
            ]
        )
    result["gates"] = gates
    return result
