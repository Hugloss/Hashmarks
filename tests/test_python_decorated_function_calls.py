from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks import CodeMap


@pytest.mark.parametrize("prefix", ["", "async "])
def test_decorated_function_keeps_its_declaration_without_an_exact_caller(
    tmp_path: Path, prefix: str
) -> None:
    service = tmp_path / "service.py"
    source = (
        "def replacement(): return 1\n"
        "def decorate(function): return replacement\n"
        "@decorate\n"
        f"{prefix}def step(): return 2\n"
        "def direct(): return step()\n"
        "def plain(): return 3\n"
        "class Record: pass\n"
    )
    service.write_text(source)
    (tmp_path / "facade.py").write_text("from service import step as exposed\n")
    (tmp_path / "consumer.py").write_text(
        "from facade import exposed as selected\n"
        "from service import plain, Record\n"
        "import facade as api\n"
        "def run(): return selected(), api.exposed(), plain(), Record()\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_service.py").write_text(
        "from service import step as use\ndef test_behavior(): assert use() == 1\n"
    )
    target = "service.py::step"
    with CodeMap(tmp_path) as codemap:
        for decorated in (True, False):
            if not decorated:
                service.write_text(source.replace("@decorate\n", ""))
            direct = codemap.structure.locality("service.py::direct", max_depth=1)
            imported = codemap.structure.locality("consumer.py::run", max_depth=1)
            expected = None if decorated else target
            assert assert_records(direct["edges"])[0]["resolved_symbol_id"] == expected
            assert {
                row["target_text"]: row["resolved_symbol_id"]
                for row in assert_records(imported["edges"])
            } == {
                "selected": expected,
                "api.exposed": expected,
                "plain": "service.py::plain",
                "Record": "service.py::Record",
            }
            if decorated:
                uncertain = [
                    *assert_records(direct["unresolved_calls"]),
                    *assert_records(imported["unresolved_calls"]),
                ]
                assert len(uncertain) == 3
                assert all(row["candidate_symbol_ids"] == [target] for row in uncertain)
            reverse = codemap.structure.locality(target, max_depth=0)
            callers = assert_records(
                assert_records(reverse["nodes"])[0]["exact_callers"]
            )
            assert {row["source"] for row in callers} == (
                set() if decorated else {"direct", "run", "test_behavior"}
            )
            replacement = codemap.structure.locality(
                "service.py::replacement", max_depth=0
            )
            assert assert_records(replacement["nodes"])[0]["exact_callers"] == []
            assert (
                codemap.source.read(target)["content"]
                == f"{prefix}def step(): return 2"
            )
            verification = codemap.verification.changed_set(["service.py"])
            assert {row["path"] for row in assert_records(verification["targets"])} == {
                "tests/test_service.py"
            }


def test_outline_only_export_does_not_become_an_exact_call(tmp_path: Path) -> None:
    (tmp_path / ".hashmarks-context.toml").write_text(
        "[[rule]]\npattern='private.py'\nvisibility='outline'\n"
    )
    (tmp_path / "private.py").write_text(
        "def decorate(fn): return fn\n@decorate\ndef step(): return 2\n"
    )
    (tmp_path / "client.py").write_text(
        "from private import step as selected\ndef run(): return selected()\n"
    )
    with CodeMap(tmp_path) as codemap:
        forward = codemap.structure.locality("client.py::run", max_depth=1)
        reverse = codemap.structure.locality("private.py::step", max_depth=0)
    assert assert_records(forward["edges"])[0]["resolved_symbol_id"] is None
    assert assert_records(reverse["nodes"])[0]["exact_callers"] == []
