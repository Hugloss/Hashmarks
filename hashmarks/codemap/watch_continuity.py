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
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("schema") != WATCH_CONTINUITY_SCHEMA:
            return None
        observation = payload.get("observation")
        if not isinstance(observation, dict):
            return None
        try:
            state = ObservationState(str(observation["state"]))
            generation = int(observation["generation"])
            dirty_paths = tuple(str(path) for path in observation["dirty_paths"])
            paths_complete = bool(observation["paths_complete"])
            dirty_path_count = int(observation["dirty_path_count"])
            owner = str(payload["owner"])
            pid = int(payload["pid"])
            heartbeat_unix = float(payload["heartbeat_unix"])
            active = bool(payload["active"])
            codemap_generation = int(payload["codemap_generation"])
        except (KeyError, TypeError, ValueError):
            return None
        if (
            not owner
            or generation < 0
            or dirty_path_count < len(dirty_paths)
            or codemap_generation < 0
        ):
            return None
        if paths_complete and dirty_path_count != len(dirty_paths):
            return None
        if state is ObservationState.CLEAN and (dirty_paths or dirty_path_count):
            return None
        reason = observation.get("reason")
        if reason is not None and not isinstance(reason, str):
            return None
        return cls(
            owner=owner,
            pid=pid,
            heartbeat_unix=heartbeat_unix,
            active=active,
            codemap_generation=codemap_generation,
            observation=RepositoryObservation(
                state=state,
                generation=generation,
                dirty_paths=dirty_paths,
                paths_complete=paths_complete,
                dirty_path_count=dirty_path_count,
                reason=reason,
            ),
        )

    def lease_live(self, *, now: float | None = None) -> bool:
        if not self.active or self.pid <= 0:
            return False
        current = time.time() if now is None else now
        if current - self.heartbeat_unix >= _MAX_HEARTBEAT_AGE_SECONDS:
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
