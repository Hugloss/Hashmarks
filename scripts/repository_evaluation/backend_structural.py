"""Selected direct-call source facts in the existing backend revision ring.

These development observations qualify caller-nominated static segments and
explicit unknown targets. They do not establish a runtime execution path.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from hashmarks.codemap import CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_file

from .backend_corpus import _check_label, confined_file
from .backend_gates import combine_required, fact_state, presentation_conformance
from .backend_grading import component_summary, validate_transport_capture
from .backend_transport import capture_cli, capture_mcp
from .common import write_json
from .fact_grading import grade_facts


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("structural qualification requires a JSON object")
    return value


def _records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        raise ValueError("structural qualification requires nonempty records")
    return [_object(row) for row in value]


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("structural qualification requires a nonempty string")
    return value


def structural_source_paths(rule: Mapping[str, object]) -> list[str]:
    return sorted({_text(row.get("path")) for row in _records(rule["source_labels"])})


def validate_structural_stage(
    source: Path, request: object, oracle: object, source_id: str
) -> None:
    """Admit exact source labels separately from public observation inputs."""
    inputs, rule = _object(request), _object(oracle)
    labels = _records(rule.get("source_labels"))
    first = labels[0]
    expected = _text(first.get("path")) + "::" + _text(first.get("symbol"))
    if inputs != {"target": expected} or rule.get("source") != source_id:
        raise ValueError("structural request differs from its admitted source target")
    checks = _records(rule.get("checks"))
    identifiers = [_text(check.get("id")) for check in checks]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("structural checks require distinct IDs")
    display = _object(rule.get("display_checks"))
    if set(display) != {"structured", "compact", "text"}:
        raise ValueError("structural oracles require each display format")
    for checks in display.values():
        _records(checks)
    for label in labels:
        _check_label(source, label)


def _source_bound(
    workspace: Path, packet: Mapping[str, object], rule: Mapping[str, object]
) -> bool:
    nodes = _records(packet.get("nodes"))
    labels = _records(rule.get("source_labels"))
    target = _text(labels[0].get("path")) + "::" + _text(labels[0].get("symbol"))
    by_id = {_text(row.get("symbol_id")): row for row in nodes}
    return (
        packet.get("target_symbol_id") == target
        and _object(packet.get("freshness")).get("state") == "current"
        and len(by_id) == len(nodes)
        and all(
            row.get("file_digest")
            == hash_file(
                confined_file(workspace, _text(row.get("path"))), domain=FILE_DOMAIN
            ).hash
            for row in nodes
        )
        and all(
            (node := by_id.get(_text(label["path"]) + "::" + _text(label["symbol"])))
            is not None
            and node.get("path") == label["path"]
            and node.get("qualname") == label["symbol"]
            and node.get("lines")
            == [label.get("declaration_line", label["start_line"]), label["end_line"]]
            for label in labels
        )
    )


def grade_structural(
    workspace: Path,
    packet: dict[str, object],
    rule: dict[str, object],
    paths: list[str],
) -> dict[str, object]:
    facts = grade_facts("structural-source", {"packet": packet}, rule)
    return {
        "facts": fact_state(facts["classification"]),
        "authority": facts["authority_violations"] == 0,
        "revision": paths == structural_source_paths(rule)
        and _source_bound(workspace, packet, rule),
        "checks": facts["checks"],
    }


def observe_structural(
    workspace: Path,
    state: Path,
    inputs: dict[str, object],
    rule: dict[str, object],
    output: Path,
    transports: tuple[str, ...],
) -> dict[str, object]:
    """Use existing public APIs and capture owners; execution stays external."""
    with CodeMap(workspace, state_dir=state) as codemap:
        packet = codemap.structure.locality(_text(inputs["target"]))
    write_json(output / "api.json", packet)
    paths = structural_source_paths(rule)
    api = grade_structural(workspace, packet, rule, paths)
    results = {}
    case = {"operation": "structural_locality", "inputs": inputs}
    for name, capture in (("cli", capture_cli), ("mcp", capture_mcp)):
        captures = capture(workspace, state, case) if name in transports else []
        write_json(output / f"{name}.json", captures)
        grades = []
        for row in captures:
            grades.append(grade_structural_transport(workspace, row, rule))
        results[name] = grades
    return component_summary(api, results)


def grade_structural_transport(
    workspace: Path, capture: dict[str, object], rule: dict[str, object]
) -> dict[str, object]:
    """Recompute native and displayed facts identically on capture and replay."""
    validate_transport_capture(capture)
    response = _object(capture["response"])
    packet = _object(response.get("result", response))
    graded = grade_structural(workspace, packet, rule, structural_source_paths(rule))
    mode = _text(capture["format"])
    parity: bool | None = True
    if mode != "none":
        presentation = _object(response["presentation"])
        display = _object(rule["display_checks"])
        facts = grade_facts(
            "structural-display",
            {"packet": presentation},
            {"checks": _records(display[mode])},
        )
        parity = combine_required(
            [
                presentation_conformance(packet, presentation)["valid"] is True,
                fact_state(facts["classification"]),
            ]
        )
    return {"format": mode, **graded, "parity": parity}
