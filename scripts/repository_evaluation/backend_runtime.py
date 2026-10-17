"""Observe supplied runtime claims in the existing backend qualification ring.

Captures are acquired externally and source-checked at corpus admission. This QA
adapter invokes repository observers only; it never executes a backend scenario.
Acquisition and retained-byte regrading use the same grading function.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import NotRequired, TypedDict

from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import FORMATS

from .backend_corpus import confined_file
from .backend_gates import combine_required, presentation_conformance
from .backend_grading import FactObservation, grade_fact_observation
from .backend_runtime_witnesses import (
    _object,
    _oracle_frames,
    _text,
    runtime_correlation_request,
    runtime_frame_checks,
    runtime_witness_context,
)
from .backend_transport import capture_cli, capture_mcp
from .backend_witnesses import captured_fact_observations
from .common import canonical_sha256, write_json
from .fact_grading import _json_equal

_CONTEXTS = (
    ("api", "none"),
    *((surface, format) for surface in ("cli", "mcp") for format in FORMATS),
)
_SurfaceGrades = dict[tuple[str, str], dict[str, bool | None]]


class RuntimeObservation(TypedDict):
    gates: dict[str, bool | None]
    gate_witnesses: list[dict[str, object]]
    debug_frame_observations: list[dict[str, object]]
    control: NotRequired[str]


def _state(value: object) -> bool | None:
    if value == "PASS":
        return True
    if value == "FAIL":
        return False
    if value in {None, "INCOMPLETE"}:
        return None
    raise ValueError("invalid runtime witness state")


def _context(oracles: Mapping[str, object]) -> FactObservation:
    bindings = {}
    for row in _oracle_frames(oracles):
        frame = _object(row["runtime_frame"])
        path = _text(frame["path"])
        revision = _text(frame["source_revision"])
        if path in bindings and bindings[path] != revision:
            raise ValueError("runtime oracle has conflicting source members")
        bindings[path] = revision
    unit, stage = _text(oracles["workflow"]), _text(oracles["stage"])
    return runtime_witness_context(
        oracles,
        FactObservation(
            "debug_correspondence",
            unit,
            stage,
            None,
            "api",
            "none",
            f"/cases/{unit}/runtime_oracles/{stage}/checks",
            None,
            tuple(
                {
                    "repository": _text(oracles["repository"]),
                    "path": path,
                    "revision": revision,
                }
                for path, revision in sorted(bindings.items())
            ),
        ),
    )


def _reduce(
    rows: _SurfaceGrades, field: str, surface: str | None = None
) -> bool | None:
    return combine_required(
        rows.get(key, {}).get(field)
        for key in _CONTEXTS
        if surface is None or key[0] == surface
    )


def _variant(
    output: Path,
    oracles: Mapping[str, object],
    context: FactObservation,
    *,
    invalidated: bool,
) -> tuple[_SurfaceGrades, list[dict[str, object]]]:
    variant = "invalidated" if invalidated else "qualified"
    checks = runtime_frame_checks(oracles, invalidated=invalidated)
    context = replace(
        context,
        gate="runtime_source_invalidation" if invalidated else "debug_correspondence",
        oracle_pointer=context.oracle_pointer + "/" + variant,
    )
    rows: _SurfaceGrades = {}
    witnesses = []
    api = None
    for observation in captured_fact_observations(
        output, "runtime/" + variant, context
    ):
        current = observation.context
        if current.surface == "api":
            api = observation.packet
        graded = grade_fact_observation(observation.packet, {"checks": checks}, current)
        witnesses.extend(graded["witnesses"])
        projection = observation.response.get("presentation")
        parity = _json_equal(observation.packet, api)
        if current.format != "none":
            parity = (
                parity
                and isinstance(projection, dict)
                and presentation_conformance(observation.packet, projection)["valid"]
                is True
            )
        revision = combine_required(
            _state(row["state"])
            for row in graded["witnesses"]
            if row["check_id"].endswith(":source-equivalence")
        )
        rows[(current.surface, current.format)] = {
            "facts": graded["gate"],
            "authority": graded["facts"]["authority_violations"] == 0,
            "revision": revision,
            "parity": parity,
        }
    return rows, witnesses


def _frames(
    oracles: Mapping[str, object], witnesses: list[dict[str, object]]
) -> list[dict[str, object]]:
    states = {
        (_text(row["surface"]), _text(row["format"]), _text(row["check_id"])): _state(
            row["state"]
        )
        for row in witnesses
    }
    if len(states) != len(witnesses):
        raise ValueError("runtime frame proof contains duplicate witnesses")
    checks = runtime_frame_checks(oracles)
    result = []
    for row in _oracle_frames(oracles):
        anchor = _text(row["anchor_id"])
        ids = [
            _text(check["id"])
            for check in checks
            if _text(check["id"]).startswith(("runtime-", anchor + ":"))
        ]
        matched = combine_required(
            states.get((surface, format, check))
            for surface, format in _CONTEXTS
            for check in ids
        )
        result.append(
            {
                "unit_id": _text(oracles["stage"]) + ":" + anchor,
                "correspondence": False
                if matched is True and row["source_declaration"] is None
                else matched,
                "declaration_state": row["declaration_state"],
            }
        )
    return result


def regrade_runtime(output: Path, oracles: Mapping[str, object]) -> RuntimeObservation:
    """Recompute facts, parity, invalidation and frozen frame metrics from bytes."""
    capture = _object(
        json.loads(confined_file(output, "runtime/capture.json").read_bytes())
    )
    if canonical_sha256(capture) != oracles.get("runtime_capture_sha256"):
        raise ValueError(
            "runtime retained capture differs from its admitted source oracle"
        )
    if not _oracle_frames(oracles):
        return {
            "gates": {},
            "gate_witnesses": [],
            "debug_frame_observations": [],
            "control": "no supplied repository frames; no correspondence proof",
        }
    context = _context(oracles)
    for variant in ("qualified", "invalidated"):
        request = json.loads(
            confined_file(output, f"runtime/{variant}/request.json").read_bytes()
        )
        expected = runtime_correlation_request(
            capture, _text(oracles["bundle_id"]), invalidated=variant == "invalidated"
        )
        if not _json_equal(request, expected):
            raise ValueError(
                "runtime retained request differs from the admitted external claims"
            )
    qualified, positive = _variant(output, oracles, context, invalidated=False)
    invalidated, adversarial = _variant(output, oracles, context, invalidated=True)
    gates = {
        field: combine_required(
            [_reduce(qualified, field), _reduce(invalidated, field)]
        )
        for field in ("facts", "authority", "revision")
    }
    gates["freshness"] = _reduce(invalidated, "revision")
    for surface in ("cli", "mcp"):
        gates[surface] = combine_required(
            [
                _reduce(rows, field, surface)
                for rows in (qualified, invalidated)
                for field in ("facts", "parity")
            ]
        )
    return {
        "gates": gates,
        "gate_witnesses": [*positive, *adversarial],
        "debug_frame_observations": _frames(oracles, positive),
    }


def observe_runtime(
    workspace: Path,
    state: Path,
    inputs: Mapping[str, object],
    oracles: Mapping[str, object],
    output: Path,
    transports: tuple[str, ...],
) -> RuntimeObservation:
    """Supply external claims through API/CLI/official MCP, never through an oracle."""
    capture = _object(inputs["capture"])
    write_json(output / "runtime/capture.json", capture)
    if not _oracle_frames(oracles):
        return regrade_runtime(output, oracles)
    for variant in ("qualified", "invalidated"):
        request = runtime_correlation_request(
            capture, _text(inputs["bundle_id"]), invalidated=variant == "invalidated"
        )
        destination = output / "runtime" / variant
        write_json(destination / "request.json", request)
        with CodeMap(workspace, state_dir=state) as codemap:
            packet = codemap.correlation.observe(**request)
        write_json(destination / "api.json", packet)
        case: dict[str, object] = {"operation": "correlate_evidence", "inputs": request}
        for surface, observe in (("cli", capture_cli), ("mcp", capture_mcp)):
            rows = observe(workspace, state, case) if surface in transports else []
            write_json(destination / f"{surface}.json", rows)
    return regrade_runtime(output, oracles)
