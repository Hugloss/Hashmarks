from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_documented_make_commands_are_real_phony_targets() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    documented = set(re.findall(r"'  make ([A-Za-z0-9_.-]+)", text))
    targets = set(re.findall(r"^([A-Za-z0-9_.-]+):(?:\s|$)", text, flags=re.MULTILINE))
    phony = {
        target
        for line in text.splitlines()
        if line.startswith(".PHONY:")
        for target in line.partition(":")[2].split()
    }

    assert documented
    assert documented <= targets
    assert documented <= phony
