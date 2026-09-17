from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hashmarks.generation_domain import require_generation

DECISION_PACKET_SCHEMA = "hashmarks.task-decision-packet.v2"
DECISION_CONTRACT_SCHEMA = "hashmarks.task-decision-contract.v1"


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
        if not isinstance(discrimination.get("needed"), bool):
            raise ValueError("decision packet discrimination.needed must be boolean")
        if not isinstance(identity.get("codemap_complete"), bool):
            raise ValueError(
                "decision packet identity.codemap_complete must be boolean"
            )
        if not isinstance(identity.get("stale"), bool):
            raise ValueError("decision packet identity.stale must be boolean")
        generation = require_generation(
            packet.get("canonical_generation"),
            field="decision packet canonical_generation",
        )
        ambiguity = discrimination.get("ambiguity")
        if ambiguity is not None and not isinstance(ambiguity, Mapping):
            raise ValueError(
                "decision packet discrimination.ambiguity must be an object or null"
            )
        if ambiguity is not None and type(ambiguity.get("ambiguous")) is not bool:
            raise ValueError(
                "decision packet discrimination.ambiguity.ambiguous must be boolean"
            )
        return cls(
            schema=DECISION_CONTRACT_SCHEMA,
            task=task,
            edit=DecisionSelection.from_value(packet.get("edit")),
            verify=DecisionSelection.from_value(packet.get("verify")),
            discrimination_needed=bool(discrimination["needed"]),
            discrimination_reason=str(discrimination.get("reason") or ""),
            ambiguous=False if ambiguity is None else ambiguity["ambiguous"],
            codemap_complete=bool(identity["codemap_complete"]),
            stale=bool(identity["stale"]),
            canonical_generation=generation,
        )
