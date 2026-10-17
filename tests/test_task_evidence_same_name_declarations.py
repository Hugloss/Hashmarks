"""Same-name declarations are source alternatives, never dispatch or ownership proof."""

import json
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
)
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS, presentation_response

_TASK = "Inspect RecordCompiler.aggregate_records in backend.py"


def _repository(root: Path) -> Path:
    source = root / "backend.py"
    source.write_text(
        "class RecordCompiler:\n"
        "    def aggregate_records(self, records, *, function_name):\n"
        "        return records\n"
        "class StringCompiler:\n"
        "    def aggregate_records(self, records):\n"
        "        return records\n"
    )
    (root / "other.py").write_text("def aggregate_records(records): return records\n")
    return source


def _results(packet: object) -> list[dict[str, object]]:
    value = assert_object(packet)
    if "encoding" in value:
        value = decode_initial_packet(value)
    return assert_records(assert_object(value["retrieval"])["results"])


def _context(packet: object) -> dict[str, object]:
    row = next(
        row
        for row in _results(packet)
        if row.get("symbol") == "RecordCompiler.aggregate_records"
    )
    context = dict(assert_object(row["same_name_declarations"]))
    if "declarations_encoding" in context:
        encoding = assert_object(context.pop("declarations_encoding"))
        context["declarations"] = decode_initial_collection(
            context["declarations"], encoding
        )
    return context


def test_same_name_context_preserves_source_and_unknown_runtime_in_every_format(
    tmp_path: Path,
) -> None:
    source = _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(_TASK)
        packets = [
            codemap.task_evidence(_TASK),
            codemap.task_evidence(_TASK, result_mode="initial"),
        ]
    expected = [
        {
            "path": "backend.py",
            "symbol": "StringCompiler.aggregate_records",
            "start_line": 5,
            "end_line": 6,
        }
    ]
    for packet, mode in zip(packets, ("default", "initial"), strict=True):
        context = _context(packet)
        assert context["declarations"] == expected
        assert context["scope"] == "same-file-same-name-declarations"
        assert context["source_revision"] == hash_file(source, domain=FILE_DOMAIN).hash
        assert context["authority"] == "indexed-lexical-declarations-only"
        assert context["ownership_authority"] is False
        assert context["runtime_members"] == "not-established"
        assert context["negative_evidence_admissible"] is False
        decoded = assert_object(
            decode_initial_packet(packet) if mode == "initial" else packet
        )
        owner = assert_object(assert_object(decoded["ownership"])["owner"])
        admitted = assert_object(action["admitted_edit"])
        for field in (
            "path",
            "qualname",
            "start_line",
            "end_line",
            "roles",
            "evidence_visibility",
        ):
            assert owner.get(field) == admitted.get(field)
        assert assert_object(decoded["verification"])["selected"] == action["verify"]
        for format in FORMATS:
            response = presentation_response(
                "task_evidence", packet, format=format, result_mode=mode
            )
            native = response.get("result", response)
            assert _context(native) == context
            if format != "none":
                visible = json.dumps(response["presentation"])
                assert "StringCompiler" in visible
                assert "aggregate_records" in visible
                assert "same-file-same-name-declarations" in visible


def test_same_name_context_accounts_for_bounded_alternatives(tmp_path: Path) -> None:
    source = _repository(tmp_path)
    source.write_text(
        source.read_text()
        + "".join(
            f"class Other{i}:\n    def aggregate_records(self, records): return records\n"
            for i in range(6)
        )
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence(_TASK)
    context = _context(packet)
    assert (
        context["observed"],
        context["returned"],
        context["omitted"],
        context["bound"],
    ) == (7, 4, 3, 4)
    assert len(assert_array(context["declarations"])) == 4
    assert context["negative_evidence_admissible"] is False
    assert context["runtime_members"] == "not-established"


@pytest.mark.parametrize("invalidity", ["hidden", "changed", "deleted"])
def test_stale_or_denied_source_cannot_supply_same_name_declarations(
    tmp_path: Path, invalidity: str
) -> None:
    source = _repository(tmp_path)
    if invalidity == "hidden":
        (tmp_path / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "backend.py"\nvisibility = "deny"\n'
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.task_evidence(_TASK)
        if invalidity == "changed":
            source.write_text(
                "class RecordCompiler:\n    def aggregate_records(self, records): return records\n"
            )
        elif invalidity == "deleted":
            source.unlink()
        packet = codemap.task_evidence(_TASK)
    assert not any("same_name_declarations" in row for row in _results(packet))
