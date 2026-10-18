from contract_assertions import assert_array, assert_object, assert_text

from hashmarks.qualification_units import _native_qualification_handoff_from_plan


def test_native_handoff_is_provenance_bound_without_execution_layout_authority(
    repository_qualification_plan: dict[str, object],
) -> None:
    first = _native_qualification_handoff_from_plan(repository_qualification_plan)
    second = _native_qualification_handoff_from_plan(repository_qualification_plan)
    assert first == second
    assert assert_text(
        assert_object(first["producer"])["implementation_identity"]
    ).startswith("sha256:")
    assert first["repository_identity"]
    assert assert_text(first["membership_identity"]).startswith("sha256:")
    assert assert_text(first["classification_identity"]).startswith("sha256:")
    assert assert_text(first["classification_policy_identity"]).startswith("sha256:")
    assert assert_text(first["plan_identity"]).startswith("sha256:")
    assert assert_text(first["handoff_identity"]).startswith("sha256:")
    assert first["execution_authority"] == "external"
    assert first["result_authority"] == "external"
    assert first["certification_authority"] == "external"
    assert first["may_regroup"] is True
    assert all(
        "preferred_granularity" in assert_object(unit)
        for unit in assert_array(first["units"])
    )
    forbidden = {
        "workers",
        "timeout",
        "retry",
        "ordering",
        "subprocesses",
        "bisection",
        "resume",
    }
    assert forbidden.isdisjoint(first)
