"""Nested retrieval keeps exact lexical containers without resolving an owner."""

from pathlib import Path
from typing import Any, cast

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import decode_initial_packet
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import presentation_response


def test_nested_helper_discloses_source_bound_enclosing_method_in_initial_and_full(
    tmp_path: Path,
) -> None:
    path = tmp_path / "backend.py"
    path.write_text(
        "class Worker:\n    def drain(self):\n        def nested_cleanup_marker():\n            return 1\n        return nested_cleanup_marker()\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        full = cast(
            "dict[str, Any]", codemap.task_evidence("Inspect nested_cleanup_marker")
        )
        wire = codemap.task_evidence(
            "Inspect nested_cleanup_marker", result_mode="initial"
        )
        initial = decode_initial_packet(wire)
    for packet in (full, initial):
        row = next(
            row
            for row in packet["retrieval"]["results"]
            if row.get("symbol") == "Worker.drain.nested_cleanup_marker"
        )
        context = row["enclosing_declarations"]
        assert context["declarations"] == [
            {
                "path": "backend.py",
                "symbol": "Worker.drain",
                "start_line": 2,
                "end_line": 5,
            }
        ]
        assert context["source_revision"] == hash_file(path, domain=FILE_DOMAIN).hash
        assert context["ownership_authority"] is False
        assert context["runtime_members"] == "not-established"
        assert context["negative_evidence_admissible"] is False
    response = cast(
        "dict[str, Any]",
        presentation_response(
            "task_evidence", wire, format="text", result_mode="initial"
        ),
    )
    text = response["presentation"]["text"]
    assert 'Common={"path":"backend.py"}' in text
    assert 'prefix="Worker."' in text
    assert '["drain",2,5]' in text


def test_deep_nesting_is_bounded_and_does_not_establish_absence(tmp_path: Path) -> None:
    lines = []
    for level in range(6):
        lines.append("    " * level + f"def level_{level}():")
    lines.append("    " * 6 + "return 1")
    (tmp_path / "backend.py").write_text("\n".join(lines) + "\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = cast("dict[str, Any]", codemap.task_evidence("Inspect level_5"))
    rows = [
        row["enclosing_declarations"]
        for row in packet["retrieval"]["results"]
        if "enclosing_declarations" in row
    ]
    assert rows
    assert all(len(row["declarations"]) <= 4 for row in rows)
    assert any(row["truncated"] is True for row in rows)
    assert all(row["negative_evidence_admissible"] is False for row in rows)
