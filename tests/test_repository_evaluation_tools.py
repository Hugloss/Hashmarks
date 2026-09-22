import contextlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.repository_evaluation.compare_runs import compare_runs
from scripts.repository_evaluation.grade_cases import grade_run
from scripts.repository_evaluation.merge_runs import merge_runs
from scripts.repository_evaluation.run_cases import run_cases


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _cases(path: Path) -> None:
    path.write_text(
        """{
  "schema": "hashmarks.repository-evaluation-cases.v1",
  "suite": "portable-evaluation",
  "cases": [
    {
      "id": "target",
      "operation": "task_action_map",
      "task": "optimize active_target",
      "limit": 20,
      "per_role": 3
    }
  ]
}
""",
        encoding="utf-8",
    )


def _grader() -> dict[str, object]:
    return {
        "schema": "hashmarks.repository-evaluation-grader.v1",
        "suite": "portable-evaluation",
        "cases": {
            "target": {
                "expected_edit_path": "src/live.py",
                "expected_edit_qualname": "active_target",
                "must_be_ambiguous": False,
            }
        },
    }


def test_repository_evaluation_scripts_are_directly_executable() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in (
        "run_cases.py",
        "grade_cases.py",
        "compare_runs.py",
        "merge_runs.py",
        "profile_cases.py",
        "compare_profiles.py",
        "merge_profiles.py",
    ):
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "scripts/repository_evaluation" / name),
                "--help",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr


def test_repository_evaluation_separates_public_cases_from_grader_and_reuses_exact_receipt(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/live.py", "def active_target():\n    return 1\n")
    cases = tmp_path / "cases.json"
    receipts = tmp_path / "receipts"
    _cases(cases)

    first = run_cases(workspace=repo, cases_path=cases, receipts_dir=receipts)
    second = run_cases(workspace=repo, cases_path=cases, receipts_dir=receipts)
    report = grade_run(run=first, grader=_grader())

    assert first["new_cases"] == 1
    assert first["reused_cases"] == 0
    assert first["timing_comparable"] is True
    assert second["new_cases"] == 0
    assert second["reused_cases"] == 1
    assert second["timing_comparable"] is False
    assert report["counters"]["PASS"] == 1
    assert report["counters"]["FALSE_SAFE_EDIT"] == 0
    assert "expected_edit_path" not in first["cases"][0]["result"]


def test_repository_evaluation_receipt_rejects_target_repository_identity_drift(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/live.py", "def active_target():\n    return 1\n")
    cases = tmp_path / "cases.json"
    receipts = tmp_path / "receipts"
    _cases(cases)
    run_cases(workspace=repo, cases_path=cases, receipts_dir=receipts)

    _write(repo, "src/live.py", "def active_target():\n    return 2\n")
    with pytest.raises(ValueError, match="receipt identity mismatch"):
        run_cases(workspace=repo, cases_path=cases, receipts_dir=receipts)


@pytest.mark.parametrize(
    ("case_rows", "options", "message"),
    [
        ([], {}, "non-empty cases list"),
        (["not-an-object"], {}, "case must be an object"),
        ([{"operation": "task_action_map", "task": "target"}], {}, "id is required"),
        (
            [{"id": "target", "operation": "unknown", "task": "target"}],
            {},
            "unsupported repository evaluation operation",
        ),
        (
            [{"id": "target", "operation": "task_action_map", "task": "target"}],
            {"shard_count": 0},
            "invalid repository evaluation shard",
        ),
    ],
)
def test_repository_evaluation_rejects_invalid_selection_contract(
    tmp_path: Path,
    case_rows: list[object],
    options: dict[str, int],
    message: str,
) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/live.py", "def target():\n    return 1\n")
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps(
            {
                "schema": "hashmarks.repository-evaluation-cases.v1",
                "suite": "invalid-selection",
                "cases": case_rows,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        run_cases(
            workspace=repo,
            cases_path=cases,
            receipts_dir=tmp_path / "receipts",
            **options,
        )


def test_repository_evaluation_grader_classifies_false_safe_edit() -> None:
    run = {
        "schema": "hashmarks.repository-evaluation-run.v1",
        "suite": "portable-evaluation",
        "protocol_identity": "sha256:run",
        "repository_identity": "sha256:repo:1",
        "producer_implementation_identity": "sha256:producer",
        "producer_artifact_identity": None,
        "timing_comparable": True,
        "cases": [
            {
                "id": "target",
                "result": {
                    "action": {
                        "edit": {"path": "src/wrong.py", "qualname": "wrong"},
                        "ambiguity": {"ambiguous": False},
                    }
                },
            }
        ],
    }
    report = grade_run(run=run, grader=_grader())
    assert report["counters"]["FALSE_SAFE_EDIT"] == 1
    assert report["counters"]["FALSE_UNIQUE"] == 0


def test_repository_evaluation_comparison_suppresses_resumed_timing() -> None:
    baseline = {
        "schema": "hashmarks.repository-evaluation-run.v1",
        "protocol_identity": "sha256:base",
        "producer_implementation_identity": "sha256:producer-a",
        "timing_comparable": True,
        "cases": [],
    }
    candidate = {
        "schema": "hashmarks.repository-evaluation-run.v1",
        "protocol_identity": "sha256:candidate",
        "producer_implementation_identity": "sha256:producer-b",
        "timing_comparable": False,
        "cases": [],
    }
    comparison = compare_runs(baseline=baseline, candidate=candidate)
    assert comparison["timing_comparable"] is False
    assert "suppressed" in comparison["timing_note"]


def test_repository_evaluation_shards_merge_without_duplicate_work(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/live.py", "def active_target():\n    return 1\n")
    cases = tmp_path / "cases.json"
    cases.write_text(
        '{"schema":"hashmarks.repository-evaluation-cases.v1","suite":"portable-evaluation","cases":['
        '{"id":"a","operation":"task_action_map","task":"fix active_target"},'
        '{"id":"b","operation":"task_action_map","task":"optimize active_target"}]}'
    )
    receipts = tmp_path / "receipts"
    first = run_cases(
        workspace=repo,
        cases_path=cases,
        receipts_dir=receipts,
        shard_count=2,
        shard_index=0,
    )
    second = run_cases(
        workspace=repo,
        cases_path=cases,
        receipts_dir=receipts,
        shard_count=2,
        shard_index=1,
    )
    merged = merge_runs([first, second])
    assert merged["complete"] is True
    assert [row["id"] for row in merged["cases"]] == ["a", "b"]


def test_repository_evaluation_merge_rejects_invalid_identity_and_membership() -> None:
    base = {
        "suite": "suite",
        "protocol_identity": "sha256:protocol",
        "repository_identity": "sha256:repository",
        "producer_implementation_identity": "sha256:producer",
        "producer_artifact_identity": None,
        "cases_sha256": "sha256:cases",
        "shard_count": 2,
        "shard_index": 0,
        "cases": [{"id": "case-a"}],
    }
    with pytest.raises(ValueError, match="at least one"):
        merge_runs([])
    with pytest.raises(ValueError, match="identity mismatch: protocol_identity"):
        merge_runs([base, {**base, "protocol_identity": "sha256:other"}])
    with pytest.raises(ValueError, match="shard-count mismatch"):
        merge_runs([base, {**base, "shard_count": 3}])
    with pytest.raises(ValueError, match="case must be an object"):
        merge_runs([{**base, "cases": ["invalid"]}])
    with pytest.raises(ValueError, match="duplicate or empty"):
        merge_runs([base, {**base, "shard_index": 1}])


def test_repository_evaluation_grader_distinguishes_over_and_wrong_ambiguity() -> None:
    base = {
        "schema": "hashmarks.repository-evaluation-run.v1",
        "suite": "portable-evaluation",
        "protocol_identity": "sha256:x",
        "repository_identity": "sha256:r",
        "producer_implementation_identity": "sha256:p",
        "producer_artifact_identity": None,
        "timing_comparable": True,
    }
    over = {
        **base,
        "cases": [
            {
                "id": "target",
                "result": {
                    "retrieval": [{"path": "src/live.py"}],
                    "action": {
                        "edit": {"path": "src/live.py", "qualname": "active_target"},
                        "ambiguity": {"ambiguous": True},
                    },
                },
            }
        ],
    }
    wrong = {
        **base,
        "cases": [
            {
                "id": "target",
                "result": {
                    "retrieval": [{"path": "src/live.py"}],
                    "action": {
                        "edit": {"path": "src/wrong.py", "qualname": "wrong"},
                        "ambiguity": {"ambiguous": True},
                    },
                },
            }
        ],
    }
    assert grade_run(run=over, grader=_grader())["counters"]["OVER_AMBIGUOUS"] == 1
    report = grade_run(run=wrong, grader=_grader())
    assert report["counters"]["WRONG_AMBIGUOUS"] == 1
    assert report["cases"][0]["failure_stage"] == "AMBIGUITY_ERROR"


def test_profile_comparison_uses_same_version_noise_floor() -> None:
    from scripts.repository_evaluation.compare_profiles import compare_profiles

    def doc(median: int):
        return {
            "cases": [
                {
                    "id": "x",
                    "median_ns": median,
                    "semantic_fingerprint": "sha256:same",
                    "semantic_stable": True,
                }
            ]
        }

    result = compare_profiles(
        baseline=doc(100), candidate=doc(94), repeat=doc(96), minimum_gain_pct=3.0
    )
    assert result["cases"][0]["same_version_noise_pct"] == 4.0
    assert result["cases"][0]["decision"] == "WIN"
    noisy = compare_profiles(
        baseline=doc(100), candidate=doc(94), repeat=doc(93), minimum_gain_pct=3.0
    )
    assert noisy["cases"][0]["decision"] == "NOISE_BAND"


def test_profile_comparison_uses_per_case_noise_not_global_p90() -> None:
    from scripts.repository_evaluation.compare_profiles import compare_profiles

    def doc(x: int, y: int):
        return {
            "cases": [
                {
                    "id": "stable",
                    "median_ns": x,
                    "semantic_fingerprint": "sha256:s",
                    "semantic_stable": True,
                },
                {
                    "id": "noisy",
                    "median_ns": y,
                    "semantic_fingerprint": "sha256:n",
                    "semantic_stable": True,
                },
            ]
        }

    result = compare_profiles(
        baseline=doc(100, 100),
        candidate=doc(88, 100),
        repeat=doc(100, 60),
        minimum_gain_pct=3.0,
    )
    rows = {row["id"]: row for row in result["cases"]}
    assert result["noise_floor_percent"] == 40.0
    assert "diagnostic only" in result["noise_floor_authority"]
    assert rows["stable"]["required_gain_pct"] == 3.0
    assert rows["stable"]["decision"] == "WIN"


def test_profile_shards_merge_strict_identity_and_complete() -> None:
    from scripts.repository_evaluation.merge_profiles import merge_profiles

    def shard(index: int, case_id: str):
        return {
            "schema": "hashmarks.repository-evaluation-profile.v1",
            "suite": "s",
            "cases_sha256": "sha256:c",
            "repository_identity": "sha256:r",
            "producer_implementation_identity": "sha256:p",
            "warmups": 2,
            "samples": 5,
            "shard_count": 2,
            "shard_index": index,
            "cases": [{"id": case_id}],
        }

    merged = merge_profiles([shard(1, "b"), shard(0, "a")])
    assert merged["complete"] is True
    assert [r["id"] for r in merged["cases"]] == ["a", "b"]
    with pytest.raises(ValueError, match="incomplete profile shards"):
        merge_profiles([shard(0, "a")])
    bad = shard(1, "b")
    bad["repository_identity"] = "sha256:other"
    with pytest.raises(ValueError, match="profile identity mismatch"):
        merge_profiles([shard(0, "a"), bad])


def test_paired_profile_interleaves_semantics_and_fails_closed_on_noise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.repository_evaluation.profile_cases as profiles

    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    _write(repo_a, "src/live.py", "def active_target():\n    return 1\n")
    _write(repo_b, "src/live.py", "def active_target():\n    return 1\n")
    cases = tmp_path / "cases.json"
    _cases(cases)
    timings = iter([100, 100, 100, 100, 100, 140, 100, 60, 100, 140])
    original = profiles._run_action

    def fake(codemap, case):
        elapsed, _ = original(codemap, case)
        with contextlib.suppress(StopIteration):
            elapsed = next(timings)
        return elapsed, "sha256:same"

    monkeypatch.setattr(profiles, "_run_action", fake)
    result = profiles.paired_profile_cases(
        workspace_a=repo_a,
        workspace_b=repo_b,
        cases_path=cases,
        warmups=0,
        pairs=5,
        max_control_mad_pct=10.0,
    )
    row = result["cases"][0]
    assert row["semantic_equal"] is True
    assert row["paired_mad_pct"] > 10.0
    assert row["admitted"] is False
    assert row["admission_reason"] == "UNSTABLE_NOISE"
