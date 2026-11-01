"""Native Python evidence preserves source relationships without runtime targets."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from hashmarks import CodeMap
from hashmarks.codemap import python_bindings as interpreter
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.codemap.python_bindings import python_bindings
from hashmarks.codemap.source_binding_contract import BindingObservationBound
from hashmarks.python_ast_cache import parse_python_ast


def _observe(source: str, limit: int = 1_000) -> list[dict[str, object]]:
    raw = source.encode("utf-8")
    return python_bindings(parse_python_ast(raw), raw, limit)[0]


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _details(row: dict[str, object], key: str) -> list[dict[str, object]]:
    value = row[key]
    assert isinstance(value, list)
    return [_mapping(item) for item in value]


def _text(row: dict[str, object]) -> str:
    return str(_mapping(row["expression"])["text"])


def _call(rows: list[dict[str, object]], name: str) -> dict[str, object]:
    matches = [row for row in rows if row["kind"] == "call-site" and _text(row) == name]
    assert len(matches) == 1
    return matches[0]


def _span_text(source: str, span: object) -> str:
    coordinates = _mapping(span)
    raw = source.encode("utf-8")
    return raw[
        int(cast(int, coordinates["start_byte"])) : int(
            cast(int, coordinates["end_byte"])
        )
    ].decode("utf-8")


def _symbolic(row: dict[str, object]) -> dict[str, object]:
    assert row["target"] is None
    assert row["qualification"] == "unknown"
    assert row["runtime_target"] == "not-established"
    value = _mapping(row["symbolic_reference"])
    assert value["runtime_identity"] == "not-established"
    return value


def test_arguments_preserve_authored_order_and_native_ranges() -> None:
    source = (
        'label = "é"\r\ninvoke("--run-" + "unit", verify=label, *items, **options)\r\n'
    )
    call = _call(_observe(source), "invoke")
    arguments = _details(call, "arguments")
    assert [item["kind"] for item in arguments] == [
        "positional",
        "keyword",
        "spread",
        "keyword-spread",
    ]
    assert [item["index"] for item in arguments] == [0, 1, 2, 3]
    assert [item["name"] for item in arguments] == [None, "verify", None, None]
    assert [_span_text(source, item["range"]) for item in arguments] == [
        '"--run-" + "unit"',
        "verify=label",
        "*items",
        "**options",
    ]
    assert [_text(item) for item in arguments] == [
        '"--run-" + "unit"',
        "label",
        "items",
        "options",
    ]
    assert [item["literal"] for item in arguments] == ["--run-unit", "é", None, None]
    assert [item["qualification"] for item in arguments] == [
        "qualified",
        "qualified",
        "unknown",
        "unknown",
    ]
    assert call["argument_count"] == 4
    assert call["arguments_completeness"] == "complete"
    assert call["arguments_truncation"] == "not-truncated"


def test_authored_names_are_native_identifiers_not_expression_previews() -> None:
    rows = _observe('def invoke(parser):\n    parser.add_argument("--run-unit")\n')
    call = _call(rows, "parser.add_argument")
    assert _mapping(call["expression"])["name"] == "add_argument"
    argument = _details(call, "arguments")[0]
    assert _mapping(argument["expression"])["name"] is None
    assert argument["literal"] == "--run-unit"
    symbolic = _symbolic(call)
    assert symbolic["properties"] == ["add_argument"]


def test_detail_bounds_do_not_hide_later_lexical_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interpreter, "MAX_BINDING_DETAILS", 2)
    source = 'flag = "yes"\ninvoke(flag, "a", "b", "c")\nflag = dynamic\n'
    call = _call(_observe(source), "invoke")
    arguments = _details(call, "arguments")
    assert call["argument_count"] == 4
    assert len(arguments) == 2
    assert call["arguments_completeness"] == "incomplete"
    assert call["arguments_truncation"] == "truncated"
    assert arguments[0]["literal"] is None
    assert arguments[0]["qualification"] == "unknown"


def test_class_bases_retain_native_shape_and_independent_qualifiers() -> None:
    source = (
        "from native import Failure as Base\n"
        "class Failure(Base, Exception, factory()):\n"
        "    pass\n"
        "def helper(value):\n"
        "    return value\n"
    )
    rows = _observe(source)
    declaration = next(
        row for row in rows if row["kind"] == "declaration" and row["name"] == "Failure"
    )
    assert declaration["declaration_kind"] == "class"
    bases = _details(declaration, "bases")
    assert [item["index"] for item in bases] == [0, 1, 2]
    assert [_text(item) for item in bases] == ["Base", "Exception", "factory()"]
    assert [_mapping(item["expression"])["name"] for item in bases] == [
        "Base",
        "Exception",
        None,
    ]
    assert [item["qualification"] for item in bases] == [
        "qualified",
        "unknown",
        "unknown",
    ]
    assert _mapping(bases[0]["target"])["module"] == "native"
    assert declaration["base_count"] == 3
    assert declaration["bases_completeness"] == "complete"
    assert declaration["bases_truncation"] == "not-truncated"
    assert {
        row["name"]: row["declaration_kind"]
        for row in rows
        if row["kind"] == "declaration"
    } == {"Failure": "class", "helper": "function", "value": "parameter"}


def test_class_base_bound_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(interpreter, "MAX_BINDING_DETAILS", 2)
    rows = _observe("class Failure(First, Second, Third):\n    pass\n")
    declaration = next(row for row in rows if row["kind"] == "declaration")
    assert len(_details(declaration, "bases")) == 2
    assert declaration["base_count"] == 3
    assert declaration["bases_completeness"] == "incomplete"
    assert declaration["bases_truncation"] == "truncated"


def test_authored_imports_survive_stars_rebinding_and_relative_origin() -> None:
    rows = _observe(
        "from ..native import *\n"
        "from . import helper as run\n"
        "import package.child as module\n"
        "import package.other\n"
        "module = replacement\n"
    )
    imports = [row for row in rows if row["kind"] == "import-binding"]
    assert [row["import_syntax"] for row in imports] == [
        {"module": "native", "name": "*", "level": 2, "local_name": None},
        {"module": "", "name": "helper", "level": 1, "local_name": "run"},
        {
            "module": "package.child",
            "name": None,
            "level": 0,
            "local_name": "module",
        },
        {
            "module": "package.other",
            "name": None,
            "level": 0,
            "local_name": "package",
        },
    ]
    assert imports[0]["qualification"] == "unknown"
    assert imports[0]["target"] is None
    assert imports[2]["qualification"] == "conditional"
    assert "binding-may-be-overwritten" in cast(list[str], imports[2]["conditions"])


def test_parameter_alias_path_is_source_evidence_not_runtime_owner() -> None:
    source = (
        "def execute(journal):\n"
        "    copy = journal\n"
        "    finish = copy.details.finish\n"
        "    finish()\n"
    )
    call = _call(_observe(source), "finish")
    symbolic = _symbolic(call)
    assert symbolic["qualification"] == "qualified"
    assert symbolic["properties"] == ["details", "finish"]
    assert symbolic["conditions"] == []
    root = _mapping(symbolic["root"])
    assert root["kind"] == "parameter"
    assert root["name"] == "journal"
    assert _span_text(source, root["range"]) == "journal"
    assert _mapping(root["scope"])["name"] == "execute"
    supports = [
        _span_text(source, span) for span in _details(symbolic, "supporting_ranges")
    ]
    assert {"journal", "copy", "finish", "copy.details.finish"}.issubset(supports)


def test_getattr_symbolic_path_remains_conditional() -> None:
    rows = _observe(
        "def execute(journal):\n"
        "    finish = getattr(journal, 'finish_' + 'detail')\n"
        "    finish()\n"
    )
    symbolic = _symbolic(_call(rows, "finish"))
    assert symbolic["properties"] == ["finish_detail"]
    assert symbolic["qualification"] == "conditional"
    assert symbolic["conditions"] == ["unshadowed-builtin-getattr"]


@pytest.mark.parametrize(
    "body",
    [
        "finish = journal.finish_detail\nfinish = other\nfinish()",
        "finish = journal.finish_detail\njournal = other\nfinish()",
        "finish()\nfinish = journal.finish_detail",
        "finish = journal[key]\nfinish()",
        "finish = getattr(journal, key)\nfinish()",
        "getattr = other\nfinish = getattr(journal, 'finish_detail')\nfinish()",
        "finish = journal.finish_detail\nexec(code)\nfinish()",
        "finish = journal.finish_detail\nlocals()['finish'] = other\nfinish()",
        "finish = cycle\ncycle = finish\nfinish()",
    ],
)
def test_unstable_or_dynamic_aliases_never_publish_a_qualified_path(body: str) -> None:
    source = "def execute(journal, key, other, code):\n" + "\n".join(
        "    " + line for line in body.splitlines()
    )
    call = _call(_observe(source), "finish")
    assert call["target"] is None
    assert call["qualification"] == "unknown"
    assert call["symbolic_reference"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        "journal.finish_detail = other",
        "del journal.finish_detail",
        "journal.finish_detail += other",
        "copy = journal\ncopy.finish_detail = other",
        "setattr(journal, 'finish_' + 'detail', other)",
        "delattr(journal, 'finish_detail')",
        "setattr(journal, key, other)",
        "journal.__dict__['finish_detail'] = other",
        "namespace = vars(journal)\nnamespace['finish_detail'] = other",
        "journal[key].finish_detail = other",
        "setattr(journal[key], 'finish_detail', other)",
        "journal.update({'finish_detail': other})",
    ],
)
def test_later_property_mutation_withdraws_symbolic_path_qualification(
    mutation: str,
) -> None:
    source = (
        "def execute(journal, key, other):\n"
        "    finish = journal.finish_detail\n"
        "    finish()\n" + "\n".join("    " + line for line in mutation.splitlines())
    )
    call = _call(_observe(source), "finish")
    symbolic = _symbolic(call)
    assert symbolic["qualification"] == "unknown"
    assert symbolic["reasons"] == ["property-binding-may-be-mutated"]
    assert len(_details(symbolic, "supporting_ranges")) >= 3


@pytest.mark.parametrize(
    "mutation",
    [
        "journal.child = other",
        "journal.child.finish_detail = other",
        "journal.child[key] = other",
        "namespace = vars(journal.child)\nnamespace.clear()",
    ],
)
def test_nested_receiver_writes_invalidate_the_qualified_prefix(mutation: str) -> None:
    source = (
        "def execute(journal, key, other):\n"
        "    finish = journal.child.finish_detail\n"
        "    finish()\n" + "\n".join("    " + line for line in mutation.splitlines())
    )
    symbolic = _symbolic(_call(_observe(source), "finish"))
    assert symbolic["qualification"] == "unknown"


def test_mutations_are_scoped_by_parameter_identity_and_property_prefix() -> None:
    rows = _observe(
        "def execute(journal, other):\n"
        "    finish = journal.finish_detail\n"
        "    finish()\n"
        "    journal.other_detail = other\n"
        "    other.finish_detail = None\n"
        "def unrelated(journal):\n"
        "    journal.finish_detail = None\n"
    )
    assert _symbolic(_call(rows, "finish"))["qualification"] == "qualified"


def test_symbolic_alias_and_expression_bounds_remain_unknown() -> None:
    aliases = "\n".join(f"    value{i} = value{i - 1}" for i in range(1, 12))
    source = (
        "def execute(journal):\n"
        "    value0 = journal.finish_detail\n"
        f"{aliases}\n"
        "    value11()\n"
        "    journal" + ".child" * 40 + "()\n"
    )
    rows = _observe(source)
    for name in ("value11", "journal" + ".child" * 40):
        call = _call(rows, name)
        assert call["target"] is None
        assert call["qualification"] == "unknown"
        assert call["symbolic_reference"] is None


def test_projection_limit_does_not_hide_later_property_writes() -> None:
    source = "def execute(journal):\n    journal.finish()\n    journal.finish = other\n"
    rows = _observe(source)
    call_index = next(i for i, row in enumerate(rows) if row["kind"] == "call-site")
    prefix = _observe(source, limit=call_index + 1)
    assert _symbolic(_call(prefix, "journal.finish"))["qualification"] == "unknown"


def test_defaults_and_helper_inputs_never_become_parameter_runtime_targets() -> None:
    rows = _observe(
        "import runner\n"
        "def execute(owner=runner):\n"
        "    launch = owner.Server\n"
        "    launch()\n"
        "execute(runner)\n"
    )
    symbolic = _symbolic(_call(rows, "launch"))
    assert symbolic["qualification"] == "qualified"
    assert symbolic["properties"] == ["Server"]
    assert _mapping(symbolic["root"])["name"] == "owner"
    relations = [
        row for row in rows if row["kind"] in {"default-binding", "argument-binding"}
    ]
    assert len(relations) == 2
    assert all(row["qualification"] == "conditional" for row in relations)
    assert all(row["runtime_target"] == "not-established" for row in relations)
    assert all(_mapping(row["target"])["module"] == "runner" for row in relations)


def test_string_literals_and_nearest_call_argument_are_native_facts() -> None:
    source = (
        'outside = "outside"\n'
        'invoke({"command": ["native", inner("nested")]}, tag="line\\nvalue")\n'
        '# "comment"\n'
    )
    rows = _observe(source)
    literals = [row for row in rows if row["kind"] == "literal-expression"]
    assert [row["literal"] for row in literals] == [
        "outside",
        "command",
        "native",
        "nested",
        "line\nvalue",
    ]
    assert literals[0]["call_argument"] is None
    invoke = _call(rows, "invoke")
    nested = _call(rows, "inner")
    for row in literals[1:3]:
        context = _mapping(row["call_argument"])
        assert context["call_range"] == invoke["range"]
        assert context["kind"] == "positional"
        assert context["name"] is None
    assert _mapping(literals[3]["call_argument"])["call_range"] == nested["range"]
    keyword = _mapping(literals[4]["call_argument"])
    assert keyword["call_range"] == invoke["range"]
    assert keyword["kind"] == "keyword"
    assert keyword["name"] == "tag"
    assert _span_text(source, keyword["range"]) == 'tag="line\\nvalue"'


def test_formatted_fragments_are_not_upgraded_to_constant_string_values() -> None:
    rows = _observe('invoke(f"prefix-{value}-suffix", f"{\'inside\'}")\n')
    literals = [row for row in rows if row["kind"] == "literal-expression"]
    assert [row["literal"] for row in literals] == [None, None, "inside"]
    assert [row["qualification"] for row in literals] == [
        "unknown",
        "unknown",
        "qualified",
    ]
    assert all(
        item["literal"] is None for item in _details(_call(rows, "invoke"), "arguments")
    )


def test_oversized_and_non_utf8_literal_expressions_remain_unknown() -> None:
    rows = _observe('invoke("' + "é" * 129 + '", "\\ud800")\n')
    literals = [row for row in rows if row["kind"] == "literal-expression"]
    assert [row["qualification"] for row in literals] == ["unknown", "unknown"]
    assert [row["reasons"] for row in literals] == [
        ["literal-byte-bound"],
        ["literal-not-utf8"],
    ]
    assert _mapping(literals[0]["expression"])["text_truncated"] is True


@pytest.mark.parametrize(
    ("statement", "context"),
    [("environment.environ = other", "store"), ("del environment.environ", "delete")],
)
def test_property_writes_preserve_receiver_evidence_without_bypassing_mutation(
    statement: str, context: str
) -> None:
    source = f"import os as environment\n{statement}\nenvironment.environ.get('key')\n"
    rows = _observe(source)
    writes = [row for row in rows if row["kind"] == "property-write"]
    assert len(writes) == 1
    write = writes[0]
    assert write["access_kind"] == "attribute"
    assert write["property"] == "environ"
    assert write["context"] == context
    assert _span_text(source, write["range"]) == "environment.environ"
    assert write["target"] is None
    assert write["qualification"] == "unknown"
    assert write["reasons"] == ["property-binding-may-be-mutated"]
    receiver = _mapping(write["receiver"])
    assert receiver["qualification"] == "qualified"
    assert _mapping(receiver["target"])["module"] == "os"
    assert receiver["runtime_target"] == "not-established"
    call = _call(rows, "environment.environ.get")
    assert call["target"] is None
    assert call["qualification"] == "unknown"


def test_parameter_property_write_keeps_only_symbolic_receiver_identity() -> None:
    rows = _observe("def configure(environment):\n    environment.environ = other\n")
    write = next(row for row in rows if row["kind"] == "property-write")
    assert _symbolic(write)["qualification"] == "unknown"
    receiver = _mapping(write["receiver"])
    symbolic = _symbolic(receiver)
    assert symbolic["qualification"] == "qualified"
    assert symbolic["properties"] == []
    assert _mapping(symbolic["root"])["name"] == "environment"


def test_rebound_property_write_receiver_stays_unknown() -> None:
    rows = _observe("import os\nos.environ = other\nos = replacement\n")
    write = next(row for row in rows if row["kind"] == "property-write")
    receiver = _mapping(write["receiver"])
    assert receiver["qualification"] == "unknown"
    assert receiver["target"] is None
    assert receiver["symbolic_reference"] is None


def _mutation_bound_source() -> str:
    return (
        "def execute(owner, other):\n"
        "    owner.finish()\n"
        "    alias0=owner\n"
        + "".join(f"    alias{i}=alias{i - 1}\n" for i in range(1, 40))
        + "    alias39.finish=other\n"
    )


def test_exhausted_mutation_alias_proof_cannot_publish_qualified_source_path() -> None:
    with pytest.raises(BindingObservationBound, match="symbolic-mutation-depth-bound"):
        _observe(_mutation_bound_source(), limit=1)


def test_exhausted_mutation_proof_withdraws_public_member_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "member.py").write_text(_mutation_bound_source(), encoding="utf-8")
    with CodeMap(tmp_path, range_provider=TreeSitterRangeProvider()) as codemap:
        codemap.index.sync()
        packet = codemap.source.bindings("member.py", limit=1)
    assert packet["availability"] == "unavailable"
    assert packet["reason"] == "source-binding-observation-bound"
    assert packet["completeness"] == "unknown"
    assert packet["facts"] == []
    assert packet["observed_fact_count"] is None
    assert packet["negative_evidence"] == "not-admissible"
