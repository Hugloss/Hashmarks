from copy import deepcopy

import pytest
from contract_assertions import assert_array, assert_records

from scripts.repository_evaluation.compare_profiles import compare_profiles


def _profile(median: int = 100) -> dict[str, object]:
    return {
        "schema": "hashmarks.repository-evaluation-profile.v1",
        "suite": "comparison-controls",
        "cases_sha256": "sha256:cases",
        "repository_identity": "sha256:repository",
        "producer_implementation_identity": "sha256:observer",
        "evaluator_implementation_identity": "sha256:evaluator",
        "warmups": 2,
        "samples": 9,
        "shard_count": 1,
        "shard_index": 0,
        "cases": [
            {
                "id": name,
                "median_ns": median,
                "semantic_fingerprint": f"sha256:{name}",
                "semantic_stable": True,
            }
            for name in ("first", "second")
        ],
    }


@pytest.mark.parametrize("side", ["candidate", "repeat"])
@pytest.mark.parametrize(
    "field",
    [
        "repository_identity",
        "cases_sha256",
        "evaluator_implementation_identity",
        "samples",
    ],
)
def test_incomparable_profile_provenance_cannot_produce_a_win(
    side: str, field: str
) -> None:
    profiles = {"baseline": _profile(), "candidate": _profile(70), "repeat": _profile()}
    profiles[side][field] = 3 if field == "samples" else "sha256:other"
    with pytest.raises(ValueError, match="profile.*(identity|protocol|provenance)"):
        compare_profiles(
            baseline=profiles["baseline"],
            candidate=profiles["candidate"],
            repeat=profiles["repeat"],
        )


def test_noise_repeat_must_come_from_the_same_observer() -> None:
    repeat = _profile()
    repeat["producer_implementation_identity"] = "sha256:different-observer"
    with pytest.raises(ValueError, match="repeat.*(producer|observer|identity)"):
        compare_profiles(baseline=_profile(), candidate=_profile(70), repeat=repeat)


@pytest.mark.parametrize("field", ["semantic_fingerprint", "semantic_stable"])
def test_noise_repeat_requires_the_same_stable_semantics(field: str) -> None:
    repeat = _profile()
    assert_records(repeat["cases"])[0][field] = (
        False if field == "semantic_stable" else "sha256:changed"
    )
    with pytest.raises(ValueError, match="repeat.*semantic"):
        compare_profiles(baseline=_profile(), candidate=_profile(70), repeat=repeat)


def test_candidate_may_have_a_new_observer_when_source_and_measurement_match() -> None:
    candidate = _profile(70)
    candidate["producer_implementation_identity"] = "sha256:new-observer"
    result = compare_profiles(
        baseline=_profile(), candidate=candidate, repeat=_profile()
    )
    assert result["wins"] == 2


def test_missing_measurement_provenance_is_not_same_version_noise() -> None:
    repeat = _profile()
    repeat.pop("producer_implementation_identity")
    with pytest.raises(ValueError, match="provenance"):
        compare_profiles(baseline=_profile(), candidate=_profile(70), repeat=repeat)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("warmups", True),
        ("samples", 2),
        ("shard_count", 0),
        ("shard_index", True),
        ("shard_index", 1),
    ],
)
def test_invalid_profile_protocol_cannot_become_comparable(
    field: str, value: object
) -> None:
    candidate = _profile(70)
    candidate[field] = value
    with pytest.raises(ValueError, match="protocol"):
        compare_profiles(baseline=_profile(), candidate=candidate, repeat=_profile())


def test_complete_merged_profiles_preserve_valid_comparison() -> None:
    profiles = [_profile(), _profile(70), _profile()]
    for profile in profiles:
        profile.update(shard_count=2, shard_index=None, complete=True)
    result = compare_profiles(
        baseline=profiles[0], candidate=profiles[1], repeat=profiles[2]
    )
    assert result["wins"] == 2
    profiles[2]["complete"] = False
    with pytest.raises(ValueError, match="merged.*complete"):
        compare_profiles(
            baseline=profiles[0], candidate=profiles[1], repeat=profiles[2]
        )


def test_missing_shard_identity_cannot_impersonate_a_complete_merge() -> None:
    profiles = [_profile(), _profile(70), _profile()]
    for profile in profiles:
        profile.pop("shard_index")
        profile["complete"] = True
    with pytest.raises(ValueError, match="shard.*identity"):
        compare_profiles(
            baseline=profiles[0], candidate=profiles[1], repeat=profiles[2]
        )


@pytest.mark.parametrize("side", ["baseline", "candidate", "repeat"])
def test_duplicate_case_cannot_disappear_before_profile_comparison(side: str) -> None:
    profiles = {"baseline": _profile(), "candidate": _profile(70), "repeat": _profile()}
    rows = assert_array(profiles[side]["cases"])
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError, match="duplicate profile case"):
        compare_profiles(
            baseline=profiles["baseline"],
            candidate=profiles["candidate"],
            repeat=profiles["repeat"],
        )


@pytest.mark.parametrize("membership", ["missing", "extra", "empty"])
def test_repeat_membership_must_match_every_compared_case(membership: str) -> None:
    repeat = _profile()
    rows = assert_array(repeat["cases"])
    if membership == "missing":
        rows.pop()
    elif membership == "extra":
        row = dict(assert_records(repeat["cases"])[0])
        row["id"] = "unexpected"
        rows.append(row)
    else:
        rows.clear()
    with pytest.raises(ValueError, match="repeat.*membership"):
        compare_profiles(baseline=_profile(), candidate=_profile(70), repeat=repeat)


def test_no_repeat_retains_unknown_noise_and_cannot_claim_a_win() -> None:
    result = compare_profiles(baseline=_profile(), candidate=_profile(70))
    assert result["noise_floor_percent"] is None
    assert result["wins"] == 0
    for row in assert_records(result["cases"]):
        assert row["decision"] == "UNCALIBRATED"
        assert row["same_version_noise_pct"] is None
        assert row["raw_gain_pct"] == 30.0


@pytest.mark.parametrize("field", ["semantic_fingerprint", "semantic_stable"])
def test_missing_semantic_evidence_cannot_prove_equal_profiles(field: str) -> None:
    baseline = _profile()
    candidate = _profile(70)
    for profile in (baseline, candidate):
        for row in assert_records(profile["cases"]):
            row.pop(field)
    with pytest.raises(ValueError, match="semantic"):
        compare_profiles(baseline=baseline, candidate=candidate, repeat=_profile())


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf")])
def test_invalid_measurements_cannot_enter_profile_reductions(value: object) -> None:
    candidate = _profile()
    assert_records(candidate["cases"])[0]["median_ns"] = value
    with pytest.raises(ValueError, match="median_ns"):
        compare_profiles(baseline=_profile(), candidate=candidate, repeat=_profile())


def test_empty_comparison_cannot_claim_zero_noise() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        compare_profiles(
            baseline={"cases": []}, candidate={"cases": []}, repeat={"cases": []}
        )
