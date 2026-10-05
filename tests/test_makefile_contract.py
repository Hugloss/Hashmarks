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
        "benchmark": (
            '@$(MAKE) --no-print-directory -C "$(AGENTS_COOKBOOK)" benchmark'
        ),
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


def test_mcp_host_make_aliases_do_not_own_gate_defaults() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert _make_recipe(text, "mcp-host-status") == (
        "@$(UV_RUN) --offline --no-sync python scripts/mcp_host_status.py",
    )

    stale_defaults = (
        "OPENCODE ?=",
        "OPENCODE_HOST_PYTHON ?=",
        "OPENCODE_HOST_RECEIPT ?=",
        "CLAUDE ?=",
        "CLAUDE_MODEL ?=",
        "CLAUDE_HOST_PYTHON ?=",
        "CLAUDE_HOST_RECEIPT ?=",
        "CODEX ?=",
        "CODEX_MODEL ?=",
        "CODEX_HOST_PYTHON ?=",
        "CODEX_HOST_RECEIPT ?=",
        "CODEX_HOST_DANGEROUS ?=",
        "PI ?=",
        "PI_HOST_PYTHON ?=",
        "PI_HOST_RECEIPT ?=",
        "CHATGPT_MCP_HANDOFF_RECEIPT ?=",
    )
    for token in stale_defaults:
        assert token not in text

    explicit_override_transports = (
        '$(if $(strip $(OPENCODE)),--opencode "$(OPENCODE)",)',
        '$(if $(strip $(OPENCODE_MODEL)),--model "$(OPENCODE_MODEL)",)',
        '$(if $(strip $(OPENCODE_HOST_PYTHON)),--python "$(OPENCODE_HOST_PYTHON)",)',
        '$(if $(strip $(OPENCODE_HOST_RECEIPT)),--receipt "$(OPENCODE_HOST_RECEIPT)",)',
        '$(if $(strip $(CLAUDE)),--claude "$(CLAUDE)",)',
        '$(if $(strip $(CLAUDE_MODEL)),--model "$(CLAUDE_MODEL)",)',
        '$(if $(strip $(CODEX)),--codex "$(CODEX)",)',
        '$(if $(strip $(CODEX_MODEL)),--model "$(CODEX_MODEL)",)',
        "$(if $(filter 1 true yes,$(CODEX_HOST_DANGEROUS)),--dangerous-bypass,)",
        '$(if $(strip $(PI)),--pi "$(PI)",)',
        (
            "$(if $(strip $(CHATGPT_MCP_HANDOFF_RECEIPT)),"
            '--output "$(CHATGPT_MCP_HANDOFF_RECEIPT)",)'
        ),
    )
    for token in explicit_override_transports:
        assert token in text


def test_hosted_diagnostic_make_aliases_transport_only_explicit_overrides() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")

    for token in ("DIAGNOSTIC_SHARDS ?=", "DIAGNOSTIC_EXTRA_MARKER ?="):
        assert token not in text

    full = _make_recipe(text, "test-diagnostic")
    assert any(
        "$(if $(strip $(DIAGNOSTIC_SHARDS)),--shards $(DIAGNOSTIC_SHARDS),)"
        in line
        for line in full
    )
    assert any(
        "$(if $(strip $(DIAGNOSTIC_EXTRA_MARKER)),"
        "--extra-marker '$(DIAGNOSTIC_EXTRA_MARKER)',)" in line
        for line in full
    )

    batch = _make_recipe(text, "test-diagnostic-batch")
    shard = _make_recipe(text, "test-diagnostic-shard")
    for recipe in (batch, shard):
        assert any(
            "$(if $(strip $(DIAGNOSTIC_SHARDS)),--shards $(DIAGNOSTIC_SHARDS),)"
            in line
            for line in recipe
        )
        assert any(
            "$(if $(strip $(DIAGNOSTIC_EXTRA_MARKER)),"
            "--extra-marker '$(DIAGNOSTIC_EXTRA_MARKER)',)" in line
            for line in recipe
        )
