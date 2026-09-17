from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks.consumer_conformance import (
    validate_native_consumer_bundle,
    validate_native_evidence_context_bundle,
    validate_native_repository_evidence_bundle,
)
from hashmarks.evidence_context import validate_evidence_context
from hashmarks.promotion_receipt import validate_external_promotion_receipt
from hashmarks.qualification_units import (
    validate_external_qualification_coverage,
    validate_native_qualification_handoff,
)
from hashmarks.test_shards import (
    validate_test_shard_plan,
    validate_work_selection_envelope,
    validate_work_selection_repository_binding,
)
from hashmarks.verification_selection import (
    validate_downstream_consumption_contract,
    validate_verification_membership,
    validate_verification_selection_envelope,
)

if TYPE_CHECKING:
    from pathlib import Path

JSON_NON_OBJECT_ROOTS = (None, True, False, 0, -1, 1.5, "x", [], [1])


@pytest.mark.parametrize("value", JSON_NON_OBJECT_ROOTS)
def test_public_interchange_validators_fail_closed_on_non_object_roots(
    tmp_path: Path, value: object
) -> None:
    checks = (
        (validate_verification_membership(value), "valid"),
        (validate_verification_selection_envelope(value), "valid"),
        (validate_downstream_consumption_contract(value, {}), "valid"),
        (validate_downstream_consumption_contract({}, value), "valid"),
        (validate_evidence_context(value, {}), "valid"),
        (validate_evidence_context({}, value), "valid"),
        (validate_external_promotion_receipt(value, {}), "valid"),
        (validate_external_promotion_receipt({}, value), "valid"),
        (validate_external_qualification_coverage(value, {}), "coverage_valid"),
        (validate_external_qualification_coverage({}, value), "coverage_valid"),
        (validate_native_qualification_handoff(value), "valid"),
        (validate_test_shard_plan(value), "valid"),
        (validate_work_selection_envelope(value), "valid"),
        (validate_work_selection_repository_binding(tmp_path, value), "valid"),
        (validate_native_consumer_bundle(value, {}), "valid"),
        (validate_native_consumer_bundle({}, value), "valid"),
        (validate_native_evidence_context_bundle(value, {}), "valid"),
        (validate_native_evidence_context_bundle({}, value), "valid"),
        (validate_native_repository_evidence_bundle(value, {}, {}, {}), "valid"),
        (validate_native_repository_evidence_bundle({}, value, {}, {}), "valid"),
        (validate_native_repository_evidence_bundle({}, {}, value, {}), "valid"),
        (validate_native_repository_evidence_bundle({}, {}, {}, value), "valid"),
    )
    for result, key in checks:
        assert result[key] is False


@pytest.mark.parametrize(
    "value", tuple(value for value in JSON_NON_OBJECT_ROOTS if value is not None)
)
def test_consumer_bundle_optional_handoff_fails_closed_on_non_object_root(
    value: object,
) -> None:
    result = validate_native_consumer_bundle({}, {}, handoff=value)
    assert result["valid"] is False
    assert any(str(reason).startswith("handoff:") for reason in result["reasons"])
