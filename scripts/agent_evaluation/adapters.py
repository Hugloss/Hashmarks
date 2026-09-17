from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from .trace import EVENT_TYPES


@dataclass(frozen=True)
class HarnessPacket:
    harness: str
    task: str
    payload: dict[str, Any]

    def as_json(self) -> str:
        return json.dumps(
            {"schema": "hashmarks.harness-packet.v1", "harness": self.harness, "task": self.task, "packet": self.payload},
            sort_keys=True,
            separators=(",", ":"),
        )


class HarnessAdapter(Protocol):
    name: str

    def packet(self, task: str, decision_packet: dict[str, Any]) -> HarnessPacket: ...
    def normalize_events(self, events: Iterable[dict[str, Any]], *, session_id: str, task_id: str, repository_identity: str | None) -> list[dict[str, Any]]: ...


def _base_event(*, event_type: str, session_id: str, task_id: str, repository_identity: str | None, actor: str) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported normalized event_type: {event_type}")
    return {
        "session_id": session_id,
        "task_id": task_id,
        "repository_identity": repository_identity,
        "generation": None,
        "actor": actor,
        "event_type": event_type,
    }


class CodexJsonlAdapter:
    """Translate Hashmarks packets and Codex JSONL events without executing Codex."""

    name = "codex-jsonl"

    def packet(self, task: str, decision_packet: dict[str, Any]) -> HarnessPacket:
        return HarnessPacket(self.name, task, decision_packet)

    def normalize_events(self, events: Iterable[dict[str, Any]], *, session_id: str, task_id: str, repository_identity: str | None) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for raw in events:
            kind = raw.get("type")
            if kind == "thread.started":
                item = _base_event(event_type="task_received", session_id=session_id, task_id=task_id, repository_identity=repository_identity, actor="codex")
                if isinstance(raw.get("thread_id"), str):
                    item["native_thread_id"] = raw["thread_id"]
                output.append(item)
                continue
            if kind == "turn.completed":
                item = _base_event(event_type="final_result", session_id=session_id, task_id=task_id, repository_identity=repository_identity, actor="codex")
                usage = raw.get("usage")
                if isinstance(usage, dict):
                    for source, target in (
                        ("input_tokens", "input_tokens"),
                        ("cached_input_tokens", "cached_input_tokens"),
                        ("output_tokens", "output_tokens"),
                        ("reasoning_output_tokens", "reasoning_tokens"),
                    ):
                        value = usage.get(source)
                        if isinstance(value, int) and value >= 0:
                            item[target] = value
                output.append(item)
                continue
            # Unknown native events are deliberately ignored rather than guessed.
        return output


class GenericJsonlAdapter:
    """Minimal integration contract for harnesses that can emit Hashmarks event names."""

    name = "generic-jsonl"

    def packet(self, task: str, decision_packet: dict[str, Any]) -> HarnessPacket:
        return HarnessPacket(self.name, task, decision_packet)

    def normalize_events(self, events: Iterable[dict[str, Any]], *, session_id: str, task_id: str, repository_identity: str | None) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for raw in events:
            event_type = raw.get("event_type")
            if not isinstance(event_type, str) or event_type not in EVENT_TYPES:
                continue
            item = _base_event(event_type=event_type, session_id=session_id, task_id=task_id, repository_identity=repository_identity, actor=str(raw.get("actor") or "external-harness"))
            for field in ("timestamp_ns", "generation", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "wall_ms", "tool_ms", "bytes_read", "files_read"):
                value = raw.get(field)
                if value is not None:
                    item[field] = value
            output.append(item)
        return output


ADAPTERS: dict[str, type[CodexJsonlAdapter] | type[GenericJsonlAdapter]] = {
    CodexJsonlAdapter.name: CodexJsonlAdapter,
    GenericJsonlAdapter.name: GenericJsonlAdapter,
}


def adapter(name: str) -> HarnessAdapter:
    cls = ADAPTERS.get(name)
    if cls is None:
        raise ValueError(f"unsupported harness adapter: {name}")
    return cls()
