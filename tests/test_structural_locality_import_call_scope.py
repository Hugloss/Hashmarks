"""Import identity uses the exact callable scope and preserves real shadowing."""

from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap


def _write_factory(root: Path) -> None:
    (root / "factory.py").write_text(
        "class Envelope:\n    @classmethod\n"
        "    def from_cmd(cls):\n        return cls()\n"
    )
    (root / "other.py").write_text(
        "class Envelope:\n    @classmethod\n"
        "    def from_cmd(cls):\n        return cls()\n"
    )


@pytest.mark.parametrize("other_scope", ["method", "nested"])
def test_unrelated_local_binding_cannot_hide_a_qualified_import_call(
    tmp_path: Path, other_scope: str
) -> None:
    _write_factory(tmp_path)
    if other_scope == "method":
        source = (
            "from factory import Envelope\n"
            "class Other:\n    def publish(self, Envelope):\n"
            "        return Envelope.from_cmd()\n"
            "class Publisher:\n    def publish(self):\n"
            "        return Envelope.from_cmd()\n"
        )
    else:
        source = (
            "from factory import Envelope\n"
            "class Publisher:\n    def publish(self):\n"
            "        def callback():\n            Envelope = object()\n"
            "        return Envelope.from_cmd()\n"
        )
    (tmp_path / "consumer.py").write_text(source)
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::Publisher.publish")
    calls = [
        row
        for row in assert_records(packet["edges"])
        if row["source_symbol_id"] == "consumer.py::Publisher.publish"
        and row["target_text"] == "Envelope.from_cmd"
    ]
    assert len(calls) == 1
    assert calls[0]["resolved_symbol_id"] == "factory.py::Envelope.from_cmd"


@pytest.mark.parametrize(
    "binding", ["argument", "assignment", "function", "class", "closure"]
)
def test_actual_lexical_shadowing_cannot_gain_import_authority(
    tmp_path: Path, binding: str
) -> None:
    _write_factory(tmp_path)
    if binding == "closure":
        text = (
            "from factory import Envelope\n"
            "def outer(Envelope):\n    def publish():\n"
            "        return Envelope.from_cmd()\n    return publish\n"
        )
        target = "consumer.py::outer.publish"
    else:
        local = {
            "argument": "",
            "assignment": "    Envelope = object()\n",
            "function": "    def Envelope(): pass\n",
            "class": "    class Envelope: pass\n",
        }[binding]
        argument = "Envelope" if binding == "argument" else ""
        text = (
            "from factory import Envelope\n"
            + f"def publish({argument}):\n"
            + local
            + "    return Envelope.from_cmd()\n"
        )
        target = "consumer.py::publish"
    (tmp_path / "consumer.py").write_text(text)
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality(target)
    calls = [
        row
        for row in assert_records(packet["edges"])
        if row["source_symbol_id"] == target
        and row["target_text"] == "Envelope.from_cmd"
    ]
    assert len(calls) == 1
    assert calls[0]["resolved_symbol_id"] is None


def test_duplicate_declarations_in_the_same_scope_stay_unresolved(
    tmp_path: Path,
) -> None:
    _write_factory(tmp_path)
    (tmp_path / "consumer.py").write_text(
        "from factory import Envelope\n"
        "def publish():\n    return Envelope.from_cmd()\n"
        "def publish(Envelope):\n    return Envelope.from_cmd()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::publish")
    assert all(
        row["resolved_symbol_id"] is None for row in assert_records(packet["edges"])
    )
