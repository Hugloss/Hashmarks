from pathlib import Path

from contract_assertions import assert_records

from hashmarks.codemap import CodeMap


def test_computed_receivers_cannot_prove_bare_callers(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(
        "def save(): return 1\n"
        "def factory(): return None\n"
        "def direct(): return save()\n"
        "def constructed(): return factory().save()\n"
        "def subscripted(items): return items[0].save()\n"
        "def nested(items): return items[0].writer.save()\n"
    )
    with CodeMap(tmp_path) as codemap:
        expected = {
            "constructed": {"factory": "worker.py::factory", "<expression>.save": None},
            "subscripted": {"<expression>.save": None},
            "nested": {"<expression>.writer.save": None},
        }
        for caller, targets in expected.items():
            packet = codemap.structure.locality(f"worker.py::{caller}")
            assert {
                row["target_text"]: row["resolved_symbol_id"]
                for row in assert_records(packet["edges"])
            } == targets
        reverse = codemap.structure.locality("worker.py::save", max_depth=0)
    callers = assert_records(assert_records(reverse["nodes"])[0]["exact_callers"])
    assert [row["source"] for row in callers] == ["direct"]


def test_module_calls_use_the_imported_module_and_qualified_member(
    tmp_path: Path,
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("")
    (tmp_path / "pkg/service.py").write_text("from impl import save as publish\n")
    (tmp_path / "impl.py").write_text("def save(): return 1\n")
    (tmp_path / "decoy.py").write_text("def publish(): return 0\n")
    (tmp_path / "consumer.py").write_text(
        "import impl\n"
        "import pkg.service\n"
        "import pkg.service as svc\n"
        "def direct(): return impl.save()\n"
        "def dotted(): return pkg.service.publish()\n"
        "def aliased(): return svc.publish()\n"
        "def shadowed(svc): return svc.publish()\n"
    )
    (tmp_path / "other.py").write_text(
        "import pkg\n"
        "import outside as ext\n"
        "def no_submodule_import(): return pkg.service.publish()\n"
        "def external(): return ext.publish()\n"
    )
    (tmp_path / "rebound.py").write_text(
        "import pkg.service as svc\n"
        "import pkg.service as replacement_target\n"
        "replacement_target.publish = lambda: 0\n"
        "def replaced(): return svc.publish()\n"
    )
    (tmp_path / "early.py").write_text(
        "svc = object()\nsvc.publish()\nimport pkg.service as svc\n"
    )
    (tmp_path / "hidden.py").write_text("from impl import save as publish\n")
    (tmp_path / ".hashmarks-context.toml").write_text(
        "[[rule]]\npattern='hidden.py'\nvisibility='outline'\n"
    )
    (tmp_path / "reader.py").write_text(
        "import hidden\ndef observe(): return hidden.publish()\n"
    )
    with CodeMap(tmp_path) as codemap:
        cases = {
            "consumer.py::direct": "impl.py::save",
            "consumer.py::dotted": "impl.py::save",
            "consumer.py::aliased": "impl.py::save",
            "consumer.py::shadowed": None,
            "other.py::no_submodule_import": None,
            "other.py::external": None,
            "rebound.py::replaced": None,
            "reader.py::observe": None,
        }
        for caller, target in cases.items():
            packet = codemap.structure.locality(caller, max_depth=1)
            assert [
                row["resolved_symbol_id"] for row in assert_records(packet["edges"])
            ] == [target]
        reverse = codemap.structure.locality("impl.py::save", max_depth=0)
    callers = assert_records(assert_records(reverse["nodes"])[0]["exact_callers"])
    assert {row["source"] for row in callers} == {"direct", "dotted", "aliased"}


def test_ambiguous_module_paths_cannot_establish_exact_caller(tmp_path: Path) -> None:
    (tmp_path / "service").mkdir()
    (tmp_path / "service/__init__.py").write_text("def save(): return 1\n")
    (tmp_path / "service.py").write_text("def save(): return 2\n")
    (tmp_path / "consumer.py").write_text(
        "import service as svc\ndef invoke(): return svc.save()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::invoke")
        unresolved = assert_records(packet["unresolved_calls"])
        assert [
            (row["target_text"], row["resolved_symbol_id"]) for row in unresolved
        ] == [("svc.save", None)]
        for path in ("service.py", "service/__init__.py"):
            reverse = codemap.structure.locality(f"{path}::save", max_depth=0)
            assert assert_records(reverse["nodes"])[0]["exact_callers"] == []
