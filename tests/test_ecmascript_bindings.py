"""Source-local bindings qualify authored provenance, never runtime call targets."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_array, assert_integer, assert_object, assert_text

from hashmarks.codemap import ecmascript_binding_scope
from hashmarks.codemap.ecmascript_bindings import ecmascript_bindings
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.codemap.source_binding_contract import BindingObservationBound

if TYPE_CHECKING:
    from collections.abc import Sequence


@pytest.fixture(scope="module")
def native() -> TreeSitterRangeProvider:
    pytest.importorskip("tree_sitter_language_pack")
    provider = TreeSitterRangeProvider.auto()
    assert provider.available
    return provider


def _observe(
    native: TreeSitterRangeProvider,
    source: str,
    *,
    grammar: str = "typescript",
    limit: int = 1000,
) -> tuple[list[dict[str, object]], int]:
    raw = source.encode()
    tree = native.syntax_tree(raw, grammar)
    assert tree is not None
    return ecmascript_bindings(tree, raw, limit)


def _kind(rows: Sequence[dict[str, object]], kind: str) -> list[dict[str, object]]:
    return [row for row in rows if row["kind"] == kind]


def _calls(native: TreeSitterRangeProvider, source: str) -> list[dict[str, object]]:
    return _kind(_observe(native, source)[0], "call-site")


def _global(name: str, *properties: str) -> dict[str, object]:
    return {
        "kind": "lexical-global",
        "name": name,
        "properties": list(properties),
        "runtime_identity": "not-established",
    }


def _slice(source: str, span: object) -> str:
    record = assert_object(span)
    return source.encode()[
        assert_integer(record["start_byte"]) : assert_integer(record["end_byte"])
    ].decode()


def test_computed_const_alias_uses_complete_native_bytes_and_exact_proof(
    native: TreeSitterRangeProvider,
) -> None:
    source = (
        "// café\nconst key = 'fe' + 'tch'; "
        "const transport = globalThis[key]; transport('/api');"
    )
    rows, total = _observe(native, source)
    call = _kind(rows, "call-site")[0]
    assert total == len(rows)
    assert call["qualification"] == "qualified"
    assert call["target"] == _global("globalThis", "fetch")
    assert call["runtime_target"] == "not-established"
    assert _slice(source, call["range"]) == "transport('/api')"
    ranges = call["supporting_ranges"]
    assert isinstance(ranges, list)
    assert {"key", "'fe' + 'tch'", "transport", "globalThis[key]"} <= {
        _slice(source, span) for span in ranges
    }
    assert all(row["runtime_target"] == "not-established" for row in rows)


def test_default_named_namespace_and_const_import_aliases(
    native: TreeSitterRangeProvider,
) -> None:
    calls = _calls(
        native,
        "import primary, {fetch as send} from 'client'; "
        "import * as registry from 'registry'; const invoke=send; "
        "primary(); invoke(); registry.send();",
    )
    assert [call["qualification"] for call in calls] == ["qualified"] * 3
    assert [call["target"] for call in calls] == [
        {
            "kind": "import",
            "module": module,
            "name": name,
            "level": 0,
            "properties": properties,
            "module_resolution": "not-performed",
        }
        for module, name, properties in [
            ("client", "default", []),
            ("client", "fetch", []),
            ("registry", "*", ["send"]),
        ]
    ]


def test_nested_shorthand_and_computed_object_destructuring(
    native: TreeSitterRangeProvider,
) -> None:
    calls = _calls(
        native,
        "const key='fe'+'tch'; "
        "const { [key]: transport, nested:{run}, ordinary } = globalThis; "
        "transport();run();ordinary();",
    )
    assert [call["target"] for call in calls] == [
        _global("globalThis", "fetch"),
        _global("globalThis", "nested", "run"),
        _global("globalThis", "ordinary"),
    ]
    assert all(call["qualification"] == "qualified" for call in calls)


def test_captured_alias_retains_initialization_condition_and_parameter_shadow(
    native: TreeSitterRangeProvider,
) -> None:
    calls = _calls(
        native,
        "const transport=globalThis.fetch; "
        "function outer(){transport();} "
        "function shadow(transport){transport();}",
    )
    assert calls[0]["qualification"] == "conditional"
    assert calls[0]["target"] == _global("globalThis", "fetch")
    assert calls[0]["conditions"] == ["captured-binding-initialization-not-observed"]
    assert calls[1]["qualification"] == "unknown"
    assert calls[1]["target"] is None
    assert calls[1]["reasons"] == ["parameter-value-unknown"]
    assert calls[0]["scope"] != calls[1]["scope"]


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("fetch(); const fetch=globalThis.fetch;", "binding-before-initialization"),
        (
            "const fetch=fetch; fetch();",
            "alias-cycle-or-depth-bound",
        ),
        ("fetch(); class fetch {}", "binding-before-initialization"),
        (
            "let fetch=globalThis.fetch; fetch();",
            "mutable-or-unsupported-binding",
        ),
        (
            "function f(){fetch(); if(other){var fetch=other;}}",
            "mutable-or-unsupported-binding",
        ),
        (
            "const fetch=globalThis.fetch; fetch=other; fetch();",
            "binding-reassigned",
        ),
        ("fetch(); fetch=other;", "global-name-reassigned"),
        ("const fetch=globalThis.fetch; ++fetch; fetch();", "binding-reassigned"),
        (
            "const fetch=globalThis.fetch; ({fetch}=other); fetch();",
            "binding-reassigned",
        ),
        ("const [fetch]=other; fetch();", "unsupported-destructuring"),
        (
            "const {fetch=other}=globalThis; fetch();",
            "destructuring-default-not-selected",
        ),
    ],
)
def test_late_shadow_mutable_and_written_bindings_never_become_globals(
    native: TreeSitterRangeProvider, source: str, reason: str
) -> None:
    call = _calls(native, source)[0]
    assert call["qualification"] == "unknown"
    assert call["target"] is None
    assert reason in assert_array(call["reasons"])


def test_block_loop_catch_and_method_names_respect_lexical_ownership(
    native: TreeSitterRangeProvider,
) -> None:
    calls = _calls(
        native,
        "{ const fetch=globalThis.fetch; fetch(); } fetch(); "
        "for (const fetch of values) { fetch(); } fetch(); "
        "try {} catch(fetch) {fetch();} fetch(); "
        "class X { fetch() {fetch();} } namespace A {var fetch;} fetch();",
    )
    assert [call["target"] for call in calls] == [
        _global("globalThis", "fetch"),
        _global("fetch"),
        None,
        _global("fetch"),
        None,
        _global("fetch"),
        _global("fetch"),
        _global("fetch"),
    ]


@pytest.mark.parametrize(
    "source",
    [
        "import type {fetch} from 'client'; fetch();",
        "import {type fetch} from 'client'; fetch();",
        "declare const fetch: unknown; fetch();",
        "declare function fetch(): void; fetch();",
        "type fetch = string; fetch();",
        "interface fetch {} fetch();",
        "import fetch = require('client'); fetch();",
        "import fetch = Client.fetch; fetch();",
        "import {fetch} from '\\x63lient'; fetch();",
        r"const \u0066etch=other; fetch();",
        r"import {fetch as \u0066etch} from 'client'; fetch();",
    ],
)
def test_type_only_ambient_and_unqualified_import_names_shadow_value_uses(
    native: TreeSitterRangeProvider, source: str
) -> None:
    call = _calls(native, source)[-1]
    assert call["qualification"] == "unknown"
    assert call["target"] is None
    assert call["reasons"]


@pytest.mark.parametrize(
    "write",
    [
        "globalThis.fetch=other;",
        "delete globalThis.fetch;",
        "globalThis.fetch++;",
        "globalThis[key]=other;",
        "({value:globalThis.fetch}=other);",
        "const receiver=globalThis; receiver.fetch=other;",
    ],
)
def test_source_property_writes_are_seen_before_result_clipping(
    native: TreeSitterRangeProvider, write: str
) -> None:
    source = "globalThis.fetch(); " + write
    rows, total = _observe(native, source)
    clipped, clipped_total = _observe(native, source, limit=3)
    assert clipped == rows[:3]
    assert clipped_total == total > 3
    call = _kind(clipped, "call-site")[0]
    assert call["qualification"] == "unknown"
    assert call["target"] is None
    assert call["reasons"] == ["source-property-reassigned"]


def test_defaults_do_not_specialize_parameters_or_see_body_var_bindings(
    native: TreeSitterRangeProvider,
) -> None:
    source = "function f(fetch=globalThis.fetch) {var globalThis; fetch();} f(other);"
    rows, _ = _observe(native, source)
    default = _kind(rows, "default-binding")[0]
    assert default["qualification"] == "conditional"
    assert default["target"] == _global("globalThis", "fetch")
    assert default["conditions"] == [
        "argument-or-property-override-possible",
        "default-binding-only",
    ]
    parameter = assert_object(default["parameter"])
    assert parameter["name"] == "fetch"
    assert _slice(source, parameter["range"]) == "fetch"
    body_call = _kind(rows, "call-site")[0]
    assert body_call["qualification"] == "unknown"
    assert body_call["reasons"] == ["parameter-value-unknown"]


@pytest.mark.parametrize(
    "source",
    [
        "declare const {request = globalThis.fetch}: any; request();",
        "declare namespace N { const {request = globalThis.fetch}: any; }",
    ],
)
def test_ambient_defaults_inherit_binding_qualification(
    native: TreeSitterRangeProvider, source: str
) -> None:
    rows, _ = _observe(native, source)
    default = _kind(rows, "default-binding")[0]
    assert default["qualification"] == "unknown"
    assert default["target"] is None
    assert default["literal"] is None
    assert default["reasons"] == ["type-only-or-ambient-binding"]
    assert _slice(source, default["range"]) == "globalThis.fetch"


def test_global_augmentation_keeps_ambient_uncertainty_without_overriding_locals(
    native: TreeSitterRangeProvider,
) -> None:
    augmentation = "export {}; declare global { const request: unknown; } "
    call = _calls(native, augmentation + "request();")[0]
    assert call["qualification"] == "unknown"
    assert call["target"] is None
    assert call["reasons"] == ["type-only-or-ambient-binding"]
    local = _calls(native, augmentation + "const request=globalThis.fetch; request();")[
        0
    ]
    assert local["qualification"] == "qualified"
    assert local["target"] == _global("globalThis", "fetch")


@pytest.mark.parametrize(
    "declaration",
    [
        "@decorate class Client {}",
        "@decorate export class Client {}",
        "export @decorate class Client {}",
    ],
)
def test_decorated_class_does_not_establish_the_transformed_binding(
    native: TreeSitterRangeProvider, declaration: str
) -> None:
    call = _calls(native, declaration + " new Client();")[0]
    assert call["qualification"] == "unknown"
    assert call["target"] is None
    assert call["reasons"] == ["decorated-declaration"]


def test_property_write_prefix_invalidates_descendants_without_sibling_leakage(
    native: TreeSitterRangeProvider,
) -> None:
    calls = _calls(
        native,
        "globalThis.channel.send(); globalThis.other.send(); "
        "another.channel.send(); globalThis.channel=other;",
    )
    assert calls[0]["qualification"] == "unknown"
    assert calls[0]["reasons"] == ["source-property-reassigned"]
    assert calls[1]["qualification"] == "qualified"
    assert calls[1]["target"] == _global("globalThis", "other", "send")
    assert calls[2]["qualification"] == "qualified"
    assert calls[2]["target"] == _global("another", "channel", "send")


@pytest.mark.parametrize(
    "write", ["client[key].send", "(client[key]).send", "client[key].deep.send"]
)
def test_nested_dynamic_property_write_invalidates_the_known_import_prefix(
    native: TreeSitterRangeProvider, write: str
) -> None:
    calls = _calls(
        native,
        f"import {{client, other}} from 'pkg'; {write}=replacement; "
        "client.child.send('x'); other.child.send('x');",
    )
    assert calls[0]["qualification"] == "unknown"
    assert calls[0]["target"] is None
    assert calls[0]["reasons"] == ["source-property-reassigned"]
    assert calls[1]["qualification"] == "qualified"
    assert assert_object(calls[1]["target"])["name"] == "other"


@pytest.mark.parametrize("grammar", ["javascript", "typescript", "tsx"])
def test_conditional_annex_b_declaration_cannot_establish_a_function_binding(
    native: TreeSitterRangeProvider, grammar: str
) -> None:
    rows, _ = _observe(
        native, "if (flag) function fetch() {}\nfetch('x');", grammar=grammar
    )
    call = _kind(rows, "call-site")[0]
    assert call["qualification"] == "unknown"
    assert call["target"] is None
    assert call["reasons"] == ["conditional-function-declaration"]


def test_unqualified_deep_write_cannot_silently_miss_its_mutated_base(
    native: TreeSitterRangeProvider,
) -> None:
    source = "client[key]" + ".child" * 34 + "=other; client.child();"
    with pytest.raises(BindingObservationBound, match="property-write-depth-bound"):
        _observe(native, source)


def test_each_direct_helper_argument_remains_a_separate_conditional_observation(
    native: TreeSitterRangeProvider,
) -> None:
    source = (
        "function f(value){value();} const invoke=f; "
        "invoke(globalThis.fetch); f(other); f.property(globalThis.fetch);"
    )
    rows, _ = _observe(native, source)
    arguments = _kind(rows, "argument-binding")
    assert len(arguments) == 2
    assert [row["target"] for row in arguments] == [
        _global("globalThis", "fetch"),
        _global("other"),
    ]
    assert all(row["qualification"] == "conditional" for row in arguments)
    assert all(
        row["conditions"] == ["observed-direct-call-only", "other-callers-not-excluded"]
        for row in arguments
    )
    assert arguments[0]["parameter"] == arguments[1]["parameter"]
    assert arguments[0]["call"] != arguments[1]["call"]
    assert _slice(source, assert_object(arguments[0]["call"])["range"]) == (
        "invoke(globalThis.fetch)"
    )
    assert _kind(rows, "call-site")[0]["reasons"] == ["parameter-value-unknown"]


def test_helper_flow_never_specializes_through_a_second_call_edge(
    native: TreeSitterRangeProvider,
) -> None:
    rows, _ = _observe(
        native,
        "function first(value){second(value);} "
        "function second(value){value();} first(globalThis.fetch);",
    )
    arguments = _kind(rows, "argument-binding")
    assert len(arguments) == 2
    assert arguments[0]["qualification"] == "unknown"
    assert arguments[0]["target"] is None
    assert arguments[1]["target"] == _global("globalThis", "fetch")
    calls = _kind(rows, "call-site")
    assert calls[1]["qualification"] == "unknown"


def test_spread_and_captured_optional_helper_relations_retain_conditions(
    native: TreeSitterRangeProvider,
) -> None:
    rows, _ = _observe(
        native,
        "function f(first,second){} const invoke=f; "
        "function captured(){invoke?.(globalThis.fetch);} f(...items,other);",
    )
    arguments = _kind(rows, "argument-binding")
    assert arguments[0]["qualification"] == "conditional"
    assert {
        "captured-binding-initialization-not-observed",
        "optional-call",
    } <= set(assert_array(arguments[0]["conditions"]))
    assert [row["qualification"] for row in arguments[1:]] == ["unknown", "unknown"]


@pytest.mark.parametrize(
    "key",
    ["dynamic", "`fetch`", "`fe${suffix}`", "'\\x66etch'", "'fe'+1"],
)
def test_dynamic_or_unqualified_keys_do_not_acquire_property_identity(
    native: TreeSitterRangeProvider, key: str
) -> None:
    call = _calls(native, f"const key={key}; globalThis[key]();")[0]
    assert call["qualification"] == "unknown"
    assert call["target"] is None


def test_literal_limit_is_independent_of_display_preview(
    native: TreeSitterRangeProvider,
) -> None:
    key = "x" * 256
    rows, _ = _observe(native, f"const key='{key}'; globalThis[key]();")
    binding = next(row for row in rows if row["name"] == "key")
    assert binding["literal"] == key
    assert assert_object(binding["expression"])["text_truncated"] is True
    assert _kind(rows, "call-site")[0]["target"] == _global("globalThis", key)
    call = _calls(native, f"const key='{key}x'; globalThis[key]();")[0]
    assert call["qualification"] == "unknown"
    assert call["target"] is None


def test_alias_depth_counts_aliases_without_counting_terminal_import(
    native: TreeSitterRangeProvider,
) -> None:
    source = "import {fetch as imported} from 'client';"
    for index in range(9):
        source += (
            f"const alias{index}={'imported' if index == 0 else f'alias{index - 1}'};"
        )
    calls = _calls(native, source + "alias7();alias8();")
    assert calls[0]["qualification"] == "qualified"
    assert assert_object(calls[0]["target"])["name"] == "fetch"
    assert calls[1]["qualification"] == "unknown"
    assert calls[1]["reasons"] == ["alias-cycle-or-depth-bound"]


def test_full_scope_node_bound_cannot_be_hidden_by_small_result_limit(
    native: TreeSitterRangeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ecmascript_binding_scope, "MAX_BINDING_NODES", 4)
    with pytest.raises(BindingObservationBound, match="binding-node-bound"):
        _observe(native, "const alias=globalThis.fetch; alias();", limit=1)


def test_unknown_write_proof_retains_a_bounded_supporting_range_list(
    native: TreeSitterRangeProvider,
) -> None:
    source = "const fetch=globalThis.fetch;" + "fetch=other;" * 70 + "fetch();"
    call = _calls(native, source)[0]
    assert call["qualification"] == "unknown"
    assert "binding-reassigned" in assert_array(call["reasons"])
    support = call["supporting_ranges"]
    assert isinstance(support, list)
    assert len(support) <= 64


@pytest.mark.parametrize(
    ("grammar", "source"),
    [
        ("javascript", "const invoke=globalThis.fetch; invoke();"),
        ("typescript", "const invoke=(globalThis.fetch as Callable)!; invoke();"),
        (
            "tsx",
            "const invoke=globalThis.fetch; "
            "export const view=<Panel action={()=>invoke('/api')}/>;",
        ),
    ],
)
def test_native_grammar_and_type_wrappers_preserve_value_binding_scope(
    native: TreeSitterRangeProvider, grammar: str, source: str
) -> None:
    rows, _ = _observe(native, source, grammar=grammar)
    call = _kind(rows, "call-site")[0]
    assert call["target"] == _global("globalThis", "fetch")
    assert call["qualification"] == ("conditional" if grammar == "tsx" else "qualified")
    assert all(
        row["qualification"] == "unknown"
        for row in rows
        if assert_text(assert_object(row["expression"])["text"]) == "Panel"
    )


def test_direct_eval_and_with_keep_lexical_identity_unknown(
    native: TreeSitterRangeProvider,
) -> None:
    rows, _ = _observe(native, "with(context){fetch();} fetch();", grammar="javascript")
    calls = _kind(rows, "call-site")
    assert calls[0]["qualification"] == "unknown"
    assert calls[0]["reasons"] == ["dynamic-lexical-scope"]
    assert calls[1]["target"] == _global("fetch")
    call = _calls(native, "function f(){eval(source); fetch();}")[-1]
    assert call["qualification"] == "unknown"
    assert call["reasons"] == ["dynamic-lexical-scope"]
