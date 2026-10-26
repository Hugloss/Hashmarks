from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
        rf"^{re.escape(target)}:[^\n]*\n(?P<recipe>(?:\t.*\n)+)",
        text,
        flags=re.MULTILINE,
    )
    assert match is not None
    return tuple(line.removeprefix("\t") for line in match.group("recipe").splitlines())


def _recorded_make(
    root: Path, target: str, **variables: str
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    native_make = shutil.which("make")
    if native_make is None:
        pytest.skip("native Make is unavailable")
    (root / "Makefile").write_bytes((ROOT / "Makefile").read_bytes())
    (root / "uv.lock").write_text("test-owned locked supply\n", encoding="utf-8")
    journal = root / "uv-calls.jsonl"
    journal.unlink(missing_ok=True)
    stub = root / "record_uv.py"
    stub.write_text(
        "import json, sys\n"
        f"with open({str(journal)!r}, 'a', encoding='utf-8') as output:\n"
        "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            native_make,
            "--no-print-directory",
            target,
            f"UV={shlex.quote(sys.executable)} {shlex.quote(str(stub))}",
            *(f"{key}={value}" for key, value in variables.items()),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    calls = (
        [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        if journal.exists()
        else []
    )
    return result, calls


def test_benchmark_make_aliases_delegate_all_launch_authority() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")

    expected = {
        "benchmark": ('@$(MAKE) --no-print-directory -C "$(EVALSHOT)" benchmark'),
        "benchmark-check": (
            '@$(MAKE) --no-print-directory -C "$(EVALSHOT)" benchmark-check'
        ),
        "benchmark-report": (
            '@$(MAKE) --no-print-directory -C "$(EVALSHOT)" benchmark-report'
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
        "$(if $(strip $(DIAGNOSTIC_SHARDS)),--shards $(DIAGNOSTIC_SHARDS),)" in line
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
            "$(if $(strip $(DIAGNOSTIC_SHARDS)),--shards $(DIAGNOSTIC_SHARDS),)" in line
            for line in recipe
        )
        assert any(
            "$(if $(strip $(DIAGNOSTIC_EXTRA_MARKER)),"
            "--extra-marker '$(DIAGNOSTIC_EXTRA_MARKER)',)" in line
            for line in recipe
        )


def test_mcp_stress_make_alias_transports_only_explicit_receipt_override() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "MCP_STRESS_RECEIPT ?=" not in text
    recipe = _make_recipe(text, "mcp-concurrency-stress")
    assert any(
        "$(if $(strip $(MCP_STRESS_RECEIPT)),"
        '--receipt "$(MCP_STRESS_RECEIPT)",)' in line
        for line in recipe
    )


def test_metrics_make_aliases_transport_only_explicit_workload_overrides() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")

    for token in ("FILES ?= 10000", "HOT_REQUESTS ?= 20"):
        assert token not in text

    for target in ("metrics", "metrics-fast"):
        recipe = _make_recipe(text, target)
        assert any("scripts/metrics.py" in line for line in recipe)
        assert any(
            "$(if $(strip $(FILES)),--files $(FILES),)" in line for line in recipe
        )
        assert any(
            "$(if $(strip $(HOT_REQUESTS)),--hot-requests $(HOT_REQUESTS),)" in line
            for line in recipe
        )

    assert _make_recipe(text, "metrics-scale") == ("@$(MAKE) metrics FILES=100000",)
    assert _make_recipe(text, "metrics-500k") == ("@$(MAKE) metrics FILES=500000",)


def test_derived_authority_make_alias_owns_only_stable_output_path() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = _make_recipe(text, "metrics-derived-authority")

    joined = "\n".join(recipe)
    assert "benchmarks.derived_authority_economics" in joined
    assert (
        "--output .hashmarks/metrics/derived-authority-economics-latest.json" in joined
    )

    for stale in (
        "--iterations 100",
        "--scale 64",
        "--real-iterations 25",
        "--fixture-root tests/fixtures/dependency_dogfood",
    ):
        assert stale not in joined


def test_metrics_agent_make_alias_delegates_normal_defaults() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert _make_recipe(text, "metrics-agent") == (
        "@$(UV_RUN) --offline python -m scripts.agent_evaluation.metrics_agent",
    )

    for stale in ("--files 1000", "--budget 1000"):
        assert stale not in "\n".join(_make_recipe(text, "metrics-agent"))


def test_metrics_agent_corpus_make_alias_delegates_normal_defaults(
    tmp_path: Path,
) -> None:
    rejected, calls = _recorded_make(tmp_path, "metrics-agent-corpus")
    assert rejected.returncode != 0
    assert "HASHMARKS_TARGET is required" in rejected.stderr
    assert calls == []

    workspace = str(tmp_path / "external frozen source")
    accepted, calls = _recorded_make(
        tmp_path, "metrics-agent-corpus", HASHMARKS_TARGET=workspace
    )
    assert accepted.returncode == 0, accepted.stderr
    assert calls[0][0] == "sync"
    assert "doctor" in calls[-2]
    command = calls[-1]
    assert "scripts.agent_evaluation.metrics_agent_corpus" in command
    assert command[command.index("--workspace") + 1] == workspace
    for delegated in ("--corpus", "--budget", "--limit"):
        assert delegated not in command


def test_fresh_multi_repo_make_alias_owns_only_repo_local_paths() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = _make_recipe(text, "metrics-fresh-multi-repo")
    joined = "\n".join(recipe)

    assert "scripts.agent_evaluation.metrics_fresh_multi_repo" in joined
    assert "--root .hashmarks/benchmarks/fresh-multi-repo" in joined
    assert "--output .hashmarks/metrics/fresh-multi-repo-latest.json" in joined

    for stale in (
        "--budget 1200",
        "--limit 20",
        "--min-file-recall 1",
        "--min-symbol-recall 1",
        "--max-fallback-rate 0",
    ):
        assert stale not in joined


def test_worker_inspection_make_alias_delegates_normal_defaults() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = _make_recipe(text, "metrics-worker-inspection-ab")
    joined = "\n".join(recipe)

    assert "scripts.agent_evaluation.metrics_worker_inspection_ab" in joined
    assert "--output .hashmarks/metrics/worker-inspection-ab-latest.json" in joined
    for stale in (
        "--root .hashmarks/benchmarks/worker-inspection-ab",
        "--limit 20",
    ):
        assert stale not in joined


def test_blind_worker_make_alias_owns_only_repo_local_paths() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = _make_recipe(text, "metrics-blind-worker-ab")
    joined = "\n".join(recipe)

    assert "scripts.agent_evaluation.metrics_blind_worker_ab" in joined
    assert "--root .hashmarks/benchmarks/blind-worker-ab" in joined
    assert "--output .hashmarks/metrics/blind-worker-ab-latest.json" in joined
    assert "--limit 20" not in joined


def test_agent_economics_make_alias_delegates_default_mode() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = _make_recipe(text, "metrics-agent-economics")
    joined = "\n".join(recipe)

    assert "scripts.agent_evaluation.metrics_agent_economics" in joined
    assert "--root .hashmarks/benchmarks/agent-economics" in joined
    assert "--output .hashmarks/metrics/agent-economics-latest.json" in joined
    assert "--mode paired" not in joined


def test_worker_behavior_make_alias_owns_only_repo_local_paths() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = _make_recipe(text, "metrics-worker-behavior-ab")
    joined = "\n".join(recipe)

    assert "scripts.agent_evaluation.metrics_worker_behavior_ab" in joined
    assert "--root .hashmarks/benchmarks/worker-behavior-ab" in joined
    assert "--output .hashmarks/metrics/worker-behavior-ab-latest.json" in joined
    assert "--limit 20" not in joined


def test_agent_suite_make_alias_keeps_only_repo_and_qualification_policy(
    tmp_path: Path,
) -> None:
    rejected, calls = _recorded_make(tmp_path, "metrics-agent-suite")
    assert rejected.returncode != 0
    assert "HASHMARKS_TARGET is required" in rejected.stderr
    assert calls == []
    hashmarks_target = str(tmp_path / "external Hashmarks source")
    rejected, calls = _recorded_make(
        tmp_path, "metrics-agent-suite", HASHMARKS_TARGET=hashmarks_target
    )
    assert rejected.returncode != 0
    assert "OH_GOON is required" in rejected.stderr
    assert calls == []

    oh_goon_target = str(tmp_path / "external Oh-Goon source")
    accepted, calls = _recorded_make(
        tmp_path,
        "metrics-agent-suite",
        HASHMARKS_TARGET=hashmarks_target,
        OH_GOON=oh_goon_target,
    )
    assert accepted.returncode == 0, accepted.stderr
    assert calls[0][0] == "sync"
    assert "doctor" in calls[-2]
    command = calls[-1]
    assert "scripts.agent_evaluation.metrics_agent_suite" in command
    repositories = [
        command[index + 1] for index, arg in enumerate(command) if arg == "--repo"
    ]
    assert repositories == [
        f"hashmarks={hashmarks_target}::benchmarks/agent_evaluation/hashmarks_342d510_retrieval_tasks.json",
        f"oh-goon={oh_goon_target}::benchmarks/external/oh_goon_dafbe930_retrieval_tasks.json",
    ]
    for flag, value in (
        ("--min-file-recall", "1"),
        ("--min-symbol-recall", "1"),
        ("--max-fallback-rate", "0"),
        ("--max-average-find-ms", "60"),
        ("--max-average-context-ms", "80"),
        ("--output", ".hashmarks/metrics/agent-suite-latest.json"),
    ):
        assert command[command.index(flag) + 1] == value
    assert "--budget" not in command
    assert "--limit" not in command


def test_codex_agent_economics_make_alias_delegates_root_default() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = _make_recipe(text, "codex-agent-economics")
    joined = "\n".join(recipe)

    assert "scripts.agent_evaluation.codex_agent_economics" in joined
    assert "--output .hashmarks/metrics/codex-agent-economics-latest.json" in joined
    assert "--root .hashmarks/benchmarks/codex-agent-economics" not in joined

    preflight = "\n".join(_make_recipe(text, "codex-agent-economics-preflight"))
    assert "--preflight" in preflight
    assert "--output .hashmarks/metrics/codex-agent-preflight.json" in preflight


def test_codex_selective_scout_make_alias_delegates_root_default() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = _make_recipe(text, "codex-selective-scout-economics")
    joined = "\n".join(recipe)

    assert "scripts.agent_evaluation.codex_selective_scout_economics" in joined
    assert "--output .hashmarks/metrics/codex-selective-scout-latest.json" in joined
    assert "--root .hashmarks/benchmarks/codex-selective-scout" not in joined
