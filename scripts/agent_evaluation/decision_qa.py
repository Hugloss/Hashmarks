from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


SAFETY_CLASSES = ("correct-safe", "false-safe", "correct-unsafe", "false-unsafe")


def _path(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    path = value.get("path")
    return str(path) if path else None


def _covered_roles(packet: Mapping[str, Any]) -> set[str]:
    context = packet.get("work_context")
    if not isinstance(context, Mapping):
        return set()
    items = context.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return set()
    roles: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        covered = item.get("covered_roles")
        if isinstance(covered, Sequence) and not isinstance(covered, (str, bytes)):
            roles.update(str(role) for role in covered if role)
        elif item.get("role"):
            roles.add(str(item["role"]))
    return roles


def packet_consistency(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Check worker-visible packet semantics without using grading truth."""
    context = packet.get("work_context") if isinstance(packet.get("work_context"), Mapping) else {}
    budget = packet.get("context_budget") if isinstance(packet.get("context_budget"), Mapping) else {}
    covered = _covered_roles(packet)
    required = {
        role for role in ("edit", "verify", "contract")
        if isinstance(packet.get(role), Mapping) and packet[role].get("path")
    }
    missing_from_items = sorted(required - covered)
    declared_missing = sorted(str(role) for role in (context.get("missing_roles") or []))
    context_safe = bool(context.get("safe"))
    budget_safe = bool(budget.get("safe"))
    expected_safe_from_items = not missing_from_items
    issues: list[str] = []
    if declared_missing != missing_from_items:
        issues.append("declared-missing-role-mismatch")
    if context_safe != expected_safe_from_items:
        issues.append("context-safety-role-coverage-mismatch")
    if budget_safe != context_safe:
        issues.append("budget-context-safety-mismatch")
    return {
        "schema": "hashmarks.decision-packet-consistency.v1",
        "consistent": not issues,
        "required_roles": sorted(required),
        "covered_roles": sorted(covered),
        "missing_roles": missing_from_items,
        "issues": issues,
        "secret_knowledge_used": False,
    }


def evaluate_decision_packet(
    packet: Mapping[str, Any],
    *,
    expected_edit_path: str | None,
    expected_verify_path: str | None,
    expected_safe: bool,
) -> dict[str, Any]:
    """Authority-side grading of a frozen worker packet.

    Expected paths/safety are SECRET grading inputs. They are never added to the
    worker packet and the returned result deliberately reports only correctness,
    not the hidden expected values.
    """
    actual_edit = _path(packet.get("edit"))
    actual_verify = _path(packet.get("verify"))
    context = packet.get("work_context") if isinstance(packet.get("work_context"), Mapping) else {}
    actual_safe = bool(context.get("safe"))
    if actual_safe and expected_safe:
        safety_class = "correct-safe"
    elif actual_safe and not expected_safe:
        safety_class = "false-safe"
    elif not actual_safe and expected_safe:
        safety_class = "false-unsafe"
    else:
        safety_class = "correct-unsafe"
    edit_correct = actual_edit == expected_edit_path
    verify_correct = actual_verify == expected_verify_path
    consistency = packet_consistency(packet)
    return {
        "schema": "hashmarks.agent-decision-qa.v1",
        "task_identity": (
            packet.get("identity", {}).get("task_identity")
            if isinstance(packet.get("identity"), Mapping)
            else None
        ),
        "edit_correct": edit_correct,
        "verify_correct": verify_correct,
        "safety_class": safety_class,
        "safe_correct": safety_class in {"correct-safe", "correct-unsafe"},
        "discrimination_needed": bool(
            packet.get("discrimination", {}).get("needed")
            if isinstance(packet.get("discrimination"), Mapping)
            else False
        ),
        "packet_consistent": bool(consistency["consistent"]),
        "packet_issues": consistency["issues"],
        "fully_correct": edit_correct and verify_correct and safety_class in {"correct-safe", "correct-unsafe"} and bool(consistency["consistent"]),
        "secret_knowledge_used_by_worker": False,
        "grading_scope": "authority-side-after-freeze",
    }


def summarize_decision_qa(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {name: 0 for name in SAFETY_CLASSES}
    for row in rows:
        label = str(row.get("safety_class") or "")
        if label not in counts:
            raise ValueError(f"unsupported safety class: {label!r}")
        counts[label] += 1
    total = len(rows)
    fully_correct = sum(bool(row.get("fully_correct")) for row in rows)
    return {
        "schema": "hashmarks.agent-decision-qa-summary.v1",
        "tasks": total,
        "fully_correct": fully_correct,
        "fully_correct_rate": (fully_correct / total) if total else None,
        "edit_correct": sum(bool(row.get("edit_correct")) for row in rows),
        "verify_correct": sum(bool(row.get("verify_correct")) for row in rows),
        "packet_consistent": sum(bool(row.get("packet_consistent")) for row in rows),
        "safety": counts,
        "false_safe_rate": (counts["false-safe"] / total) if total else None,
        "false_unsafe_rate": (counts["false-unsafe"] / total) if total else None,
    }
