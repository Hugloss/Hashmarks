from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

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
        (("default", "hashmarks.task-evidence.v2"),),
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
)

_OPERATION_BY_NAME = {contract.operation: contract for contract in OPERATION_CONTRACTS}


def operation_contract(operation: str) -> OperationContract:
    try:
        return _OPERATION_BY_NAME[operation]
    except KeyError as exc:
        raise ValueError(f"unknown Hashmarks operation: {operation}") from exc


def operation_schema(operation: str, mode: str | None = None) -> str:
    return operation_contract(operation).schema_for_mode(mode)


def operation_modes(operation: str) -> dict[str, str]:
    return operation_contract(operation).mode_map()


def require_operation_mode(operation: str, mode: str | None = None) -> str:
    contract = operation_contract(operation)
    selected = contract.default_mode if mode is None else mode
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
    if not isinstance(value, dict):
        raise RuntimeError(
            f"Hashmarks operation {operation} returned a non-object response"
        )
    expected = operation_schema(operation, mode)
    actual = value.get("schema")
    if actual != expected:
        raise RuntimeError(
            "Hashmarks operation response schema drift: "
            f"operation={operation} mode={mode or operation_contract(operation).default_mode} "
            f"expected={expected} got={actual!r}"
        )
    return value


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
