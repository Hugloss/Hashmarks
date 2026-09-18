from hashmarks.codemap.engine import CodeMap


def _row(path: str, rank: int, role: str) -> dict[str, object]:
    return {
        "path": path,
        "canonical_rank": rank,
        "roles": [role],
        "name": "target",
        "qualname": "pkg.target",
        "signature": "def target(value: int) -> int",
    }


def _action() -> dict[str, object]:
    return {
        "edit": _row("pkg/engine.py", 1, "edit"),
        "verify": _row("tests/test_engine.py", 2, "verify"),
        "contract": _row("pkg/contracts.py", 3, "contract"),
        "related": [
            _row("pkg/helper.py", 4, "related"),
            _row("pkg/adapter.py", 5, "related"),
        ],
        "inspect": [_row("README.md", 6, "inspect")],
    }


def test_work_context_preserves_mandatory_roles_monotonically() -> None:
    codemap = object.__new__(CodeMap)
    previous_mandatory: set[tuple[str, str]] = set()
    for budget in (128, 192, 256, 384, 512, 640, 768, 1024, 1280, 1536, 1800):
        packet = codemap.work_context(_action(), token_budget=budget)
        assert packet["safe"] is True
        assert packet["role_coverage"] == {
            "edit": True,
            "verify": True,
            "contract": True,
        }
        mandatory = {
            (str(item["role"]), str(item["path"]))
            for item in packet["items"]
            if item["mandatory"]
        }
        assert previous_mandatory <= mandatory
        previous_mandatory = mandatory


def test_optional_evidence_never_evicts_mandatory_skeleton() -> None:
    codemap = object.__new__(CodeMap)
    action = _action()
    baseline = codemap.work_context(action, token_budget=128)
    expanded = codemap.work_context(action, token_budget=1800)
    baseline_mandatory = [item for item in baseline["items"] if item["mandatory"]]
    expanded_mandatory = [item for item in expanded["items"] if item["mandatory"]]
    assert baseline_mandatory == expanded_mandatory[: len(baseline_mandatory)]
    assert expanded["estimated_tokens"] >= baseline["estimated_tokens"]


def test_tiny_budget_reports_missing_roles_instead_of_claiming_safety() -> None:
    codemap = object.__new__(CodeMap)
    packet = codemap.work_context(_action(), token_budget=1)
    assert packet["safe"] is False
    assert packet["items"] == []
    assert packet["missing_roles"] == ["edit", "verify", "contract"]


def test_budget_sweep_finds_smallest_safe_budget_and_density() -> None:
    codemap = object.__new__(CodeMap)
    sweep = codemap.work_context_budget_sweep(
        _action(), budgets=(64, 128, 192, 256, 384, 512)
    )
    assert sweep["mandatory_monotonic"] is True
    assert sweep["smallest_safe_budget"] is not None
    rows = sweep["rows"]
    assert [row["budget"] for row in rows] == [64, 128, 192, 256, 384, 512]
    assert all(row["duplicate_evidence_bytes"] == 0 for row in rows)
    assert all(0.0 <= row["useful_bytes_ratio"] <= 1.0 for row in rows)
    safe_rows = [row for row in rows if row["safe"]]
    assert safe_rows
    assert all(
        row["tokens_per_safe_packet"] == row["estimated_tokens"] for row in safe_rows
    )


def test_same_path_can_cover_multiple_mandatory_roles_without_false_unsafe() -> None:
    codemap = object.__new__(CodeMap)
    shared = _row("pkg/policy.py", 1, "edit")
    action = {
        "edit": shared,
        "verify": _row("tests/test_policy.py", 2, "verify"),
        "contract": dict(shared),
        "related": [],
        "inspect": [],
    }
    packet = codemap.work_context(action, token_budget=512)
    assert packet["safe"] is True
    assert packet["missing_roles"] == []
    assert packet["role_coverage"] == {"edit": True, "verify": True, "contract": True}
    shared_items = [item for item in packet["items"] if item["path"] == "pkg/policy.py"]
    assert len(shared_items) == 1
    assert shared_items[0]["covered_roles"] == ["edit", "contract"]
    assert packet["evidence_metrics"]["duplicate_evidence_bytes"] == 0


def test_optional_duplicate_of_mandatory_path_cannot_change_role_authority() -> None:
    codemap = object.__new__(CodeMap)
    action = _action()
    action["related"] = [
        _row("pkg/engine.py", 99, "related"),
        _row("pkg/new_helper.py", 7, "related"),
    ]
    packet = codemap.work_context(action, token_budget=1800)
    engine = [item for item in packet["items"] if item["path"] == "pkg/engine.py"]
    assert len(engine) == 1
    assert engine[0]["role"] == "edit"
    assert engine[0]["mandatory"] is True
    assert engine[0]["covered_roles"] == ["edit"]


def test_shared_mandatory_path_reports_all_uncovered_roles_when_budget_is_tiny() -> (\n    None\n):
    codemap = object.__new__(CodeMap)
    shared = _row("pkg/policy.py", 1, "edit")
    action = {
        "edit": shared,
        "verify": _row("tests/test_policy.py", 2, "verify"),
        "contract": dict(shared),
        "related": [],
        "inspect": [],
    }
    packet = codemap.work_context(action, token_budget=1)
    assert packet["safe"] is False
    assert packet["items"] == []
    assert packet["missing_roles"] == ["edit", "verify", "contract"]
    assert packet["role_coverage"] == {
        "edit": False,
        "verify": False,
        "contract": False,
    }
