"""Incomplete owner precision cannot hide contradictions or become exact proof."""

import pytest

from scripts.repository_evaluation.backend_grading import (
    _authority_safe,
    _owner_top_three,
)


@pytest.mark.parametrize(
    "actual,expected",
    [
        ({}, None),
        ({"path": "backend.ts"}, True),
        ({"path": "backend.ts", "qualname": None}, True),
        ({"path": "wrong.ts"}, False),
        ({"path": "backend.ts", "qualname": "Other.run"}, False),
        ({"path": "backend.ts", "start_line": 4}, False),
        ({"path": "backend.ts", "end_line": 4}, False),
        ({"path": "backend.ts", "qualname": "Worker.run"}, True),
        ({"path": "backend.ts", "start_line": 3.0}, False),
        ({"path": "backend.ts", "start_line": True}, False),
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
def test_symbol_oracle_checks_asserted_facts_without_waiving_fine_evidence(
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
    # Coarse authority safety never substitutes for exact declaration recall.
    assert (
        _owner_top_three({"retrieval": {"results": [{"path": "backend.ts"}]}}, rule)
        is False
    )
    rule["authority_checks"] = [
        {
            "id": "contradiction",
            "pointer": "/known_fact",
            "predicate": "equals",
            "value": True,
        }
    ]
    assert (
        _authority_safe({"known_fact": False, "ownership": {"owner": actual}}, rule)
        is False
    )


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ({}, True),
        ({"symbol": "Other.run"}, False),
        ({"path": "other.py"}, False),
        ({"start_line": 3.0}, False),
        ({"start_line": True}, False),
        ({"end_line": 6}, False),
    ],
)
def test_retrieval_presence_accepts_exact_same_name_source_facts_only(
    mutation: dict[str, object], expected: bool
) -> None:
    declaration = {
        "path": "backend.py",
        "symbol": "Worker.run",
        "start_line": 3,
        "end_line": 5,
        **mutation,
    }
    context = {
        "authority": "indexed-lexical-declarations-only",
        "ownership_authority": False,
        "negative_evidence_admissible": False,
        "source_revision": "1" * 64,
        "runtime_members": "not-established",
        "declarations": [declaration],
    }
    packet = {
        "retrieval": {
            "results": [
                {
                    "path": "backend.py",
                    "symbol": "Other.run",
                    "same_name_declarations": context,
                }
            ]
        },
        "ownership": {"owner": None},
    }
    rule = {
        "owner_oracle": {
            "scope": "symbol",
            "resolution": "unique",
            "candidates": [
                {
                    "path": "backend.py",
                    "qualname": "Worker.run",
                    "start_line": 3,
                    "end_line": 5,
                }
            ],
        }
    }
    assert _owner_top_three(packet, rule) is expected
    assert packet["ownership"]["owner"] is None
    context["ownership_authority"] = True
    assert _owner_top_three(packet, rule) is False
    context["ownership_authority"] = False
    context["source_revision"] = ""
    assert _owner_top_three(packet, rule) is False
