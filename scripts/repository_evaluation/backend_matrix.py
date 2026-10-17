"""Independent backend coverage accounting; never imported by product code."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .backend_gates import combine_required
from .backend_grading import witness_identity

SCHEMA = "hashmarks.backend-evidence-matrix.v5"
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
COMMON_GATES = frozenset(
    {
        "facts",
        "authority",
        "revision",
        "freshness",
        "cli",
        "mcp",
        "presentation",
        "initial_size",
    }
)
SPECIAL_GATES = {
    1: "owner_top_three",
    4: "debug_correspondence",
    7: "initial_evidence",
    17: "presentation",
    18: "fresh_acquisition",
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
        required.add("native_binding")
    if any(workflow.get("native_fresh_required") is True for workflow in workflows):
        required.update({"native_binding", "fresh_acquisition"})
    if capability == 18:
        required.add("native_binding")
    return required


def _population(workflows: list[Mapping[str, Any]], name: str) -> dict[str, Any]:
    population: dict[str, Any] = {
        "workflows": [],
        "by_problem": {},
        "missing": [],
        "ineligible": [],
        "repositories": set(),
        "unknown_problems": set(),
    }
    for workflow in workflows:
        problem = (str(workflow["repository"]), str(workflow["problem_id"]))
        if name in THRESHOLDS:
            eligibility = workflow.get("metric_eligibility", {}).get(name)
            if eligibility is None:
                population["missing"].append(str(workflow["id"]))
                population["unknown_problems"].add(problem)
                continue
            if (
                not isinstance(eligibility, Mapping)
                or type(eligibility.get("eligible")) is not bool
                or not isinstance(eligibility.get("reason"), str)
                or not eligibility["reason"].strip()
            ):
                raise ValueError(
                    "backend metric eligibility requires a boolean and reason"
                )
            if eligibility["eligible"] is False:
                population["ineligible"].append(str(workflow["id"]))
                continue
            population["repositories"].add(str(workflow["repository"]))
        population["workflows"].append(workflow)
        population["by_problem"].setdefault(problem, []).append(workflow)
    return population


def _metric_state(
    values: list[bool | None],
    population: dict[str, Any],
    name: str,
    unknown_frames: list[str],
) -> str:
    passed, missing = (
        sum(value is True for value in values),
        sum(value is None for value in values),
    )
    percent = round(THRESHOLDS.get(name, 1.0) * 100)
    unknown = len(population["unknown_problems"] - population["by_problem"].keys())
    expected = len(values) + unknown
    impossible = (
        bool(expected) and 100 * (passed + missing + unknown) < percent * expected
    )
    if (
        percent == 100
        and any(value is False for value in values)
        or impossible
        and not unknown_frames
    ):
        return "FAIL"
    if missing or not values or population["missing"] or unknown_frames:
        return "INCOMPLETE"
    if name in THRESHOLDS and (
        len(population["by_problem"]) < MIN_WORKFLOWS
        or len(population["repositories"]) < MIN_REPOSITORIES
    ):
        return "INCOMPLETE"
    return "PASS" if 100 * passed >= percent * len(values) else "FAIL"


def _gate(
    workflows: list[Mapping[str, Any]], outcomes: Mapping[str, Any], name: str
) -> dict[str, object]:
    population = _population(workflows, name)
    unknown_frames = []
    if name == "debug_correspondence":
        unknown_frames = [
            str(row["id"])
            for row in population["workflows"]
            if row.get("debug_frame_units") is None
        ]
        values = _frame_values(
            [
                row
                for row in population["workflows"]
                if row.get("debug_frame_units") is not None
            ],
            outcomes,
        )
    else:
        values = [
            _problem_gate(
                [
                    outcomes.get(str(row["id"]), {}).get("gates", {}).get(name)
                    for row in group
                ]
            )
            for group in population["by_problem"].values()
        ]
    missing, passed = (
        sum(value is None for value in values),
        sum(value is True for value in values),
    )
    return {
        "state": _metric_state(values, population, name, unknown_frames),
        "expected": len(values),
        "observed": len(values) - missing,
        "passed": passed,
        "fraction": passed / len(values) if values else 0.0,
        "threshold": THRESHOLDS.get(name, 1.0),
        "eligible_problems": len(population["by_problem"]),
        "eligible_repositories": sorted(population["repositories"]),
        "eligibility_missing": population["missing"],
        "frame_membership_missing": unknown_frames,
        "ineligible_workflows": population["ineligible"],
    }


def _problem_gate(values: list[object]) -> bool | None:
    checked: list[bool | None] = []
    for value in values:
        if value is None or isinstance(value, bool):
            checked.append(value)
        else:
            raise ValueError("backend gate observations must be bool or None")
    return combine_required(checked)


def _frame_values(
    workflows: list[Mapping[str, Any]], outcomes: Mapping[str, Any]
) -> list[bool | None]:
    """Reduce frozen repository-frame units; transports never add frame breadth."""
    by_frame: dict[tuple[str, str, str], list[bool | None]] = {}
    unreviewed = []
    for workflow in workflows:
        units = workflow.get("debug_frame_units")
        if units is None:
            unreviewed.append(None)
            continue
        if (
            not isinstance(units, list)
            or not units
            or not all(isinstance(unit, str) and unit for unit in units)
            or len(set(units)) != len(units)
        ):
            raise ValueError(
                "debug frame units must be distinct reviewed frame identities"
            )
        rows = outcomes.get(str(workflow["id"]), {}).get("debug_frame_observations", [])
        observed = {row["unit_id"]: row["correspondence"] for row in rows}
        if len(observed) != len(rows) or set(observed) - set(units):
            raise ValueError("unexpected or duplicate debug frame observation")
        for unit in units:
            key = (str(workflow["repository"]), str(workflow["problem_id"]), unit)
            by_frame.setdefault(key, []).append(observed.get(unit))
    return [*unreviewed, *(combine_required(group) for group in by_frame.values())]


def _native_population(
    workflows: list[Mapping[str, Any]], name: str, capability: int
) -> list[Mapping[str, Any]]:
    if capability == 18 or name not in {"native_binding", "fresh_acquisition"}:
        return workflows
    flags = (
        ("native_required", "native_fresh_required")
        if name == "native_binding"
        else ("native_fresh_required",)
    )
    return [row for row in workflows if any(row.get(flag) is True for flag in flags)]


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
        name: _gate(_native_population(selected, name, capability), outcomes, name)
        for name in sorted(_required_gates(capability, selected))
    }
    gates["capability_proof"] = _capability_proof(capability, selected, outcomes)
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


def _capability_proof(
    capability: int, workflows: list[Mapping[str, Any]], outcomes: Mapping[str, Any]
) -> dict[str, object]:
    """Tags cannot replace independently reviewed semantic proof membership."""
    by_problem: dict[tuple[str, str], list[bool | None]] = {}
    for workflow in workflows:
        proof = workflow.get("capability_proofs", {}).get(str(capability))
        value = _reviewed_proof(proof, outcomes.get(str(workflow["id"]), {}))
        key = (str(workflow["repository"]), str(workflow["problem_id"]))
        by_problem.setdefault(key, []).append(value)
    values = [combine_required(group) for group in by_problem.values()]
    value = combine_required(values)
    return {
        "state": "PASS"
        if value is True
        else "FAIL"
        if value is False
        else "INCOMPLETE",
        "expected": len(values),
        "observed": sum(item is not None for item in values),
        "passed": sum(item is True for item in values),
    }


def _reviewed_proof(proof: object, outcome: Mapping[str, Any]) -> bool | None:
    if not isinstance(proof, Mapping) or proof.get("reviewed") is not True:
        return None
    positive, adversarial = (
        proof.get("positive_check_ids"),
        proof.get("adversarial_check_ids"),
    )
    for ids in (positive, adversarial):
        if not isinstance(ids, list) or not ids:
            return None
        if any(not isinstance(check, str) or not check for check in ids) or len(
            set(ids)
        ) != len(ids):
            raise ValueError(
                "capability proof check IDs must be distinct nonempty strings"
            )
    membership = proof.get("required_witnesses")
    if not isinstance(membership, list) or not membership:
        return None
    assert isinstance(positive, list) and isinstance(adversarial, list)
    expected = _proof_membership(
        membership, {"positive": set(positive), "adversarial": set(adversarial)}
    )
    witnessed = _witness_states(outcome)
    return combine_required(witnessed.get(key) for key in expected)


def _proof_membership(
    membership: list[dict[str, Any]], roles: dict[str, set[str]]
) -> dict[tuple[object, ...], dict[str, Any]]:
    expected = {}
    covered = {"positive": set(), "adversarial": set()}
    for reference in membership:
        if not isinstance(reference, Mapping):
            raise ValueError("capability proof witness must be an object")
        role = reference.get("role")
        if role not in roles or reference.get("check_id") not in roles[role]:
            raise ValueError("capability proof witness has an unreviewed role or check")
        key = witness_identity(reference)
        if key in expected:
            raise ValueError("duplicate capability proof witness membership")
        expected[key] = reference
        covered[role].add(reference["check_id"])
    if covered != roles:
        raise ValueError("capability proof membership omits a reviewed check")
    return expected


def _witness_states(
    outcome: Mapping[str, Any],
) -> dict[tuple[object, ...], bool | None]:
    witnessed = {}
    for row in outcome.get("gate_witnesses", []):
        key = witness_identity(row)
        if key in witnessed:
            raise ValueError("duplicate backend gate witness context")
        if row["state"] not in {"PASS", "FAIL", "INCOMPLETE"}:
            raise ValueError("unsupported capability witness state")
        binding = (
            isinstance(row.get("artifact"), str)
            and bool(row["artifact"])
            and isinstance(row.get("artifact_sha256"), str)
            and len(row["artifact_sha256"]) == 64
            and bool(row.get("source_bindings"))
            and isinstance(row.get("oracle_pointer"), str)
            and row["oracle_pointer"].startswith("/")
        )
        witnessed[key] = (
            False
            if row["state"] == "FAIL"
            else (True if row["state"] == "PASS" and binding else None)
        )
    return witnessed


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
