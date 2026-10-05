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
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("schema") != WATCH_CONTINUITY_SCHEMA:
            return None
        observation = payload.get("observation")
        if not isinstance(observation, dict):
            return None

        owner = payload.get("owner")
        pid = payload.get("pid")
        heartbeat_unix = payload.get("heartbeat_unix")
        active = payload.get("active")
        codemap_generation = payload.get("codemap_generation")
        state_raw = observation.get("state")
        generation = observation.get("generation")
        dirty_paths = observation.get("dirty_paths")
        paths_complete = observation.get("paths_complete")
        dirty_path_count = observation.get("dirty_path_count")
        reason = observation.get("reason")
        if not (
            isinstance(owner, str)
            and owner
            and isinstance(pid, int)
            and not isinstance(pid, bool)
            and isinstance(heartbeat_unix, (int, float))
            and not isinstance(heartbeat_unix, bool)
            and isinstance(active, bool)
            and isinstance(codemap_generation, int)
            and not isinstance(codemap_generation, bool)
            and isinstance(state_raw, str)
            and isinstance(generation, int)
            and not isinstance(generation, bool)
            and isinstance(dirty_paths, list)
            and all(isinstance(path, str) for path in dirty_paths)
            and isinstance(paths_complete, bool)
            and isinstance(dirty_path_count, int)
            and not isinstance(dirty_path_count, bool)
            and (reason is None or isinstance(reason, str))
        ):
            return None
        try:
            state = ObservationState(state_raw)
        except ValueError:
            return None
        paths = tuple(dirty_paths)
        if (
            generation < 0
            or dirty_path_count < len(paths)
            or codemap_generation < 0
            or (paths_complete and dirty_path_count != len(paths))
            or (state is ObservationState.CLEAN and (paths or dirty_path_count))
        ):
            return None
        return cls(
            owner=owner,
            pid=pid,
            heartbeat_unix=float(heartbeat_unix),
            active=active,
            codemap_generation=codemap_generation,
            observation=RepositoryObservation(
                state=state,
                generation=generation,
                dirty_paths=paths,
                paths_complete=paths_complete,
                dirty_path_count=dirty_path_count,
                reason=reason,
            ),
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
