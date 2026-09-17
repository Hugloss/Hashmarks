from __future__ import annotations

import tomllib
from pathlib import Path


EXPECTED_RULES = {
    "E4",
    "E7",
    "E9",
    "F",
    "B",
    "I",
    "UP",
    "FAST",
    "SIM",
    "C4",
    "TID25",
    "T20",
    "G",
    "TC",
    "C901",
    "PLR0911",
    "PLR0912",
    "PLR0913",
    "PLR0914",
    "PLR0915",
    "PLR0916",
}


def test_clean_code_rule_contract_is_explicit_and_version_independent() -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    lint = config["tool"]["ruff"]["lint"]

    assert set(lint["select"]) == EXPECTED_RULES
    assert "extend-select" not in lint


def test_ruff_diagnostic_compatibility_uses_minimum_without_becoming_release_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    makefile = (root / "Makefile").read_text(encoding="utf-8")

    assert config["tool"]["hashmarks"]["diagnostics"] == {"ruff-min": "0.12"}
    assert "RUFF_VERSION" not in makefile
    assert "uv run --with" not in makefile.replace("$(UV)", "uv")
