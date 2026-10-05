from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from hashmarks.client import RepositoryObservation
from hashmarks.observation import ChangeSnapshot, ObservationState

WATCH_CONTINUITY_META = "watcher.observation"
WATCH_CONTINUITY_SCHEMA = "hashmarks.codemap-watch-observation.v1"
_MAX_DIRTY_PATHS = 1000
_MAX_HEARTBEAT_AGE_SECONDS = 2.5


def _plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _decode_payload(raw: str | None) -> dict[str, object] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != WATCH_CONTINUITY_SCHEMA:
        return None
    return payload


def _parse_lease(
    payload: dict[str, object],
) -> tuple[str, int, float, bool, int] | None:
    owner = payload.get("owner")
    pid = payload.get("pid")
    heartbeat = payload.get("heartbeat_unix")
    active = payload.get("active")
    generation = payload.get("codemap_generation")
    if not isinstance(owner, str) or not owner:
        return None
    if not _plain_int(pid) or not _number(heartbeat):
        return None
    if not isinstance(active, bool) or not _plain_int(generation):
        return None
    if int(generation) < 0:
        return None
    return owner, int(pid), float(heartbeat), active, int(generation)


def _string_paths(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    if not all(isinstance(path, str) for path in value):
        return None
    return tuple(value)


def _observation_fields(
    payload: dict[str, object],
) -> tuple[str, int, tuple[str, ...], bool, int, str | None] | None:
    state = payload.get("state")
    generation = payload.get("generation")
    paths = _string_paths(payload.get("dirty_paths"))
    complete = payload.get("paths_complete")
    count = payload.get("dirty_path_count")
    reason = payload.get("reason")
    if not isinstance(state, str) or not _plain_int(generation):
        return None
    if paths is None or not isinstance(complete, bool) or not _plain_int(count):
        return None
    if reason is not None and not isinstance(reason, str):
        return None
    return state, int(generation), paths, complete, int(count), reason


def _observation_semantics_valid(
    state: ObservationState,
    generation: int,
    paths: tuple[str, ...],
    complete: bool,
    count: int,
) -> bool:
    if generation < 0 or count < len(paths):
        return False
    if complete and count != len(paths):
        return False
    if state is ObservationState.CLEAN and (paths or count):
        return False
    return True


def _parse_observation(payload: object) -> RepositoryObservation | None:
    if not isinstance(payload, dict):
        return None
    fields = _observation_fields(payload)
    if fields is None:
        return None
    state_raw, generation, paths, complete, count, reason = fields
    try:
        state = ObservationState(state_raw)
    except ValueError:
        return None
    if not _observation_semantics_valid(state, generation, paths, complete, count):
        return None
    return RepositoryObservation(
        state=state,
        generation=generation,
        dirty_paths=paths,
        paths_complete=complete,
        dirty_path_count=count,
        reason=reason,
    )


@dataclass(frozen=True, slots=True)
class WatchContinuityRecord:
    owner: str
    pid: int
    heartbeat_unix: float
    active: bool
    codemap_generation: int
    observation: RepositoryObservation

    def to_json(self) -> str:
        payload = {
            "schema": WATCH_CONTINUITY_SCHEMA,
            "owner": self.owner,
            "pid": self.pid,
            "heartbeat_unix": self.heartbeat_unix,
            "active": self.active,
            "codemap_generation": self.codemap_generation,
            "observation": {
                "state": self.observation.state.value,
                "generation": self.observation.generation,
                "dirty_paths": list(self.observation.dirty_paths),
                "paths_complete": self.observation.paths_complete,
                "dirty_path_count": self.observation.dirty_path_count,
                "reason": self.observation.reason,
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str | None) -> WatchContinuityRecord | None:
        payload = _decode_payload(raw)
        if payload is None:
            return None
        lease = _parse_lease(payload)
        observation = _parse_observation(payload.get("observation"))
        if lease is None or observation is None:
            return None
        owner, pid, heartbeat, active, generation = lease
        return cls(
            owner=owner,
            pid=pid,
            heartbeat_unix=heartbeat,
            active=active,
            codemap_generation=generation,
            observation=observation,
        )

    def lease_live(self, *, now: float | None = None) -> bool:
        if not self.active or self.pid <= 0:
            return False
        current = time.time() if now is None else now
        age = current - self.heartbeat_unix
        if age < 0 or age >= _MAX_HEARTBEAT_AGE_SECONDS:
            return False
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def stale_for(self, generation: int) -> bool | None:
        if not self.lease_live():
            return None
        if self.observation.state is ObservationState.DIRTY:
            return True
        if self.observation.state is ObservationState.UNKNOWN:
            return None
        if self.codemap_generation != generation:
            return None
        return False

    def status_projection(self) -> dict[str, object]:
        observation = self.observation
        return {
            "owner": self.owner,
            "pid": self.pid if self.active else None,
            "active": self.active,
            "state": observation.state.value,
            "heartbeat_unix": self.heartbeat_unix,
            "observation_generation": observation.generation,
            "codemap_generation": self.codemap_generation,
            "paths_complete": observation.paths_complete,
            "dirty_path_count": observation.dirty_path_count,
            "reason": observation.reason,
        }


def watch_record_from_snapshot(
    snapshot: ChangeSnapshot,
    *,
    owner: str,
    pid: int,
    heartbeat_unix: float,
    active: bool,
    codemap_generation: int,
) -> WatchContinuityRecord:
    dirty_paths = snapshot.paths[:_MAX_DIRTY_PATHS]
    return WatchContinuityRecord(
        owner=owner,
        pid=pid,
        heartbeat_unix=heartbeat_unix,
        active=active,
        codemap_generation=codemap_generation,
        observation=RepositoryObservation(
            state=snapshot.state,
            generation=snapshot.generation,
            dirty_paths=dirty_paths,
            paths_complete=len(dirty_paths) == len(snapshot.paths),
            dirty_path_count=len(snapshot.paths),
            reason=snapshot.reason,
        ),
    )


def watch_status_projection(
    record: WatchContinuityRecord | None,
) -> dict[str, object]:
    if record is not None:
        return record.status_projection()
    return {
        "owner": None,
        "pid": None,
        "active": False,
        "state": None,
        "heartbeat_unix": None,
        "observation_generation": None,
        "codemap_generation": None,
        "paths_complete": None,
        "dirty_path_count": None,
        "reason": None,
    }
