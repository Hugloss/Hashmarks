"""Qualified Python origins never imply unconditional runtime call targets."""

from __future__ import annotations

from typing import cast

import pytest

from hashmarks.codemap import python_binding_scope
from hashmarks.codemap.python_bindings import python_bindings
from hashmarks.codemap.source_binding_contract import BindingObservationBound
from hashmarks.python_ast_cache import parse_python_ast


def _observe(source: str | bytes, limit: int = 500) -> list[dict[str, object]]:
    raw = source.encode("utf-8") if isinstance(source, str) else source
    return python_bindings(parse_python_ast(raw), raw, limit)[0]


def _expression(row: dict[str, object]) -> str:
    expression = row["expression"]
    return (
        "" if expression is None else str(cast(dict[str, object], expression)["text"])
    )


def _facts(rows: list[dict[str, object]], kind: str) -> list[dict[str, object]]:
    return [row for row in rows if row["kind"] == kind]


def _call(rows: list[dict[str, object]], expression: str) -> dict[str, object]:
    matches = [
        row for row in _facts(rows, "call-site") if _expression(row) == expression
    ]
    assert len(matches) == 1, matches
    return matches[0]


def _import(row: dict[str, object]) -> dict[str, object]:
    target = row["target"]
    assert isinstance(target, dict)
    assert target["kind"] == "import"
    assert target["module_resolution"] == "not-performed"
    assert row["runtime_target"] == "not-established"
    return target


@pytest.mark.parametrize(
    ("source", "expression", "module", "name", "properties"),
    [
        (
            "import subprocess as p\np.Popen([])\n",
            "p.Popen",
            "subprocess",
            None,
            ["Popen"],
        ),
        (
            "from subprocess import Popen as launch\nlaunch([])\n",
            "launch",
            "subprocess",
            "Popen",
            [],
        ),
        (
            "import package.child\npackage.child.launch()\n",
            "package.child.launch",
            "package",
            None,
            ["child", "launch"],
        ),
        ("from .native import launch as run\nrun()\n", "run", "native", "launch", []),
        (
            "def run():\n    import subprocess as p\n    p.Popen([])\n",
            "p.Popen",
            "subprocess",
            None,
            ["Popen"],
        ),
        (
            "import subprocess as p\nfirst = p.Popen\nsecond = first\nsecond([])\n",
            "second",
            "subprocess",
            None,
            ["Popen"],
        ),
        (
            "import subprocess as p\nlaunch = getattr(p, 'Po' + 'pen')\nlaunch([])\n",
            "launch",
            "subprocess",
            None,
            ["Popen"],
        ),
        (
            "import subprocess as p\nattribute = 'Po'\nlaunch = getattr(p, attribute + 'pen')\nlaunch([])\n",
            "launch",
            "subprocess",
            None,
            ["Popen"],
        ),
    ],
)
def test_supported_python_import_origins(
    source: str, expression: str, module: str, name: str | None, properties: list[str]
) -> None:
    row = _call(_observe(source), expression)
    target = _import(row)
    assert target["module"] == module
    assert target["name"] == name
    assert target["properties"] == properties
    assert row["qualification"] in {"qualified", "conditional"}
    assert row["supporting_ranges"]


@pytest.mark.parametrize(
    "body",
    [
        "def run(p):\n    p.Popen([])\n",
        "def run(p, /):\n    p.Popen([])\n",
        "def run(*, p):\n    p.Popen([])\n",
        "def run(*p):\n    p.Popen([])\n",
        "def run(**p):\n    p.Popen([])\n",
        "def run():\n    p.Popen([])\n    p = unknown\n",
        "def run():\n    p: object\n    p.Popen([])\n",
        "def outer(p):\n    def run():\n        p.Popen([])\n",
        "def run():\n    def p(): pass\n    p.Popen([])\n",
        "def run():\n    class p: pass\n    p.Popen([])\n",
        "for p in unknown:\n    p.Popen([])\n",
        "try:\n    pass\nexcept Exception as p:\n    p.Popen([])\n",
        "match unknown:\n    case {'p': p}:\n        p.Popen([])\n",
        "p, other = unknown\np.Popen([])\n",
        "p = unknown\np.Popen([])\n",
        "del p\np.Popen([])\n",
        "def rebind():\n    global p\n    p = unknown\np.Popen([])\n",
        "class Writer:\n    global p\n    p = unknown\np.Popen([])\n",
        "[p.Popen([]) for p in unknown]\n",
        "lambda p: p.Popen([])\n",
        "from another import *\np.Popen([])\n",
        "if unknown:\n    import another as p\np.Popen([])\n",
    ],
)
def test_shadowed_rebound_or_dynamic_names_never_gain_import_authority(
    body: str,
) -> None:
    row = _call(_observe("import subprocess as p\n" + body), "p.Popen")
    assert row["qualification"] == "unknown"
    assert row["target"] is None
    assert row["reasons"]


def test_nonlocal_write_invalidates_the_affected_outer_binding() -> None:
    source = (
        "import subprocess as p\n"
        "def outer():\n    factory = p.Popen\n"
        "    def rebind():\n        nonlocal factory\n        factory = unknown\n"
        "    def use():\n        factory([])\n"
    )
    row = _call(_observe(source), "factory")
    assert row["qualification"] == "unknown"
    assert row["target"] is None


def test_class_body_bindings_do_not_leak_into_method_lexical_lookup() -> None:
    rows = _observe(
        "import subprocess as p\nfactory = p.Popen\n"
        "class Runner:\n    factory = p.run\n"
        "    def use(self):\n        factory([])\n"
        "    def with_default(self, callback=factory):\n        callback([])\n"
    )
    assert _import(_call(rows, "factory"))["properties"] == ["Popen"]
    default = _facts(rows, "default-binding")[0]
    assert _import(default)["properties"] == ["run"]
    assert default["qualification"] == "conditional"
    assert _call(rows, "callback")["qualification"] == "unknown"


def test_comprehension_first_iterable_uses_outer_scope_but_body_uses_its_target() -> (
    None
):
    rows = _observe("import subprocess as p\n[p.Popen() for p in p.items()]\n")
    assert _import(_call(rows, "p.items"))["properties"] == ["items"]
    assert _call(rows, "p.Popen")["qualification"] == "unknown"


@pytest.mark.parametrize(
    "expression",
    [
        "getattr(p, unknown)",
        "getattr(p, 'Popen', fallback)",
        "getattr(p, 'not-an-identifier')",
        "__import__('subprocess').Popen",
    ],
)
def test_unsupported_dynamic_alias_expressions_stay_unknown(expression: str) -> None:
    rows = _observe(f"import subprocess as p\nlaunch = {expression}\nlaunch([])\n")
    assert _call(rows, "launch")["qualification"] == "unknown"
    assert _call(rows, "launch")["target"] is None


def test_shadowed_getattr_cannot_establish_a_property_alias() -> None:
    row = _call(
        _observe(
            "import subprocess as p\ndef run(getattr):\n    launch = getattr(p, 'Popen')\n    launch([])\n"
        ),
        "launch",
    )
    assert row["qualification"] == "unknown"


def test_default_binding_is_evaluated_in_defining_scope_and_never_resolves_parameter_calls() -> (
    None
):
    rows = _observe(
        "import subprocess as p\nfactory = p.Popen\n"
        "def run(factory=factory):\n    return factory([])\n"
        "run(p.run)\n"
    )
    default = _facts(rows, "default-binding")[0]
    assert _import(default)["properties"] == ["Popen"]
    assert default["qualification"] == "conditional"
    assert default["conditions"] == ["default-is-used"]
    supplied = _facts(rows, "argument-binding")[0]
    assert _import(supplied)["properties"] == ["run"]
    assert supplied["qualification"] == "conditional"
    parameter_call = _call(rows, "factory")
    assert parameter_call["qualification"] == "unknown"
    assert parameter_call["target"] is None
    assert parameter_call["binding_range"] == default["binding_range"]


@pytest.mark.parametrize(
    "signature", ["factory=p.Popen", "*, factory=p.Popen", "factory=p.Popen, /"]
)
def test_default_parameter_forms_preserve_conditional_origin(signature: str) -> None:
    rows = _observe(f"import subprocess as p\ndef run({signature}):\n    factory([])\n")
    default = _facts(rows, "default-binding")[0]
    assert _import(default)["properties"] == ["Popen"]
    assert _call(rows, "factory")["qualification"] == "unknown"


def test_default_cannot_resolve_a_name_bound_after_definition() -> None:
    rows = _observe(
        "def run(factory=launch):\n    factory([])\nfrom subprocess import Popen as launch\n"
    )
    default = _facts(rows, "default-binding")[0]
    assert default["qualification"] == "unknown"
    assert default["target"] is None
    assert "read-before-binding" in cast(list[str], default["reasons"])


@pytest.mark.parametrize("call", ["helper(p.Popen)", "helper(factory=p.Popen)"])
def test_one_direct_helper_input_is_conditional_and_does_not_rewrite_parameter_use(
    call: str,
) -> None:
    rows = _observe(
        f"import subprocess as p\ndef helper(factory):\n    factory([])\n{call}\n"
    )
    supplied = _facts(rows, "argument-binding")
    assert len(supplied) == 1
    assert _import(supplied[0])["properties"] == ["Popen"]
    assert supplied[0]["qualification"] == "conditional"
    assert "external-callers-not-observed" in cast(list[str], supplied[0]["conditions"])
    assert _call(rows, "factory")["qualification"] == "unknown"


@pytest.mark.parametrize(
    "second",
    ["helper(p.run)", "helper(unknown)", "helper(p.Popen)", "helper(*unknown)"],
)
def test_multiple_helper_callers_do_not_create_a_unique_parameter_target(
    second: str,
) -> None:
    rows = _observe(
        f"import subprocess as p\ndef helper(factory):\n    factory([])\nhelper(p.Popen)\n{second}\n"
    )
    supplied = _facts(rows, "argument-binding")
    assert supplied
    assert all(
        row["qualification"] == "unknown" and row["target"] is None for row in supplied
    )
    assert all(
        "single-observed-local-call" not in cast(list[str], row["conditions"])
        for row in supplied
    )


@pytest.mark.parametrize(
    "call",
    [
        "helper(*unknown)",
        "helper(**unknown)",
        "helper(factory=p.Popen, factory=p.run)",
        "helper(p.Popen, factory=p.run)",
        "helper()",
        "helper(other=p.Popen)",
    ],
)
def test_unsupported_helper_argument_binding_is_explicitly_unknown(call: str) -> None:
    rows = _observe(
        f"import subprocess as p\ndef helper(factory):\n    factory([])\n{call}\n"
    )
    supplied = _facts(rows, "argument-binding")
    assert supplied
    assert all(row["qualification"] == "unknown" and row["reasons"] for row in supplied)


def test_helper_argument_flow_never_composes_a_second_edge() -> None:
    rows = _observe(
        "import subprocess as p\ndef first(factory):\n    second(factory)\n"
        "def second(callback):\n    callback([])\nfirst(p.Popen)\n"
    )
    supplied = _facts(rows, "argument-binding")
    assert (
        next(row for row in supplied if row["name"] == "factory")["qualification"]
        == "conditional"
    )
    assert (
        next(row for row in supplied if row["name"] == "callback")["qualification"]
        == "unknown"
    )
    assert _call(rows, "callback")["qualification"] == "unknown"


def test_full_scope_qualification_precedes_projection_and_alias_bounds() -> None:
    source = "import subprocess as p\nlaunch = p.Popen\nlaunch([])\nlaunch = unknown\n"
    raw = source.encode()
    tree = parse_python_ast(raw)
    full, count = python_bindings(tree, raw, 500)
    prefix, bounded_count = python_bindings(tree, raw, 2)
    assert bounded_count == count > len(prefix)
    assert prefix == full[:2]
    assert _call(full, "launch")["qualification"] == "unknown"
    chain = "import subprocess as p\na0 = p.Popen\n"
    chain += "".join(f"a{index} = a{index - 1}\n" for index in range(1, 10))
    chain += "a9([])\n"
    row = _call(_observe(chain), "a9")
    assert row["qualification"] == "unknown"
    assert "alias-depth-bound" in cast(list[str], row["reasons"])


def test_source_node_bound_never_returns_partial_qualified_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(python_binding_scope, "MAX_BINDING_NODES", 5)
    with pytest.raises(BindingObservationBound):
        _observe("import subprocess as p\nlaunch = p.Popen\nlaunch([])\n")


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_python_ranges_reference_exact_utf8_bytes_with_native_newlines(
    newline: str,
) -> None:
    raw = newline.join(
        [
            "label = 'å😀'",
            "import subprocess as p",
            "launch = p.Popen",
            "launch([])",
            "",
        ]
    ).encode()
    rows = _observe(raw)
    call = _call(rows, "launch")
    span = cast(dict[str, int], call["range"])
    assert raw[span["start_byte"] : span["end_byte"]] == b"launch([])"
    alias = next(
        row for row in _facts(rows, "alias-binding") if row["name"] == "launch"
    )
    expression = cast(dict[str, object], alias["expression"])
    span = cast(dict[str, int], expression["range"])
    assert raw[span["start_byte"] : span["end_byte"]] == b"p.Popen"
    support = cast(list[dict[str, int]], call["supporting_ranges"])
    assert b"p.Popen" in [raw[row["start_byte"] : row["end_byte"]] for row in support]


def test_escaped_literals_use_native_values_and_large_values_remain_unknown() -> None:
    rows = _observe(
        "import subprocess as p\nlaunch = getattr(p, '\\x50open')\nlaunch([])\n"
    )
    assert _import(_call(rows, "launch"))["properties"] == ["Popen"]
    rows = _observe("value = '" + "x" * 257 + "'\n")
    alias = _facts(rows, "alias-binding")[0]
    assert alias["qualification"] == "unknown"
    assert alias["literal"] is None
    assert cast(dict[str, object], alias["expression"])["text_truncated"] is True


def test_annotations_preserve_type_context_without_claiming_runtime_use() -> None:
    rows = _observe("import subprocess as p\ndef run(value: p.Type()): pass\n")
    call = _call(rows, "p.Type")
    assert call["qualification"] == "conditional"
    assert "type-syntax" in cast(list[str], call["conditions"])
    assert call["runtime_target"] == "not-established"


def test_module_annotation_only_does_not_rebind_import_or_create_alias() -> None:
    rows = _observe("import subprocess as p\np: object\np.Popen([])\n")
    assert _import(_call(rows, "p.Popen"))["properties"] == ["Popen"]
    assert _facts(rows, "alias-binding") == []


@pytest.mark.parametrize(
    "mutation",
    [
        "p.Popen = replacement",
        "p.Popen += replacement",
        "del p.Popen",
        "alias = p\nalias.Popen = replacement",
        "setattr(p, 'Popen', replacement)",
        "setattr(p, unknown, replacement)",
        "delattr(p, 'Popen')",
        "def mutate():\n    p.Popen = replacement",
    ],
)
def test_property_writes_cannot_preserve_an_unqualified_original_alias(
    mutation: str,
) -> None:
    rows = _observe(
        f"import subprocess as p\nlaunch = p.Popen\n{mutation}\nlaunch([])\n"
    )
    row = _call(rows, "launch")
    assert row["qualification"] == "unknown"
    assert row["target"] is None
    assert "property-binding-may-be-mutated" in cast(list[str], row["reasons"])


def test_module_property_mutation_also_qualifies_from_import_alias_uncertainty() -> (
    None
):
    rows = _observe(
        "import subprocess as p\np.Popen = replacement\n"
        "from subprocess import Popen as launch\nlaunch([])\n"
    )
    assert _call(rows, "launch")["qualification"] == "unknown"


@pytest.mark.parametrize(
    "mutation", ["p.other = replacement", "def change(p):\n    p.Popen = replacement"]
)
def test_unrelated_or_shadowed_property_write_does_not_poison_import_origin(
    mutation: str,
) -> None:
    rows = _observe(f"import subprocess as p\n{mutation}\np.Popen([])\n")
    assert _import(_call(rows, "p.Popen"))["properties"] == ["Popen"]


def test_comprehension_walrus_write_qualifies_the_enclosing_binding() -> None:
    rows = _observe(
        "import subprocess as p\n[(p := unknown) for item in values]\np.Popen([])\n"
    )
    assert _call(rows, "p.Popen")["qualification"] == "unknown"


def _balanced_literal_expression(size: int) -> str:
    if size == 1:
        return "'x'"
    first = size // 2
    return f"({_balanced_literal_expression(first)} + {_balanced_literal_expression(size - first)})"


def test_expression_and_support_bounds_preserve_unknown_without_partial_targets() -> (
    None
):
    rows = _observe("import source as p\n" + "p" + ".member" * 40 + "()\n")
    row = _facts(rows, "call-site")[0]
    assert cast(dict[str, object], row["expression"])["text_truncated"] is True
    assert row["qualification"] == "unknown"
    assert "expression-depth-bound" in cast(list[str], row["reasons"])
    rows = _observe("literal = " + _balanced_literal_expression(64) + "\n")
    literal = _facts(rows, "alias-binding")[0]
    assert literal["qualification"] == "unknown"
    assert literal["literal"] is None
    assert "supporting-range-bound" in cast(list[str], literal["reasons"])


def test_escaped_non_utf8_literal_is_unknown_without_rejecting_valid_source_bytes() -> (
    None
):
    rows = _observe("literal = '\\ud800'\n")
    literal = _facts(rows, "alias-binding")[0]
    assert literal["qualification"] == "unknown"
    assert "literal-not-utf8" in cast(list[str], literal["reasons"])


@pytest.mark.parametrize(
    "mutation",
    [
        'exec("p = other")',
        'def mutate():\n    exec("global p; p = other")',
        'globals()["p"] = other',
        'locals()["p"] = other',
        'vars()["p"] = other',
        'del globals()["p"]',
        'namespace = globals()\nnamespace["p"] = other',
        'globals().update({"p": other})',
        'globals().__setitem__("p", other)',
    ],
)
def test_dynamic_namespace_writes_qualify_dependent_origins_as_unknown(
    mutation: str,
) -> None:
    rows = _observe(f"import subprocess as p\n{mutation}\np.Popen([])\n")
    row = _call(rows, "p.Popen")
    assert row["qualification"] == "unknown"
    assert row["target"] is None
    assert "dynamic-namespace-write" in cast(list[str], row["reasons"])


@pytest.mark.parametrize(
    "body",
    [
        'def use(exec):\n    exec("p = other")\n    p.Popen([])',
        'def use(globals):\n    globals()["p"] = other\n    p.Popen([])',
        'current = globals()["p"]\np.Popen([])',
        'copy = globals().copy()\ncopy["p"] = other\np.Popen([])',
    ],
)
def test_shadowed_or_read_only_namespace_forms_do_not_claim_a_namespace_write(
    body: str,
) -> None:
    rows = _observe("import subprocess as p\n" + body + "\n")
    assert _import(_call(rows, "p.Popen"))["properties"] == ["Popen"]


@pytest.mark.parametrize(
    "source",
    [
        "def helper(callback=helper):\n    return callback()\n",
        "import subprocess as p\ndef helper(callback=helper(p.Popen)):\n    return callback()\n",
        "class Client(Client):\n    pass\n",
        "class Client:\n    result = Client()\n",
    ],
)
def test_immediate_self_reference_cannot_observe_an_unpublished_declaration(
    source: str,
) -> None:
    rows = _observe(source)
    references = [
        row for row in _facts(rows, "reference") if row["name"] in {"helper", "Client"}
    ]
    assert references
    assert all(
        row["qualification"] == "unknown" and row["target"] is None
        for row in references
    )
    assert all(
        "read-before-binding" in cast(list[str], row["reasons"]) for row in references
    )
    assert _facts(rows, "argument-binding") == []


def test_deferred_recursive_body_reference_retains_the_published_declaration_origin() -> (
    None
):
    rows = _observe("def helper():\n    return helper()\n")
    call = _call(rows, "helper")
    assert call["qualification"] == "qualified"
    assert cast(dict[str, object], call["target"])["kind"] == "declaration"


def test_ancestor_global_declaration_redirects_nested_lookup_to_module_scope() -> None:
    source = (
        "import subprocess as p\ndef outer():\n    import another as p\n"
        "    def middle():\n        global p\n        def inner():\n            p.Popen([])\n"
    )
    target = _import(_call(_observe(source), "p.Popen"))
    assert target["module"] == "subprocess"


@pytest.mark.parametrize(
    "body",
    [
        "def use():\n    nonlocal p\n    p.Popen([])\n",
        "def use(p):\n    global p\n    p.Popen([])\n",
        "def outer():\n    import another as p\n    def use(p):\n        nonlocal p\n        p.Popen([])\n",
        "def outer():\n    import another as p\n    def middle():\n        global p\n        def use():\n            nonlocal p\n            p.Popen([])\n",
        "def use():\n    p.Popen([])\n    global p\n",
        "def outer():\n    import another as p\n    def use():\n        p.Popen([])\n        nonlocal p\n",
    ],
)
def test_unqualified_scope_declarations_never_fall_through_to_import_authority(
    body: str,
) -> None:
    row = _call(_observe("import subprocess as p\n" + body), "p.Popen")
    assert row["qualification"] == "unknown"
    assert row["target"] is None
    assert row["reasons"]


def test_nonlocal_lexical_binding_is_qualified_without_resolving_module_names() -> None:
    rows = _observe(
        "import subprocess as p\ndef outer():\n    launch = p.Popen\n"
        "    def use():\n        nonlocal launch\n        launch([])\n"
    )
    assert _import(_call(rows, "launch"))["properties"] == ["Popen"]
