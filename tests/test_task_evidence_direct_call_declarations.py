"""Qualified source call positions do not grant transitive or runtime authority."""

import json
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import decode_initial_packet
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS, presentation_response

_TASK = "A reserved attribute causes a warning."


def _repository(root: Path, *, shadow: bool = False) -> Path:
    path = root / "backend.py"
    path.write_text(
        "def _third(value): return value\n"
        "def _local(value): return _third(value)\n"
        f"def _prepare({'_local, ' if shadow else ''}value):\n"
        "    warn('attribute is reserved')\n"
        "    def nested(): return _third(value)\n"
        "    return _local(value)\n"
    )
    (root / "other.py").write_text("def _local(value): return value\n")
    return path


def _context(packet: object) -> dict[str, object]:
    value = assert_object(packet)
    if "encoding" in value:
        value = decode_initial_packet(value)
    rows = assert_records(assert_object(value["retrieval"])["results"])
    row = next(row for row in rows if row.get("symbol") == "_prepare")
    return assert_object(row["direct_call_declarations"])


def test_direct_source_call_keeps_exact_target_and_unknown_runtime_across_formats(
    tmp_path: Path,
) -> None:
    source = _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packets = [
            codemap.task_evidence(_TASK),
            codemap.task_evidence(_TASK, result_mode="initial"),
        ]
    for packet, mode in zip(packets, ("default", "initial"), strict=True):
        context = _context(packet)
        declarations: object = context["declarations"]
        if "declarations_encoding" in context:
            from hashmarks.codemap.task_evidence_initial import (
                decode_initial_collection,
            )

            declarations = decode_initial_collection(
                declarations, assert_object(context["declarations_encoding"])
            )
        assert assert_records(declarations) == [
            {
                "path": "backend.py",
                "symbol": "_local",
                "start_line": 2,
                "end_line": 2,
                "call_line": 6,
            }
        ]
        assert context["source_revision"] == hash_file(source, domain=FILE_DOMAIN).hash
        assert context["scope"] == "same-file-direct-call-target-declarations"
        assert context["authority"] == "indexed-qualified-local-call-declarations-only"
        assert context["ownership_authority"] is False
        assert context["runtime_members"] == "not-established"
        assert context["negative_evidence_admissible"] is False
        assert context["observed_calls"] == 2
        assert context["unresolved_or_other_scope_calls"] == 1
        for format in FORMATS:
            response = presentation_response(
                "task_evidence", packet, format=format, result_mode=mode
            )
            if format != "none":
                visible = json.dumps(response["presentation"])
                assert "_local" in visible
                assert "same-file-direct-call-target-declarations" in visible
                assert "not-established" in visible
            if format == "compact" and mode == "initial":
                projection = assert_object(response["presentation"])
                groups = assert_records(projection["groups"])
                group = next(
                    group for group in groups if group["family"] == "retrieval_evidence"
                )
                assert "finding source_ref + /family" in str(group["declaration_table"])
                findings = assert_records(group["findings"])
                finding = next(
                    f
                    for f in findings
                    if "direct_call_declarations" in assert_object(f["details"])
                )
                details = assert_object(finding["details"])
                table = details["direct_call_declarations"]
                assert isinstance(table, str)
                assert '"_local"' in table
                assert '"call_line"' in table
                shared = assert_object(group["declaration_qualifiers"])
                assert shared["source_revision"] == context["source_revision"]


def test_shadowed_call_name_does_not_admit_same_named_declaration(
    tmp_path: Path,
) -> None:
    _repository(tmp_path, shadow=True)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence(_TASK)
    rows = assert_records(assert_object(packet["retrieval"])["results"])
    assert not any("direct_call_declarations" in row for row in rows)


def test_direct_call_bound_accounts_for_unreturned_targets(tmp_path: Path) -> None:
    (tmp_path / "backend.py").write_text(
        "".join(f"def local_{i}(): return {i}\n" for i in range(6))
        + "def _prepare():\n"
        "    warn('reserved attribute')\n"
        + "".join(f"    local_{i}()\n" for i in range(6))
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
    ) == (6, 4, 2, 4)
    assert context["observed_calls"] == 7
    assert context["examined_calls"] == 7
    assert context["unexamined_calls"] == 0
    assert context["negative_evidence_admissible"] is False


@pytest.mark.parametrize("invalidity", ["deny", "changed", "deleted"])
def test_direct_calls_cannot_reuse_stale_or_hidden_source(
    tmp_path: Path, invalidity: str
) -> None:
    source = _repository(tmp_path)
    if invalidity == "deny":
        (tmp_path / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern="backend.py"\nvisibility="deny"\n'
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        if invalidity == "changed":
            source.write_text("def replacement(): return None\n")
        elif invalidity == "deleted":
            source.unlink()
        packet = codemap.task_evidence(_TASK)
    rows = assert_records(assert_object(packet["retrieval"])["results"])
    assert not any("direct_call_declarations" in row for row in rows)
