from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

SCHEMA = "hashmarks.harness-economics.v1"
COMPLEMENTARITY_SCHEMA = "hashmarks.agent-complementarity-economics.v1"


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _nonnegative_float(value: object) -> float:
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return 0.0


def _or_none(value: int | float) -> int | float | None:
    if value:
        return value
    return None


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _per_verified(value: int | float | None, verified: int) -> float | None:
    if value is None or verified == 0:
        return None
    return value / verified


@dataclass(frozen=True)
class GradedRun:
    task_id: str
    verified_solution: bool


@dataclass
class _TraceTotals:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    wall_ms: float = 0.0
    tool_ms: float = 0.0
    bytes_read: int = 0
    files_read: int = 0
    scout_calls: int = 0

    def add(self, event: dict[str, Any]) -> None:
        self.input_tokens += _nonnegative_int(event.get("input_tokens"))
        self.cached_input_tokens += _nonnegative_int(event.get("cached_input_tokens"))
        self.output_tokens += _nonnegative_int(event.get("output_tokens"))
        self.reasoning_tokens += _nonnegative_int(event.get("reasoning_tokens"))
        self.wall_ms += _nonnegative_float(event.get("wall_ms"))
        self.tool_ms += _nonnegative_float(event.get("tool_ms"))
        self.bytes_read += _nonnegative_int(event.get("bytes_read"))
        self.files_read += _nonnegative_int(event.get("files_read"))
        self.scout_calls += int(event.get("event_type") == "scout_requested")


def _validated_events(trace: dict[str, Any], grade: GradedRun) -> list[object]:
    if trace.get("schema") != "hashmarks.agent-event-trace.v1":
        raise ValueError("unsupported trace schema")
    if str(trace.get("task_id")) != grade.task_id:
        raise ValueError("trace/grade task identity mismatch")
    events = trace.get("events")
    if not isinstance(events, list):
        raise ValueError("trace events must be a list")
    return events


def trace_economics(trace: dict[str, Any], grade: GradedRun) -> dict[str, Any]:
    totals = _TraceTotals()
    for event in _validated_events(trace, grade):
        if isinstance(event, dict):
            totals.add(event)
    model_tokens = totals.input_tokens + totals.output_tokens + totals.reasoning_tokens
    return {
        "task_id": grade.task_id,
        "verified_solution": grade.verified_solution,
        "input_tokens": _or_none(totals.input_tokens),
        "cached_input_tokens": _or_none(totals.cached_input_tokens),
        "output_tokens": _or_none(totals.output_tokens),
        "reasoning_tokens": _or_none(totals.reasoning_tokens),
        "model_tokens": _or_none(model_tokens),
        "wall_ms": _or_none(totals.wall_ms),
        "tool_ms": _or_none(totals.tool_ms),
        "bytes_read": totals.bytes_read,
        "files_read": totals.files_read,
        "scout_calls": totals.scout_calls,
    }


def _available_sum(items: list[dict[str, Any]], key: str, types: tuple[type, ...]) -> tuple[bool, float | int | None]:
    values = [row.get(key) for row in items]
    available = bool(items) and all(isinstance(value, types) for value in values)
    if not available:
        return False, None
    if types == (int,):
        return True, sum(int(value) for value in values)
    return True, sum(float(value) for value in values)


def summarize_lane(name: str, rows: Iterable[dict[str, Any]], *, model: str | None = None, strategy: str | None = None) -> dict[str, Any]:
    items = list(rows)
    verified = sum(int(bool(row.get("verified_solution"))) for row in items)
    tokens_available, total_tokens = _available_sum(items, "model_tokens", (int,))
    wall_available, total_wall = _available_sum(items, "wall_ms", (int, float))
    return {
        "schema": SCHEMA, "name": name, "model": model, "strategy": strategy,
        "runs": len(items), "verified_solutions": verified,
        "verified_rate": _rate(verified, len(items)),
        "token_metrics_available": tokens_available, "total_model_tokens": total_tokens,
        "tokens_per_verified_solution": _per_verified(total_tokens, verified),
        "wall_metrics_available": wall_available, "total_wall_ms": total_wall,
        "wall_ms_per_verified_solution": _per_verified(total_wall, verified),
        "scout_calls": sum(_nonnegative_int(row.get("scout_calls")) for row in items),
        "bytes_read": sum(_nonnegative_int(row.get("bytes_read")) for row in items),
        "files_read": sum(_nonnegative_int(row.get("files_read")) for row in items),
    }


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_tokens, right_tokens = left.get("total_model_tokens"), right.get("total_model_tokens")
    if not isinstance(left_tokens, int) or not isinstance(right_tokens, int):
        return False
    left_rate = float(left.get("verified_rate") or 0.0)
    right_rate = float(right.get("verified_rate") or 0.0)
    return left_rate >= right_rate and left_tokens <= right_tokens and (left_rate > right_rate or left_tokens < right_tokens)


def pareto_dominance(lanes: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    rows = list(lanes)
    return [
        {"dominant": str(left.get("name")), "dominated": str(right.get("name"))}
        for left in rows for right in rows if left is not right and _dominates(left, right)
    ]


def _positional_targets(args: list[str], start: int, *, skip: set[str] | None = None) -> list[str]:
    ignored = skip or set()
    return [value for value in args[start:] if value not in ignored and not value.startswith("-")]


def _pytest_surface(args: list[str], start: int) -> dict[str, str | None]:
    targets = _positional_targets(args, start)
    target = targets[-1] if targets else ""
    path, _separator, selector = target.partition("::")
    return {"runner": "pytest", "surface": path or None, "selector": selector or None}


def _tsc_surface(args: list[str]) -> dict[str, str | None]:
    for flag in ("-p", "--project"):
        if flag not in args:
            continue
        index = args.index(flag)
        config = args[index + 1] if index + 1 < len(args) else None
        return {"runner": "typescript-compiler", "surface": config, "selector": None}
    return {"runner": "typescript-compiler", "surface": None, "selector": None}


def _go_surface(args: list[str]) -> dict[str, str | None]:
    targets = _positional_targets(args, 2)
    surface = targets[-1] if targets else None
    return {"runner": "go-test", "surface": surface, "selector": None}


def _node_surface(args: list[str]) -> dict[str, str | None]:
    targets = _positional_targets(args, 2)
    surface = targets[-1] if targets else None
    return {"runner": "node-test", "surface": surface, "selector": None}


def _vitest_surface(args: list[str]) -> dict[str, str | None]:
    targets = _positional_targets(args, 1, skip={"run"})
    surface = targets[-1] if targets else None
    return {"runner": "vitest", "surface": surface, "selector": None}


def _maybe_python_pytest(args: list[str]) -> dict[str, str | None] | None:
    if args[:3] == ["python", "-m", "pytest"]:
        return _pytest_surface(args, 3)
    return None


def _maybe_pytest(args: list[str]) -> dict[str, str | None] | None:
    if args and (args[0].endswith("pytest") or args[0] == "pytest"):
        return _pytest_surface(args, 1)
    return None


def _maybe_go(args: list[str]) -> dict[str, str | None] | None:
    if args[:2] == ["go", "test"]:
        return _go_surface(args)
    return None


def _maybe_tsc(args: list[str]) -> dict[str, str | None] | None:
    if args and args[0] == "tsc":
        return _tsc_surface(args)
    return None


def _maybe_node(args: list[str]) -> dict[str, str | None] | None:
    if args[:2] == ["node", "--test"]:
        return _node_surface(args)
    return None


def _maybe_vitest(args: list[str]) -> dict[str, str | None] | None:
    if args and args[0].endswith("vitest"):
        return _vitest_surface(args)
    return None


def verification_surface(argv: Iterable[str]) -> dict[str, str | None]:
    args = [str(value) for value in argv]
    parsers = (_maybe_python_pytest, _maybe_pytest, _maybe_go, _maybe_tsc, _maybe_node, _maybe_vitest)
    for parser in parsers:
        result = parser(args)
        if result is not None:
            return result
    runner = args[0] if args else "unknown"
    return {"runner": runner, "surface": None, "selector": None}


def verification_surface_equivalent(candidate: Iterable[str], authority: Iterable[str]) -> bool:
    left, right = verification_surface(candidate), verification_surface(authority)
    if left["runner"] != right["runner"] or left["surface"] != right["surface"]:
        return False
    required_selector = right.get("selector")
    return required_selector is None or left.get("selector") == required_selector


def summarize_complementarity_lane(name: str, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(rows)
    verified = sum(int(bool(row.get("verified_solution"))) for row in items)
    totals = {key: sum(_nonnegative_int(row.get(key)) for row in items) for key in ("decision_visible_bytes", "repository_evidence_bytes", "decision_interactions", "search_calls", "read_calls")}
    return {
        "schema": COMPLEMENTARITY_SCHEMA, "name": name, "runs": len(items),
        "verified_solutions": verified, "verified_rate": _rate(verified, len(items)),
        "decision_visible_bytes": totals["decision_visible_bytes"],
        "decision_visible_bytes_per_verified_solution": _per_verified(totals["decision_visible_bytes"], verified),
        "repository_evidence_bytes": totals["repository_evidence_bytes"],
        "repository_evidence_bytes_per_verified_solution": _per_verified(totals["repository_evidence_bytes"], verified),
        "decision_interactions": totals["decision_interactions"],
        "decision_interactions_per_verified_solution": _per_verified(totals["decision_interactions"], verified),
        "search_calls": totals["search_calls"], "read_calls": totals["read_calls"],
    }


def _reduction(native: dict[str, Any], assisted: dict[str, Any], key: str) -> float | None:
    base, value = native.get(key), assisted.get(key)
    if not isinstance(base, (int, float)) or not isinstance(value, (int, float)) or base == 0:
        return None
    return (float(base) - float(value)) / float(base) * 100.0


def complementarity_comparison(native: dict[str, Any], assisted: dict[str, Any]) -> dict[str, Any]:
    native_rate, assisted_rate = float(native.get("verified_rate") or 0.0), float(assisted.get("verified_rate") or 0.0)
    native_cost = native.get("decision_visible_bytes_per_verified_solution")
    assisted_cost = assisted.get("decision_visible_bytes_per_verified_solution")
    supports = assisted_rate >= native_rate and isinstance(native_cost, (int, float)) and isinstance(assisted_cost, (int, float)) and assisted_cost < native_cost
    return {
        "schema": COMPLEMENTARITY_SCHEMA,
        "verified_rate_delta_pp": (assisted_rate - native_rate) * 100.0,
        "decision_visible_bytes_reduction_pct": _reduction(native, assisted, "decision_visible_bytes"),
        "repository_evidence_bytes_reduction_pct": _reduction(native, assisted, "repository_evidence_bytes"),
        "decision_interactions_reduction_pct": _reduction(native, assisted, "decision_interactions"),
        "search_call_reduction_pct": _reduction(native, assisted, "search_calls"),
        "read_call_reduction_pct": _reduction(native, assisted, "read_calls"),
        "supports_complementarity_claim": supports,
    }
