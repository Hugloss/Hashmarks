from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap


def test_function_local_module_calls_use_the_import_in_the_caller(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "service.py").write_text("def build(): return {}\n")
    (tmp_path / "other.py").write_text("def build(): return {}\n")
    (tmp_path / "worker.py").write_text(
        "import other as svc\n"
        "def outside(): return svc.build()\n"
        "def local():\n    import pkg.service as svc\n    return svc.build()\n"
        "async def dotted():\n    import pkg.service\n    return pkg.service.build()\n"
        "def header():\n    import pkg.service as svc\n"
        "    def inner(value=svc.build()): return value\n    return inner\n"
        "def target(items):\n    import pkg.service as svc\n"
        "    return [None for svc.build()[0] in items]\n"
    )
    with CodeMap(tmp_path) as codemap:
        for caller in ("local", "dotted", "header", "target", "outside"):
            expected = (
                "other.py::build" if caller == "outside" else "pkg/service.py::build"
            )
            packet = codemap.structure.locality(f"worker.py::{caller}", max_depth=1)
            assert [
                row["resolved_symbol_id"] for row in assert_records(packet["edges"])
            ] == [expected]
        for path, callers in (
            ("pkg/service.py", {"local", "dotted", "header", "target"}),
            ("other.py", {"outside"}),
        ):
            reverse = codemap.structure.locality(f"{path}::build", max_depth=0)
            node = assert_records(reverse["nodes"])[0]
            assert {
                row["source"] for row in assert_records(node["exact_callers"])
            } == callers


@pytest.mark.parametrize(
    "body",
    [
        "    result = svc.build()\n    import service as svc\n    return result\n",
        "    import service as svc; return svc.build()\n",
        "    if values: import service as svc\n    return svc.build()\n",
        "    import service as svc\n    svc = values[0]\n    return svc.build()\n",
        "    import service as svc\n    patch = svc\n    patch.build = values[0]\n    return svc.build()\n",
        "    import service as svc\n    return [None for svc in values for svc.build()[0] in values]\n",
        "    import service as svc\n    return (lambda svc: svc.build())\n",
    ],
)
def test_local_module_import_requires_an_unshadowed_preceding_binding(
    tmp_path: Path, body: str
) -> None:
    (tmp_path / "service.py").write_text("def build(): return {}\n")
    (tmp_path / "other.py").write_text("def build(): return {}\n")
    (tmp_path / "worker.py").write_text(
        "import other as svc\ndef local(values):\n" + body
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("worker.py::local")
        assert [
            row["resolved_symbol_id"]
            for row in assert_records(packet["edges"])
            if row["target_text"] == "svc.build"
        ] == [None]
        for path in ("other.py", "service.py"):
            reverse = codemap.structure.locality(f"{path}::build", max_depth=0)
            assert assert_records(reverse["nodes"])[0]["exact_callers"] == []


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


@pytest.mark.parametrize(
    ("imports", "patch_source", "receiver", "write"),
    [
        ("import pkg.service as svc", "svc", "svc", "patch.build = replacement"),
        ("import pkg.service", "pkg.service", "pkg.service", "del patch.build"),
        (
            "import pkg.service as svc\nimport pkg.service",
            "pkg.service",
            "svc",
            "setattr(patch, 'build', replacement)",
        ),
        (
            "import pkg.service\nfrom pkg import service",
            "service",
            "pkg.service",
            "patch.build = replacement",
        ),
    ],
)
def test_module_write_through_assignment_alias_qualifies_only_affected_call(
    tmp_path: Path, imports: str, patch_source: str, receiver: str, write: str
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "service.py").write_text("def build(): return 1\ndef keep(): return 2\n")
    worker = tmp_path / "worker.py"
    source = (
        f"{imports}\ndef replacement(): return 3\npatch = {patch_source}\n"
        f"{write}\ndef run(): return {receiver}.build(), {receiver}.keep()\n"
    )
    worker.write_text(source)
    with CodeMap(tmp_path) as codemap:
        for changed in (True, False):
            if not changed:
                # A parameter with the same spelling is a separate binding.
                worker.write_text(source.replace(write, f"def other(patch): {write}"))
            forward = codemap.structure.locality("worker.py::run")
            assert {
                row["target_text"]: row["resolved_symbol_id"]
                for row in assert_records(forward["edges"])
            } == {
                f"{receiver}.build": None if changed else "pkg/service.py::build",
                f"{receiver}.keep": "pkg/service.py::keep",
            }
            for target, callers in (
                ("pkg/service.py::build", [] if changed else ["run"]),
                ("pkg/service.py::keep", ["run"]),
                ("worker.py::replacement", []),
            ):
                reverse = codemap.structure.locality(target, max_depth=0)
                node = assert_records(reverse["nodes"])[0]
                assert [
                    row["source"] for row in assert_records(node["exact_callers"])
                ] == callers


@pytest.mark.parametrize(
    ("caller", "relative_import", "affected"),
    [
        ("pkg/worker.py", "from . import service", True),
        ("pkg/inner/worker.py", "from .. import service", True),
        ("pkg/inner/__init__.py", "from .. import service", True),
        ("other/worker.py", "from . import service", False),
        ("pkg/inner/worker.py", "from . import service", False),
    ],
)
def test_relative_alias_write_uses_its_own_indexed_package(
    tmp_path: Path, caller: str, relative_import: str, affected: bool
) -> None:
    for dirname in ("pkg", "pkg/inner", "other"):
        package = tmp_path / dirname
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "service.py").write_text(
            "def build(): return 1\ndef keep(): return 2\n"
        )
    (tmp_path / caller).write_text(
        f"import pkg.service as svc\n{relative_import} as patch\n"
        "def replacement(): return 3\npatch.build = replacement\n"
        "def run(): return svc.build(), svc.keep()\n"
    )
    with CodeMap(tmp_path) as codemap:
        forward = codemap.structure.locality(f"{caller}::run")
        assert {
            row["target_text"]: row["resolved_symbol_id"]
            for row in assert_records(forward["edges"])
        } == {
            "svc.build": None if affected else "pkg/service.py::build",
            "svc.keep": "pkg/service.py::keep",
        }
        for target, expected in (
            ("pkg/service.py::build", [] if affected else [caller]),
            ("pkg/service.py::keep", [caller]),
            ("other/service.py::build", []),
        ):
            packet = codemap.structure.locality(target, max_depth=0)
            node = assert_records(packet["nodes"])[0]
            assert [
                row["path"] for row in assert_records(node["exact_callers"])
            ] == expected
