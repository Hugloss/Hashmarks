import json
from pathlib import Path

from hashmarks.qualification_units import native_qualification_handoff
from scripts.promotion_gate import main


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_handoff(tmp_path: Path, value: dict[str, object]) -> Path:
    path = tmp_path / "qualification-handoff.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_promotion_gate_cli_accepts_current_bound_handoff_without_authorizing_release(
    tmp_path: Path, capsys
) -> None:
    handoff = _write_handoff(tmp_path, native_qualification_handoff(_root()))
    code = main([
        "--root", str(_root()),
        "--qualification-handoff", str(handoff),
    ])
    value = json.loads(capsys.readouterr().out)
    assert code == 0
    assert value["manifest_valid"] is True
    assert value["release_authorized"] is False
    assert value["release_authority"] == "external-release-process"
    assert value["native_qualification_handoff"]["valid"] is True
    assert value["native_ruff_receipt"]["present"] is False


def test_promotion_gate_cli_fails_closed_for_handoff_from_different_repository(
    tmp_path: Path, capsys
) -> None:
    handoff = native_qualification_handoff(_root())
    handoff["repository_identity"] = "sha256:" + "a" * 64 + ":1"
    handoff_path = _write_handoff(tmp_path, handoff)
    code = main([
        "--root", str(_root()),
        "--qualification-handoff", str(handoff_path),
    ])
    value = json.loads(capsys.readouterr().out)
    assert code == 3
    assert value["manifest_valid"] is False
    assert "qualification-repository-identity-mismatch" in value["native_qualification_handoff"]["reasons"]
