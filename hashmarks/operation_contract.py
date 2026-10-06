from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import wraps
from typing import Callable, TypeVar, cast

OPERATION_CONTRACT_SCHEMA = "hashmarks.operation-contract.v1"


@dataclass(frozen=True, slots=True)
class OperationContract:
    operation: str
    modes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise ValueError("operation must not be empty")
        if not self.modes:
            raise ValueError(f"operation contract has no modes: {self.operation}")
        names = [mode for mode, _schema in self.modes]
        schemas = [schema for _mode, schema in self.modes]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate operation mode: {self.operation}")
        if any(not mode.strip() for mode in names):
            raise ValueError(f"operation mode must not be empty: {self.operation}")
        if any(not schema.strip() for schema in schemas):
            raise ValueError(f"operation schema must not be empty: {self.operation}")

    @property
    def default_mode(self) -> str:
        return self.modes[0][0]

    @property
    def default_schema(self) -> str:
        return self.modes[0][1]

    def schema_for_mode(self, mode: str | None = None) -> str:
        selected = self.default_mode if mode is None else mode
        for candidate, schema in self.modes:
            if candidate == selected:
                return schema
        raise ValueError(
            f"unknown Hashmarks operation mode for {self.operation}: {selected}"
        )

    def mode_map(self) -> dict[str, str]:
        return dict(self.modes)


OPERATION_CONTRACTS = (
    OperationContract(
        "repository_context",
        (("default", "hashmarks.repository-capsule.v1"),),
    ),
    OperationContract(
        "find",
        (("default", "hashmarks.find.v2"),),
    ),
    OperationContract(
        "task_evidence",
        (("default", "hashmarks.task-evidence.v4"),),
    ),
    OperationContract(
        "change_impact",
        (("default", "hashmarks.task-change-impact.v1"),),
    ),
    OperationContract(
        "correlate_evidence",
        (("default", "hashmarks.evidence-correlation.v2"),),
    ),
    OperationContract(
        "dependency_codemap",
        (
            ("observation", "hashmarks.dependency-codemap.v1"),
            ("explain", "hashmarks.dependency-resolution-explain.v1"),
            ("compare", "hashmarks.dependency-resolution-delta.v3"),
        ),
    ),
    OperationContract(
        "repository_declarations",
        (
            ("observation", "hashmarks.repository-declarations.v1"),
            ("explain", "hashmarks.repository-declaration-explain.v1"),
        ),
    ),
    OperationContract(
        "post_change",
        (("default", "hashmarks.task-post-change-delta.v2"),),
    ),
    OperationContract("projects", (("default", "hashmarks.codemap-projects.v1"),)),
    OperationContract("outline", (("default", "hashmarks.outline.v1"),)),
    OperationContract("grep", (("default", "hashmarks.grep.v1"),)),
    OperationContract(
        "structural",
        (("default", "hashmarks.structural-search.v1"),),
    ),
    OperationContract("symbol", (("default", "hashmarks.symbol.v1"),)),
    OperationContract("source", (("default", "hashmarks.source.v1"),)),
    OperationContract(
        "affected",
        (("default", "hashmarks.codemap-affected.v1"),),
    ),
    OperationContract("tests", (("default", "hashmarks.codemap-tests.v1"),)),
    OperationContract(
        "structural_locality",
        (("default", "hashmarks.structural-locality.v1"),),
    ),
    OperationContract(
        "structural_locality_delta",
        (("default", "hashmarks.structural-locality-delta.v1"),),
    ),
    OperationContract("context", (("default", "hashmarks.context-pack.v2"),)),
    OperationContract(
        "repository_findings",
        (("default", "hashmarks.repository-findings.v1"),),
    ),
    OperationContract(
        "import_ownership",
        (("default", "hashmarks.import-ownership.v2"),),
    ),
    OperationContract(
        "concurrency_risk",
        (("default", "hashmarks.concurrency-risk.v1"),),
    ),
    OperationContract(
        "verification_ownership",
        (("default", "hashmarks.verification-ownership.v2"),),
    ),
    OperationContract(
        "repository_ownership",
        (("default", "hashmarks.authority-ownership-graph.v3"),),
    ),
    OperationContract(
        "cache_ownership",
        (("default", "hashmarks.cache-ownership.v1"),),
    ),
    OperationContract(
        "cache_invalidation_ownership",
        (("default", "hashmarks.cache-invalidation-ownership.v1"),),
    ),
    OperationContract(
        "task_action_map",
        (("default", "hashmarks.task-action-map.v1"),),
    ),
    OperationContract(
        "verification_relevance",
        (("default", "hashmarks.verification-relevance.v1"),),
    ),
    OperationContract(
        "ownership_relation_graph",
        (("default", "hashmarks.ownership-relation-graph.v1"),),
    ),
    OperationContract(
        "task_decision_packet",
        (("default", "hashmarks.task-decision-packet.v2"),),
    ),
    OperationContract(
        "task_decision_brief",
        (("default", "hashmarks.task-decision-brief.v1"),),
    ),
    OperationContract(
        "task_action_brief",
        (("default", "hashmarks.task-action-brief.v1"),),
    ),
    OperationContract(
        "task_decision_brief_budget_sweep",
        (("default", "hashmarks.task-decision-brief-budget-sweep.v1"),),
    ),
    OperationContract(
        "repository_intelligence_query",
        (("default", "hashmarks.repository-intelligence-query.v1"),),
    ),
    OperationContract(
        "refresh_after_change_delta",
        (("default", "hashmarks.refresh-delta.v1"),),
    ),
    OperationContract(
        "refresh_after_change_brief",
        (("default", "hashmarks.post-change-refresh-brief.v1"),),
    ),
    OperationContract(
        "refresh_after_change",
        (("default", "hashmarks.post-change-refresh.v1"),),
    ),
)

_OPERATION_BY_NAME = {contract.operation: contract for contract in OPERATION_CONTRACTS}


def operation_contract(operation: str) -> OperationContract:
    try:
        return _OPERATION_BY_NAME[operation]
    except KeyError as exc:
        raise ValueError(f"unknown Hashmarks operation: {operation}") from exc


def registered_operations() -> tuple[str, ...]:
    return tuple(_OPERATION_BY_NAME)


def require_registered_operation(operation: str) -> OperationContract:
    return operation_contract(operation)


def operation_schema(operation: str, mode: str | None = None) -> str:
    return operation_contract(operation).schema_for_mode(mode)


def operation_modes(operation: str) -> dict[str, str]:
    return operation_contract(operation).mode_map()


def operation_default_mode(operation: str) -> str:
    return operation_contract(operation).default_mode


def require_operation_mode(operation: str, mode: str | None = None) -> str:
    selected = operation_default_mode(operation) if mode is None else mode
    allowed = operation_modes(operation)
    if selected not in allowed:
        raise ValueError(f"result_mode must be one of: {', '.join(allowed)}")
    return selected


def validate_operation_response(
    operation: str,
    value: object,
    *,
    mode: str | None = None,
) -> dict[str, object]:
    contract = require_registered_operation(operation)
    if not isinstance(value, dict):
        raise RuntimeError(
            f"Hashmarks operation {operation} returned a non-object response"
        )
    expected = contract.schema_for_mode(mode)
    actual = value.get("schema")
    if actual != expected:
        raise RuntimeError(
            "Hashmarks operation response schema drift: "
            f"operation={operation} mode={mode or contract.default_mode} "
            f"expected={expected} got={actual!r}"
        )
    return value


_OperationResponse = TypeVar(
    "_OperationResponse",
    bound=Callable[..., dict[str, object]],
)


def operation_response(
    operation: str,
    *,
    mode: str | None = None,
) -> Callable[[_OperationResponse], _OperationResponse]:
    """Bind one public core producer to its canonical operation response proof."""

    require_registered_operation(operation)

    def decorate(function: _OperationResponse) -> _OperationResponse:
        @wraps(function)
        def wrapped(*args: object, **kwargs: object) -> dict[str, object]:
            return validate_operation_response(
                operation,
                function(*args, **kwargs),
                mode=mode,
            )

        return cast(_OperationResponse, wrapped)

    return decorate


def operation_contract_manifest() -> dict[str, object]:
    mappings = [
        {
            "operation": contract.operation,
            "modes": contract.mode_map(),
        }
        for contract in OPERATION_CONTRACTS
    ]
    payload: dict[str, object] = {
        "schema": OPERATION_CONTRACT_SCHEMA,
        "mappings": mappings,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    payload["contract_identity"] = (
        "sha256:"
        + hashlib.sha256(
            OPERATION_CONTRACT_SCHEMA.encode("utf-8") + b"\0" + encoded
        ).hexdigest()
    )
    return payload
