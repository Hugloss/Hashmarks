from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_array, assert_object

from hashmarks.cli import main

if TYPE_CHECKING:
    from pathlib import Path


def test_cli_exposes_verification_relevance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "owner.py").write_text("def widget(value):\n    return value\n")
    (tmp_path / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\n\ndef test_widget():\n    assert widget(1) == 1\n"
    )
    assert (
        main(
            [
                "--workspace",
                str(tmp_path),
                "verification-relevance",
                "widget implementation test",
                "--candidate-limit",
                "1",
            ]
        )
        == 0
    )
    payload = assert_object(json.loads(capsys.readouterr().out))
    assert payload["schema"] == "hashmarks.verification-relevance.v1"
    assert assert_object(payload["selected"])["path"] == "tests/test_owner.py"
    assert len(assert_array(payload["candidates"])) == 1
