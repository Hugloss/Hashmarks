"""Backend change-intelligence B01–B05: direct line ranges, never inferred impact."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashmarks.codemap import ChangeImpactOptions, CodeMap
from hashmarks.codemap.change_line_evidence import (
    MAX_CHANGED_SPANS,
    normalize_changed_line_spans,
)
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation
from hashmarks.mcp_surface import HashmarksMcpSurface
from hashmarks.repository_cli import _changed_line_span_args

PATH = "src/backend.py"
TASK = "Fix the backend widget returned from process_widget"


def _repo(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / PATH).write_text(
        "def process_widget(value):\n"
        "    result = value + 1\n"
        "    return result\n\n"
        "def other_widget(value):\n"
        "    return value - 1\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_backend.py").write_text(
        "from src.backend import process_widget\n\n"
        "def test_widget():\n"
        "    assert process_widget(2) == 3\n",
        encoding="utf-8",
    )


def _options(
    *,
    start: int = 2,
    end: int = 3,
    path: str = PATH,
) -> ChangeImpactOptions:
    return ChangeImpactOptions(
        changed_line_spans=[{"path": path, "start_line": start, "end_line": end}]
    )


def test_direct_changed_lines_preserve_owner_and_verifier_surfaces(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        plain = cm.task_change_impact(TASK, [PATH])
        augmented = cm.task_change_impact(TASK, [PATH], options=_options())
    assert "changed_line_evidence" not in plain
    assert augmented["changed"] == plain["changed"]
    assert augmented["surfaces"] == plain["surfaces"]
    assert augmented["authority"] == "advisory"
    evidence = augmented["changed_line_evidence"]
    assert evidence["input_authority"] == "caller-reported-line-spans"
    assert evidence["runtime_impact"] == "not-asserted"
    assert evidence["verification_coverage"] == "not-asserted"
    row = evidence["observations"][0]
    assert row["state"] == "source-index-correspondence-observed"
    assert row["member_state"] == "known-present"
    assert row["symbol_coverage"] == "complete-index-range-query"
    assert row["member_revision"]
    assert row["negative_evidence_admissible"] is False
    symbols = row["symbols"]
    assert len(symbols) == 1
    assert symbols[0]["subject"] == "src/backend.py::process_widget"
    assert symbols[0]["overlap"] == {"start_line": 2, "end_line": 3}
    assert symbols[0]["semantic_impact"] == "not-asserted"
    assert symbols[0]["relationship_detail"] == {
        "target": "src/backend.py::process_widget",
        "result_mode": "relationships",
    }
    presentation = present_repository_evidence(augmented, format="compact")
    assert validate_evidence_presentation(augmented, presentation)["valid"] is True
    assert "/changed_line_evidence" in json.dumps(presentation)


def test_changed_lines_are_not_implicit_at_file_scope(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = cm.task_change_impact(TASK, [PATH], options=_options(start=4, end=4))
    row = impact["changed_line_evidence"]["observations"][0]
    assert row["state"] == "source-index-correspondence-observed"
    assert row["symbols"] == []
    assert row["symbol_coverage"] == "complete-index-range-query"
    assert row["negative_evidence_admissible"] is False


def test_changed_lines_outside_source_never_claim_missing_symbol(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = cm.task_change_impact(TASK, [PATH], options=_options(start=20, end=20))
    row = impact["changed_line_evidence"]["observations"][0]
    assert row["state"] == "unresolved"
    assert row["reason"] == "span-outside-current-source"
    assert row["symbols"] == []
    assert row["symbol_coverage"] == "unknown"


@pytest.mark.parametrize(
    "spans",
    [
        "src/backend.py:2:3",
        [{"path": PATH, "start_line": True, "end_line": 3}],
        [{"path": PATH, "start_line": 3, "end_line": False}],
        [{"path": PATH, "start_line": 0, "end_line": 2}],
        [{"path": PATH, "start_line": 4, "end_line": 2}],
        [{"path": PATH, "start_line": 1, "end_line": 129}],
        [{"path": "tests/test_backend.py", "start_line": 1, "end_line": 2}],
        [{"path": "../secret.py", "start_line": 1, "end_line": 2}],
        [{"path": PATH, "start_line": 1, "end_line": 2, "trust": True}],
        [{"path": PATH, "start_line": 1, "end_line": 2}] * 2,
        [
            {"path": PATH, "start_line": n + 1, "end_line": n + 1}
            for n in range(MAX_CHANGED_SPANS + 1)
        ],
    ],
)
def test_bad_spans_fail_before_sync(tmp_path: Path, spans: object) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as cm:

        def forbidden_sync(*args, **kwargs):
            raise AssertionError("work before range admission")

        cm.sync = forbidden_sync  # type: ignore[method-assign]
        with pytest.raises(ValueError):
            cm.task_change_impact(
                TASK,
                [PATH],
                options=ChangeImpactOptions(changed_line_spans=spans),  # type: ignore[arg-type]
            )


def test_order_is_deterministic_and_max_span_count_is_inclusive() -> None:
    spans = [
        {"path": PATH, "start_line": n + 1, "end_line": n + 1}
        for n in reversed(range(MAX_CHANGED_SPANS))
    ]
    normal = normalize_changed_line_spans(spans, [PATH])
    assert len(normal) == MAX_CHANGED_SPANS
    assert normal == normalize_changed_line_spans(list(reversed(spans)), [PATH])
    assert normal[0]["start_line"] == 1


def test_source_denial_does_not_expose_symbol_names(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "src/backend.py"\nvisibility = "deny"\n'
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = cm.task_change_impact(TASK, [PATH], options=_options())
    row = impact["changed_line_evidence"]["observations"][0]
    assert row["state"] == "unresolved"
    assert row["symbols"] == []


def test_sparse_source_or_unsupported_file_has_unknown_coverage(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "src/other.txt").write_bytes(b"\xff\x80")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = cm.task_change_impact(
            TASK,
            [PATH, "src/other.txt"],
            options=_options(path="src/other.txt", start=1, end=1),
        )
    row = impact["changed_line_evidence"]["observations"][0]
    assert row["state"] == "unresolved"
    assert row["symbols"] == []


def test_overlap_is_bounded_with_excess_reported(tmp_path: Path) -> None:
    _repo(tmp_path)
    nested = ["def fn_0():", "    return 1"]
    for index in range(1, 40):
        nested.extend([f"def fn_{index}():", "    return 1"])
    (tmp_path / PATH).write_text("\n".join(nested) + "\n")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = cm.task_change_impact(
            TASK,
            [PATH],
            options=_options(start=1, end=80),
        )
    row = impact["changed_line_evidence"]["observations"][0]
    assert row["symbol_retained_count"] <= 32
    assert row["negative_evidence_admissible"] is False


def test_mcp_native_and_compact_reuse_same_source_owner(tmp_path: Path) -> None:
    _repo(tmp_path)
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        value = surface.change_impact(
            TASK,
            [PATH],
            changed_line_spans=[{"path": PATH, "start_line": 2, "end_line": 3}],
        )
    finally:
        surface.close()
    assert (
        value["changed_line_evidence"]["observations"][0]["symbols"][0]["subject"]
        == "src/backend.py::process_widget"
    )


def test_cli_span_parser_is_explicit_and_leaves_proof_to_core() -> None:
    assert _changed_line_span_args(None) is None
    assert _changed_line_span_args(["src/backend.py:2:3"]) == [
        {"path": "src/backend.py", "start_line": 2, "end_line": 3}
    ]


@pytest.mark.parametrize(
    "value", ["src/backend.py:2", "src/backend.py:x:2", "src/backend.py:-1:2"]
)
def test_cli_span_parser_rejects_malformed_bounds_without_new_exception_owner(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="changed-line-span"):
        _changed_line_span_args([value])


def test_backend_route_decorator_maps_to_handler_without_false_symbol_overlap(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / PATH).write_text(
        "@router.get(\n"
        '    "/widgets"\n'
        ")\n"
        "@cached\n"
        "async def process_widget(value):\n"
        "    return value\n\n"
        "def other_widget(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = cm.task_change_impact(TASK, [PATH], options=_options(start=2, end=2))
    row = impact["changed_line_evidence"]["observations"][0]
    assert row["state"] == "source-index-correspondence-observed"
    assert row["symbols"] == []  # Def starts after the edited decorator.
    evidence = row["decorator_associations"]
    assert evidence["state"] == "bounded-python-decorator-syntax"
    assert evidence["negative_evidence_admissible"] is False
    assert evidence["unresolved_count"] == 0
    assert evidence["omitted_count"] == 0
    assert len(evidence["associations"]) == 1
    observed = evidence["associations"][0]
    assert observed["subject"] == "src/backend.py::process_widget"
    assert observed["declaration_line"] == 5
    assert observed["indexed_symbol_range"]["start_line"] == 5
    assert observed["overlapping_decorator_ranges"] == [
        {"start_line": 1, "end_line": 3}
    ]
    assert observed["runtime_registration"] == "not-asserted"
    assert observed["semantic_impact"] == "not-asserted"
    presentation = present_repository_evidence(impact, format="compact")
    assert validate_evidence_presentation(impact, presentation)["valid"] is True


def test_backend_nested_method_decorator_is_not_confused_with_enclosing_class(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / PATH).write_text(
        "class WidgetView:\n"
        '    @router.post("/widgets")\n'
        "    def process_widget(self, value):\n"
        "        return value\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = cm.task_change_impact(TASK, [PATH], options=_options(start=2, end=2))
    row = impact["changed_line_evidence"]["observations"][0]
    # The enclosing class overlaps the edited line; the method declaration
    # starts later. The separate syntax association must bind exactly.
    assert [s["qualname"] for s in row["symbols"]] == ["WidgetView"]
    associations = row["decorator_associations"]["associations"]
    assert len(associations) == 1
    assert associations[0]["subject"] == "src/backend.py::WidgetView.process_widget"
    assert associations[0]["declaration_line"] == 3


def test_backend_decorator_association_is_bounded_and_never_negative(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    lines = []
    for number in range(20):
        lines.extend(
            [
                "@decorator",
                f"def handler_{number}():",
                "    return 1",
            ]
        )
    (tmp_path / PATH).write_text("\n".join(lines) + "\n", encoding="utf-8")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = cm.task_change_impact(
            TASK, [PATH], options=_options(start=1, end=len(lines))
        )
    evidence = impact["changed_line_evidence"]["observations"][0][
        "decorator_associations"
    ]
    assert evidence["matched_declaration_count"] == 20
    assert evidence["retained_count"] == 16
    assert evidence["omitted_count"] == 4
    assert evidence["negative_evidence_admissible"] is False
    assert [x["name"] for x in evidence["associations"]] == [
        f"handler_{number}" for number in range(16)
    ]


def test_backend_decorator_evidence_absent_when_source_is_denied(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / PATH).write_text(
        '@router.get("/secret")\ndef process_widget(value):\n    return value\n',
        encoding="utf-8",
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "src/backend.py"\nvisibility = "deny"\n'
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = cm.task_change_impact(TASK, [PATH], options=_options(start=1, end=1))
    row = impact["changed_line_evidence"]["observations"][0]
    assert row["state"] == "unresolved"
    assert row["symbols"] == []
    assert "decorator_associations" not in row


def test_backend_python_decorator_parse_bound_is_explicit() -> None:
    from hashmarks.codemap.change_decorator_evidence import (
        MAX_DECORATOR_SOURCE_BYTES,
        observe_python_decorator_associations,
    )

    class _NoIndex:
        def symbols_overlapping_lines(self, *args, **kwargs):
            raise AssertionError("index work before input-size admission")

    evidence = observe_python_decorator_associations(
        _NoIndex(),
        PATH,
        b"#" * (MAX_DECORATOR_SOURCE_BYTES + 1),
        {"start_line": 1, "end_line": 1},
    )
    assert evidence is not None
    assert evidence["state"] == "unresolved"
    assert evidence["reason"] == "python-decorator-source-over-bound"
    assert evidence["negative_evidence_admissible"] is False


def test_backend_changed_auth_decorator_shows_adjacent_route_syntax(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / PATH).write_text(
        "@auth.required\n"
        "@router.get(\n"
        '    "/widgets"\n'
        ")\n"
        "async def process_widget(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        result = cm.task_change_impact(TASK, [PATH], options=_options(start=1, end=1))
    row = result["changed_line_evidence"]["observations"][0]
    assert row["symbols"] == []
    (association,) = row["decorator_associations"]["associations"]
    context = association["decorator_context"]
    assert context["state"] == "bounded-current-python-ast-decorator-syntax"
    assert context["runtime_registration"] == "not-asserted"
    assert context["negative_evidence_admissible"] is False
    assert context["omitted_count"] == 0
    assert len(context["observations"]) == 2
    auth, route = context["observations"]
    assert auth["intersects_reported_span"] is True
    assert auth["callee_syntax"] == {
        "state": "simple-member",
        "receiver_syntax": "auth",
        "member_syntax": "required",
    }
    assert route["intersects_reported_span"] is False
    assert route["start_line"] == 2
    assert route["end_line"] == 4
    assert route["callee_syntax"] == {
        "state": "simple-member",
        "receiver_syntax": "router",
        "member_syntax": "get",
    }
    assert route["arguments"]["first_positional_string"] == {
        "state": "literal",
        "value": "/widgets",
    }
    assert route["arguments"]["path_keyword_string"] == {"state": "not-supplied"}
    assert route["arguments"]["has_argument_expansion"] is False
    presentation = present_repository_evidence(result, format="compact")
    assert validate_evidence_presentation(result, presentation)["valid"] is True


def test_backend_decorator_call_arguments_preserve_dynamic_and_unpacking(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / PATH).write_text(
        "@router.get(make_path(), **route_options)\n"
        "async def process_widget(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        result = cm.task_change_impact(TASK, [PATH], options=_options(start=1, end=1))
    ctx = result["changed_line_evidence"]["observations"][0]["decorator_associations"][
        "associations"
    ][0]["decorator_context"]
    (site,) = ctx["observations"]
    assert site["callee_syntax"]["member_syntax"] == "get"
    assert site["arguments"]["first_positional_string"] == {
        "state": "dynamic-or-unsupported"
    }
    assert site["arguments"]["path_keyword_string"] == {"state": "not-supplied"}
    assert site["arguments"]["has_argument_expansion"] is True


def test_backend_decorator_context_prioritizes_edited_under_bound(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    lines = [f"@dec_{i}" for i in range(9)]
    lines += [
        "@router.post(" + repr("/" + "x" * 129) + ")",
        "def process_widget(value):",
        "    return value",
    ]
    (tmp_path / PATH).write_text("\n".join(lines) + "\n", encoding="utf-8")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        result = cm.task_change_impact(TASK, [PATH], options=_options(start=10, end=10))
    context = result["changed_line_evidence"]["observations"][0][
        "decorator_associations"
    ]["associations"][0]["decorator_context"]
    assert context["declaration_decorator_count"] == 10
    assert context["retained_count"] == 6
    assert context["omitted_count"] == 4
    edited = [s for s in context["observations"] if s["intersects_reported_span"]]
    assert len(edited) == 1
    assert edited[0]["start_line"] == 10
    assert edited[0]["arguments"]["first_positional_string"] == {"state": "over-bound"}
    assert context["negative_evidence_admissible"] is False


def test_backend_decorator_context_does_not_expose_literals_in_outline(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / PATH).write_text(
        '@router.get("/secret-route")\ndef process_widget(value):\n    return value\n',
        encoding="utf-8",
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "src/backend.py"\nvisibility = "outline"\n'
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        result = cm.task_change_impact(TASK, [PATH], options=_options(start=1, end=1))
    row = result["changed_line_evidence"]["observations"][0]
    if row["state"] == "source-index-correspondence-observed":
        assert all(
            a["decorator_context"]["state"] == "source-visibility-required"
            and a["decorator_context"]["observations"] == []
            for a in row["decorator_associations"]["associations"]
        )
    else:
        assert row["state"] == "unresolved"
    assert "/secret-route" not in json.dumps(result)


def test_mcp_backend_decorator_context_tracks_current_source_after_edit(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    source = tmp_path / PATH
    source.write_text(
        '@router.get("/before")\n'
        "def process_widget(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        request = [{"path": PATH, "start_line": 1, "end_line": 1}]
        before = surface.change_impact(TASK, [PATH], changed_line_spans=request)
        repeated = surface.change_impact(TASK, [PATH], changed_line_spans=request)
        source.write_text(
            '@router.get("/after")\n'
            "def process_widget(value):\n"
            "    return value\n",
            encoding="utf-8",
        )
        after = surface.change_impact(TASK, [PATH], changed_line_spans=request)
    finally:
        surface.close()

    def first_literal(packet: dict[str, object]) -> str:
        observations = packet["changed_line_evidence"]["observations"]
        context = observations[0]["decorator_associations"]["associations"][0][
            "decorator_context"
        ]
        return context["observations"][0]["arguments"]["first_positional_string"][
            "value"
        ]

    assert first_literal(before) == "/before"
    assert first_literal(repeated) == "/before"
    assert first_literal(after) == "/after"
    assert before["changed_line_evidence"] == repeated["changed_line_evidence"]
    assert (
        before["changed_line_evidence"]["observations"][0]["member_revision"]
        != after["changed_line_evidence"]["observations"][0]["member_revision"]
    )
