"""Incomplete owner precision cannot hide contradictions or become exact proof."""

import pytest

from scripts.repository_evaluation.backend_grading import _authority_safe


@pytest.mark.parametrize(
    "actual,expected",
    [
        ({"path": "backend.ts"}, None),
        ({"path": "backend.ts", "qualname": None}, None),
        ({"path": "wrong.ts"}, False),
        ({"path": "backend.ts", "qualname": "Other.run"}, False),
        ({"path": "backend.ts", "start_line": 4}, False),
        ({"path": "backend.ts", "end_line": 4}, False),
        ({"path": "backend.ts", "qualname": "Worker.run"}, None),
        (
            {
                "path": "backend.ts",
                "qualname": "Worker.run",
                "start_line": 3,
                "end_line": 5,
            },
            True,
        ),
    ],
)
def test_symbol_oracle_distinguishes_missing_and_wrong_precision(
    actual: dict[str, object], expected: bool | None
) -> None:
    rule: dict[str, object] = {
        "owner_oracle": {
            "scope": "symbol",
            "resolution": "unique",
            "candidates": [
                {
                    "path": "backend.ts",
                    "qualname": "Worker.run",
                    "start_line": 3,
                    "end_line": 5,
                }
            ],
        }
    }
    assert _authority_safe({"ownership": {"owner": actual}}, rule) is expected
    rule["authority_checks"] = [
        {
            "id": "contradiction",
            "pointer": "/ownership/owner/path",
            "predicate": "equals",
            "value": "wrong.ts",
        }
    ]
    if actual["path"] != "wrong.ts":
        assert _authority_safe({"ownership": {"owner": actual}}, rule) is False
