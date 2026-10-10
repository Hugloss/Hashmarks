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
        "target": "src/backend.py::process_widget", "result_mode": "relationships"
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
        [{"path": PATH, "start_line": n + 1, "end_line": n + 1}
         for n in range(MAX_CHANGED_SPANS + 1)],
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
                TASK, [PATH],
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
    (tmp_path / ".hashmarks.toml").write_text(
        "[[rule]]\npattern = \"src/backend.py\"\nvisibility = \"deny\"\n"
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
            TASK, [PATH, "src/other.txt"],
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
            TASK, [PATH], options=_options(start=1, end=80),
        )
    row = impact["changed_line_evidence"]["observations"][0]
    assert row["symbol_retained_count"] <= 32
    assert row["negative_evidence_admissible"] is False


def test_mcp_native_and_compact_reuse_same_source_owner(tmp_path: Path) -> None:
    _repo(tmp_path)
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        value = surface.change_impact(
            TASK, [PATH],
            changed_line_spans=[{"path": PATH, "start_line": 2, "end_line": 3}],
        )
    finally:
        surface.close()
    assert value["changed_line_evidence"]["observations"][0]["symbols"][0][
        "subject"
    ] == "src/backend.py::process_widget"
