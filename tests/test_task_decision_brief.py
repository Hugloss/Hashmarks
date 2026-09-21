from __future__ import annotations

import json
from typing import TYPE_CHECKING

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
        c.sync()
        full = c.task_decision_packet("widget implementation test")
        brief = c.task_decision_brief("widget implementation test")
    assert brief["edit"]["path"] == full["edit"]["path"]
    assert brief["verify"]["path"] == full["verify"]["path"]
    assert brief["verification_argv"] == full["verification_plan"]["argv"]
    assert brief["safe"] == full["context_budget"]["safe"]
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
        c.sync()
        brief = c.task_decision_brief("change policy config test")
    if brief["edit"] and brief.get("contract"):
        assert brief["edit"]["path"] != brief["contract"]["path"]


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
        c.sync()
        packet = c.task_decision_packet("Fix publish_result")
        brief = c.task_decision_brief("Fix publish_result")

    assert packet["edit"] is None
    assert packet["candidate"]["path"] in {"src/a.py", "src/b.py"}
    assert packet["owner_resolved"] is False
    assert brief["safe"] is False
    assert brief["edit"] is None
    assert brief["candidate"]["path"] in {"src/a.py", "src/b.py"}
    assert brief["discrimination"] == {
        "needed": True,
        "reason": "competing-action-roles",
    }
