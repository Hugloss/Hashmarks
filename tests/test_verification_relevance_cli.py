from __future__ import annotations

import json
from pathlib import Path

from hashmarks.cli import main


def test_cli_exposes_verification_relevance(tmp_path: Path, capsys) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "owner.py").write_text("def widget(value):\n    return value\n")
    (tmp_path / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\n\ndef test_widget():\n    assert widget(1) == 1\n"
    )
    assert main([
        "--workspace", str(tmp_path),
        "verification-relevance", "widget implementation test",
        "--candidate-limit", "1",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "hashmarks.verification-relevance.v1"
    assert payload["selected"]["path"] == "tests/test_owner.py"
    assert len(payload["candidates"]) == 1
