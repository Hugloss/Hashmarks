from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_task_evidence_v2_separates_retrieval_ownership_and_freshness(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/owner.py",
        "def target_impl(value: int) -> int:\n    return value + 1\n",
    )
    _write(
        tmp_path,
        "tests/test_owner.py",
        "from src.owner import target_impl\n\n"
        "def test_target_impl():\n"
        "    assert target_impl(1) == 2\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence("change target_impl behavior", token_budget=256)

    assert packet["schema"] == "hashmarks.task-evidence.v2"
    assert "status" not in packet
    assert packet["retrieval"]["ownership_authority"] is False
    assert packet["ownership"]["status"] == "resolved"
    assert packet["ownership"]["owner"]["path"] == "src/owner.py"
    assert packet["ownership"]["basis"] in {"unique-exact-symbol", "exact-symbol"}
    assert packet["ownership"]["authority"] == "repository-ownership-only"
    assert packet["verification"]["selected"]["path"] == "tests/test_owner.py"
    assert packet["freshness"]["state"] in {"unknown", "current", "stale"}
    assert packet["consumer_action"] == "external"


def test_task_evidence_v2_keeps_ambiguity_independent_from_freshness(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/a.py", "def calculate_value():\n    return 1\n")
    _write(tmp_path, "src/b.py", "def calculate_value():\n    return 2\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence("fix calculate_value", token_budget=256)

    assert packet["ownership"]["status"] == "ambiguous"
    assert packet["ownership"]["owner"] is None
    assert packet["ownership"]["ambiguity"]["ambiguous"] is True
    assert packet["ownership"]["source_evidence"] is None
    assert packet["freshness"]["state"] in {"unknown", "current", "stale"}


def test_task_evidence_v2_owner_is_invariant_to_bounded_retrieval(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/runtime/executor_pool.py",
        "def cancel_queued_admission(*, expected_sequence: int) -> None:\n"
        "    del expected_sequence\n",
    )
    for index in range(8):
        _write(
            tmp_path,
            f"frontend/src/client_{index}.ts",
            "export function cancelQueuedAdmission(expected_sequence: number) {\n"
            "  return { action: 'cancel_queued_admission', expected_sequence };\n"
            "}\n"
            "// cancel_queued_admission expected_sequence consumer\n",
        )

    task = "cancel_queued_admission expected_sequence"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        narrow = codemap.task_evidence(task, limit=1, per_role=1, token_budget=256)
        wide = codemap.task_evidence(task, limit=20, per_role=3, token_budget=256)

    assert narrow["ownership"]["status"] == "resolved"
    assert wide["ownership"]["status"] == "resolved"
    assert narrow["ownership"]["owner"]["path"] == "backend/runtime/executor_pool.py"
    assert wide["ownership"]["owner"]["path"] == "backend/runtime/executor_pool.py"
    assert narrow["ownership"]["basis"] in {"exact-symbol", "unique-exact-symbol"}
    assert wide["ownership"]["basis"] in {"exact-symbol", "unique-exact-symbol"}


def test_task_evidence_v2_keeps_dependency_as_related_evidence_not_owner(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/publish.py", "def publish_result(value):\n    return value\n")
    _write(
        tmp_path,
        "src/authority.py",
        "class AuthorityReceipt:\n"
        "    def canonical_identity(self):\n"
        "        return 'canonical'\n",
    )
    task = "Fix publish_result so it uses AuthorityReceipt.canonical_identity"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)
        packet = codemap.task_evidence(task, limit=20, token_budget=256)

    assert packet["ownership"]["status"] == "resolved"
    assert packet["ownership"]["owner"]["path"] == "src/publish.py"
    assert packet["ownership"]["candidate"]["path"] == "src/publish.py"
    assert packet["explicit_target"]["path"] == "src/publish.py"
    assert packet["ownership"]["ambiguity"]["ambiguous"] is False

    retrieval_paths = {row["path"] for row in packet["retrieval"]["results"]}
    canonical_paths = {row["path"] for row in action["canonical"]}
    assert "src/authority.py" in canonical_paths
    assert "src/authority.py" in retrieval_paths
    assert packet["related"]["candidates"] == action["related"]


def test_task_evidence_projects_same_authority_proof_across_bounds(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/owner.py", "def unique_owner(value):\n    return value\n")
    task = "Refactor owner.unique_owner without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=1, per_role=1)
        narrow = codemap.task_evidence(task, limit=1, per_role=1, token_budget=64)
        wide = codemap.task_evidence(task, limit=20, per_role=3, token_budget=256)

    proof = action["ownership_authority"]["authority_proof_identity"]
    assert narrow["ownership"]["authority_proof_identity"] == proof
    assert wide["ownership"]["authority_proof_identity"] == proof
    assert narrow["ownership"]["owner"]["path"] == "src/owner.py"
    assert wide["ownership"]["owner"]["path"] == "src/owner.py"
    assert narrow["ownership"]["proof_scope_complete"] is True
    assert wide["ownership"]["proof_scope_complete"] is True
