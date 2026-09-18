from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hashmarks.generation_domain import require_generation

DECISION_PACKET_SCHEMA = "hashmarks.task-decision-packet.v2"
DECISION_CONTRACT_SCHEMA = "hashmarks.task-decision-contract.v1"


def _required_boolean_field(value: Mapping[str, Any], field: str, label: str) -> bool:
    if not isinstance(value.get(field), bool):
        raise ValueError(f"decision packet {label} must be boolean")
    return value[field]


def _ambiguity_flag(discrimination: Mapping[str, Any]) -> bool:
    ambiguity = discrimination.get("ambiguity")
    if ambiguity is None:
        return False
    if not isinstance(ambiguity, Mapping):
        raise ValueError(
            "decision packet discrimination.ambiguity must be an object or null"
        )
    if type(ambiguity.get("ambiguous")) is not bool:
        raise ValueError(
            "decision packet discrimination.ambiguity.ambiguous must be boolean"
        )
    return ambiguity["ambiguous"]


@dataclass(frozen=True)
class DecisionSelection:
    path: str | None

    @classmethod
    def from_value(cls, value: object) -> DecisionSelection:
        if value is None:
            return cls(path=None)
        if not isinstance(value, Mapping):
            raise ValueError("decision selection must be an object or null")
        path = value.get("path")
        if path is not None and (not isinstance(path, str) or not path.strip()):
            raise ValueError(
                "decision selection path must be a nonblank string or null"
            )
        return cls(path=path)


@dataclass(frozen=True)
class DecisionPacketContract:
    """Strict public projection used by benchmarks and integrations.

    Consumers must parse through this contract rather than guessing internal
    dictionary nesting. Unknown schemas fail closed.
    """

    schema: str
    task: str
    edit: DecisionSelection
    verify: DecisionSelection
    discrimination_needed: bool
    discrimination_reason: str
    ambiguous: bool
    codemap_complete: bool
    stale: bool
    canonical_generation: int

    @classmethod
    def parse(cls, packet: Mapping[str, Any]) -> DecisionPacketContract:
        schema = packet.get("schema")
        if schema != DECISION_PACKET_SCHEMA:
            raise ValueError(f"unsupported decision packet schema: {schema!r}")
        task = packet.get("task")
        if not isinstance(task, str) or not task:
            raise ValueError("decision packet task must be a non-empty string")
        discrimination = packet.get("discrimination")
        identity = packet.get("identity")
        if not isinstance(discrimination, Mapping):
            raise ValueError("decision packet discrimination must be an object")
        if not isinstance(identity, Mapping):
            raise ValueError("decision packet identity must be an object")
        needed = _required_boolean_field(
            discrimination, "needed", "discrimination.needed"
        )
        complete = _required_boolean_field(
            identity, "codemap_complete", "identity.codemap_complete"
        )
        stale = _required_boolean_field(identity, "stale", "identity.stale")
        generation = require_generation(
            packet.get("canonical_generation"),
            field="decision packet canonical_generation",
        )
        ambiguous = _ambiguity_flag(discrimination)
        return cls(
            schema=DECISION_CONTRACT_SCHEMA,
            task=task,
            edit=DecisionSelection.from_value(packet.get("edit")),
            verify=DecisionSelection.from_value(packet.get("verify")),
            discrimination_needed=needed,
            discrimination_reason=str(discrimination.get("reason") or ""),
            ambiguous=ambiguous,
            codemap_complete=complete,
            stale=stale,
            canonical_generation=generation,
        )
