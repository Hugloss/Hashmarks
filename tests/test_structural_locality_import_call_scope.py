"""Import identity uses the exact callable scope and preserves real shadowing."""

from pathlib import Path
from textwrap import indent

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


@pytest.mark.parametrize("inside_function", [False, True])
@pytest.mark.parametrize(
    "class_body",
    [
        "global Envelope\nEnvelope = replacement\n",
        "global Envelope\n(Envelope := replacement)\n",
        "class Inner:\n    global Envelope\n    Envelope = replacement\n",
    ],
)
def test_executed_class_global_writes_cannot_gain_imported_call_authority(
    tmp_path: Path, class_body: str, inside_function: bool
) -> None:
    _write_factory(tmp_path)
    declaration = "class Rebind:\n" + indent(class_body, "    ")
    caller = "def publish():\n"
    source = "from factory import Envelope\nfrom other import Envelope as replacement\n"
    source += (
        caller + indent(declaration, "    ")
        if inside_function
        else declaration + caller
    )
    source += "    return Envelope.from_cmd()\n"
    (tmp_path / "consumer.py").write_text(source)
    with CodeMap(tmp_path) as codemap:
        forward = codemap.structure.locality("consumer.py::publish")
        reverse = codemap.structure.locality(
            "factory.py::Envelope.from_cmd", max_depth=0
        )
    call = next(
        row
        for row in assert_records(forward["edges"])
        if row["target_text"] == "Envelope.from_cmd"
    )
    assert call["resolved_symbol_id"] is None
    assert any(
        row["target_text"] == "Envelope.from_cmd"
        for row in assert_records(forward["unresolved_calls"])
        + assert_records(forward["external_or_unindexed_calls"])
    )
    owner = next(
        row
        for row in assert_records(reverse["nodes"])
        if row["symbol_id"] == "factory.py::Envelope.from_cmd"
    )
    assert assert_records(owner["exact_callers"]) == []
    if not inside_function:
        assert any(
            row["path"] == "consumer.py" and row["source"] == "publish"
            for row in assert_records(owner["unresolved_caller_candidates"])
        )


@pytest.mark.parametrize(
    "class_body",
    [
        "Envelope = replacement\n",
        "global Envelope\nvalue = replacement\n",
        "def later(self):\n    global Envelope\n    Envelope = replacement\n",
        "def later(self):\n    class Inner:\n        global Envelope\n        Envelope = replacement\n",
        "class Inner:\n    Envelope = replacement\n",
    ],
)
def test_class_namespace_and_deferred_writes_preserve_imported_call_authority(
    tmp_path: Path, class_body: str
) -> None:
    _write_factory(tmp_path)
    (tmp_path / "consumer.py").write_text(
        "from factory import Envelope\nfrom other import Envelope as replacement\n"
        "class Other:\n"
        + indent(class_body, "    ")
        + "def publish():\n    return Envelope.from_cmd()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::publish")
    call = next(
        row
        for row in assert_records(packet["edges"])
        if row["target_text"] == "Envelope.from_cmd"
    )
    assert call["resolved_symbol_id"] == "factory.py::Envelope.from_cmd"


@pytest.mark.parametrize(
    ("class_body", "member"),
    [
        ("global build\ndef build(): return 1\n", "build"),
        ("global Inner\nclass Inner:\n    def build(): return 1\n", "Inner.build"),
    ],
)
def test_class_global_declarations_cannot_become_exact_class_members(
    tmp_path: Path, class_body: str, member: str
) -> None:
    (tmp_path / "factory.py").write_text(
        "class Factory:\n" + indent(class_body, "    ")
    )
    (tmp_path / "consumer.py").write_text(
        f"from factory import Factory\ndef publish():\n    return Factory.{member}()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::publish")
        reverse = codemap.structure.locality(
            f"factory.py::Factory.{member}", max_depth=0
        )
    call = next(
        row
        for row in assert_records(packet["edges"])
        if row["target_text"] == f"Factory.{member}"
    )
    assert call["resolved_symbol_id"] is None
    assert assert_records(reverse["nodes"])[0]["exact_callers"] == []


def test_nested_class_global_write_does_not_rebind_an_outer_class_member(
    tmp_path: Path,
) -> None:
    (tmp_path / "factory.py").write_text(
        "class Factory:\n    def build(): return 1\n"
        "    class Rebind:\n        global build\n        def build(): return 2\n"
    )
    (tmp_path / "consumer.py").write_text(
        "from factory import Factory\ndef publish():\n    return Factory.build()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::publish")
    call = next(
        row
        for row in assert_records(packet["edges"])
        if row["target_text"] == "Factory.build"
    )
    assert call["resolved_symbol_id"] == "factory.py::Factory.build"


@pytest.mark.parametrize("receiver", ["self", "cls"])
def test_global_function_in_class_syntax_cannot_prove_a_method_receiver(
    tmp_path: Path, receiver: str
) -> None:
    decorator = "    @classmethod\n" if receiver == "cls" else ""
    (tmp_path / "factory.py").write_text(
        "class Factory:\n    global publish\n"
        + decorator
        + f"    def publish({receiver}):\n        return {receiver}.build()\n"
        + "    def build(self): return 1\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("factory.py::Factory.publish")
    call = next(
        row
        for row in assert_records(packet["edges"])
        if row["target_text"] == f"{receiver}.build"
    )
    assert call["resolved_symbol_id"] is None


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


@pytest.mark.parametrize(
    "expression",
    [
        "[Envelope.from_cmd() for Envelope in factories]",
        "{Envelope.from_cmd() for Envelope in factories}",
        "{key: Envelope.from_cmd() for key, Envelope in factories}",
        "(Envelope.from_cmd() for Envelope in factories)",
        "lambda Envelope: Envelope.from_cmd()",
        "lambda *, Envelope: Envelope.from_cmd()",
        "lambda *Envelope: Envelope.from_cmd()",
        "lambda **Envelope: Envelope.from_cmd()",
        "lambda: ((Envelope := factories[0]), Envelope.from_cmd())",
        "lambda: (Envelope.from_cmd(), (Envelope := factories[0]))",
        "[item for Envelope in factories if Envelope.from_cmd() for item in ()]",
        "[item for item in factories for Envelope in Envelope.from_cmd()]",
    ],
)
def test_expression_local_bindings_cannot_gain_import_authority(
    tmp_path: Path, expression: str
) -> None:
    _write_factory(tmp_path)
    (tmp_path / "consumer.py").write_text(
        "from factory import Envelope\n"
        f"def publish(factories):\n    return {expression}\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::publish")
    calls = [
        row
        for row in assert_records(packet["edges"])
        if row["target_text"] == "Envelope.from_cmd"
    ]
    assert len(calls) == 1
    assert calls[0]["resolved_symbol_id"] is None


@pytest.mark.parametrize(
    "expression",
    [
        "[item for Envelope in Envelope.from_cmd() for item in ()]",
        "lambda Envelope=Envelope.from_cmd(): Envelope",
        "lambda: (lambda: (Envelope := None), Envelope.from_cmd())",
    ],
)
def test_expression_headers_preserve_outer_import_authority(
    tmp_path: Path, expression: str
) -> None:
    _write_factory(tmp_path)
    (tmp_path / "consumer.py").write_text(
        f"from factory import Envelope\ndef publish():\n    return {expression}\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::publish")
    calls = [
        row
        for row in assert_records(packet["edges"])
        if row["target_text"] == "Envelope.from_cmd"
    ]
    assert len(calls) == 1
    assert calls[0]["resolved_symbol_id"] == "factory.py::Envelope.from_cmd"


@pytest.mark.parametrize(
    "expression", ["[Envelope for Envelope in factories]", "lambda Envelope: Envelope"]
)
def test_expression_bindings_do_not_hide_later_import_calls(
    tmp_path: Path, expression: str
) -> None:
    _write_factory(tmp_path)
    (tmp_path / "consumer.py").write_text(
        "from factory import Envelope\ndef publish(factories):\n"
        f"    callback = {expression}\n    return Envelope.from_cmd()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::publish")
    calls = [
        row
        for row in assert_records(packet["edges"])
        if row["target_text"] == "Envelope.from_cmd"
    ]
    assert len(calls) == 1
    assert calls[0]["resolved_symbol_id"] == "factory.py::Envelope.from_cmd"


@pytest.mark.parametrize(
    "expression", ["[build() for build in factories]", "lambda build: build()"]
)
def test_plain_expression_local_calls_cannot_gain_import_authority(
    tmp_path: Path, expression: str
) -> None:
    (tmp_path / "factory.py").write_text("def build(): return 1\n")
    (tmp_path / "consumer.py").write_text(
        f"from factory import build\ndef publish(factories):\n    return {expression}\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::publish")
    calls = [
        row for row in assert_records(packet["edges"]) if row["target_text"] == "build"
    ]
    assert len(calls) == 1
    assert calls[0]["resolved_symbol_id"] is None


def test_module_expression_bindings_do_not_become_exact_imported_callers(
    tmp_path: Path,
) -> None:
    _write_factory(tmp_path)
    (tmp_path / "consumer.py").write_text(
        "from factory import Envelope\n"
        "def publish():\n    return Envelope.from_cmd()\n"
        "callbacks = [Envelope.from_cmd() for Envelope in factories]\n"
        "callback = lambda Envelope: Envelope.from_cmd()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality(
            "factory.py::Envelope.from_cmd", max_depth=0
        )
    node = next(
        row
        for row in assert_records(packet["nodes"])
        if row["symbol_id"] == "factory.py::Envelope.from_cmd"
    )
    assert {
        (row["path"], row["source"]) for row in assert_records(node["exact_callers"])
    } == {("consumer.py", "publish")}


def test_same_line_shadowing_cannot_strengthen_an_indistinguishable_call(
    tmp_path: Path,
) -> None:
    _write_factory(tmp_path)
    (tmp_path / "consumer.py").write_text(
        "from factory import Envelope\ndef publish(factories):\n"
        "    return Envelope.from_cmd(), [Envelope.from_cmd() for Envelope in factories]\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::publish")
        reverse = codemap.structure.locality(
            "factory.py::Envelope.from_cmd", max_depth=0
        )
    calls = [
        row
        for row in assert_records(packet["edges"])
        if row["target_text"] == "Envelope.from_cmd"
    ]
    assert calls
    assert all(row["resolved_symbol_id"] is None for row in calls)
    assert any(
        row["target_text"] == "Envelope.from_cmd"
        for row in assert_records(packet["unresolved_calls"])
    )
    target = next(
        row
        for row in assert_records(reverse["nodes"])
        if row["symbol_id"] == "factory.py::Envelope.from_cmd"
    )
    assert target["exact_callers"] == []
    assert any(
        row["source"] == "publish"
        for row in assert_records(target["unresolved_caller_candidates"])
    )
