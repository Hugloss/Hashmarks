from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_owner_resolution_recovers_unique_exact_symbol_without_retrieval_rows(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/runtime/executor_pool.py",
        "def cancel_queued_admission(*, expected_sequence: int) -> None:\n"
        "    del expected_sequence\n",
    )
    _write(
        tmp_path,
        "frontend/src/createApiClient.ts",
        "export function cancelQueuedAdmission(expectedSequence: number) {\n"
        "  return { action: 'cancel_queued_admission', expectedSequence };\n"
        "}\n",
    )

    task = "cancel_queued_admission expected_sequence"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        discrimination = codemap._task_action_discrimination_state(task, [])
        owner = codemap._task_action_resolve_owner(
            task=task,
            hits=[],
            rows=[],
            failed=set(),
            edit=None,
            verify=None,
            discrimination=discrimination,
            verification_anchor_tokens=(),
            literal_reference_owner=None,
            localized_config_edit=False,
            explicit_config_surface_request=False,
            explicit_edit_surface_selected=False,
            limit=1,
        )

    assert owner.edit is not None
    assert owner.edit["path"] == "backend/runtime/executor_pool.py"
    assert owner.basis == "unique-exact-symbol"
    assert owner.exact_identifier_paths == ("backend/runtime/executor_pool.py",)


def test_owner_resolution_keeps_duplicate_exact_symbols_unresolved(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/a.py", "def cancel_queued_admission():\n    return 1\n")
    _write(tmp_path, "src/b.py", "def cancel_queued_admission():\n    return 2\n")

    task = "fix cancel_queued_admission"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        discrimination = codemap._task_action_discrimination_state(task, [])
        owner = codemap._task_action_resolve_owner(
            task=task,
            hits=[],
            rows=[],
            failed=set(),
            edit=None,
            verify=None,
            discrimination=discrimination,
            verification_anchor_tokens=(),
            literal_reference_owner=None,
            localized_config_edit=False,
            explicit_config_surface_request=False,
            explicit_edit_surface_selected=False,
            limit=1,
        )

    assert owner.edit is None
    assert owner.basis is None
    assert owner.exact_identifier_paths == ("src/a.py", "src/b.py")


def test_owner_resolution_marks_literal_path_as_stronger_than_retrieval_order(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/worker.py", "def run_task():\n    return 1\n")
    _write(
        tmp_path,
        "src/wrapper.py",
        "from .worker import run_task\n"
        "# src/worker.py wrapper context\n",
    )

    task = "optimize src/worker.py"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        context = codemap._task_action_map_context(task, 20)
        selection = codemap._task_action_surface_owner_state(task, context, 20, 3)

    assert selection.edit is not None
    assert selection.edit["path"] == "src/worker.py"
    assert selection.owner_basis == "literal-path"


def test_owner_resolution_marks_structural_repository_owner(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/__init__.py", "")
    _write(tmp_path, "src/case/__init__.py", "")
    _write(
        tmp_path,
        "src/case/engine.py",
        "def apply_case(value: str) -> str:\n    return value + '-active'\n",
    )
    _write(
        tmp_path,
        "src/case/route.py",
        "from .engine import apply_case\n\n"
        "def handle_ember(value: str) -> str:\n"
        "    return apply_case(value)\n",
    )
    _write(
        tmp_path,
        "tests/case/test_behavior.py",
        "from src.case.route import handle_ember\n\n"
        "def test_ember_contract():\n"
        "    assert handle_ember('x') == 'x-active'\n",
    )

    task = "Fix ember accepted response behavior owner"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        context = codemap._task_action_map_context(task, 20)
        selection = codemap._task_action_surface_owner_state(task, context, 20, 3)

    assert selection.edit is not None
    assert selection.edit["path"] == "src/case/engine.py"
    assert selection.owner_basis == "structural-owner"
