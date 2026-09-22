from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.agent_evaluation.repository_quality_measurement import (
    comparable_economics,
    measurement_health,
    measurement_receipt,
)
from scripts.agent_evaluation.repository_quality_receipt import (
    execution_receipt,
    execution_receipt_health,
    validate_execution_receipt,
)


def _execution() -> dict:
    return execution_receipt(
        case_id="case",
        corpus_identity="sha256:corpus",
        identities={
            "repository_identity": "sha256:repo",
            "source_identity": "sha256:source",
            "task_identity": "sha256:task",
            "policy_identity": "policy:v1",
            "generation_identity": "sha256:generation",
            "authority_proof_identity": "sha256:proof",
        },
        surfaces=[\n            {\n                "surface": "task-evidence",\n                "authority_proof_identity": "sha256:proof",\n            }\n        ],
        mutations=[],
    )


def _measurement(**overrides) -> dict:
    values = {
        "execution_receipt_identity": _execution()["receipt_identity"],
        "environment_fingerprint": "env:linux-py311",
        "mode": "warm",
        "ranking": {"rank": 1},
        "verification": {"rank": 2},
        "retention": {
            "related_dependency_retained": True,
            "impact_evidence_retained": True,
        },
        "economics": {
            "latency_ms": 12,
            "rows_inspected": 40,
            "candidate_count": 5,
            "peak_memory_bytes": 2048,
        },
    }
    values.update(overrides)
    return measurement_receipt(**values)


def test_execution_receipt_identity_is_recomputed_not_trusted() -> None:
    receipt = _execution()
    validate_execution_receipt(receipt)
    tampered = json.loads(json.dumps(receipt))
    tampered["identities"]["generation_identity"] = "sha256:other"
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_execution_receipt(tampered)


def test_receipt_health_separates_invalid_from_stale() -> None:
    fresh = _execution()
    stale = _execution()
    stale["identities"] = {\n        **stale["identities"],\n        "generation_identity": "sha256:old",\n    }
    stale["receipt_identity"] = execution_receipt(
        case_id="case",
        corpus_identity="sha256:corpus",
        identities=stale["identities"],
        surfaces=stale["surfaces"],
        mutations=[],
    )["receipt_identity"]
    health = execution_receipt_health(
        [fresh, stale],
        repository_identity="sha256:repo",
        generation_identity="sha256:generation",
    )
    assert health == {
        "receipts": 2,
        "valid": 2,
        "invalid": 0,
        "fresh": 1,
        "stale": 1,
        "ready": False,
    }


def test_measurement_identity_binds_execution_and_environment() -> None:
    baseline = _measurement()
    changed_execution = _measurement(execution_receipt_identity="sha256:other")
    changed_environment = _measurement(environment_fingerprint="env:other")
    assert baseline["measurement_identity"] != changed_execution["measurement_identity"]
    assert baseline["measurement_identity"] != changed_environment["measurement_identity"]


def test_economics_are_comparable_only_inside_same_environment_and_mode() -> None:
    warm = _measurement()
    cold = _measurement(mode="cold")
    other_environment = _measurement(environment_fingerprint="env:other")
    assert comparable_economics([warm, _measurement()])["comparable"] is True
    assert comparable_economics([warm, cold])["comparable"] is False
    assert comparable_economics([warm, other_environment])["comparable"] is False


def test_measurement_health_reports_ranking_retention_and_comparability() -> None:
    report = measurement_health([_measurement(), _measurement()])
    assert report["economics"]["comparable"] is True
    assert report["owner_ranking"]["recall_at_1"] == 1
    assert report["verification_ranking"]["recall_at_1"] == 0
    assert report["verification_ranking"]["recall_at_5"] == 1
    assert report["retention"]["related_dependency_retained"]["rate"] == 1


@pytest.mark.parametrize(
    "economics",
    [
        {"latency_ms": -1},
        {"rows_inspected": -1},
        {"candidate_count": -1},
        {"peak_memory_bytes": -1},
    ],
)
def test_negative_economics_fail_closed(economics) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        _measurement(economics=economics)


def test_retained_benchmark_artifacts_are_real_repository_evidence() -> None:
    root = Path(__file__).resolve().parents[1] / "benchmarks/agent_evaluation/retained"
    corpora = sorted(root.glob("challenge/base/corpora/*.json"))
    repos = sorted(\n        path for path in (root / "challenge/base/repos").iterdir() if path.is_dir()\n    )
    outputs = sorted(root.glob("outputs/*.json"))
    assert len(corpora) >= 3
    assert len(repos) >= 3
    assert outputs
