"""Source-position retrieval finds opaque callable names without owner authority."""

import json
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import decode_initial_packet
from hashmarks.evidence_presentation import FORMATS, presentation_response


def _repository(root: Path) -> Path:
    source = root / "builder.py"
    source.write_text(
        "".join(f"def helper_{i}(): return {i}\n" for i in range(80))
        + "class Builder:\n"
        "    def _prepare(self, value):\n"
        "        warn('attribute is reserved by the mapper')\n"
        "        return value\n"
    )
    (root / "events.py").write_text(
        "def instance_construction_warning(): pass\n"
        "def reserved_attribute_events(): pass\n"
    )
    return source


def test_diagnostic_words_retrieve_their_enclosing_callable(tmp_path: Path) -> None:
    _repository(tmp_path)
    task = "A reserved attribute causes a warning during instance construction."
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.task_action_map(task)
        packets = [
            codemap.task_evidence(task),
            decode_initial_packet(codemap.task_evidence(task, result_mode="initial")),
        ]
    for packet in packets:
        rows = assert_records(assert_object(packet["retrieval"])["results"])
        assert any(
            row.get("path") == "builder.py"
            and row.get("symbol") == "Builder._prepare"
            and (row.get("start_line"), row.get("end_line")) == (82, 84)
            for row in rows[:3]
        )
        assert assert_object(packet["ownership"])["owner"] == action["admitted_edit"]
        assert assert_object(packet["verification"])["selected"] == action["verify"]


@pytest.mark.parametrize("invalidity", ["deny", "outline", "changed", "deleted"])
def test_lexical_disclosure_requires_current_source_visibility(
    tmp_path: Path, invalidity: str
) -> None:
    source = _repository(tmp_path)
    if invalidity in {"deny", "outline"}:
        (tmp_path / ".hashmarks-context.toml").write_text(
            f'[[rule]]\npattern = "builder.py"\nvisibility = "{invalidity}"\n'
        )
    task = "A reserved attribute causes a warning during instance construction."
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        if invalidity == "changed":
            source.write_text("def replacement(): return None\n")
        elif invalidity == "deleted":
            source.unlink()
        packet = codemap.task_evidence(task)
    rows = assert_records(assert_object(packet["retrieval"])["results"])
    assert not any(
        row.get("path") == "builder.py"
        and row.get("supplement") == "bounded-lexical-source-position"
        for row in rows
    )


def test_lexical_lookup_uses_closest_callable_and_ignores_signature_only_matches(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text(
        "def outer():\n"
        "    def inner():\n"
        "        raise ValueError('reserved attribute')\n"
        "    return inner\n"
        "def reserved_attribute():\n"
        "    return None\n"
        "def split_tokens():\n"
        "    reserved = True\n"
        "    attribute = True\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        rows = codemap.store.lexical_declaration_candidates(
            [("reserved", "attribute")], ["reserved", "attribute"]
        )
    assert [(r["qualname"], r["match_line"]) for r in rows] == [("outer.inner", 3)]


def test_denied_declarations_cannot_exhaust_the_lookup_bound(tmp_path: Path) -> None:
    (tmp_path / "a_hidden.py").write_text(
        "".join(
            f"def hidden_{i}():\n    return 'reserved attribute'\n" for i in range(40)
        )
    )
    (tmp_path / "z_visible.py").write_text(
        "def visible():\n    return 'reserved attribute'\n"
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "a_hidden.py"\nvisibility = "deny"\n'
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        rows = codemap.store.lexical_declaration_candidates(
            [("reserved", "attribute")], ["reserved", "attribute"], limit=1
        )
    assert [(r["path"], r["qualname"]) for r in rows] == [("z_visible.py", "visible")]


def test_lexical_hint_keeps_literal_precedence_and_survives_every_format(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    task = "A reserved attribute causes a warning during instance construction."
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        for mode in ("default", "initial"):
            packet = codemap.task_evidence(task, result_mode=mode)
            for format in FORMATS:
                response = presentation_response(
                    "task_evidence", packet, format=format, result_mode=mode
                )
                if format != "none":
                    visible = json.dumps(response["presentation"])
                    assert "Builder._prepare" in visible
                    assert "bounded-lexical-source-position" in visible
        explicit = codemap.task_evidence(
            task + " Inspect events.py::reserved_attribute_events."
        )
    rows = assert_records(assert_object(explicit["retrieval"])["results"])
    assert rows[0]["path"] == "events.py"
    assert rows[0]["symbol"] == "reserved_attribute_events"


@pytest.mark.parametrize("limit", [-1, 0, 33, True])
def test_lexical_query_rejects_unbounded_or_noninteger_limits(
    tmp_path: Path, limit: int
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with pytest.raises(ValueError, match="limit"):
            codemap.store.lexical_declaration_candidates(
                [("reserved", "attribute")], ["reserved", "attribute"], limit=limit
            )
