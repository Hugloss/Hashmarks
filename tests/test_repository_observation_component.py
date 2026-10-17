"""The identity observation boundary needs neither CodeMap nor an index."""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from hashmarks.client import (
    DaemonCompatibilityError,
    DaemonProtocolError,
    DaemonUnavailableError,
    RepositoryObservation,
)
from hashmarks.codemap.repository_observation import RepositoryObservationSource
from hashmarks.observation import ObservationState


@dataclass
class _Reader:
    observation: RepositoryObservation
    failure: Exception | None = None
    calls: int = 0

    def repository_observation(self) -> RepositoryObservation:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.observation


def _observation(generation: int) -> RepositoryObservation:
    return RepositoryObservation(
        state=ObservationState.DIRTY,
        generation=generation,
        dirty_paths=("owner.py",),
        paths_complete=True,
        dirty_path_count=1,
    )


def test_source_preserves_the_atomic_observation_without_caching() -> None:
    reader = _Reader(_observation(3))
    source = RepositoryObservationSource(reader)
    assert source.observe() is reader.observation
    reader.observation = _observation(4)
    assert source.observe() is reader.observation
    assert reader.calls == 2


@pytest.mark.parametrize(
    "failure",
    [
        DaemonUnavailableError("unavailable"),
        DaemonCompatibilityError("incompatible"),
        DaemonProtocolError("invalid reply"),
        OSError("socket unavailable"),
    ],
)
def test_expected_transport_failure_is_unknown_and_does_not_pin_a_value(
    failure: Exception,
) -> None:
    reader = _Reader(_observation(3), failure=failure)
    source = RepositoryObservationSource(reader)
    assert source.observe() is None
    reader.failure = None
    assert source.observe() is reader.observation
    assert reader.calls == 2


def test_unexpected_reader_failure_propagates() -> None:
    reader = _Reader(_observation(3), failure=ValueError("invalid caller state"))
    with pytest.raises(ValueError, match="invalid caller state"):
        RepositoryObservationSource(reader).observe()


def test_source_import_does_not_load_derived_index_or_facade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.repository_observation import RepositoryObservationSource; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_index_store' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_retired_root_observation_alias_is_removed() -> None:
    from hashmarks.codemap import CodeMap

    assert not hasattr(CodeMap, "_daemon_observation")
