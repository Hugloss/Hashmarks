from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ownership(packet: dict[str, object]) -> dict[str, object]:
    value = packet.get("ownership")
    assert isinstance(value, dict)
    return value


def _candidate_path(packet: dict[str, object]) -> str:
    candidate = _ownership(packet).get("candidate")
    assert isinstance(candidate, dict)
    return str(candidate.get("path") or "")


def _owner_path(packet: dict[str, object]) -> str | None:
    owner = _ownership(packet).get("owner")
    if not isinstance(owner, dict):
        return None
    return str(owner.get("path") or "") or None


def test_exact_owner_is_invariant_to_retrieval_saturation(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/runtime/executor_pool.py",
        "def cancel_queued_admission(*, expected_sequence: int) -> None:\n"
        "    del expected_sequence\n",
    )
    for index in range(24):
        _write(
            tmp_path,
            f"frontend/src/client_{index}.ts",
            "export function cancelQueuedAdmission(expected_sequence: number) {\n"
            "  return { action: 'cancel_queued_admission', expected_sequence };\n"
            "}\n"
            "// cancel_queued_admission expected_sequence consumer\n",
        )

    task = "change cancel_queued_admission expected_sequence"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packets = [
            codemap.task_evidence(task, limit=limit, per_role=1, token_budget=256)
            for limit in (1, 2, 5, 20)
        ]

    assert {
        _owner_path(packet) for packet in packets
    } == {"backend/runtime/executor_pool.py"}
    assert {str(_ownership(packet)["status"]) for packet in packets} == {"resolved"}


def test_weaker_docs_comments_and_tests_cannot_displace_exact_owner(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/publication.py",
        "class PublicationAuthority:\n"
        "    pass\n",
    )
    for index in range(16):
        _write(
            tmp_path,
            f"docs/note_{index}.md",
            "PublicationAuthority publication authority contract policy "
            "PublicationAuthority\n",
        )
    for index in range(8):
        _write(
            tmp_path,
            f"tests/test_publication_{index}.py",
            "def test_publication_authority_contract():\n"
            "    # PublicationAuthority publication authority policy\n"
            "    assert True\n",
        )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence(
            "change PublicationAuthority contract",
            limit=3,
            per_role=1,
            token_budget=256,
        )

    assert _owner_path(packet) == "src/publication.py"
    assert _ownership(packet)["status"] == "resolved"


def test_second_exact_owner_weakens_unique_ownership_to_ambiguous(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/a.py", "def target_impl():\n    return 1\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.task_evidence("change target_impl", limit=1)
        assert _owner_path(before) == "src/a.py"

        _write(tmp_path, "src/b.py", "def target_impl():\n    return 2\n")
        codemap.sync(["src/b.py"])
        after = codemap.task_evidence("change target_impl", limit=1)

    assert _ownership(after)["status"] == "ambiguous"
    assert _ownership(after)["owner"] is None
    assert _ownership(after)["ambiguity"]["ambiguous"] is True


def test_removed_exact_owner_cannot_survive_as_current_authority(
    tmp_path: Path,
) -> None:
    owner = tmp_path / "src/owner.py"
    _write(tmp_path, "src/owner.py", "def target_impl():\n    return 1\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.task_evidence("change target_impl")
        assert _owner_path(before) == "src/owner.py"

        owner.unlink()
        codemap.sync(["src/owner.py"])
        after = codemap.task_evidence("change target_impl")

    assert _ownership(after)["status"] != "resolved"
    assert _ownership(after)["owner"] is None


def test_denied_exact_symbol_cannot_participate_in_target_or_ownership(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        ".hashmarks-context.toml",
        '[[rule]]\npattern = "hidden/**"\nvisibility = "deny"\n',
    )
    _write(
        tmp_path,
        "hidden/owner.py",
        "def denied_target():\n    return 'secret'\n",
    )
    _write(
        tmp_path,
        "src/consumer.py",
        "# denied_target is mentioned here but does not own it\n"
        "VALUE = 'denied_target'\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence("change denied_target")

    assert "hidden/owner.py" not in str(packet)
    assert _owner_path(packet) != "hidden/owner.py"
    assert _candidate_path(packet) != "hidden/owner.py"


def test_test_only_exact_symbol_is_not_silently_promoted_to_implementation_owner(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "tests/test_worker.py",
        "def test_target_impl():\n    assert True\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence("diagnose test_target_impl behavior")

    assert _ownership(packet)["owner"] is None
    assert _ownership(packet)["status"] != "resolved"


def test_explicit_test_edit_is_target_evidence_not_implementation_ownership(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/worker.py",
        "def run_task():\n    return 1\n",
    )
    _write(
        tmp_path,
        "tests/test_worker.py",
        "from src.worker import run_task\n\n"
        "def test_run_task_contract():\n"
        "    assert run_task() == 1\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence(
            "strengthen regression test test_run_task_contract"
        )

    explicit = packet["explicit_target"]
    assert explicit["status"] == "resolved"
    assert explicit["path"] == "tests/test_worker.py"
    assert explicit["basis"] == "explicit-test-edit"
    assert _candidate_path(packet) == "tests/test_worker.py"
    assert _ownership(packet)["owner"] is None


def test_freshness_state_does_not_upgrade_or_downgrade_owner_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write(tmp_path, "src/owner.py", "def target_impl():\n    return 1\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        generation = codemap.store.generation()
        monkeypatch.setattr(
            codemap, "_generation_status", lambda: (generation, 41, True)
        )
        packet = codemap.task_evidence("change target_impl")

    assert _owner_path(packet) == "src/owner.py"
    assert _ownership(packet)["status"] == "resolved"
    assert packet["freshness"]["state"] == "stale"
    assert "safe" not in str(packet["freshness"]).lower()


def test_external_correlation_cannot_change_task_ownership_authority(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/a.py", "def duplicate_owner():\n    return 1\n")
    _write(tmp_path, "src/b.py", "def duplicate_owner():\n    return 2\n")
    bundle = [
        {
            "bundle_id": "runtime:1",
            "producer": {"kind": "traceback"},
            "completeness": "complete",
            "scope": {"kind": "bounded-runtime-observation"},
            "truncation": "complete",
            "anchors": [
                {
                    "anchor_id": "frame:0",
                    "path": "/app/src/a.py",
                    "symbol": "duplicate_owner",
                }
            ],
        }
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.task_evidence("change duplicate_owner")
        correlation = codemap.correlate_evidence(
            bundle,
            path_mappings=[
                {"external_prefix": "/app", "repository_prefix": ""}
            ],
            include_relationships=False,
        )
        after = codemap.task_evidence("change duplicate_owner")

    assert correlation["authority"] == "repository-intelligence-only"
    assert correlation["interpretation_authority"] == "consumer-owned"
    assert _ownership(before)["status"] == "ambiguous"
    assert _ownership(after)["status"] == "ambiguous"
    assert _ownership(before)["owner"] is None
    assert _ownership(after)["owner"] is None


def test_candidate_never_becomes_admitted_owner_across_action_projections(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/a.py", "def duplicate_owner():\n    return 1\n")
    _write(tmp_path, "src/b.py", "def duplicate_owner():\n    return 2\n")
    _write(tmp_path, "tests/test_owner.py", "def test_owner():\n    assert True\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("fix duplicate_owner")
        evidence = codemap.task_evidence("fix duplicate_owner")
        packet = codemap.task_decision_packet("fix duplicate_owner")
        decision_brief = codemap.task_decision_brief("fix duplicate_owner")
        action_brief = codemap.task_action_brief(
            "fix duplicate_owner", token_budget=256
        )

    assert action["edit"]["path"] in {"src/a.py", "src/b.py"}
    assert action["admitted_edit"] is None
    assert action["ownership_authority"]["owner_resolved"] is False
    assert _ownership(evidence)["status"] == "ambiguous"
    assert _ownership(evidence)["owner"] is None
    assert packet["candidate"]["path"] in {"src/a.py", "src/b.py"}
    assert packet["edit"] is None
    assert packet["discrimination"]["needed"] is True
    assert decision_brief["candidate"]["path"] in {"src/a.py", "src/b.py"}
    assert decision_brief["edit"] is None
    assert decision_brief["safe"] is False
    assert action_brief["candidate"] in {"src/a.py", "src/b.py"}
    assert "edit" not in action_brief
    assert action_brief["status"] == "unsafe"


def test_resolved_owner_survives_all_action_projections(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/owner.py", "def exact_owner():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_owner.py",
        "from src.owner import exact_owner\n"
        "def test_owner():\n    assert exact_owner() == 1\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("fix exact_owner")
        evidence = codemap.task_evidence("fix exact_owner")
        packet = codemap.task_decision_packet("fix exact_owner")
        decision_brief = codemap.task_decision_brief("fix exact_owner")
        action_brief = codemap.task_action_brief("fix exact_owner", token_budget=256)

    assert action["edit"]["path"] == "src/owner.py"
    assert action["admitted_edit"]["path"] == "src/owner.py"
    assert _owner_path(evidence) == "src/owner.py"
    assert packet["candidate"]["path"] == "src/owner.py"
    assert packet["edit"]["path"] == "src/owner.py"
    assert decision_brief["candidate"]["path"] == "src/owner.py"
    assert decision_brief["edit"]["path"] == "src/owner.py"
    assert action_brief["candidate"] == "src/owner.py"
    assert action_brief["edit"] == "src/owner.py"
