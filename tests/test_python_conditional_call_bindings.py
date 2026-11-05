"""Conditional source use never becomes an unconditional runtime call target."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from hashmarks import CodeMap
from hashmarks.codemap import python_bindings as interpreter
from hashmarks.codemap.python_bindings import python_bindings
from hashmarks.codemap.source_binding_contract import BindingObservationBound
from hashmarks.python_ast_cache import parse_python_ast


def _observe(source: str, *, limit: int = 1_000) -> list[dict[str, object]]:
    raw = source.encode()
    return python_bindings(parse_python_ast(raw), raw, limit)[0]


def _joined(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if row["kind"] == "conditional-call-binding"]


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _strings(value: object) -> list[str]:
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return cast(list[str], value)


def test_callable_default_has_a_conditional_use_but_the_call_stays_unknown() -> None:
    source = "from native import Factory\ndef execute(factory=Factory):\n    return factory()\n"
    rows = _observe(source)
    call = next(row for row in rows if row["kind"] == "call-site")
    assert call["qualification"] == "unknown" and call["target"] is None
    row = _joined(rows)[0]
    assert row["qualification"] == "conditional"
    assert _mapping(row["target"])["module"] == "native"
    assert _mapping(row["target"])["name"] == "Factory"
    assert "default-is-used" in _strings(row["conditions"])
    assert "external-callers-not-observed" in _strings(row["conditions"])
    assert "call-site-execution-not-established" in _strings(row["conditions"])
    assert _mapping(row["input_binding"])["kind"] == "default-binding"
    use = _mapping(row["parameter_use"])
    assert use["qualification"] == "unknown" and use["target"] is None
    assert use["call_range"] == call["range"] == row["range"]
    assert row["runtime_target"] == "not-established"
    assert row["negative_evidence"] == "not-admissible"


def test_single_helper_input_and_aliased_parameter_use_retain_one_edge() -> None:
    rows = _observe(
        "import native\ndef start():\n    return execute(native)\n"
        "def execute(provider):\n    alias=provider\n    launch=alias.Server\n    return launch()\n"
    )
    row = _joined(rows)[0]
    assert row["qualification"] == "conditional"
    target = _mapping(row["target"])
    assert target["module"] == "native" and target["properties"] == ["Server"]
    assert "caller-supplied-value" in _strings(row["conditions"])
    assert "single-observed-local-call" in _strings(row["conditions"])
    assert "external-callers-not-observed" in _strings(row["conditions"])
    assert row["helper_edges"] == 1
    assert _mapping(row["input_call"])["range"] != row["range"]
    assert _mapping(row["parameter"])["name"] == "provider"
    assert all(
        call["target"] is None
        for call in rows
        if call["kind"] == "call-site"
        and _mapping(call["expression"])["text"] == "launch"
    )


def test_unused_defaults_and_foreign_same_named_parameters_are_not_joined() -> None:
    rows = _observe(
        "import native\ndef unused(provider=native):\n    return provider\n"
        "def unrelated(provider):\n    return provider.Server()\n"
    )
    assert any(row["kind"] == "default-binding" for row in rows)
    assert any(row["kind"] == "call-site" for row in rows)
    assert _joined(rows) == []


@pytest.mark.parametrize(
    "source",
    [
        "import native\ndef execute(provider=native):\n    provider=other\n    provider.Server()\n",
        "import native\ndef execute(provider=native):\n    alias=provider\n    alias=other\n    alias.Server()\n",
        "import native\ndef execute(provider):\n    provider.Server()\nexecute(native)\nexecute(other)\n",
        "import native\ndef execute(provider):\n    provider.Server()\nexecute(*values)\n",
        "import native\ndef inner(provider):\n    provider.Server()\ndef outer(value):\n    inner(value)\nouter(native)\n",
    ],
)
def test_ambiguous_dynamic_or_multihop_inputs_do_not_gain_a_target(source: str) -> None:
    rows = _joined(_observe(source))
    assert not any(
        row["qualification"] == "conditional" and row["target"] is not None
        for row in rows
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "provider.Server=other",
        "del provider.Server",
        "setattr(provider, 'Server', other)",
        "native.Server=other",
    ],
)
def test_later_property_writes_withdraw_the_conditional_target(mutation: str) -> None:
    rows = _joined(
        _observe(
            f"import native\ndef execute(provider=native):\n    provider.Server()\n    {mutation}\n"
        )
    )
    assert len(rows) == 1
    assert rows[0]["qualification"] == "unknown" and rows[0]["target"] is None
    assert rows[0]["runtime_target"] == "not-established"
    assert "default-is-used" in _strings(rows[0]["conditions"])
    assert "external-callers-not-observed" in _strings(rows[0]["conditions"])


def test_defaults_and_supplied_inputs_remain_separate_conditional_alternatives() -> (
    None
):
    rows = _joined(
        _observe(
            "import first\nimport second\ndef execute(provider=first):\n    provider.Server()\nexecute(second)\n"
        )
    )
    assert len(rows) == 2
    assert {_mapping(row["target"])["module"] for row in rows} == {"first", "second"}
    assert {_mapping(row["input_binding"])["kind"] for row in rows} == {
        "default-binding",
        "argument-binding",
    }
    assert all(row["qualification"] == "conditional" for row in rows)
    assert all(row["runtime_target"] == "not-established" for row in rows)


def test_support_bound_preserves_conditions_without_a_qualified_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interpreter, "MAX_BINDING_SUPPORTING_RANGES", 2)
    rows = _joined(
        _observe(
            "import native\ndef execute(provider=native):\n    provider.Server()\n"
        )
    )
    assert len(rows) == 1
    assert rows[0]["qualification"] == "unknown" and rows[0]["target"] is None
    assert rows[0]["reasons"] == ["supporting-range-bound"]
    assert "default-is-used" in _strings(rows[0]["conditions"])


def test_conditional_use_bound_qualifies_full_scope_before_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interpreter, "MAX_BINDING_DETAILS", 2)
    source = "import native\ndef execute(provider=native):\n    provider.First()\n    provider.Second()\n    provider.Third()\n"
    with pytest.raises(
        BindingObservationBound, match="conditional-parameter-call-use-bound"
    ):
        _observe(source, limit=1)


def test_public_conditional_rows_bind_original_member_parser_and_fact_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "source.py").write_text(
        "import native\ndef execute(provider=native):\n    provider.Server()\n"
    )
    with CodeMap(tmp_path) as native:
        packet = native.source.bindings("source.py", limit=1_000)
    assert packet["availability"] == "observed" and packet["completeness"] == "complete"
    row = _joined(cast(list[dict[str, object]], packet["facts"]))[0]
    assert row["evidence_identity"]
    assert _mapping(packet["member"])["member_revision"]
    assert (
        _mapping(packet["producer"])["binding_interpreter"]
        == "hashmarks.source-binding-interpreter.v6"
    )
    assert "conditional-call-binding" in _strings(
        _mapping(packet["coverage"])["fact_kinds"]
    )
    assert (
        row["qualification"] == "conditional"
        and row["runtime_target"] == "not-established"
    )


def test_projection_limit_keeps_full_conditional_observation_count_and_denies_absence(
    tmp_path: Path,
) -> None:
    (tmp_path / "source.py").write_text(
        "import native\ndef execute(provider=native):\n    provider.Server()\n"
    )
    with CodeMap(tmp_path) as native:
        full = native.source.bindings("source.py", limit=1_000)
        prefix = native.source.bindings("source.py", limit=1)
    assert any(
        row["kind"] == "conditional-call-binding"
        for row in cast(list[dict[str, object]], full["facts"])
    )
    assert prefix["observed_fact_count"] == full["observed_fact_count"]
    assert prefix["returned_fact_count"] == 1
    assert prefix["completeness"] == "incomplete"
    assert prefix["truncation"] == "truncated"
    assert prefix["negative_evidence"] == "not-admissible"
