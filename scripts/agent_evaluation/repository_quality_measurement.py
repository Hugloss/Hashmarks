from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

MEASUREMENT_SCHEMA = "hashmarks.repository-quality-measurement.v1"
ECONOMICS_KEYS = ("latency_ms", "rows_inspected", "candidate_count", "peak_memory_bytes")


def _identity(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def measurement_receipt(
    *,
    execution_receipt_identity: str,
    environment_fingerprint: str,
    mode: str,
    ranking: Mapping[str, Any],
    verification: Mapping[str, Any],
    retention: Mapping[str, Any],
    economics: Mapping[str, Any],
) -> dict[str, Any]:
    if not execution_receipt_identity or not environment_fingerprint:
        raise ValueError("measurement requires execution receipt and environment identity")
    if mode not in {"cold", "warm", "incremental"}:
        raise ValueError("measurement mode must be cold, warm, or incremental")
    _validate_economics(economics)
    payload = {
        "schema": MEASUREMENT_SCHEMA,
        "execution_receipt_identity": execution_receipt_identity,
        "environment_fingerprint": environment_fingerprint,
        "mode": mode,
        "ranking": dict(ranking),
        "verification": dict(verification),
        "retention": dict(retention),
        "economics": dict(economics),
    }
    return {**payload, "measurement_identity": _identity(payload)}


def _validate_economics(economics: Mapping[str, Any]) -> None:
    for key in ECONOMICS_KEYS:
        value = economics.get(key)
        if value is not None and (
            not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
        ):
            raise ValueError(f"{key} must be a non-negative number")


def comparable_economics(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fingerprints = {str(row.get("environment_fingerprint") or "") for row in receipts}
    modes = {str(row.get("mode") or "") for row in receipts}
    fingerprints.discard("")
    modes.discard("")
    comparable = bool(receipts) and len(fingerprints) == 1 and len(modes) == 1
    return {
        "samples": len(receipts),
        "environment_fingerprints": sorted(fingerprints),
        "modes": sorted(modes),
        "comparable": comparable,
        "reason": None if comparable else "environment-or-mode-mismatch",
    }


def ranking_distribution(receipts: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    ranks = [
        int(value["rank"])
        for row in receipts
        if isinstance((value := row.get(field)), Mapping) and value.get("rank") is not None
    ]
    if any(rank < 1 for rank in ranks):
        raise ValueError("ranking positions must be >= 1")
    return {
        "samples": len(ranks),
        "recall_at_1": sum(rank <= 1 for rank in ranks) / len(ranks) if ranks else None,
        "recall_at_5": sum(rank <= 5 for rank in ranks) / len(ranks) if ranks else None,
        "worst_rank": max(ranks) if ranks else None,
    }


def retention_distribution(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    keys = sorted(
        {
            str(key)
            for row in receipts
            if isinstance(row.get("retention"), Mapping)
            for key in row["retention"]
        }
    )
    result: dict[str, Any] = {}
    for key in keys:
        values = [
            bool(row["retention"][key])
            for row in receipts
            if isinstance(row.get("retention"), Mapping) and key in row["retention"]
        ]
        result[key] = {
            "samples": len(values),
            "rate": sum(values) / len(values) if values else None,
        }
    return result


def measurement_health(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    schemas = Counter(str(row.get("schema") or "") for row in receipts)
    identities = [str(row.get("measurement_identity") or "") for row in receipts]
    duplicate_identities = len(identities) - len(set(identities))
    return {
        "samples": len(receipts),
        "schemas": dict(sorted(schemas.items())),
        "missing_identity": sum(not identity for identity in identities),
        "duplicate_identity": duplicate_identities,
        "economics": comparable_economics(receipts),
        "owner_ranking": ranking_distribution(receipts, "ranking"),
        "verification_ranking": ranking_distribution(receipts, "verification"),
        "retention": retention_distribution(receipts),
    }
