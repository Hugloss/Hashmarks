from __future__ import annotations

from typing import Any

TRACE_SCHEMA = "hashmarks.agent-event-trace.v1"
EVENT_TYPES = frozenset({
    "task_received",
    "context_requested",
    "work_packet",
    "source_read",
    "hypothesis",
    "edit_attempt",
    "verification_started",
    "verification_result",
    "failure_evidence",
    "decision_refresh",
    "scout_requested",
    "scout_result",
    "final_result",
})


def _event_type(raw: dict[str, Any]) -> str:
    kind = raw.get("event")
    if kind == "decision":
        return "decision_refresh" if raw.get("failed_edit_targets") else "work_packet"
    if kind == "verification":
        return "verification_result"
    if kind == "attempt-result":
        if raw.get("verified"):
            return "final_result"
        return "failure_evidence"
    return "hypothesis"


def normalize_work_session(
    *,
    session_id: str,
    task_id: str,
    task: str,
    repository_identity: str | None,
    events: list[dict[str, Any]],
    actor: str = "external-agent",
) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = [{
        "timestamp_ns": int(events[0].get("timestamp_ns", 0)) if events else 0,
        "session_id": session_id,
        "task_id": task_id,
        "repository_identity": repository_identity,
        "generation": None,
        "actor": actor,
        "event_type": "task_received",
        "task": task,
    }]
    for raw in events:
        event_type = _event_type(raw)
        item: dict[str, Any] = {
            "timestamp_ns": int(raw.get("timestamp_ns", 0)),
            "session_id": session_id,
            "task_id": task_id,
            "repository_identity": raw.get("repository_identity") or repository_identity,
            "generation": raw.get("generation"),
            "actor": actor,
            "event_type": event_type,
        }
        for field in (
            "attempt", "edit", "verify", "verification_executed", "verification_passed",
            "failed_edit_targets", "verified", "scout", "context_budget", "elapsed_ms",
            "argv", "returncode", "executed", "passed", "timed_out",
        ):
            if field in raw:
                item[field] = raw[field]
        normalized.append(item)
    return {
        "schema": TRACE_SCHEMA,
        "session_id": session_id,
        "task_id": task_id,
        "repository_identity": repository_identity,
        "actor_model": "external-agent-owns-solution/hashmarks-normalizes-evidence",
        "event_types": sorted(EVENT_TYPES),
        "events": normalized,
    }
