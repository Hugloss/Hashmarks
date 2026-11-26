from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap.providers import TreeSitterRangeProvider


def test_repeated_classes_keep_declared_members_with_their_actual_parent(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text(
        "class ChannelBackend:\n"
        "    def subscribe(self): return 'first'\n"
        "    def poll(self): return 1\n\n"
        "class ChannelBackend:\n"
        "    def publish(self): return 'second'\n"
        "    def poll(self): return 2\n"
    )
    with CodeMap(tmp_path) as cm:
        rows = assert_records(cm.source.outline("backend.py")["symbols"])
        assert {
            row["qualname"]: row["parent"] for row in rows if row["kind"] == "method"
        } == {
            "ChannelBackend.subscribe": "ChannelBackend",
            "ChannelBackend.poll": "ChannelBackend",
            "ChannelBackend.publish": "ChannelBackend@L5",
            "ChannelBackend.poll@L7": "ChannelBackend@L5",
        }
        candidates = cm.source.symbol("ChannelBackend.poll")
        assert [row["qualname"] for row in assert_records(candidates["matches"])] == [
            "ChannelBackend.poll",
            "ChannelBackend.poll@L7",
        ]
        assert cm.source.read("backend.py::ChannelBackend.poll@L7")["lines"] == [7, 7]
        assert cm.source.read("backend.py::ChannelBackend@L5.poll")["symbol_id"] == (
            "backend.py::ChannelBackend.poll@L7"
        )
        task = cm.tasks.evidence("Inspect ChannelBackend subscription behavior")
        retrieval = assert_object(task["retrieval"])
        classes = {
            row["symbol"]: [
                method["symbol"]
                for method in assert_records(
                    assert_object(row["class_declarations"])["declarations"]
                )
            ]
            for row in assert_records(retrieval["results"])
            if "class_declarations" in row
        }
        assert classes["ChannelBackend"] == [
            "ChannelBackend.subscribe",
            "ChannelBackend.poll",
        ]
        assert classes["ChannelBackend@L5"] == [
            "ChannelBackend.publish",
            "ChannelBackend.poll@L7",
        ]


def test_nested_call_and_enclosing_scope_agree_on_the_repeated_function(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text(
        "def factory(): return None\n"
        "def factory():\n"
        "    def build(): return 2\n"
        "    return build()\n"
    )
    with CodeMap(tmp_path) as cm:
        (build,) = assert_records(cm.source.symbol("factory.build")["matches"])
        assert build["parent"] == "factory@L2"
        assert cm.source.read(f"backend.py::{build['parent']}")["lines"] == [2, 4]
        outgoing = cm.structure.locality("backend.py::factory@L2", max_depth=1)
        assert [
            edge["resolved_symbol_id"] for edge in assert_records(outgoing["edges"])
        ] == ["backend.py::factory.build"]
        callers = cm.structure.locality("backend.py::factory.build", max_depth=0)
        (node,) = assert_records(callers["nodes"])
        assert [row["source"] for row in assert_records(node["exact_callers"])] == [
            "factory@L2"
        ]


def test_advisory_python_symbols_keep_parent_occurrences_and_native_parse_error(
    tmp_path: Path,
) -> None:
    provider = TreeSitterRangeProvider.auto()
    if provider.signature("python") is None:
        pytest.skip("Optional Python range provider unavailable")
    (tmp_path / "legacy.py").write_text(
        "print 'legacy'\nclass Backend:\n    def first(self): pass\n"
        "class Backend:\n    def second(self): pass\n"
    )
    with CodeMap(tmp_path, range_provider=provider) as cm:
        outline = cm.source.outline("legacy.py")
        assert outline["parse_error"]
        rows = assert_records(outline["symbols"])
        assert {row["qualname"]: row["parent"] for row in rows} == {
            "Backend": None,
            "Backend.first": "Backend",
            "Backend@L4": None,
            "Backend.second": "Backend@L4",
        }
