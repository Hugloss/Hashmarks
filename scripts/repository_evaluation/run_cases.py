from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.research_receipts import evaluate_with_receipt, work_identity
from hashmarks.codemap import CodeMap
from hashmarks.producer_identity import native_producer_implementation_identity
from hashmarks.test_shards import repository_content_identity
from scripts.repository_evaluation.common import (
    CASES_SCHEMA,
    RUN_SCHEMA,
    canonical_sha256,
    load_json,
    write_json,
)


def _repository_identity(codemap: CodeMap) -> str:
    excluded = [codemap.state_dir]
    artifact_path = getattr(getattr(codemap, "artifacts", None), "db_path", None)
    if isinstance(artifact_path, Path):
        excluded.append(artifact_path)
    return repository_content_identity(
        codemap.workspace,
        excluded_paths=tuple(excluded),
    )


def _case_result(codemap: CodeMap, case: Mapping[str, object]) -> dict[str, Any]:
    operation = str(case.get("operation") or "")
    if operation != "task_action_map":
        raise ValueError(f"unsupported repository evaluation operation: {operation}")
    task = str(case.get("task") or "")
    limit = int(case.get("limit") or 20)
    started = time.perf_counter_ns()
    with codemap.decision_session(diagnostics=True):
        hits = codemap.find_task(task, limit=limit)
        action = codemap.task_action_map(
            task,
            limit=limit,
            per_role=int(case.get("per_role") or 3),
        )
        diagnostics = codemap.decision_session_diagnostics()
    return {
        "task": task,
        "retrieval": [
            {
                "path": hit.path,
                "name": hit.name,
                "qualname": hit.qualname,
                "score": hit.score,
                "kind": hit.kind,
            }
            for hit in hits
        ],
        "action": action,
        "diagnostics": diagnostics,
        "elapsed_ns": time.perf_counter_ns() - started,
    }


def run_cases(
    *,
    workspace: Path,
    cases_path: Path,
    receipts_dir: Path,
    producer_artifact_identity: str | None = None,
    shard_count: int = 1,
    shard_index: int = 0,
) -> dict[str, Any]:
    cases_doc = load_json(cases_path, schema=CASES_SCHEMA)
    cases = cases_doc.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("repository evaluation requires a non-empty cases list")
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("invalid repository evaluation shard")
    selected_cases = [
        case for index, case in enumerate(cases) if index % shard_count == shard_index
    ]

    workspace = workspace.resolve()
    producer_identity = native_producer_implementation_identity()
    started = time.perf_counter_ns()
    rows: list[dict[str, object]] = []
    counters = {"reused": 0, "created": 0}

    shard_state = (receipts_dir / f".state-{shard_index}").resolve()
    shard_state.mkdir(parents=True, exist_ok=True)
    with CodeMap(
        workspace,
        state_dir=shard_state,
        artifact_db=shard_state / "artifacts.sqlite3",
    ) as codemap:
        sync = codemap.sync()
        repository_identity = _repository_identity(codemap)
        protocol_identity = "sha256:" + canonical_sha256(
            {
                "schema": CASES_SCHEMA,
                "suite": cases_doc.get("suite"),
                "cases_sha256": canonical_sha256(cases_doc),
                "repository_identity": repository_identity,
                "producer_implementation_identity": producer_identity,
                "producer_artifact_identity": producer_artifact_identity,
            }
        )

        for case in selected_cases:
            if not isinstance(case, Mapping):
                raise ValueError("repository evaluation case must be an object")
            case_id = str(case.get("id") or "")
            if not case_id:
                raise ValueError("repository evaluation case id is required")
            result, was_reused = evaluate_with_receipt(
                receipt_path=receipts_dir / f"{case_id}.json",
                identity=work_identity(
                    protocol_identity=protocol_identity,
                    work_id=case_id,
                    work_payload={
                        "case": dict(case),
                        "repository_identity": repository_identity,
                        "producer_implementation_identity": producer_identity,
                    },
                    lane="repository-evaluation",
                ),
                evaluate=lambda case=case: _case_result(codemap, case),
            )
            counters["reused"] += int(was_reused)
            counters["created"] += int(not was_reused)
            rows.append(
                {
                    "id": case_id,
                    "receipt_reused": was_reused,
                    "result": result,
                }
            )

    return {
        "schema": RUN_SCHEMA,
        "suite": cases_doc.get("suite"),
        "protocol_identity": protocol_identity,
        "repository_identity": repository_identity,
        "producer_implementation_identity": producer_identity,
        "producer_artifact_identity": producer_artifact_identity,
        "codemap_generation": int(sync.generation),
        "cases_sha256": "sha256:" + canonical_sha256(cases_doc),
        "shard_count": shard_count,
        "shard_index": shard_index,
        "selected_case_count": len(selected_cases),
        "reused_cases": counters["reused"],
        "new_cases": counters["created"],
        "timing_comparable": counters["reused"] == 0,
        "elapsed_ns": time.perf_counter_ns() - started,
        "cases": rows,
        "authority": "repository-intelligence-measurement-only",
        "execution_authority": "external",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--producer-artifact-identity")
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()
    result = run_cases(
        workspace=args.workspace,
        cases_path=args.cases,
        receipts_dir=args.receipts,
        producer_artifact_identity=args.producer_artifact_identity,
        shard_count=args.shard_count,
        shard_index=args.shard_index,
    )
    write_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
