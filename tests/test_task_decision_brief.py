from __future__ import annotations

import json
from typing import TYPE_CHECKING

from contract_assertions import assert_object

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def test_brief_preserves_action_and_verification_without_verbose_candidates(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "engine.py").write_text("def widget():\n    return 'old'\n")
    (tmp_path / "tests" / "test_engine.py").write_text(
        "from src.engine import widget\ndef test_widget(): assert widget() == 'new'\n"
    )
    with CodeMap(tmp_path) as c:
        c.index.sync()
        full = c.tasks.decision_packet("widget implementation test")
        brief = c.tasks.decision_brief("widget implementation test")
    assert assert_object(brief["edit"])["path"] == assert_object(full["edit"])["path"]
    assert (
        assert_object(brief["verify"])["path"] == assert_object(full["verify"])["path"]
    )
    assert (
        brief["verification_argv"] == assert_object(full["verification_plan"])["argv"]
    )
    assert brief["safe"] == assert_object(full["context_budget"])["safe"]
    assert "ambiguity" not in brief
    assert (
        len(json.dumps(brief, sort_keys=True))
        < len(json.dumps(full, sort_keys=True)) * 0.55
    )


def test_brief_deduplicates_contract_when_edit_is_contract(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "policy.toml").write_text("mode='old'\n")
    (tmp_path / "tests" / "test_policy.py").write_text(
        "def test_policy(): assert True\n"
    )
    with CodeMap(tmp_path) as c:
        c.index.sync()
        brief = c.tasks.decision_brief("change policy config test")
    if brief["edit"] and brief.get("contract"):
        assert (
            assert_object(brief["edit"])["path"]
            != assert_object(brief["contract"])["path"]
        )


def test_decision_brief_keeps_ambiguous_candidate_out_of_edit_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    for name in ("a", "b"):
        (tmp_path / "src" / f"{name}.py").write_text(
            "def publish_result(value):\n    return value\n", encoding="utf-8"
        )
    (tmp_path / "tests/test_publish.py").write_text(
        "def test_publish(): assert True\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as c:
        c.index.sync()
        packet = c.tasks.decision_packet("Fix publish_result")
        brief = c.tasks.decision_brief("Fix publish_result")

    assert packet["edit"] is None
    assert assert_object(packet["candidate"])["path"] in {"src/a.py", "src/b.py"}
    assert assert_object(packet["ownership_authority"])["owner_resolved"] is False
    assert brief["safe"] is False
    assert brief["edit"] is None
    assert assert_object(brief["candidate"])["path"] in {"src/a.py", "src/b.py"}
    assert brief["discrimination"] == {
        "needed": True,
        "reason": "competing-action-roles",
    }
