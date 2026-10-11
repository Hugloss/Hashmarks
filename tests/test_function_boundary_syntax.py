"""Source/index-bound syntax stays distinct from runtime boundary ownership."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

import pytest

from hashmarks.codemap import ChangeImpactOptions, CodeMap
from hashmarks.python_ast_cache import read_python_ast
from scripts.repository_evaluation.backend_transport import capture_cli


def _observe(root: Path, *, start: int = 2, end: int = 2) -> dict[str, Any]:
    with CodeMap(root) as codemap:
        codemap.sync()
        packet = codemap.task_change_impact(
            "Inspect reported changes in service.py",
            ["service.py"],
            options=ChangeImpactOptions(
                changed_line_spans=[
                    {"path": "service.py", "start_line": start, "end_line": end}
                ]
            ),
        )
    return cast("dict[str, Any]", packet)["changed_line_evidence"]["observations"][0]


def test_async_context_calls_and_exception_syntax_are_source_facts(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        "async def process(session, task, message):\n"
        "    async with session.transaction():\n"
        "        try:\n"
        "            await task\n"
        "            await message.ack()\n"
        "            session.commit()\n"
        "        except arbitrary.CancelledError:\n"
        "            task.cancel()\n"
        "            session.rollback()\n"
    )
    row = _observe(tmp_path, start=5, end=5)
    boundary = row["function_boundary_syntax"]
    assert boundary["authority"] == "direct-static-syntax-only"
    assert boundary["runtime_boundary_kind"] == "not-established"
    assert boundary["task_ownership"] == "not-established"
    assert boundary["callee_resolution"] == "not-established"
    assert boundary["execution_order"] == "not-established"
    assert boundary["negative_evidence_admissible"] is False
    function = boundary["observations"][0]
    assert function["subject"] == "service.py::process"
    assert function["state"] == "source-index-bound"
    assert function["declaration_syntax"] == "async"
    sites = function["sites"]
    assert [
        (site["line"], site["callee_identifier_syntax"])
        for site in sites
        if site["syntax_kind"] == "await"
    ] == [(4, None), (5, "message.ack")]
    assert {
        site["callee_identifier_syntax"]
        for site in sites
        if site["syntax_kind"] == "call"
    } == {
        "session.transaction",
        "message.ack",
        "session.commit",
        "task.cancel",
        "session.rollback",
    }
    handler = next(site for site in sites if site["syntax_kind"] == "exception-handler")
    assert handler["exception_identifier_syntax"] == "arbitrary.CancelledError"
    assert row["member_revision"]


def test_nested_scopes_and_complex_receivers_do_not_gain_resolution(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        "def process():\n"
        "    def hidden():\n"
        "        secret.commit()\n"
        "    callback = lambda: secret.rollback()\n"
        "    acquire().commit()\n"
    )
    row = _observe(tmp_path, start=5, end=5)
    boundary = row["function_boundary_syntax"]
    function = boundary["observations"][0]
    assert function["declaration_syntax"] == "sync"
    sites = function["sites"]
    assert all(site["line"] == 5 for site in sites)
    commit = next(
        site for site in sites if site.get("callee_member_syntax") == "commit"
    )
    assert commit["callee_identifier_syntax"] is None
    assert commit["callee_expression_kind"] == "Attribute"
    assert boundary["task_ownership"] == "not-established"


def test_reported_multiline_call_and_cli_formats_retain_qualified_syntax(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        "async def process():\n"
        + "    earlier()\n" * 40
        + "    await changed(\n        argument,\n    )\n"
    )
    state = tmp_path / "state"
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.sync()
    captures = capture_cli(
        tmp_path,
        state,
        {
            "operation": "change_impact",
            "inputs": {
                "task": "Inspect reported process argument change",
                "changed_paths": ["service.py"],
                "changed_line_spans": [
                    {"path": "service.py", "start_line": 43, "end_line": 43}
                ],
                "max_depth": 1,
            },
        },
    )
    for capture in captures:
        reply = capture["response"]
        packet = reply.get("result", reply)
        boundary = packet["changed_line_evidence"]["observations"][0][
            "function_boundary_syntax"
        ]
        observed = boundary["observations"][0]
        assert observed["truncation"] == "truncated"
        assert boundary["runtime_boundary_kind"] == "not-established"
        assert boundary["negative_evidence_admissible"] is False
        assert {
            site["syntax_kind"]
            for site in observed["sites"]
            if site.get("callee_identifier_syntax") == "changed"
        } == {"await", "call"}


def test_bounded_sites_keep_reported_line_without_claiming_completeness(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        "def process():\n"
        + "".join(f"    calls.site_{index}()\n" for index in range(50))
    )
    function = _observe(tmp_path, start=51, end=51)["function_boundary_syntax"][
        "observations"
    ][0]
    assert function["observed_site_count"] == 50
    assert len(function["sites"]) == 32
    assert function["omitted_site_count"] == 18
    assert function["truncation"] == "truncated"
    assert any(
        site["callee_identifier_syntax"] == "calls.site_49"
        for site in function["sites"]
    )


def test_file_backed_body_and_decorator_share_cached_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "service.py"
    path.write_text(
        "@router.post('/jobs')\nasync def process():\n    await execute()\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        read_python_ast(path)

        def forbidden_parse(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("file-backed observation reparsed cached source")

        monkeypatch.setattr(ast, "parse", forbidden_parse)
        packet = cast(
            "dict[str, Any]",
            codemap.task_change_impact(
                "Inspect service.py",
                ["service.py"],
                options=ChangeImpactOptions(
                    changed_line_spans=[
                        {"path": "service.py", "start_line": 1, "end_line": 3}
                    ]
                ),
            ),
        )
    row = packet["changed_line_evidence"]["observations"][0]
    assert (
        row["function_boundary_syntax"]["observations"][0]["declaration_syntax"]
        == "async"
    )
    assert (
        row["decorator_associations"]["associations"][0]["subject"]
        == "service.py::process"
    )


@pytest.mark.parametrize("visibility", ["outline", "deny"])
def test_source_visibility_blocks_boundary_syntax(
    tmp_path: Path, visibility: str
) -> None:
    (tmp_path / "service.py").write_text(
        "async def process():\n    await private_commit()\n"
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        f'[[rule]]\npattern="service.py"\nvisibility="{visibility}"\n'
    )
    row = _observe(tmp_path)
    assert row["state"] == "unresolved"
    assert "function_boundary_syntax" not in row
    assert "private_commit" not in str(row)
