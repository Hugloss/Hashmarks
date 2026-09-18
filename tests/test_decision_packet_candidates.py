from __future__ import annotations

from hashmarks.codemap import CodeMap


def test_decision_packet_candidates_keep_role_order_and_deduplicate_paths() -> None:
    action = {
        "contract": {"path": "CONTRACT.md", "canonical_rank": 3, "roles": ["contract"]},
        "inspect": [
            {"path": "src/edit.py", "canonical_rank": 99},
            {"path": "src/inspect.py", "canonical_rank": 4, "roles": ["inspect"]},
            "invalid",
        ],
        "related": [{"path": "src/related.py", "canonical_rank": 5}],
    }
    candidates = CodeMap._decision_packet_candidates(
        action,
        {"path": "src/edit.py", "canonical_rank": 1, "roles": ["edit"]},
        {"path": "tests/test_edit.py", "canonical_rank": 2, "roles": ["verify"]},
    )
    assert [row["path"] for row in candidates] == [
        "src/edit.py",
        "tests/test_edit.py",
        "CONTRACT.md",
        "src/inspect.py",
        "src/related.py",
    ]
    assert candidates[0] == {
        "path": "src/edit.py",
        "canonical_rank": 1,
        "roles": ["edit"],
    }


def test_decision_packet_candidates_bound_valid_rows_and_ignore_invalid_groups() -> (
    None
):
    action = {
        "inspect": "invalid",
        "related": [{"path": f"src/{index}.py"} for index in range(10)],
    }
    candidates = CodeMap._decision_packet_candidates(action, None, None)
    assert [row["path"] for row in candidates] == [
        "src/0.py",
        "src/1.py",
        "src/2.py",
        "src/3.py",
        "src/4.py",
        "src/5.py",
    ]
