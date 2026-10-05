from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_documented_make_commands_are_real_phony_targets() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    documented = set(re.findall(r"'  make ([A-Za-z0-9_.-]+)", text))
    targets = {
        target
        for match in re.finditer(
            r"^([A-Za-z0-9_.-]+(?:[ \t]+[A-Za-z0-9_.-]+)*):(?:[ \t]|$)",
            text,
            flags=re.MULTILINE,
        )
        for target in match.group(1).split()
    }
    phony = {
        target
        for line in text.splitlines()
        if line.startswith(".PHONY:")
        for target in line.partition(":")[2].split()
    }

    assert documented
    assert documented <= targets
    assert documented <= phony


def _make_recipe(text: str, target: str) -> tuple[str, ...]:
    match = re.search(
        rf"^{re.escape(target)}:\n(?P<recipe>(?:\t.*\n)+)",
        text,
        flags=re.MULTILINE,
    )
    assert match is not None
    return tuple(line.removeprefix("\t") for line in match.group("recipe").splitlines())


def test_benchmark_make_aliases_delegate_all_launch_authority() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")

    expected = {
        "benchmark": '@$(MAKE) --no-print-directory -C "$(AGENTS_COOKBOOK)" benchmark',
        "benchmark-check": (
            '@$(MAKE) --no-print-directory -C "$(AGENTS_COOKBOOK)" benchmark-check'
        ),
        "benchmark-report": (
            '@$(MAKE) --no-print-directory -C "$(AGENTS_COOKBOOK)" benchmark-report'
        ),
    }
    for target, command in expected.items():
        assert _make_recipe(text, target) == (command,)

    stale_launch_owners = (
        "BENCHMARK ?=",
        "BENCH_AGENT ?=",
        "BENCH_ROOT ?=",
        "BENCH_PYTHON ?=",
        "BENCH_RUN ?=",
        "BENCH_PARTIAL ?=",
        "benchmark-show",
        "native-matrix-v3",
        "enola-cycle-reproduction-v1",
        "agent-selection",
    )
    for token in stale_launch_owners:
        assert token not in text
