"""Independent recovery of source facts from the consumer's readable table."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
    encode_initial_packet,
    initial_packet_identity,
)
from hashmarks.evidence_presentation import presentation_response


def _read_table(table: dict[str, Any], shared: dict[str, Any]) -> dict[str, Any]:
    metadata = {**shared, **table["metadata"]}
    common, prefix, columns, extras = (
        table[key] for key in ("common", "prefix", "columns", "extras")
    )
    declarations = []
    for row in table["rows"]:
        declaration = {**common, **dict(zip(columns, row[: len(columns)], strict=True))}
        if prefix:
            declaration["symbol"] = prefix + declaration["symbol"]
        if extras:
            assert len(row) == len(columns) + 1
            declaration.update(row[-1])
        declarations.append(declaration)
    return {**metadata, "declarations": declarations}


def test_compact_tables_recover_all_locators_qualifiers_and_future_fields(
    tmp_path: Path,
) -> None:
    (tmp_path / "répository.py").write_text(
        "class Worker:\n    def update(self):\n        return self.failed_update()\n    def failed_update(self):\n        return False\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        wire = cast(
            "dict[str, Any]",
            codemap.tasks.evidence(
                "Inspect Worker.update in répository.py", result_mode="initial"
            ),
        )
    logical = decode_initial_packet(wire)
    row = next(
        row for row in logical["retrieval"]["results"] if "class_declarations" in row
    )
    context = row["class_declarations"]
    context["declarations"] = decode_initial_collection(
        context["declarations"], context.pop("declarations_encoding")
    )
    context["declarations"][0]["future_fact"] = {
        "unknown": None,
        "false": False,
        "zero": 0.0,
    }
    context["future_qualification"] = False
    other = deepcopy(row)
    other["class_declarations"]["future_qualification"] = 0
    logical["retrieval"]["results"] = [row, other]
    logical["evidence_packet_identity"] = initial_packet_identity(logical)
    wire = encode_initial_packet(logical)
    before = deepcopy(wire)
    response = cast(
        "dict[str, Any]",
        presentation_response(
            "task_evidence", wire, result_mode="initial", format="compact"
        ),
    )
    group = next(
        group
        for group in response["presentation"]["groups"]
        if group["family"] == "retrieval_evidence"
    )
    for index, finding in enumerate(group["findings"]):
        rendered = finding["details"]["class_declarations"]
        assert finding["source_refs"][0] + "/class_declarations" == (
            f"/retrieval/results/{index}/class_declarations"
        )
        recovered = _read_table(rendered, group["declaration_qualifiers"])
        expected = logical["retrieval"]["results"][index]["class_declarations"]
        assert recovered == expected
        assert type(recovered["future_qualification"]) is type(
            expected["future_qualification"]
        )
    assert "future_qualification" not in group["declaration_qualifiers"]
    assert response["result"] == before == wire
