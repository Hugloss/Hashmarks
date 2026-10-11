"""Independent backend coverage accounting; never imported by product code."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "hashmarks.backend-evidence-matrix.v1"
MIN_WORKFLOWS = 12
MIN_REPOSITORIES = 3
INITIAL_TOKEN_CEILING = 4_000

CAPABILITIES = (
    "Exact backend owner localization",
    "Exact caller → callee → handler evidence",
    "Changed code → symbol → test correspondence",
    "Debugging and failure localization",
    "Verification and regression evidence",
    "Freshness, completeness and source authority",
    "Evidence sufficiency and ordering",
    "API, route and handler contracts",
    "Producer–consumer data correspondence",
    "Model and schema declarations",
    "Dependency injection and configuration",
    "Async and concurrency boundaries",
    "Queue, event and message boundaries",
    "Database and transaction boundaries",
    "Dependency and build authority",
    "Cross-repository service correspondence",
    "Evidence presentation and retrieval effectiveness",
    "Additional LSP/SCIP evidence types",
    "More language/framework coverage",
    "Indexing, packet size and performance",
)
COMMON_GATES = frozenset({"facts", "authority", "revision", "freshness", "cli", "mcp"})
SPECIAL_GATES = {
    1: "owner_top_three",
    4: "debug_correspondence",
    7: "initial_evidence",
    17: "presentation",
    18: "live",
    19: "language_parity",
    20: "performance",
}
THRESHOLDS = {
    "owner_top_three": 0.95,
    "debug_correspondence": 0.90,
    "initial_evidence": 0.90,
}


def _records(workflows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for workflow in workflows:
        key = str(workflow["id"])
        if key in result:
            raise ValueError(f"duplicate backend workflow: {key}")
        result[key] = workflow
    return result


def _required_gates(capability: int, workflows: list[Mapping[str, Any]]) -> set[str]:
    required = set(COMMON_GATES)
    if capability in SPECIAL_GATES:
        required.add(SPECIAL_GATES[capability])
    if any(workflow.get("native_required") is True for workflow in workflows):
        required.add("live")
    return required


def _gate(
    workflows: list[Mapping[str, Any]], outcomes: Mapping[str, Any], name: str
) -> dict[str, object]:
    by_problem: dict[tuple[str, str], list[object]] = {}
    for workflow in workflows:
        problem = (str(workflow["repository"]), str(workflow["problem_id"]))
        by_problem.setdefault(problem, []).append(
            outcomes.get(str(workflow["id"]), {}).get("gates", {}).get(name)
        )
    values = [_problem_gate(group) for group in by_problem.values()]
    missing = sum(type(value) is not bool for value in values)
    passed = sum(value is True for value in values)
    fraction = passed / len(values) if values else 0.0
    threshold = THRESHOLDS.get(name, 1.0)
    state = (
        "FAIL"
        if threshold == 1.0 and any(value is False for value in values)
        else "INCOMPLETE"
        if missing or not values
        else "PASS"
        if fraction >= threshold
        else "FAIL"
    )
    return {
        "state": state,
        "expected": len(values),
        "observed": len(values) - missing,
        "passed": passed,
        "fraction": fraction,
        "threshold": threshold,
    }


def _problem_gate(values: list[object]) -> bool | None:
    if any(value is False for value in values):
        return False
    return True if all(value is True for value in values) else None


def _capability(
    capability: int, workflows: Sequence[Mapping[str, Any]], outcomes: Mapping[str, Any]
) -> dict[str, Any]:
    selected = [
        workflow for workflow in workflows if capability in workflow["capabilities"]
    ]
    # One upstream problem contributes at most once per capability. Rewordings,
    # transports and mutations cannot manufacture breadth.
    problems = {
        (workflow["repository"], workflow["problem_id"]) for workflow in selected
    }
    repositories = {str(workflow["repository"]) for workflow in selected}
    gates = {
        name: _gate(selected, outcomes, name)
        for name in sorted(_required_gates(capability, selected))
    }
    breadth = len(problems) >= MIN_WORKFLOWS and len(repositories) >= MIN_REPOSITORIES
    states = {row["state"] for row in gates.values()}
    status = (
        "FAIL"
        if "FAIL" in states
        else "INCOMPLETE"
        if not breadth or "INCOMPLETE" in states
        else "PASS"
    )
    return {
        "capability": capability,
        "name": CAPABILITIES[capability - 1],
        "genuine_workflows": len(problems),
        "repositories": sorted(repositories),
        "missing_workflows": max(0, MIN_WORKFLOWS - len(problems)),
        "missing_repositories": max(0, MIN_REPOSITORIES - len(repositories)),
        "gates": gates,
        "status": status,
        "local_e2e_rating": 5 if status == "PASS" else None,
    }


def capability_matrix(
    workflows: Sequence[Mapping[str, Any]], outcomes: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    expected, observed = _records(workflows), _records(outcomes)
    unexpected = sorted(set(observed) - set(expected))
    if unexpected:
        raise ValueError(f"unexpected backend outcomes: {unexpected}")
    rows = [_capability(capability, workflows, observed) for capability in range(1, 21)]
    status = (
        "FAIL"
        if any(row["status"] == "FAIL" for row in rows)
        else "PASS"
        if all(row["status"] == "PASS" for row in rows)
        else "INCOMPLETE"
    )
    return {
        "schema": SCHEMA,
        "authority": "repository-intelligence-measurement-only",
        "minimum_genuine_workflows": MIN_WORKFLOWS,
        "minimum_repositories": MIN_REPOSITORIES,
        "initial_token_ceiling": INITIAL_TOKEN_CEILING,
        "missing_outcomes": sorted(set(expected) - set(observed)),
        "status": status,
        "capabilities": rows,
    }
