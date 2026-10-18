"""Identity observations consumed by derived repository intelligence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Protocol

from hashmarks.client import (
    DaemonCompatibilityError,
    DaemonProtocolError,
    DaemonUnavailableError,
    RepositoryObservation,
)


class RepositoryObservationReader(Protocol):
    def repository_observation(self) -> RepositoryObservation: ...


class RepositoryObservationSource:
    """Own the optional identity observation, without derived-index dependencies.

    Each call observes the reader anew. Expected unavailable or incompatible
    transport state supplies no observation and therefore cannot prove freshness.
    Read scopes, rather than this source, own reuse of an atomic observation.
    """

    def __init__(self, reader: RepositoryObservationReader) -> None:
        self._reader = reader

    def observe(self) -> RepositoryObservation | None:
        try:
            return self._reader.repository_observation()
        except (
            DaemonUnavailableError,
            DaemonCompatibilityError,
            DaemonProtocolError,
            OSError,
        ):
            return None


def evidence_identity(schema: str, value: Mapping[str, object]) -> str:
    """Return a deterministic domain-separated identity for observer evidence."""
    import hashlib
    import json

    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    digest = hashlib.sha256(schema.encode("utf-8") + b"\0" + raw).hexdigest()
    return f"sha256:{digest}"


def packet_digest(domain: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(domain.encode("utf-8") + b"\0" + encoded).hexdigest()


def _observer_descriptor() -> dict[str, object]:
    """Describe the observer capability separately from repository identity."""
    return {
        "producer": "hashmarks",
        "surface": "repository-intelligence",
        "schema": "hashmarks.repository-observer.v1",
        "capabilities": [
            "affected",
            "dependencies",
            "evidence-bindings",
            "freshness",
            "ownership",
            "symbols",
            "verification",
        ],
    }


def repository_observer_packet() -> dict[str, object]:
    """Return the canonical observer capability descriptor with stable identity."""
    observer = _observer_descriptor()
    return {
        **observer,
        "identity": "sha256:"
        + packet_digest("hashmarks.repository-observer.v1", observer),
    }
