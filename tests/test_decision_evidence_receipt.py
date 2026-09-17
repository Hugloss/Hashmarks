from pathlib import Path

from hashmarks.codemap import CodeMap


def _repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(
        "def widget(value: str) -> str:\n    return value + '-old'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_engine.py").write_text(
        "from src.engine import widget\n\ndef test_widget():\n    assert widget('x') == 'x-new'\n",
        encoding="utf-8",
    )


def _identity(packet: dict[str, object]) -> str:
    receipt = packet["evidence_receipt"]
    assert isinstance(receipt, dict)
    assert receipt["schema"] == "hashmarks.decision-evidence-receipt.v1"
    return str(receipt["evidence_identity"])


def test_all_decision_surfaces_share_one_evidence_identity(tmp_path: Path) -> None:
    _repo(tmp_path)
    task = "Change widget behavior and verify it"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet(task, token_budget=512)
        brief = codemap.task_decision_brief(task, token_budget=128)
        action = codemap.task_action_brief(task, token_budget=64)
        start = codemap.task_evidence(task, token_budget=32)

    identities = {_identity(value) for value in (packet, brief, action, start)}
    assert len(identities) == 1


def test_evidence_identity_is_worker_budget_independent(tmp_path: Path) -> None:
    _repo(tmp_path)
    task = "Change widget behavior and verify it"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        identities = {
            _identity(codemap.task_action_brief(task, token_budget=budget))
            for budget in (1, 16, 32, 64, 128, 512)
        }
    assert len(identities) == 1


def test_evidence_identity_changes_with_task_or_repository_authority(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = _identity(codemap.task_action_brief("Change widget behavior and verify it"))
        other_task = _identity(codemap.task_action_brief("Inspect widget semantics and verify it"))
        assert other_task != original

        (tmp_path / "src" / "engine.py").write_text(
            "def widget(value: str) -> str:\n    return value + '-new-authority'\n",
            encoding="utf-8",
        )
        codemap.sync()
        changed_repo = _identity(codemap.task_action_brief("Change widget behavior and verify it"))
        assert changed_repo != original


def test_receipt_is_compact_reference_not_embedded_full_evidence(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_brief("Change widget behavior and verify it")
    receipt = action["evidence_receipt"]
    assert isinstance(receipt, dict)
    assert set(receipt) == {
        "schema", "evidence_identity", "repository_identity", "task_identity",
        "codemap_generation", "stale",
    }
    assert "verification_relevance" not in receipt
    assert "work_context" not in receipt
