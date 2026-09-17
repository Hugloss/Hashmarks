from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "hosted_diagnostic.py"
SPEC = importlib.util.spec_from_file_location("hosted_diagnostic", SCRIPT)
assert SPEC and SPEC.loader
hosted = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hosted)


def test_marker_expression_keeps_mandatory_exclusions_when_extra_filter_is_added() -> None:
    expression = hosted.marker_expression("not experimental")
    assert "not certification" in expression
    assert "not host_dns" in expression
    assert "not slow" in expression
    assert "not scale" in expression
    assert expression.endswith("and (not experimental)")


def test_capability_inventory_is_explicitly_non_authoritative() -> None:
    payload = hosted.capabilities()
    assert payload["schema"] == "hashmarks.hosted-diagnostic.v1"
    assert payload["mode"] == "HOSTED-DIAGNOSTIC"
    assert payload["authoritative"] is False
    assert payload["external_dns"] is False
    assert isinstance(payload["interpreter"], str)


def test_shard_range_is_bounded() -> None:
    assert hosted._validate_range(64, 12, 8) == (12, 20)
    assert hosted._validate_range(64, 60, 8) == (60, 64)


def test_mandatory_policy_excludes_scale_measurements() -> None:
    assert "not scale" in hosted.marker_expression()
