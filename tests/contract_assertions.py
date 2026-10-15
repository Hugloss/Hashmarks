"""Checked narrowing for test assertions over open JSON response fields."""

from typing import TypeGuard, TypeVar

from hashmarks.codemap.task_evidence_types import (
    AvailableVerificationPlan,
    TaskVerificationPlan,
)

_T = TypeVar("_T")


def assert_present(value: _T | None) -> _T:
    assert value is not None
    return value


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def assert_object(value: object) -> dict[str, object]:
    assert _is_object(value), f"Expected a JSON object, got {type(value).__name__}"
    return value


def assert_array(value: object) -> list[object]:
    assert isinstance(value, list), f"Expected a JSON array, got {type(value).__name__}"
    return value


def assert_records(value: object) -> list[dict[str, object]]:
    return [assert_object(row) for row in assert_array(value)]


def assert_text(value: object) -> str:
    assert isinstance(value, str), f"Expected a string, got {type(value).__name__}"
    return value


def assert_number(value: object) -> int | float:
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    return value


def is_available_plan(
    plan: TaskVerificationPlan,
) -> TypeGuard[AvailableVerificationPlan]:
    return plan["available"] is True
