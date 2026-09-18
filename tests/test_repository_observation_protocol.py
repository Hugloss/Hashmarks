from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks.client import DaemonProtocolError, IdentityClient, RepositoryObservation
from hashmarks.observation import ObservationState
from hashmarks.schema import DAEMON_PROTOCOL_VERSION, DAEMON_SEMANTICS

if TYPE_CHECKING:
    from pathlib import Path


def _client(tmp_path: Path) -> IdentityClient:
    client = IdentityClient(tmp_path)
    client._compatibility_validated = True
    return client


def test_protocol_is_explicitly_broken_for_atomic_observation_authority():
    assert DAEMON_PROTOCOL_VERSION == 3
    assert DAEMON_SEMANTICS == "fastidentity.daemon-semantics.v3"


def test_repository_observation_returns_typed_atomic_snapshot(
    tmp_path: Path, monkeypatch
):
    client = _client(tmp_path)
    monkeypatch.setattr(
        client,
        "request",
        lambda op: {
            "ok": True,
            "observation": "dirty",
            "generation": 7,
            "dirty_paths": 2,
            "paths": ["a.py", "b.py"],
            "paths_complete": True,
            "reason": None,
        },
    )

    observed = client.repository_observation()

    assert isinstance(observed, RepositoryObservation)
    assert observed.state is ObservationState.DIRTY
    assert observed.generation == 7
    assert observed.dirty_paths == ("a.py", "b.py")
    assert observed.can_incrementally_reconcile is True


@pytest.mark.parametrize(
    "payload",
    [
        {"observation": "dirty", "generation": 2},
        {
            "observation": "dirty",
            "generation": 2,
            "dirty_paths": 0,
            "paths": [],
            "paths_complete": 1,
        },
        {
            "observation": "dirty",
            "generation": 2,
            "dirty_paths": 2,
            "paths": ["a.py"],
            "paths_complete": True,
        },
        {
            "observation": "dirty",
            "generation": 2,
            "dirty_paths": 1,
            "paths": [1],
            "paths_complete": True,
        },
        {
            "observation": "dirty",
            "generation": 2,
            "dirty_paths": 2,
            "paths": ["a.py"],
            "paths_complete": False,
        },
        {
            "observation": "clean",
            "generation": 2,
            "dirty_paths": 1,
            "paths": ["a.py"],
            "paths_complete": True,
        },
        {
            "observation": "unknown",
            "generation": 2,
            "dirty_paths": 1,
            "paths": ["a.py"],
            "paths_complete": True,
        },
        {
            "observation": "clean",
            "generation": 2,
            "dirty_paths": 0,
            "paths": [],
            "paths_complete": True,
            "reason": 42,
        },
    ],
)
def test_repository_observation_rejects_incoherent_payloads(
    tmp_path: Path, monkeypatch, payload
):
    client = _client(tmp_path)
    monkeypatch.setattr(
        client, "request", lambda op: {"ok": True, "reason": None, **payload}
    )
    with pytest.raises(DaemonProtocolError):
        client.repository_observation()
