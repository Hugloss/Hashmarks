"""Call arguments remain bounded source syntax across public observations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import ChangeImpactOptions, CodeMap
from scripts.repository_evaluation.backend_transport import capture_cli, capture_mcp


def _request() -> dict[str, object]:
    return {
        "task": "Inspect source arguments",
        "changed_paths": ["service.py"],
        "changed_line_spans": [{"path": "service.py", "start_line": 2, "end_line": 2}],
        "max_depth": 1,
    }


def _observe(root: Path) -> dict[str, object]:
    with CodeMap(root, state_dir=root / "state") as codemap:
        codemap.index.sync()
        return dict(
            codemap.task_change_impact(
                "Inspect source arguments",
                ["service.py"],
                options=ChangeImpactOptions(
                    changed_line_spans=[
                        {"path": "service.py", "start_line": 2, "end_line": 2}
                    ]
                ),
            )
        )


def _call(packet: dict[str, object], callee: str) -> dict[str, object]:
    evidence = assert_object(packet.get("changed_line_evidence"))
    member = assert_records(evidence.get("observations"))[0]
    boundary = assert_object(member.get("function_boundary_syntax"))
    assert boundary["authority"] == "direct-static-syntax-only"
    assert boundary["negative_evidence_admissible"] is False
    assert boundary["callee_resolution"] == "not-established"
    function = assert_records(boundary.get("observations"))[0]
    return next(
        site
        for site in assert_records(function.get("sites"))
        if site.get("syntax_kind") == "call"
        and site.get("callee_identifier_syntax") == callee
    )


def test_boolean_arguments_and_expansions_are_syntax_without_runtime_binding(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        "async def process(message, batch, options):\n"
        "    await message.nack(*batch, multiple=False, requeue=True, **options)\n"
        "raise RuntimeError('source must never execute')\n"
    )
    call = _call(_observe(tmp_path), "message.nack")
    arguments = assert_object(call.get("argument_syntax"))
    assert call["has_argument_expansion"] is True
    assert arguments == {
        "positional": [
            {
                "position": 0,
                "expansion": True,
                "value": {"state": "identifier-syntax", "identifier": "batch"},
            }
        ],
        "keywords": [
            {
                "name": "multiple",
                "name_state": "literal",
                "expansion": False,
                "value": {"state": "literal-syntax", "kind": "bool", "value": False},
            },
            {
                "name": "requeue",
                "name_state": "literal",
                "expansion": False,
                "value": {"state": "literal-syntax", "kind": "bool", "value": True},
            },
            {
                "name": None,
                "name_state": "mapping-expansion",
                "expansion": True,
                "value": {"state": "identifier-syntax", "identifier": "options"},
            },
        ],
        "omitted_positional_count": 0,
        "omitted_keyword_count": 0,
        "truncation": "complete",
        "runtime_binding": "not-established",
    }


def test_literals_and_dynamic_expressions_are_not_evaluated(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        "def process():\n"
        "    message.send(None, 'topic', 17, 0.5, -1, flag is False, factory())\n"
    )
    arguments = assert_object(
        _call(_observe(tmp_path), "message.send").get("argument_syntax")
    )
    values = [row["value"] for row in assert_records(arguments.get("positional"))]
    assert values[:4] == [
        {"state": "literal-syntax", "kind": "none", "value": None},
        {"state": "literal-syntax", "kind": "string", "value": "topic"},
        {
            "state": "literal-syntax",
            "kind": "integer",
            "value": "17",
            "encoding": "decimal-text",
        },
        {"state": "literal-syntax", "kind": "float", "value": 0.5},
    ]
    assert values[4:] == [
        {"state": "expression-unestablished", "expression_kind": "UnaryOp"},
        {"state": "expression-unestablished", "expression_kind": "Compare"},
        {"state": "expression-unestablished", "expression_kind": "Call"},
    ]


def test_argument_bounds_account_for_omissions_and_hidden_expansion(
    tmp_path: Path,
) -> None:
    positional = ", ".join(str(index) for index in range(12))
    keywords = ", ".join(f"field_{index}=True" for index in range(12))
    (tmp_path / "service.py").write_text(
        f"def process():\n    message.send({positional}, {keywords}, **options)\n"
    )
    call = _call(_observe(tmp_path), "message.send")
    arguments = assert_object(call.get("argument_syntax"))
    assert len(assert_records(arguments.get("positional"))) == 8
    assert len(assert_records(arguments.get("keywords"))) == 8
    assert arguments["omitted_positional_count"] == 4
    assert arguments["omitted_keyword_count"] == 5
    assert arguments["truncation"] == "truncated"
    assert arguments["runtime_binding"] == "not-established"
    assert call["has_argument_expansion"] is True


def test_oversized_nonfinite_and_unsupported_literals_remain_unknown(
    tmp_path: Path,
) -> None:
    long_name = "name" * 70
    (tmp_path / "service.py").write_text(
        f"def process():\n    message.send({'x' * 129!r}, {2**300}, 1e400, b'data', {long_name}=True)\n"
    )
    packet = _observe(tmp_path)
    arguments = assert_object(_call(packet, "message.send").get("argument_syntax"))
    values = [row["value"] for row in assert_records(arguments.get("positional"))]
    assert values == [
        {"state": "literal-over-bound", "kind": "string"},
        {"state": "literal-over-bound", "kind": "integer"},
        {"state": "literal-over-bound", "kind": "float"},
        {"state": "unsupported-literal", "kind": "bytes"},
    ]
    keyword = assert_records(arguments.get("keywords"))[0]
    assert keyword["name"] is None
    assert keyword["name_state"] == "over-bound"
    assert keyword["expansion"] is False
    json.dumps(packet, allow_nan=False)


def test_integer_literal_preserves_precision_in_wire_safe_decimal_text(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        "def process():\n    message.send(9007199254740993)\n"
    )
    wire = json.dumps(_observe(tmp_path), allow_nan=False)
    packet = json.loads(wire)
    arguments = assert_object(_call(packet, "message.send").get("argument_syntax"))
    value = assert_records(arguments.get("positional"))[0]["value"]
    assert value == {
        "state": "literal-syntax",
        "kind": "integer",
        "value": "9007199254740993",
        "encoding": "decimal-text",
    }


@pytest.mark.parametrize(
    "transport", ["cli", pytest.param("mcp", marks=pytest.mark.host_mcp_sdk)]
)
def test_public_transports_preserve_literal_arguments_and_unknown_binding(
    tmp_path: Path, transport: str
) -> None:
    (tmp_path / "service.py").write_text(
        "async def process(consumer):\n"
        "    await invoke(consumer.commit, 9007199254740993, asynchronous=False)\n"
    )
    packet = _observe(tmp_path)
    expected = _call(packet, "invoke")
    capture = capture_cli if transport == "cli" else capture_mcp
    for row in capture(
        tmp_path,
        tmp_path / "state",
        {"operation": "change_impact", "inputs": _request()},
    ):
        response = row["response"]
        observed = response.get("result", response)
        assert _call(observed, "invoke") == expected
