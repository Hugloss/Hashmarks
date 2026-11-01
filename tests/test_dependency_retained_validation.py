"""Retained dependency inputs keep canonical shape before live qualification."""

from __future__ import annotations

from copy import deepcopy

import pytest
from contract_assertions import assert_object, assert_records
from test_dependency_derivation_explain import _snapshot

from hashmarks import CodeMap, hash_file
from hashmarks.codemap.dependency_resolution_evidence import _dependency_identities_v3
from hashmarks.codemap.repository_dependencies import RepositoryDependencies


@pytest.fixture(scope="module")
def retained_observation(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    workspace = tmp_path_factory.mktemp("retained-dependency-validation")
    member = workspace / "dependency.lock"
    member.write_bytes(b"dependency input\n")
    snapshot = _snapshot()
    snapshot["repository_inputs"] = [
        {"path": "dependency.lock", "member_revision": hash_file(member).hash}
    ]
    with CodeMap(workspace) as repository:
        return repository.dependencies.observe(snapshot)


def _resign(observation: dict[str, object]) -> None:
    (
        observation["definition_identity"],
        observation["resolution_identity"],
        observation["observation_identity"],
    ) = _dependency_identities_v3(observation)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("path", "./dependency.lock", "path is not normalized"),
        ("path", " dependency.lock", "path is not normalized"),
        ("path", "nested//dependency.lock", "path is not normalized"),
        ("path", "nested\\dependency.lock", "path is not normalized"),
        ("path", "../dependency.lock", "must not contain"),
        ("repository_state", "invented", "state is malformed"),
        ("repository_state", None, "state is malformed"),
        ("repository_state", [], "state is malformed"),
        ("repository_state", "known-absent", "state and revision disagree"),
        ("claimed_member_revision", int("1" * 64), "revision is malformed"),
        ("observed_member_revision", int("1" * 64), "revision is malformed"),
        ("observed_member_revision", None, "state and revision disagree"),
    ],
)
def test_rehashed_retained_input_cannot_bypass_shape_validation(
    retained_observation: dict[str, object], field: str, value: object, message: str
) -> None:
    malformed = deepcopy(retained_observation)
    assert_records(malformed["repository_inputs"])[0][field] = value
    _resign(malformed)

    with pytest.raises(ValueError, match=message):
        RepositoryDependencies.delta(retained_observation, malformed)


@pytest.mark.parametrize("state", ["known-absent", "unknown", "unsupported"])
def test_retained_unavailable_input_remains_a_valid_unknown_claim(
    retained_observation: dict[str, object], state: str
) -> None:
    unavailable = deepcopy(retained_observation)
    assert_records(unavailable["repository_inputs"])[0].update(
        repository_state=state,
        observed_member_revision=None,
        source_equivalence="unknown",
    )
    _resign(unavailable)

    delta = RepositoryDependencies.delta(retained_observation, unavailable)

    assert delta["comparability"] == "comparable"


def test_oversized_qualified_envelope_is_rejected_even_with_valid_content_identity(
    retained_observation: dict[str, object],
) -> None:
    oversized = deepcopy(retained_observation)
    assert_object(oversized["producer"])["opaque_capture"] = "x" * 4_194_304
    _resign(oversized)

    with pytest.raises(ValueError, match="qualified dependency observation exceeds"):
        RepositoryDependencies.delta(oversized, retained_observation)
