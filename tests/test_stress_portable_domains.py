from __future__ import annotations

import math
import pytest

from scripts.agent_evaluation.experimentability import experiment_environment, normalize_capabilities
from hashmarks.portable_scalar import MAX_PORTABLE_INTEGER
from hashmarks.product_acceptance import scale_class_contract


@pytest.mark.parametrize("value", [True, False, -1, 1.0, 1.5, float("nan"), float("inf"), 1 << 53, 10**100, "1", None])
def test_scale_contract_rejects_nonportable_file_counts(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        scale_class_contract(files=value, source_bytes=1)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [True, False, -1, 1.0, float("nan"), float("inf"), 1 << 53, 10**100, "1", None])
def test_scale_contract_rejects_nonportable_source_bytes(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        scale_class_contract(files=1, source_bytes=value)  # type: ignore[arg-type]


def test_scale_contract_accepts_portable_boundaries() -> None:
    assert scale_class_contract(files=0, source_bytes=0)["observed"] == {"files": 0, "source_bytes": 0}
    assert scale_class_contract(files=MAX_PORTABLE_INTEGER, source_bytes=MAX_PORTABLE_INTEGER)["class"] == "large"


@pytest.mark.parametrize("field,value", [
    ("codemap_generation", True), ("codemap_generation", -1), ("codemap_generation", 1.5), ("codemap_generation", 1 << 53),
    ("identity_generation", False), ("identity_generation", -1), ("identity_generation", 1.5), ("identity_generation", 1 << 53),
    ("seed", True), ("seed", -1), ("seed", 1.5), ("seed", float("nan")), ("seed", float("inf")), ("seed", 1 << 53),
])
def test_experiment_environment_rejects_nonportable_numeric_identity(field: str, value: object) -> None:
    kwargs=dict(hashmarks_version="0.13.0", repository_identity="repo", codemap_generation=1, identity_generation=1, seed=1)
    kwargs[field]=value
    with pytest.raises((TypeError, ValueError)):
        experiment_environment(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None, [], {}])
def test_capabilities_reject_boolean_coercion(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_capabilities({"semantic_nomination": value})  # type: ignore[dict-item]


def test_experiment_environment_accepts_portable_boundaries_and_is_deterministic() -> None:
    kwargs=dict(hashmarks_version="0.13.0", repository_identity="repo", codemap_generation=0,
                identity_generation=None, seed=MAX_PORTABLE_INTEGER,
                capabilities={"semantic_nomination": False})
    first=experiment_environment(**kwargs)
    second=experiment_environment(**kwargs)
    assert first == second
    assert first["capabilities"]["values"]["semantic_nomination"] is False
