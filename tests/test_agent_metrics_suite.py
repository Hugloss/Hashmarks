from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run_benchmark_script(script: str, root: Path) -> dict:
    output = root.parent / f"{root.name}-result.json"
    module = ".".join(Path(script).with_suffix("").parts)
    subprocess.run(
        [sys.executable, "-m", module, "--root", str(root), "--output", str(output)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return json.loads(output.read_text(encoding="utf-8"))


def _load_script(name: str, path: Path):
    del name
    module = ".".join(path.with_suffix("").parts)
    return importlib.import_module(module)


def test_agent_suite_aggregates_multiple_repositories(tmp_path: Path) -> None:
    corpus_script = _load_script(
        "metrics_agent_corpus", Path("scripts/agent_evaluation/metrics_agent_corpus.py")
    )
    suite = _load_script(
        "metrics_agent_suite", Path("scripts/agent_evaluation/metrics_agent_suite.py")
    )
    repos = []
    for index in range(2):
        workspace = tmp_path / f"repo{index}"
        workspace.mkdir()
        (workspace / "service.py").write_text(
            "def locate_me():\n    return 1\n", encoding="utf-8"
        )
        corpus = tmp_path / f"corpus{index}.json"
        corpus.write_text(
            '{"schema":"hashmarks.agent-task-corpus.v1","tasks":['
            '{"id":"locate","query":"locate_me","expected_files":["service.py"],"expected_symbols":["locate_me"]}'
            "]}"
        )
        repos.append((f"repo{index}", workspace, corpus))
    payload = suite.collect_suite(repos, budget=400, limit=10)
    assert payload["schema"] == "hashmarks.agent-suite-metrics.v1"
    assert payload["parameters"]["repositories"] == 2
    assert payload["parameters"]["tasks"] == 2
    assert payload["summary"]["file_recall"] == 1.0
    assert payload["summary"]["symbol_recall"] == 1.0
    assert payload["summary"]["average_find_ms"] >= 0.0
    assert payload["summary"]["average_context_ms"] >= 0.0
    assert len(payload["repositories"]) == 2


def test_agent_suite_rejects_nested_repository_roots(tmp_path: Path) -> None:
    _load_script(
        "metrics_agent_corpus", Path("scripts/agent_evaluation/metrics_agent_corpus.py")
    )
    suite = _load_script(
        "metrics_agent_suite", Path("scripts/agent_evaluation/metrics_agent_suite.py")
    )
    outer = tmp_path / "outer"
    inner = outer / "external" / "inner"
    inner.mkdir(parents=True)
    corpus = tmp_path / "corpus.json"
    corpus.write_text('{"schema":"hashmarks.agent-task-corpus.v1","tasks":[]}')
    try:
        suite.collect_suite([("outer", outer, corpus), ("inner", inner, corpus)])
    except ValueError as exc:
        assert "must be disjoint" in str(exc)
    else:
        raise AssertionError("nested repository roots must be rejected")


def test_suite_protocol_identity_binds_corpus_workspace_and_parameters(
    tmp_path: Path, monkeypatch
) -> None:
    module = importlib.import_module("scripts.agent_evaluation.metrics_agent_suite")
    corpus = tmp_path / "tasks.json"
    corpus.write_text('{"tasks": []}\n', encoding="utf-8")
    workspace = tmp_path / "repo"
    workspace.mkdir()
    report = {
        "schema": "hashmarks.agent-corpus-metrics.v1",
        "parameters": {"tasks": 1},
        "summary": {
            "file_recall": 1.0,
            "symbol_recall": 1.0,
            "first_query_hit_rate": 1.0,
            "fallback_search_rate": 0.0,
            "average_context_tokens": 1.0,
            "average_candidate_file_reduction": 1.0,
            "average_find_ms": 1.0,
            "average_context_ms": 1.0,
            "p95_find_ms": 1.0,
            "p95_context_ms": 1.0,
            "selected_file_tokens_avoided": 1,
            "seconds": 1.0,
        },
        "sync": {"workspace_fingerprint": "abc"},
    }
    monkeypatch.setattr(module, "collect", lambda *args, **kwargs: report)
    first = module.collect_suite([("repo", workspace, corpus)], budget=1200, limit=20)
    second = module.collect_suite([("repo", workspace, corpus)], budget=1200, limit=20)
    assert first["benchmark_protocol_identity"] == second["benchmark_protocol_identity"]
    assert first["benchmark_protocol"]["repositories"][0]["corpus_sha256"].startswith(
        "sha256:"
    )
    changed = module.collect_suite([("repo", workspace, corpus)], budget=1300, limit=20)
    assert (
        changed["benchmark_protocol_identity"] != first["benchmark_protocol_identity"]
    )


def test_fresh_multi_repo_fixture_is_reproducible_and_disjoint(tmp_path: Path) -> None:
    _load_script(
        "metrics_agent_corpus", Path("scripts/agent_evaluation/metrics_agent_corpus.py")
    )
    _load_script(
        "metrics_agent_suite", Path("scripts/agent_evaluation/metrics_agent_suite.py")
    )
    fresh = _load_script(
        "metrics_fresh_multi_repo",
        Path("scripts/agent_evaluation/metrics_fresh_multi_repo.py"),
    )
    first = fresh.collect_fresh(tmp_path / "first", budget=800, limit=20)
    second = fresh.collect_fresh(tmp_path / "second", budget=800, limit=20)
    assert first["fixture_identity"] == second["fixture_identity"]
    assert first["suite"]["parameters"]["repositories"] == 3
    assert first["suite"]["parameters"]["tasks"] == 18
    assert (
        len(
            {row["workspace_tree_identity"] for row in first["fixture"]["repositories"]}
        )
        == 3
    )


def test_fresh_multi_repo_fixture_has_perfect_localization_floor(
    tmp_path: Path,
) -> None:
    _load_script(
        "metrics_agent_corpus", Path("scripts/agent_evaluation/metrics_agent_corpus.py")
    )
    _load_script(
        "metrics_agent_suite", Path("scripts/agent_evaluation/metrics_agent_suite.py")
    )
    fresh = _load_script(
        "metrics_fresh_multi_repo_floor",
        Path("scripts/agent_evaluation/metrics_fresh_multi_repo.py"),
    )
    payload = fresh.collect_fresh(tmp_path / "fresh", budget=1200, limit=20)
    summary = payload["suite"]["summary"]
    assert summary["file_recall"] == 1.0
    assert summary["symbol_recall"] == 1.0
    assert summary["fallback_search_rate"] == 0.0


def test_blind_worker_input_never_contains_expected_answers(tmp_path: Path) -> None:
    blind = _load_script(
        "metrics_blind_worker_ab",
        Path("scripts/agent_evaluation/metrics_blind_worker_ab.py"),
    )
    repos = blind.materialize_challenge(tmp_path / "challenge")
    assert len(repos) == 3
    for _name, _workspace, corpus, public_path in repos:
        public = json.loads(public_path.read_text(encoding="utf-8"))
        assert public["tasks"]
        assert all(set(row) == {"id", "query"} for row in public["tasks"])
        hidden = json.loads(corpus.read_text(encoding="utf-8"))
        assert any(row.get("expected_files") for row in hidden["tasks"])


@pytest.mark.parametrize(
    ("strategy", "result_field"),
    [
        ("grep", "hits"),
        ("hashmarks", "hits"),
        ("entry-points", "hits"),
        ("ambiguity-reviewer", "review"),
    ],
)
def test_blind_worker_runs_each_public_strategy(
    tmp_path: Path, strategy: str, result_field: str
) -> None:
    from scripts.agent_evaluation.metrics_blind_worker_ab import (
        materialize_challenge,
        run_worker,
    )

    _name, workspace, _corpus, public = materialize_challenge(tmp_path / "challenge")[0]
    output = tmp_path / f"{strategy}.json"

    run_worker(
        strategy=strategy,
        workspace=workspace,
        tasks_path=public,
        output=output,
        limit=20,
    )

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["schema"] == "hashmarks.blind-worker-output.v1"
    assert result["strategy"] == strategy
    assert len(result["tasks"]) == 6
    assert all(result_field in row for row in result["tasks"])


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"schema": "wrong", "tasks": []}, "unsupported blind worker input"),
        (
            {"schema": "hashmarks.blind-worker-tasks.v1", "tasks": {}},
            "blind worker tasks must be a list",
        ),
        (
            {
                "schema": "hashmarks.blind-worker-tasks.v1",
                "tasks": [{"id": "x", "query": "find config", "expected": []}],
            },
            "only id and query",
        ),
    ],
)
def test_blind_worker_rejects_invalid_public_input(
    tmp_path: Path, payload: dict, message: str
) -> None:
    from scripts.agent_evaluation.metrics_blind_worker_ab import run_worker

    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        run_worker(
            strategy="grep",
            workspace=tmp_path,
            tasks_path=tasks,
            output=tmp_path / "output.json",
            limit=20,
        )


@pytest.mark.scale
def test_blind_worker_ab_is_reproducible_and_scores_both_workers(
    tmp_path: Path,
) -> None:
    blind = _load_script(
        "metrics_blind_worker_ab_run",
        Path("scripts/agent_evaluation/metrics_blind_worker_ab.py"),
    )
    first = blind.collect(tmp_path / "first", limit=20)
    assert first["protocol_identity"] == blind._identity(first["protocol"])
    assert first["summary"]["tasks"] == 18
    assert first["summary"]["hashmarks_top20_all_expected_rate"] == 1.0
    assert first["summary"]["entry_points_top20_all_expected_rate"] == 1.0
    assert (
        first["summary"]["entry_points_top1_rate"]
        >= first["summary"]["hashmarks_top1_rate"]
    )
    assert first["protocol"]["worker_input_fields"] == ["id", "query"]
    assert first["protocol"]["hidden_fields"] == ["expected_files", "expected_symbols"]
    assert "hashmarks.ambiguity_reviewer" in first["protocol"]["strategies"]
    assert first["summary"]["reviewer_top1_failure_recall"] == 1.0
    assert first["summary"]["reviewer_success_false_positive_rate"] <= 0.1
    assert first["summary"]["reviewer_spawn"] == "independent-subprocess-per-repository"


@pytest.mark.scale
def test_worker_behavior_ab_is_answer_blind_and_reproducible(tmp_path: Path) -> None:
    first = _run_benchmark_script(
        "scripts/agent_evaluation/metrics_worker_behavior_ab.py", tmp_path / "first"
    )
    assert first["schema"] == "hashmarks.worker-behavior-ab.v1"
    from scripts.agent_evaluation.metrics_worker_behavior_ab import _identity

    assert first["protocol_identity"] == _identity(first["protocol"])
    assert first["protocol"]["worker_input_fields"] == ["id", "query"]
    assert first["protocol"]["hidden_fields"] == ["expected_files", "expected_symbols"]
    assert (
        first["summary"]["direct_unsafe_wrong_first_edits"]
        >= first["summary"]["gated_unsafe_wrong_first_edits"]
    )
    assert first["summary"]["unsafe_wrong_first_edit_reduction"] == 1.0
    assert first["summary"]["gated_unsafe_wrong_first_edits"] == 0
    assert first["summary"]["gated_inspections"] > 0
    assert first["summary"]["correct_immediate_edits_deferred"] >= 0


def test_worker_behavior_worker_rejects_hidden_fields(tmp_path: Path) -> None:
    from scripts.agent_evaluation.metrics_worker_behavior_ab import run_worker

    tasks = tmp_path / "tasks.json"
    tasks.write_text(
        json.dumps(
            {
                "schema": "hashmarks.blind-worker-tasks.v1",
                "tasks": [
                    {"id": "x", "query": "find config", "expected_files": ["secret"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="only id and query"):
        run_worker(
            policy="uncertainty-gated",
            workspace=tmp_path,
            tasks_path=tasks,
            output=tmp_path / "out.json",
            limit=20,
        )


@pytest.mark.scale
def test_worker_inspection_ab_recovers_ambiguity_without_hidden_answers(
    tmp_path: Path,
) -> None:
    first = _run_benchmark_script(
        "scripts/agent_evaluation/metrics_worker_inspection_ab.py", tmp_path / "first"
    )
    assert first["schema"] == "hashmarks.worker-inspection-ab.v1"
    from scripts.agent_evaluation.metrics_worker_inspection_ab import _identity

    assert first["protocol_identity"] == _identity(first["protocol"])
    assert first["protocol"]["worker_input_fields"] == ["id", "query"]
    assert first["protocol"]["hidden_fields"] == ["expected_files", "expected_symbols"]
    assert first["summary"]["inspections"] > 0
    assert first["summary"]["recovered_after_inspection"] > 0
    assert first["summary"]["resolved_unsafe_wrong_final_edits"] == 0


def test_worker_inspection_worker_rejects_hidden_fields(tmp_path: Path) -> None:
    from scripts.agent_evaluation.metrics_worker_inspection_ab import run_worker

    tasks = tmp_path / "tasks.json"
    tasks.write_text(
        json.dumps(
            {
                "schema": "hashmarks.blind-worker-tasks.v1",
                "tasks": [
                    {"id": "x", "query": "find config", "expected_files": ["secret"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="only id and query"):
        run_worker(
            policy="inspect-then-resolve",
            workspace=tmp_path,
            tasks_path=tasks,
            output=tmp_path / "out.json",
            limit=20,
        )


@pytest.mark.parametrize("policy", ["defer-only", "inspect-then-resolve"])
def test_worker_inspection_public_worker_contract(tmp_path: Path, policy: str) -> None:
    from scripts.agent_evaluation.metrics_blind_worker_ab import materialize_challenge
    from scripts.agent_evaluation.metrics_worker_inspection_ab import run_worker

    _name, workspace, _corpus, public = materialize_challenge(tmp_path / "challenge")[0]
    output = tmp_path / f"{policy}.json"

    run_worker(
        policy=policy,
        workspace=workspace,
        tasks_path=public,
        output=output,
        limit=20,
    )

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["policy"] == policy
    assert len(result["tasks"]) == 6
    assert {row["action"] for row in result["tasks"]} <= {
        "edit",
        "no-evidence",
        "inspect-competing-evidence",
        "edit-after-inspection",
        "defer-after-inspection",
    }


@pytest.mark.scale
def test_worker_multistep_ab_improves_edit_safety_and_preserves_verification(
    tmp_path: Path,
) -> None:
    first = _run_benchmark_script(
        "scripts/agent_evaluation/metrics_worker_multistep_ab.py", tmp_path / "first"
    )
    assert first["schema"] == "hashmarks.worker-multistep-ab.v1"
    from scripts.agent_evaluation.metrics_worker_multistep_ab import _identity

    assert first["protocol_identity"] == _identity(first["protocol"])
    assert first["protocol"]["worker_input_fields"] == ["id", "query"]
    assert first["summary"]["guided_unsafe_wrong_edits"] == 0
    assert (
        first["summary"]["guided_correct_edits"]
        >= first["summary"]["direct_correct_edits"]
    )
    assert first["summary"]["guided_correct_verifications"] == first["summary"]["tasks"]
    assert first["summary"]["guided_recovered_wrong_first_hypotheses"] > 0
    assert (
        first["summary"]["guided_evidence_approx_tokens"]
        >= first["summary"]["direct_evidence_approx_tokens"]
    )


def test_worker_multistep_worker_rejects_hidden_fields(tmp_path: Path) -> None:
    from scripts.agent_evaluation.metrics_worker_multistep_ab import run_worker

    tasks = tmp_path / "tasks.json"
    tasks.write_text(
        json.dumps(
            {
                "schema": "hashmarks.blind-worker-tasks.v1",
                "tasks": [
                    {
                        "id": "x",
                        "query": "find config",
                        "expected_verification": "tests/secret.py",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="only id and query"):
        run_worker(
            policy="uncertainty-aware-sequence",
            workspace=tmp_path,
            tasks_path=tasks,
            output=tmp_path / "out.json",
            limit=20,
        )


@pytest.mark.scale
def test_worker_failed_verification_ab_recovers_without_hidden_answers(
    tmp_path: Path,
) -> None:
    from scripts.agent_evaluation.metrics_worker_failed_verification_ab import collect

    first = collect(tmp_path / "first", limit=4)
    assert first["schema"] == "hashmarks.worker-failed-verification-ab.v1"
    from scripts.agent_evaluation.metrics_worker_failed_verification_ab import _identity

    assert first["protocol_identity"] == _identity(first["protocol"])
    assert first["summary"]["tasks"] == 18
    assert first["summary"]["injected_failed_edits"] == 18
    assert first["summary"]["repeat_repeated_failed_edits"] == 18
    assert (
        first["summary"]["fresh_correct_recoveries"]
        > first["summary"]["repeat_correct_recoveries"]
    )
    assert first["summary"]["guided_correct_recoveries"] == 18
    assert first["summary"]["guided_repeated_failed_edits"] == 0
    assert first["summary"]["guided_different_wrong_edits"] == 0
    assert first["protocol"]["injection_authority"] == "grader-only"
    assert "expected_files" in first["protocol"]["worker_hidden_fields"]


def test_worker_failed_verification_worker_rejects_hidden_fields(
    tmp_path: Path,
) -> None:
    from scripts.agent_evaluation.metrics_worker_failed_verification_ab import (
        run_worker,
    )

    tasks = tmp_path / "tasks.json"
    tasks.write_text(
        json.dumps(
            {
                "schema": "hashmarks.worker-failed-verification-input.v1",
                "tasks": [
                    {
                        "id": "x",
                        "query": "fix config",
                        "failed_edit_target": "wrong.py",
                        "verification_target": "tests/test_x.py",
                        "verification_outcome": "failed",
                        "expected_files": ["secret.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hidden or unsupported fields"):
        run_worker(
            policy="evidence-guided-recovery",
            workspace=tmp_path,
            tasks_path=tasks,
            output=tmp_path / "out.json",
            limit=20,
        )


def test_agent_economics_native_baseline_is_answer_blind(tmp_path: Path) -> None:
    from scripts.agent_evaluation.metrics_agent_economics import collect

    first = collect(tmp_path / "first", strategies=("native",))
    second = collect(tmp_path / "second", strategies=("native",))
    assert first["protocol_identity"] == second["protocol_identity"]
    assert first["summary"]["tasks"] == 18
    assert first["summary"]["native_repository_scan_bytes"] > 0
    assert first["summary"]["native_correct_verifications"] == 18
    assert first["protocol"]["worker_public_fields"] == ["id", "query"]


def test_agent_economics_hashmarks_reduces_archaeology_cost(tmp_path: Path) -> None:
    from scripts.agent_evaluation.metrics_agent_economics import collect

    value = collect(tmp_path / "paired", strategies=("native", "hashmarks"))
    s = value["summary"]
    assert s["hashmarks_correct_first_edits"] > s["native_correct_first_edits"]
    assert s["hashmarks_correct_verifications"] == 18
    assert s["hashmarks_repository_scan_bytes"] == 0
    assert s["hashmarks_evidence_approx_tokens"] < s["native_repository_scan_bytes"] / 4


def test_fielded_bm25_economics_is_additive_and_answer_blind(tmp_path: Path) -> None:
    from scripts.agent_evaluation.metrics_bm25_economics import collect

    value = collect(tmp_path / "bm25")
    assert value["summary"]["tasks"] == 18
    assert value["summary"]["current_hashmarks_correct_first"] == 16
    assert (
        value["summary"]["bm25_correct_first"]
        < value["summary"]["current_hashmarks_correct_first"]
    )
    assert (
        value["summary"]["candidate_fused_correct_first"]
        < value["summary"]["current_hashmarks_correct_first"]
    )
    assert value["summary"]["promotion_decision"] == "reject"
    assert value["summary"]["canonical_after_experiment_correct_first"] == 16
    assert value["protocol"]["hidden_fields"] == ["expected_files", "expected_symbols"]


def test_constrained_bm25_does_not_earn_promotion(tmp_path: Path) -> None:
    from scripts.agent_evaluation.metrics_bm25_constrained import collect

    value = collect(tmp_path / "constrained")
    s = value["summary"]
    assert s["current_hashmarks_correct_first"] == 16
    assert s["constrained_bm25_correct_first"] <= 16
    assert s["role_resolved_correct_first"] == 18
    assert s["bm25_incremental_gain"] <= 0
    assert s["promotion_decision"] == "reject"


def test_retrieval_residuals_reject_new_recall_indexes_for_ambiguity_only_misses(
    tmp_path: Path,
) -> None:
    from scripts.agent_evaluation.metrics_retrieval_residuals import collect

    value = collect(tmp_path / "residuals")
    s = value["summary"]
    assert s["tasks"] == 18
    assert s["top1_correct"] == 16
    assert s["top5_any_expected"] == 18
    assert s["top20_all_expected"] == 18
    assert s["residual_counts"]["role-authority-ambiguity"] == 2
    assert s["residual_counts"]["discovery-miss"] == 0
    assert s["ngram_admission"] is False
    assert s["embedding_admission"] is False
    assert s["retrieval_subagent_admission"] is True


@pytest.mark.scale
def test_selective_scout_targets_only_observed_ambiguity(tmp_path: Path) -> None:
    from scripts.agent_evaluation.metrics_selective_scout import collect

    value = collect(tmp_path / "scout")
    s = value["summary"]
    assert s["no_scout_correct_final"] == 16
    assert s["selective_scout_correct_final"] == 18
    assert s["selective_scout_wrong_final"] == 0
    assert s["selective_scout_scout_spawns"] == 2
    assert s["always_scout_scout_spawns"] == 18
    assert s["always_extra_spawns_vs_selective"] == 16
    assert s["selective_spawn_rate"] == 2 / 18
    assert value["protocol"]["hidden_fields"] == ["expected_files", "expected_symbols"]


def test_codex_agent_economics_preflight_reports_missing_binary() -> None:
    from scripts.agent_evaluation.codex_agent_economics import preflight

    value = preflight("definitely-not-a-real-codex-binary-hashmarks")
    assert value["available"] is False
    assert value["reason"] == "executable-not-found"


def test_codex_agent_economics_exec_contract_with_fake_codex(tmp_path: Path) -> None:
    from scripts.agent_evaluation.codex_agent_economics import CodexRunConfig, _run_one

    fake = tmp_path / "codex"
    fake.write_text(
        """#!/usr/bin/env python3\nimport json, pathlib, sys\nargs=sys.argv[1:]\nif args==["--version"]:\n print("codex-cli fake-1.0"); raise SystemExit(0)\nout=pathlib.Path(args[args.index("--output-last-message")+1]); out.parent.mkdir(parents=True,exist_ok=True)\nprompt=sys.stdin.read(); tid=prompt.split("Task id: ",1)[1].splitlines()[0]\nvalue={"task_id":tid,"first_edit_target":"src/example.py","verification_target":"tests/test_example.py","confidence":"high","notes":"fake"}\nout.write_text(json.dumps(value))\nprint(json.dumps({"type":"thread.started","thread_id":"fake-thread"}))\nprint(json.dumps({"type":"turn.completed","usage":{"input_tokens":101,"cached_input_tokens":50,"output_tokens":23,"reasoning_output_tokens":7,"total_tokens":124}}))\n""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    ws = tmp_path / "repo"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src/example.py").write_text("x=1\n")
    (ws / "tests").mkdir()
    (ws / "tests/test_example.py").write_text("def test_x(): pass\n")
    task = {"id": "t1", "query": "fix example"}
    value = _run_one(
        CodexRunConfig(
            codex=str(fake),
            model="fake-model",
            effort="low",
            sandbox="read-only",
            bridge=Path("unused"),
            timeout_s=30,
        ),
        "native",
        task,
        ws,
        tmp_path / "run",
    )
    assert value["returncode"] == 0
    assert value["final"]["task_id"] == "t1"
    assert value["usage"]["input_tokens"] == 101
    assert value["usage"]["total_tokens"] == 124
    assert "--output-schema" in value["command"]
    assert "--output-last-message" in value["command"]
    assert "-C" in value["command"]


def test_codex_selective_scout_rejects_path_outside_worker_visible_candidates(
    tmp_path: Path,
) -> None:
    from scripts.agent_evaluation.codex_agent_economics import CodexRunConfig
    from scripts.agent_evaluation.codex_selective_scout_economics import _run_scout

    fake = tmp_path / "codex"
    fake.write_text(
        """#!/usr/bin/env python3\nimport json, pathlib, sys\nargs=sys.argv[1:]; out=pathlib.Path(args[args.index("--output-last-message")+1]); out.parent.mkdir(parents=True,exist_ok=True); prompt=sys.stdin.read(); tid=prompt.split("Task id: ",1)[1].splitlines()[0]; out.write_text(json.dumps({"task_id":tid,"recommended_path":"secret/not-a-candidate.py","confidence":"high","reason":"bad"})); print(json.dumps({"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15}}))\n"""
    )
    fake.chmod(0o755)
    ws = tmp_path / "repo"
    ws.mkdir()
    (ws / "a.py").write_text("x=1\n")
    pkt = {
        "ambiguity": {
            "alternatives": [
                {"role": "implementation", "path": "a.py", "canonical_rank": 1}
            ]
        }
    }
    result = _run_scout(
        CodexRunConfig(
            codex=str(fake),
            model=None,
            effort=None,
            sandbox="read-only",
            bridge=Path("unused"),
            timeout_s=30,
        ),
        {"id": "x", "query": "fix x"},
        ws,
        pkt,
        tmp_path / "run",
    )
    assert result["returncode"] == 0
    assert result["final"]["recommended_path"] is None
    assert result["final"]["reason"] == "rejected-non-candidate-scout-output"
    assert result["usage"]["total_tokens"] == 15


def test_codex_selective_scout_prompt_is_answer_blind() -> None:
    from scripts.agent_evaluation.codex_selective_scout_economics import _scout_prompt

    pkt = {
        "ambiguity": {
            "alternatives": [
                {"role": "authority", "path": "AGENTS.md", "canonical_rank": 4},
                {
                    "role": "verification",
                    "path": "tests/test_x.py",
                    "canonical_rank": 1,
                },
            ]
        }
    }
    prompt = _scout_prompt(
        {"id": "x", "query": "find authority"}, Path("/tmp/repo"), pkt
    )
    assert "expected_files" not in prompt
    assert "AGENTS.md" in prompt and "tests/test_x.py" in prompt
    assert "hidden answers" in prompt.lower()


def test_codex_rollout_usage_recovers_thread_and_token_counts(tmp_path: Path) -> None:
    from scripts.agent_evaluation.codex_rollout_usage import recover

    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"type": "thread.started", "thread_id": "thread-123"}) + "\n"
    )
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    rollout = sessions / "rollout-thread-123.jsonl"
    rollout.write_text(
        json.dumps(
            {
                "event_msg": {
                    "payload": {
                        "type": "token_count",
                        "input_tokens": 120,
                        "cached_input_tokens": 80,
                        "output_tokens": 30,
                        "reasoning_output_tokens": 10,
                        "total_tokens": 150,
                    }
                }
            }
        )
        + "\n"
    )
    value = recover(events, sessions)
    assert value["recovered"] is True
    assert value["thread_id"] == "thread-123"
    assert value["usage"]["total_tokens"] == 150
    assert value["usage"]["input_tokens"] == 120


def test_codex_economics_matrix_plan_is_fail_closed_without_codex(
    tmp_path: Path,
) -> None:
    from scripts.agent_evaluation.codex_economics_matrix import parse_variant, plan

    variants = [
        parse_variant("cheap-native:cheap-model:low:native"),
        parse_variant("cheap-hm:cheap-model:low:hashmarks"),
        parse_variant("cheap-scout:cheap-model:low:selective-real"),
        parse_variant("strong-native:strong-model:medium:native"),
    ]
    value = plan(variants, tmp_path, "definitely-no-codex-here", None)
    assert value["preflight"]["available"] is False
    assert value["execution_units"] == 18 + 18 + 21 + 18
    assert len(value["variants"]) == 4
    assert value["variants"][2]["strategy"] == "selective-real"
