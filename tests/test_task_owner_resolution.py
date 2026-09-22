from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_action_types import (
    _TaskActionInitialSurfaceState,
    _TaskActionMapContext,
    _TaskActionOwnerResolutionRequest,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _owner_request(codemap: CodeMap, task: str) -> _TaskActionOwnerResolutionRequest:
    return _TaskActionOwnerResolutionRequest(
        task=task,
        context=cast(
            "_TaskActionMapContext", SimpleNamespace(hits=[], rows=[], failed=set())
        ),
        surface=cast(
            "_TaskActionInitialSurfaceState",
            SimpleNamespace(
                edit=None,
                verify=None,
                verification_anchor_tokens=(),
                literal_reference_owner=None,
                localized_config_edit=False,
                explicit_config_surface_request=False,
                explicit_edit_surface_selected=False,
            ),
        ),
        discrimination=codemap._task_action_discrimination_state(task, []),
        limit=1,
    )


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
        owner = codemap._task_action_resolve_owner(_owner_request(codemap, task))

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
        owner = codemap._task_action_resolve_owner(_owner_request(codemap, task))

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
        "from .worker import run_task\n# src/worker.py wrapper context\n",
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


def test_unique_exact_owner_does_not_enter_weaker_structural_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from hashmarks.codemap.ownership_graph import OwnershipGraphMixin

    _write(
        tmp_path,
        "src/owner.py",
        "def cancel_queued_admission(*, expected_sequence: int) -> None:\n"
        "    del expected_sequence\n",
    )

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("exact owner must terminate before structural resolution")

    monkeypatch.setattr(
        OwnershipGraphMixin,
        "_structural_owner_candidate",
        forbidden,
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "change cancel_queued_admission",
            limit=1,
            per_role=1,
        )

    assert action["edit"]["path"] == "src/owner.py"
    assert action["owner_basis"] in {"exact-symbol", "unique-exact-symbol"}
    assert action["ownership_authority"]["owner_resolved"] is True


def test_exact_owner_cannot_be_displaced_by_contract_projection(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/authority.py",
        "class PublicationAuthority:\n    pass\n",
    )
    _write(
        tmp_path,
        "INVARIANTS.md",
        "PublicationAuthority contract contract contract policy evidence.\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Change PublicationAuthority contract",
            limit=20,
            per_role=3,
        )

    assert action["edit"]["path"] == "src/authority.py"
    assert action["owner_basis"] == "exact-symbol"
    assert action["ownership_authority"]["owner_resolved"] is True


def _write_publish_dependency_fixture(
    root: Path, *, duplicate_target: bool = False
) -> None:
    _write(
        root,
        "src/publish.py",
        "def publish_result(value):\n    return value\n",
    )
    if duplicate_target:
        _write(
            root,
            "src/alternate_publish.py",
            "def publish_result(value):\n    return value\n",
        )
    _write(
        root,
        "src/authority.py",
        "class AuthorityReceipt:\n"
        "    def canonical_identity(self):\n"
        "        return 'canonical'\n",
    )


def test_requested_edit_target_owns_dependency_identifier_evidence(
    tmp_path: Path,
) -> None:
    _write_publish_dependency_fixture(tmp_path)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix publish_result so it uses AuthorityReceipt.canonical_identity",
            limit=20,
        )

    assert action["edit"]["path"] == "src/publish.py"
    assert action["edit"]["name"] == "publish_result"
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_authority"]["owner_resolved"] is True


def test_requested_edit_target_role_survives_dependency_first_wording(
    tmp_path: Path,
) -> None:
    _write_publish_dependency_fixture(tmp_path)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Use AuthorityReceipt.canonical_identity in publish_result",
            limit=20,
        )

    assert action["edit"]["path"] == "src/publish.py"
    assert action["edit"]["name"] == "publish_result"
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_authority"]["owner_resolved"] is True


def test_requested_edit_role_does_not_hide_true_duplicate_target_ambiguity(
    tmp_path: Path,
) -> None:
    _write_publish_dependency_fixture(tmp_path, duplicate_target=True)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix publish_result so it uses AuthorityReceipt.canonical_identity",
            limit=20,
        )

    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-exact-identifier-edit-owners"
    assert action["ownership_authority"]["owner_resolved"] is False


def test_requested_edit_role_is_stable_across_dependency_phrasings(
    tmp_path: Path,
) -> None:
    _write_publish_dependency_fixture(tmp_path)
    tasks = (
        "Update publish_result using AuthorityReceipt.canonical_identity",
        "Refactor publish_result to call AuthorityReceipt.canonical_identity",
        "Change publish_result via AuthorityReceipt.canonical_identity",
        "Call AuthorityReceipt.canonical_identity from publish_result",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        actions = [codemap.task_action_map(task, limit=20) for task in tasks]

    assert all(action["edit"]["path"] == "src/publish.py" for action in actions)
    assert all(action["edit"]["name"] == "publish_result" for action in actions)
    assert all(action["ambiguity"]["ambiguous"] is False for action in actions)
    assert all(
        action["ownership_authority"]["owner_resolved"] is True for action in actions
    )


def test_two_requested_exact_edit_targets_remain_ambiguous(tmp_path: Path) -> None:
    _write(tmp_path, "src/publish.py", "def publish_result(value):\n    return value\n")
    _write(tmp_path, "src/store.py", "def store_result(value):\n    return value\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Change publish_result and store_result",
            limit=20,
        )

    assert action["ambiguity"]["ambiguous"] is True
    assert action["ownership_authority"]["owner_resolved"] is False
