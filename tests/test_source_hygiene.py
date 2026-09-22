from __future__ import annotations

from pathlib import Path

from scripts.source_hygiene import _check


def test_source_hygiene_accepts_valid_lf_python(tmp_path: Path) -> None:
    path = tmp_path / "valid.py"
    path.write_bytes(b"value = 1\n")
    assert _check(path) == []


def test_source_hygiene_rejects_literal_newline_source_corruption(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_bytes(b"def value():\\n    return 1\\n")
    errors = _check(path)
    assert any("invalid Python syntax" in error for error in errors)


def test_source_hygiene_rejects_crlf(tmp_path: Path) -> None:
    path = tmp_path / "crlf.py"
    path.write_bytes(b"value = 1\r\n")
    assert _check(path) == ["contains CR/CRLF; repository text policy is LF"]
