# Imports below follow the standalone script path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hashmarks.codemap import (
    CodeMap,
)
from scripts.agent_evaluation.economics import (
    verification_surface,
)

SCHEMA = "hashmarks.agent-task-start-qualification.v1"


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _task_candidate(packet: dict[str, object]) -> dict[str, object] | None:
    ownership = packet.get("ownership")
    if not isinstance(ownership, dict):
        return None
    candidate = ownership.get("candidate")
    return candidate if isinstance(candidate, dict) else None


def _task_verification(packet: dict[str, object]) -> dict[str, object]:
    value = packet.get("verification")
    return value if isinstance(value, dict) else {}


def _packet_bytes(packet: dict[str, object]) -> int:
    return len(
        json.dumps(
            packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )


def run(
    repo: Path,
    public_path: Path,
    secret_path: Path,
    output: Path,
    *,
    token_budget: int = 1536,
) -> dict[str, Any]:
    public = json.loads(public_path.read_text(encoding="utf-8"))
    tasks = public.get("tasks")
    if (
        not isinstance(tasks, list)
        or not tasks
        or any(set(row) != {"id", "query"} for row in tasks)
    ):
        raise ValueError("PUBLIC tasks must contain exactly id/query")
    if token_budget < 1:
        raise ValueError("token_budget must be >= 1")

    frozen: list[dict[str, Any]] = []
    with CodeMap(repo) as codemap:
        sync_started = time.perf_counter()
        codemap.sync()
        sync_ms = (time.perf_counter() - sync_started) * 1000.0

        for task in tasks:
            started = time.perf_counter()
            packet = codemap.task_evidence(
                str(task["query"]), token_budget=token_budget
            )
            first_ms = (time.perf_counter() - started) * 1000.0
            provenance = (
                packet.get("provenance")
                if isinstance(packet.get("provenance"), dict)
                else {}
            )
            candidate = _task_candidate(packet)
            edit_path = (
                str(candidate.get("path") or "") if candidate is not None else ""
            )
            file_row = codemap.store.file_row(edit_path) if edit_path else None
            indexed_revision = (
                str(file_row["file_digest"]) if file_row is not None else None
            )
            frozen.append(
                {
                    "id": str(task["id"]),
                    "packet": packet,
                    "packet_bytes": _packet_bytes(packet),
                    "first_warm_ms": first_ms,
                    "provenance_complete": bool(
                        provenance.get("why")
                        and provenance.get("revision")
                        and isinstance(packet.get("freshness"), dict)
                        and packet["freshness"].get("state")
                        in {"current", "stale", "unknown"}
                    ),
                    "revision_current": bool(
                        indexed_revision
                        and provenance.get("revision") == indexed_revision
                    ),
                    "freshness_state": str(
                        (packet.get("freshness") or {}).get("state", "missing")
                    ),
                    "selection_reason": str(provenance.get("why") or "missing"),
                }
            )

        # A second identical pass measures the long-lived service/cache fast path.
        # It runs before SECRET is opened and must not alter the frozen decisions.
        for row, task in zip(frozen, tasks, strict=True):
            started = time.perf_counter()
            repeated = codemap.task_evidence(
                str(task["query"]), token_budget=token_budget
            )
            row["cached_warm_ms"] = (time.perf_counter() - started) * 1000.0
            row["cached_packet_identity"] = _identity(repeated)
            row["packet_identity"] = _identity(row["packet"])
            row["stable"] = row["cached_packet_identity"] == row["packet_identity"]

    frozen_identity = _identity(
        [{"id": row["id"], "packet_identity": row["packet_identity"]} for row in frozen]
    )

    # SECRET is opened only after every first-pass and cached-pass packet is frozen.
    secret = json.loads(secret_path.read_text(encoding="utf-8"))
    expected = {str(row["id"]): row for row in secret.get("tasks") or []}
    if set(expected) != {row["id"] for row in frozen}:
        raise ValueError("SECRET task set does not match frozen PUBLIC task set")

    results: list[dict[str, Any]] = []
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    next_read_reasons: Counter[str] = Counter()
    for row in frozen:
        truth = expected[row["id"]]
        packet = row["packet"]
        candidate = _task_candidate(packet)
        edit_correct = (
            str(candidate.get("path") or "") if candidate is not None else ""
        ) == str(truth["expected_edit_path"])
        verification = _task_verification(packet)
        plan = (
            verification.get("plan")
            if isinstance(verification.get("plan"), dict)
            else {}
        )
        argv = plan.get("argv")
        surface = verification_surface(argv if isinstance(argv, list) else ())
        verify_correct = str(surface.get("surface") or "") == str(
            truth["expected_verify_path"]
        )
        ownership = (
            packet.get("ownership") if isinstance(packet.get("ownership"), dict) else {}
        )
        next_read = ownership.get("next_read")
        if isinstance(next_read, dict) and next_read.get("reason"):
            next_read_reasons[str(next_read["reason"])] += 1
        source_budget = (
            ownership.get("source_budget")
            if isinstance(ownership.get("source_budget"), dict)
            else {}
        )
        graded = {
            "id": row["id"],
            "category": str(truth.get("category") or "unknown"),
            "ownership_status": str(ownership.get("status") or "unresolved"),
            "owner_resolved": isinstance(ownership.get("owner"), dict),
            "candidate_correct": edit_correct,
            "verify_correct": verify_correct,
            "fully_correct": edit_correct and verify_correct,
            "source_complete": bool(source_budget.get("complete")),
            "packet_bytes": int(row["packet_bytes"]),
            "first_warm_ms": float(row["first_warm_ms"]),
            "cached_warm_ms": float(row["cached_warm_ms"]),
            "stable": bool(row["stable"]),
            "provenance_complete": bool(row["provenance_complete"]),
            "revision_current": bool(row["revision_current"]),
            "freshness_state": str(row["freshness_state"]),
            "selection_reason": str(row["selection_reason"]),
        }
        results.append(graded)
        categories[graded["category"]].append(graded)

    count = len(results)
    freshness_states = Counter(str(row["freshness_state"]) for row in results)
    selection_reasons = Counter(str(row["selection_reason"]) for row in results)
    summary = {
        "tasks": count,
        "candidate_correct": sum(bool(row["candidate_correct"]) for row in results),
        "verify_correct": sum(bool(row["verify_correct"]) for row in results),
        "fully_correct": sum(bool(row["fully_correct"]) for row in results),
        "owner_resolved": sum(bool(row["owner_resolved"]) for row in results),
        "owner_unresolved_or_ambiguous": sum(
            not bool(row["owner_resolved"]) for row in results
        ),
        "source_complete": sum(bool(row["source_complete"]) for row in results),
        "stable_packets": sum(bool(row["stable"]) for row in results),
        "provenance_complete": sum(bool(row["provenance_complete"]) for row in results),
        "revision_current": sum(bool(row["revision_current"]) for row in results),
        "freshness_states": dict(sorted(freshness_states.items())),
        "selection_reasons": dict(sorted(selection_reasons.items())),
        "visible_bytes": sum(int(row["packet_bytes"]) for row in results),
        "visible_bytes_per_task": sum(int(row["packet_bytes"]) for row in results)
        / count,
        "mean_first_warm_ms": sum(float(row["first_warm_ms"]) for row in results)
        / count,
        "mean_cached_warm_ms": sum(float(row["cached_warm_ms"]) for row in results)
        / count,
        "sync_ms": sync_ms,
        "next_read_reasons": dict(sorted(next_read_reasons.items())),
    }
    category_summary = {
        name: {
            "tasks": len(rows),
            "fully_correct": sum(bool(row["fully_correct"]) for row in rows),
            "source_complete": sum(bool(row["source_complete"]) for row in rows),
        }
        for name, rows in sorted(categories.items())
    }
    protocol = {
        "public_fields": ["id", "query"],
        "secret_fields": [
            "expected_edit_path",
            "expected_verify_path",
            "expected_safe",
            "category",
        ],
        "secret_join_after_two_frozen_passes": True,
        "source_budget_tokens": token_budget,
        "public_sha256": _sha(public_path),
        "secret_sha256": _sha(secret_path),
        "frozen_packet_identity": frozen_identity,
        "exact_model_token_telemetry": False,
        "visible_measurement": "UTF-8 serialized packet bytes",
    }
    payload = {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": _identity(protocol),
        "summary": summary,
        "categories": category_summary,
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-budget", type=int, default=1536)
    args = parser.parse_args()
    payload = run(
        args.repo, args.public, args.secret, args.output, token_budget=args.token_budget
    )
    print(  # noqa: T201 - intentional command output
        json.dumps(
            {"summary": payload["summary"], "categories": payload["categories"]},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
