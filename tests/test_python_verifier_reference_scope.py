"""Python verifier selection retains the lexical binding and enclosing test."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap.query_router import normalize_task_query
from hashmarks.codemap.verification_relevance_model import VerificationRequest


def _repository(root: Path, test: str) -> CodeMap:
    (root / "tests").mkdir()
    (root / "owner.py").write_text("def calculate_tax(): return 2\n")
    (root / "other.py").write_text("def calculate_tax(): return 3\n")
    (root / "tests/test_amounts.py").write_text(test)
    return CodeMap(root)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "def helper():\n    from owner import calculate_tax as len\n"
            "def test_amount(): assert len([1]) == 1\n",
            False,
        ),
        (
            "from owner import calculate_tax\n"
            "def identity(calculate_tax): return calculate_tax\n"
            "def test_amount(): assert calculate_tax() == 2\n",
            True,
        ),
        (
            "def helper():\n    from owner import calculate_tax as amount\n"
            "def test_amount():\n    from other import calculate_tax as amount\n"
            "    assert amount() == 3\n",
            False,
        ),
    ],
)
def test_changed_set_qualifies_each_python_use_in_its_own_scope(
    tmp_path: Path, source: str, expected: bool
) -> None:
    with _repository(tmp_path, source) as repository:
        repository.index.sync()
        changed = repository.verification.changed_set(["owner.py"])
    assert bool(changed["targets"]) is expected
    assert changed["negative_evidence_admissible"] is False


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "from owner import calculate_tax\n"
            "def test_calculate_tax(): assert True\n"
            "def test_charges(): assert calculate_tax() == 2\n",
            "test_charges",
        ),
        (
            "import owner as amounts\n"
            "def test_calculate_tax(): assert True\n"
            "async def test_charges(): assert amounts.calculate_tax() == 2\n",
            "test_charges",
        ),
        (
            "from owner import calculate_tax\n"
            "class TestProduct:\n    def test_calculate_tax(self): assert calculate_tax() == 2\n",
            None,
        ),
        (
            "from owner import calculate_tax\n"
            "def charged(): return calculate_tax()\n"
            "def test_calculate_tax(): assert charged() == 2\n",
            None,
        ),
        (
            "from owner import calculate_tax\n"
            "def test_charges(): assert calculate_tax() == 2\n"
            "def test_charges(): assert True\n",
            None,
        ),
    ],
)
def test_task_packet_narrows_to_a_source_witnessed_test_node(
    tmp_path: Path, source: str, expected: str | None
) -> None:
    with _repository(tmp_path, source) as repository:
        repository.index.sync()
        verify = repository.tasks.evidence("Change calculate_tax in owner.py")[
            "verification"
        ]
    selected = assert_object(verify["relevance"]["selected"])
    assert selected["direct_reference"] is True
    assert selected["test_symbol"] == expected
    assert assert_object(verify["selected"])["qualname"] == expected
    plan = assert_object(verify["plan"])
    assert plan["test_symbol"] == expected
    assert plan["scope"] == ("test-node" if expected else "test-file")


def test_method_reference_ignores_use_of_a_same_named_free_function(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        "from owner import calculate_tax, Amounts\n"
        "def test_calculate_tax(): assert calculate_tax() == 9\n"
        "def test_charges(): assert Amounts.calculate_tax(None) == 2\n",
    ) as repository:
        (tmp_path / "owner.py").write_text(
            "def calculate_tax(): return 9\n"
            "class Amounts:\n    def calculate_tax(self): return 2\n"
        )
        repository.index.sync()
        with repository.reads.session() as session:
            relevance = repository.verification.for_owner(
                VerificationRequest(
                    session,
                    normalize_task_query("calculate_tax"),
                    "nominated",
                    {
                        "path": "owner.py",
                        "name": "calculate_tax",
                        "qualname": "Amounts.calculate_tax",
                    },
                    None,
                    (),
                )
            )
    assert assert_object(relevance["selected"])["test_symbol"] == "test_charges"


@pytest.mark.parametrize(
    ("prefix", "guard", "body_has_use", "direct"),
    [
        (
            "from typing import TYPE_CHECKING as static_only\n",
            "static_only",
            True,
            False,
        ),
        ("import typing as hints\n", "not hints.TYPE_CHECKING", False, False),
        (
            "from typing import TYPE_CHECKING as static_only\n",
            "not static_only",
            True,
            True,
        ),
        ("TYPE_CHECKING = True\n", "TYPE_CHECKING", True, True),
        ("class Flags:\n    TYPE_CHECKING = True\n", "Flags.TYPE_CHECKING", True, True),
        (
            "import typing as hints\nhints.TYPE_CHECKING = True\n",
            "hints.TYPE_CHECKING",
            True,
            True,
        ),
        ("", "True", False, False),
    ],
)
def test_only_qualified_typing_guard_removes_a_test_reference(
    tmp_path: Path, prefix: str, guard: str, body_has_use: bool, direct: bool
) -> None:
    use = "assert calculate_tax() == 2"
    source = (
        "from owner import calculate_tax\n"
        + prefix
        + f"def test_amount():\n    if {guard}: {use if body_has_use else 'pass'}\n"
        f"    else: {'pass' if body_has_use else use}\n"
    )
    with _repository(tmp_path, source) as repository:
        repository.index.sync()
        evidence = repository.tasks.verification_relevance(
            "Change calculate_tax in owner.py"
        )
        changed = repository.verification.changed_set(["owner.py"])
    row = next(
        row for row in evidence["candidates"] if row["path"] == "tests/test_amounts.py"
    )
    assert row.get("direct_reference") is direct
    assert bool(changed["targets"]) is direct
    assert changed["negative_evidence_admissible"] is False


def test_shadowed_type_checking_parameter_preserves_sibling_test_identity(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        "from typing import TYPE_CHECKING\nfrom owner import calculate_tax\n"
        "def test_type_only():\n    if TYPE_CHECKING: assert calculate_tax() == 9\n"
        "def test_charges(TYPE_CHECKING):\n    if TYPE_CHECKING: assert calculate_tax() == 2\n",
    ) as repository:
        repository.index.sync()
        evidence = repository.tasks.verification_relevance(
            "Change calculate_tax in owner.py"
        )
    assert assert_object(evidence["selected"])["test_symbol"] == "test_charges"


def test_repository_typing_module_withdraws_external_guard_semantics(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        "from typing import TYPE_CHECKING as flag\nfrom owner import calculate_tax\n"
        "def test_charges():\n    if flag: assert calculate_tax() == 2\n",
    ) as repository:
        repository.index.sync()
        assert repository.verification.changed_set(["owner.py"])["targets"] == []
        local = tmp_path / "typing.py"
        local.write_text("TYPE_CHECKING = True\n")
        repository.index.sync()
        changed = repository.verification.changed_set(["owner.py"])
        local.unlink()
        repository.index.sync()
        assert repository.verification.changed_set(["owner.py"])["targets"] == []
    change = assert_records(changed["changes"])[0]
    relation = assert_records(change["relationships"])[0]
    assert relation["relation_kind"] == "direct-reference"
    assert "typing.py" in {
        row["path"] for row in assert_records(relation["supporting_source_members"])
    }
    assert changed["negative_evidence_admissible"] is False


def test_local_annotation_call_syntax_does_not_displace_a_real_verifier(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        "from owner import calculate_tax\n"
        "def test_calculate_tax():\n    preview: calculate_tax()\n    assert True\n"
        "def test_charges(): assert calculate_tax() == 2\n",
    ) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence("Change calculate_tax in owner.py")
    assert (
        assert_object(packet["verification"]["plan"])["test_symbol"] == "test_charges"
    )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("preview: calculate_tax()", False),
        ("preview: calculate_tax() = 2", False),
        ("preview: int = calculate_tax()", True),
        ("calculate_tax().value: int", True),
    ],
)
def test_verification_distinguishes_local_annotation_from_evaluated_expressions(
    tmp_path: Path, body: str, expected: bool
) -> None:
    with _repository(
        tmp_path,
        "from owner import calculate_tax\ndef test_charges():\n    " + body + "\n",
    ) as repository:
        repository.index.sync()
        packet = repository.verification.changed_set(["owner.py"])
    relevance = assert_object(assert_records(packet["changes"])[0]["relevance"])
    candidate = assert_records(relevance["candidates"])[0]
    assert bool(packet["targets"]) is expected
    assert candidate["reference_strength"] == (
        "reachable-symbol-use" if expected else "reachable-import"
    )
    assert packet["negative_evidence_admissible"] is False


def test_indexed_calls_and_annotation_evidence_agree_with_verification(
    tmp_path: Path,
) -> None:
    test_path = "tests/test_amounts.py"
    with _repository(
        tmp_path,
        "from owner import calculate_tax\n"
        "def test_calculate_tax():\n    preview: calculate_tax()\n    assert True\n"
        "def test_charges():\n    value: int = calculate_tax()\n"
        "def test_target():\n    calculate_tax().amount: int\n",
    ) as repository:
        repository.index.sync()
        reverse = repository.structure.locality("owner.py::calculate_tax", max_depth=0)
        callers = assert_records(assert_records(reverse["nodes"])[0]["exact_callers"])
        assert {(row["source"], row["line"]) for row in callers} == {
            ("test_charges", 6),
            ("test_target", 8),
        }
        for name, lines in (
            ("test_calculate_tax", []),
            ("test_charges", [6]),
            ("test_target", [8]),
        ):
            forward = repository.structure.locality(f"{test_path}::{name}", max_depth=1)
            assert [
                (row["resolved_symbol_id"], row["line"])
                for row in assert_records(forward["edges"])
            ] == [("owner.py::calculate_tax", line) for line in lines]
        deps = repository.relationships.deps("test_calculate_tax")
    assert [
        (row["kind"], row["confidence"])
        for row in assert_records(deps["edges"])
        if row["source"] == "test_calculate_tax" and row["target"] == "calculate_tax"
    ] == [("attribute-type", "annotation")]


@pytest.mark.parametrize("future_import", [True, False])
def test_verifier_and_call_graph_follow_module_annotation_semantics(
    tmp_path: Path, future_import: bool
) -> None:
    header = '"""Example module."""\n'
    if future_import:
        header += (
            "from __future__ import division\nfrom __future__ import annotations\n"
        )
    source = (
        header + "from owner import calculate_tax\n"
        "tag: calculate_tax()\n"
        "class Value:\n    amount: calculate_tax()\n"
        "def test_types(value: calculate_tax()) -> calculate_tax():\n"
        "    async def inner(*args: calculate_tax(), **kwargs: calculate_tax()) -> calculate_tax(): pass\n"
        "    assert True\n"
    )
    with _repository(tmp_path, source) as repository:
        repository.index.sync()
        targets = repository.verification.changed_set(["owner.py"])
        reverse = repository.structure.locality("owner.py::calculate_tax", max_depth=0)
        inner = repository.relationships.deps("test_types.inner")
        cls = repository.relationships.deps("Value")
        outer = repository.structure.locality(
            "tests/test_amounts.py::test_types", max_depth=1
        )
    eager = not future_import and sys.version_info < (3, 14)
    callers = assert_records(assert_records(reverse["nodes"])[0]["exact_callers"])
    if eager:
        assert {None, "test_types"} <= {r["source"] for r in callers}
    else:
        assert callers == []
    class_edges = {
        r["kind"]
        for r in assert_records(cls["edges"])
        if r["source"] == "Value" and r["target"] == "calculate_tax"
    }
    assert class_edges == ({"call", "attribute-type"} if eager else {"attribute-type"})
    assert bool(outer["edges"]) is eager
    assert bool(targets["targets"]) is eager
    assert targets["negative_evidence_admissible"] is False
    assert {
        row["kind"]
        for row in assert_records(inner["edges"])
        if row["source"] == "test_types.inner"
        and row["target"] == "calculate_tax"
        and row["confidence"] == "annotation"
    } == {"parameter-type", "return-type"}


def test_postponement_preserves_decorators_defaults_and_initializers(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        "from __future__ import annotations\nfrom owner import calculate_tax\n"
        "def keep(value): return lambda f: f\n"
        "def test_amount():\n"
        "    @keep(calculate_tax())\n"
        "    def local(\n"
        "        amount: calculate_tax() =\n"
        "            calculate_tax(),\n"
        "        *, fee=calculate_tax(),\n"
        "    ) -> calculate_tax(): pass\n"
        "    result: calculate_tax() = calculate_tax()\n",
    ) as repository:
        repository.index.sync()
        relevance = repository.tasks.verification_relevance(
            "Change calculate_tax in owner.py"
        )
        reverse = repository.structure.locality("owner.py::calculate_tax", max_depth=0)
        forward = repository.structure.locality(
            "tests/test_amounts.py::test_amount", max_depth=1
        )
    assert assert_object(relevance["selected"])["test_symbol"] == "test_amount"
    callers = assert_records(assert_records(reverse["nodes"])[0]["exact_callers"])
    assert [row["source"] for row in callers] == ["test_amount"]
    assert {
        row["line"]
        for row in assert_records(forward["edges"])
        if row["resolved_symbol_id"] == "owner.py::calculate_tax"
    } == {5, 8, 9, 11}


@pytest.mark.skipif(
    sys.version_info < (3, 12), reason="Native PEP 695 grammar required"
)
@pytest.mark.parametrize(
    "declaration",
    [
        "def local[T: calculate_tax()](): pass",
        "async def local[T: (str, calculate_tax())](): pass",
        "class View[T: calculate_tax()]: pass",
        "type Alias[T: calculate_tax()] = list[T]",
        "type Alias = calculate_tax()",
        pytest.param(
            "def local[T = calculate_tax()](): pass",
            marks=pytest.mark.skipif(
                sys.version_info < (3, 13), reason="PEP 696 default"
            ),
        ),
    ],
)
def test_lazy_type_declaration_is_not_an_immediate_verifier_call(
    tmp_path: Path, declaration: str
) -> None:
    source = (
        "from owner import calculate_tax\ndef test_amount():\n    "
        + declaration
        + "\n    assert True\n"
    )
    with _repository(tmp_path, source) as repository:
        repository.index.sync()
        changed = repository.verification.changed_set(["owner.py"])
        forward = repository.structure.locality(
            "tests/test_amounts.py::test_amount", max_depth=1
        )
        reverse = repository.structure.locality("owner.py::calculate_tax", max_depth=0)
        deps = repository.relationships.deps("test_amount")
    assert forward["edges"] == []
    assert assert_records(reverse["nodes"])[0]["exact_callers"] == []
    assert not any(row["kind"] == "call" for row in assert_records(deps["edges"]))
    candidate = assert_records(
        assert_object(assert_records(changed["changes"])[0]["relevance"])["candidates"]
    )[0]
    assert candidate["reference_strength"] == "reachable-import"
    assert changed["targets"] == []
    assert changed["negative_evidence_admissible"] is False


@pytest.mark.skipif(
    sys.version_info < (3, 12), reason="Native PEP 695 grammar required"
)
def test_generic_defaults_bases_and_alias_declarations_keep_their_evidence(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        "from owner import calculate_tax\n"
        "type Amount = calculate_tax()\n"
        "def test_amount():\n"
        "    def local[\n"
        "        T: calculate_tax(),\n"
        "    ](value=calculate_tax()): pass\n"
        "    class View[\n"
        "        T: calculate_tax(),\n"
        "    ](calculate_tax()): pass\n",
    ) as repository:
        (tmp_path / "owner.py").write_text("def calculate_tax(): return object\n")
        repository.index.sync()
        target = repository.structure.locality(
            "tests/test_amounts.py::test_amount", max_depth=1
        )
        changed = repository.verification.changed_set(["owner.py"])
        outline = repository.source.outline("tests/test_amounts.py")
    assert [
        (r["resolved_symbol_id"], r["line"]) for r in assert_records(target["edges"])
    ] == [("owner.py::calculate_tax", 6), ("owner.py::calculate_tax", 9)]
    assert [row["path"] for row in assert_records(changed["targets"])] == [
        "tests/test_amounts.py"
    ]
    assert ("Amount", "type") in {
        (row["qualname"], row["kind"]) for row in assert_records(outline["symbols"])
    }


@pytest.mark.parametrize(
    ("expression", "observed"),
    [
        ("(calculate_tax() for _ in (1,))", False),
        ("lambda: calculate_tax()", False),
        ("assert (calculate_tax() for _ in (1,)), calculate_tax()", False),
        ("assert lambda: calculate_tax()", False),
        ("(item for item in (calculate_tax() for _ in (1,)))", False),
        ("lambda callback=(lambda: calculate_tax()): callback", False),
        ("(item for item in calculate_tax())", True),
        ("lambda *, value=calculate_tax(): value", True),
        ("(lambda: calculate_tax())()", True),
        ("list(calculate_tax() for _ in (1,))", True),
        ("[calculate_tax() for _ in (1,)]", True),
        ("callback = lambda: calculate_tax()\n    assert callback() == (1, 2)", True),
        (
            "checks = (calculate_tax() for _ in (1,))\n    assert next(checks) == (1, 2)",
            True,
        ),
    ],
)
def test_discarded_and_consumed_python_expressions(
    tmp_path: Path, expression: str, observed: bool
) -> None:
    test_path = "tests/test_amounts.py"
    source = (
        "from owner import calculate_tax\ndef test_amount():\n    " + expression + "\n"
    )
    with _repository(tmp_path, source) as repository:
        (tmp_path / "owner.py").write_text("def calculate_tax(): return (1, 2)\n")
        repository.index.sync()
        changed = repository.verification.changed_set(["owner.py"])
        locality = repository.structure.locality("owner.py::calculate_tax", max_depth=0)
        forward = repository.structure.locality(
            f"{test_path}::test_amount", max_depth=1
        )
    relevance = assert_object(assert_records(changed["changes"])[0]["relevance"])
    candidate = assert_records(relevance["candidates"])[0]
    assert candidate["reference_strength"] == (
        "reachable-symbol-use" if observed else "reachable-import"
    )
    assert candidate["direct_reference"] is observed
    assert bool(changed["targets"]) is observed
    assert changed["negative_evidence_admissible"] is False
    callers = assert_records(assert_records(locality["nodes"])[0]["exact_callers"])
    assert [(row["path"], row["source"]) for row in callers] == (
        [(test_path, "test_amount")] if observed else []
    )
    assert (
        any(
            row["resolved_symbol_id"] == "owner.py::calculate_tax"
            for row in assert_records(forward["edges"])
        )
        is observed
    )


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("[calculate_tax() for _ in [1, 2]]", "test_charges"),
        ("{calculate_tax() for _ in (1, 2)}", "test_charges"),
        ("{index: calculate_tax() for index in {1, 2}}", "test_charges"),
        ("[[calculate_tax() for _ in (1,)] for _ in (1,)]", "test_charges"),
        ("[calculate_tax() for _ in ()]", None),
        ("[calculate_tax() for left, right in (1,)]", None),
        ("[calculate_tax() for _ in (1,) if visible]", None),
        ("(calculate_tax() for _ in (1,))", None),
        ("lambda: [calculate_tax() for _ in (1,)]", None),
        ("([calculate_tax() for _ in (1,)] for _ in (1,))", None),
    ],
)
def test_only_qualified_eager_comprehension_uses_narrow_the_test_node(
    tmp_path: Path, expression: str, expected: str | None
) -> None:
    source = (
        "from owner import calculate_tax\n"
        "def test_calculate_tax(): assert True\n"
        "def test_charges():\n    observed = " + expression + "\n"
    )
    with _repository(tmp_path, source) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence("Change calculate_tax in owner.py")
    verify = packet["verification"]
    assert assert_object(verify["plan"])["test_symbol"] == expected
    assert assert_object(verify["relevance"]["selected"])["test_symbol"] == expected


@pytest.mark.parametrize("generator", [False, True])
def test_outermost_iterable_retains_its_import_despite_a_shadowed_body(
    tmp_path: Path, generator: bool
) -> None:
    delimiters = ("(", ")") if generator else ("[", "]")
    source = (
        "from owner import calculate_tax\n"
        f"def test_charges():\n    values = {delimiters[0]}\n"
        "        calculate_tax()\n"
        "        for calculate_tax in calculate_tax()\n"
        f"    {delimiters[1]}\n"
    )
    with _repository(tmp_path, source) as repository:
        (tmp_path / "owner.py").write_text("def calculate_tax(): return (lambda: 1,)\n")
        repository.index.sync()
        changed = repository.verification.changed_set(["owner.py"])
        forward = repository.structure.locality(
            "tests/test_amounts.py::test_charges", max_depth=1
        )
    candidate = assert_records(
        assert_object(assert_records(changed["changes"])[0]["relevance"])["candidates"]
    )[0]
    assert candidate["direct_reference"] is True
    assert candidate["test_symbol"] == "test_charges"
    assert {
        (r["line"], r["resolved_symbol_id"]) for r in assert_records(forward["edges"])
    } == {(4, None), (5, "owner.py::calculate_tax")}


def test_only_a_shadowed_comprehension_name_cannot_supply_a_verifier(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        "from owner import calculate_tax\n"
        "def test_charges(): assert [calculate_tax for calculate_tax in (1,)] == [1]\n",
    ) as repository:
        repository.index.sync()
        changed = repository.verification.changed_set(["owner.py"])
    candidate = assert_records(
        assert_object(assert_records(changed["changes"])[0]["relevance"])["candidates"]
    )[0]
    assert candidate["reference_strength"] == "reachable-import"
    assert candidate["direct_reference"] is False
    assert changed["targets"] == []
    assert changed["negative_evidence_admissible"] is False


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        ("def quoted(value=calculate_tax): pass", "test_charges"),
        ("@calculate_tax\n    def quoted(): pass", "test_charges"),
        ("class Example(calculate_tax()): pass", "test_charges"),
        (
            "class Example:\n        def quote(self, *, value=calculate_tax()): pass",
            "test_charges",
        ),
        (
            "class Example:\n        @calculate_tax\n        async def quote(self): pass",
            "test_charges",
        ),
        ("class Example:\n        class Nested(calculate_tax()): pass", "test_charges"),
        ("class Example:\n        def quote(self): return calculate_tax()", None),
        (
            "def helper():\n        class Example:\n            mark = calculate_tax()",
            None,
        ),
        ("class Example(metaclass=type):\n        mark = calculate_tax()", None),
    ],
)
def test_nested_definition_headers_retain_the_qualified_test_witness(
    tmp_path: Path, declaration: str, expected: str | None
) -> None:
    source = (
        "from owner import calculate_tax\n"
        "def test_calculate_tax(): assert True\n"
        "def test_charges():\n    " + declaration + "\n"
    )
    with _repository(tmp_path, source) as repository:
        (tmp_path / "owner.py").write_text(
            "def calculate_tax(value=None): return object if value is None else value\n"
        )
        repository.index.sync()
        packet = repository.tasks.evidence("Change calculate_tax in owner.py")
        changed = repository.verification.changed_set(["owner.py"])
    verify = packet["verification"]
    row = assert_object(verify["relevance"]["selected"])
    assert row["direct_reference"] is True
    assert row["test_symbol"] == expected
    assert assert_object(verify["plan"])["scope"] == (
        "test-node" if expected else "test-file"
    )
    assert assert_object(verify["plan"])["test_symbol"] == expected
    change = assert_records(changed["changes"])[0]
    candidate = assert_records(assert_object(change["relevance"])["candidates"])[0]
    assert candidate["test_symbol"] == expected
    assert [r["path"] for r in assert_records(changed["targets"])] == [
        "tests/test_amounts.py"
    ]


def test_class_namespace_shadow_keeps_a_method_header_from_becoming_a_witness(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        "from owner import calculate_tax\n"
        "def test_charges():\n"
        "    class Example:\n"
        "        calculate_tax = lambda: 5\n"
        "        def quote(self, value=calculate_tax()): pass\n",
    ) as repository:
        repository.index.sync()
        changed = repository.verification.changed_set(["owner.py"])
    candidate = assert_records(
        assert_object(assert_records(changed["changes"])[0]["relevance"])["candidates"]
    )[0]
    assert candidate["direct_reference"] is False
    assert changed["targets"] == []
    assert changed["negative_evidence_admissible"] is False
