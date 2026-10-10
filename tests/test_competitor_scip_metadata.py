"""Direct SCIP metadata evidence is bounded, attributed and non-authoritative.

Do not infer caller completeness, missing documentation, or semantic ownership
from occurrence flags or producer display strings.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from hashmarks.codemap.scip_adapter import parse_scip_json
from hashmarks.codemap.scip_relationship_adapter import scip_occurrence_payload


def _index(*, roles: int = 9, documentation: object = None, supply_docs: bool = True) -> dict:
    symbol = {
        "symbol": "scip-python python pkg 1.0 api/validate().",
        "displayName": "validate",
        "kind": 12,
    }
    if supply_docs:
        symbol["documentation"] = documentation
    return {
        "metadata": {"toolInfo": {"name": "fixture", "version": "1"}},
        "documents": [
            {
                "relativePath": "src/api.py",
                "symbols": [symbol],
                "occurrences": [
                    {
                        "symbol": symbol["symbol"],
                        "symbolRoles": roles,
                        "range": [0, 4, 12],
                    }
                ],
            }
        ],
    }


def _single(index: dict):
    producer, rows = parse_scip_json(index)
    assert producer == "fixture:1"
    assert len(rows) == 1
    return rows[0]


def test_preserves_documentation_roles_and_original_producer_metadata() -> None:
    row = _single(_index(documentation=["Validate credentials.", "May reject tokens."]))
    assert row.definition is True
    assert row.occurrence_roles == {
        "producer_role_bits": 9,
        "observed_roles": ["definition", "read_access"],
        "unrecognized_role_bits": 0,
        "authority": "direct-scip-occurrence-flags",
        "negative_evidence_admissible": False,
    }
    assert row.declaration_metadata == {
        "display_name": "validate",
        "kind": 12,
        "documentation_state": "supplied",
        "documentation": ["Validate credentials.", "May reject tokens."],
        "documentation_omitted": 0,
        "documentation_clipped_entries": 0,
        "documentation_truncated": False,
        "authority": "scip-producer-supplied",
        "negative_evidence_admissible": False,
    }
    packet = scip_occurrence_payload(
        row,
        "observed-at-import",
        {"source_revisions": {}, "source_provenance": {}},
    )
    assert packet["declaration"] == row.declaration_metadata
    assert packet["occurrence_roles"] == row.occurrence_roles
    assert packet["source_revision_authority"] == "codemap-observed-at-scip-import"


def test_empty_documentation_is_not_missing_or_negative_evidence() -> None:
    unavailable = _single(_index(supply_docs=False))
    observed_empty = _single(_index(documentation=[]))
    assert unavailable.declaration_metadata["documentation_state"] == "not-supplied"
    assert "documentation" not in unavailable.declaration_metadata
    assert observed_empty.declaration_metadata["documentation_state"] == "supplied"
    assert observed_empty.declaration_metadata["documentation"] == []
    assert observed_empty.declaration_metadata["negative_evidence_admissible"] is False


def test_large_documentation_keeps_bounded_prefix_and_omission_count() -> None:
    docs = ["a" * 3000 for _ in range(10)]
    original = deepcopy(docs)
    row = _single(_index(documentation=docs))
    metadata = row.declaration_metadata
    assert docs == original
    assert len(metadata["documentation"]) == 4
    assert sum(map(len, metadata["documentation"])) == 8192
    assert metadata["documentation_omitted"] == 6
    assert metadata["documentation_clipped_entries"] == 4
    assert metadata["documentation_truncated"] is True


def test_unknown_role_bits_are_not_promoted_to_known_roles() -> None:
    row = _single(_index(roles=1 | 1024, documentation=[]))
    assert row.occurrence_roles["observed_roles"] == ["definition"]
    assert row.occurrence_roles["unrecognized_role_bits"] == 1024


@pytest.mark.parametrize("invalid", ["a doc string", [42], {"text": "x"}])
def test_invalid_symbol_documentation_fails_admission(invalid: object) -> None:
    with pytest.raises(ValueError, match="documentation"):
        parse_scip_json(_index(documentation=invalid))


def test_negative_role_bits_fail_without_inferred_semantics() -> None:
    with pytest.raises(ValueError, match="roles must be nonnegative"):
        parse_scip_json(_index(roles=-1, documentation=[]))
