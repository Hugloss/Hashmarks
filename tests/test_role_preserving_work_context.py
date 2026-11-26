from copy import deepcopy
from pathlib import Path

from contract_assertions import (
    assert_number,
    assert_object,
    assert_records,
    assert_text,
)

from hashmarks import CodeMap
from hashmarks.codemap.python_ast import estimate_tokens
from hashmarks.codemap.work_context import WorkContextProjection


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


def test_observed_python_action_keeps_edit_and_verifier_with_a_large_default(
    tmp_path: Path,
) -> None:
    head = "def encode_record(value='"
    default = "a" * (511 - len(head)) + "界" * 400
    (tmp_path / "codec.py").write_text(
        f"{head}{default}'):\n    return value\n", encoding="utf-8"
    )
    (tmp_path / "test_codec.py").write_text(
        "from codec import encode_record\ndef test_encode_record(): assert encode_record('x') == 'x'\n"
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        action = repository.tasks.action_map("Fix encode_record in codec.py")
        original = deepcopy(action)
        packet = repository.context.work(action, token_budget=256)
    assert action == original
    anchors = {row["role"]: row for row in assert_records(packet["items"])}
    edit, verify = anchors["edit"], anchors["verify"]
    selected = assert_object(action["edit"])
    exact = assert_text(selected["signature"])
    shown = assert_text(edit["content"]).split("\nsignature preview: ", 1)[1]
    assert shown == exact.encode()[:512].decode("utf-8", errors="ignore")
    assert edit["signature_truncated"] is True
    assert (edit["path"], edit["symbol"], edit["canonical_rank"]) == (
        selected["path"],
        selected["qualname"],
        selected["canonical_rank"],
    )
    assert "\nsignature: def test_encode_record()" in assert_text(verify["content"])
    assert "signature_truncated" not in verify
    assert packet["role_coverage"] == {"edit": True, "verify": True, "contract": False}
    assert packet["estimated_tokens"] == sum(
        estimate_tokens(assert_text(row["content"])) for row in anchors.values()
    )


def test_supplied_short_preview_stays_explicitly_partial() -> None:
    edit = _row("pkg/engine.py", 1, "edit")
    edit.update(
        signature=None, signature_preview="def target( ", signature_truncated=True
    )
    result = WorkContextProjection().work({"edit": edit})
    (anchor,) = assert_records(result["items"])
    assert anchor["signature_truncated"] is True
    assert assert_text(anchor["content"]).endswith("\nsignature preview: def target( ")


def test_work_context_preserves_mandatory_roles_monotonically() -> None:
    codemap = WorkContextProjection()
    previous_mandatory: set[tuple[str, str]] = set()
    for budget in (128, 192, 256, 384, 512, 640, 768, 1024, 1280, 1536, 1800):
        packet = codemap.work(_action(), token_budget=budget)
        assert packet["safe"] is True
        assert packet["role_coverage"] == {
            "edit": True,
            "verify": True,
            "contract": True,
        }
        mandatory = {
            (str(item["role"]), str(item["path"]))
            for item in assert_records(packet["items"])
            if item["mandatory"]
        }
        assert previous_mandatory <= mandatory
        previous_mandatory = mandatory


def test_optional_evidence_never_evicts_mandatory_skeleton() -> None:
    codemap = WorkContextProjection()
    action = _action()
    baseline = codemap.work(action, token_budget=128)
    expanded = codemap.work(action, token_budget=1800)
    baseline_mandatory = [
        item for item in assert_records(baseline["items"]) if item["mandatory"]
    ]
    expanded_mandatory = [
        item for item in assert_records(expanded["items"]) if item["mandatory"]
    ]
    assert baseline_mandatory == expanded_mandatory[: len(baseline_mandatory)]
    assert assert_number(expanded["estimated_tokens"]) >= assert_number(
        baseline["estimated_tokens"]
    )


def test_tiny_budget_reports_missing_roles_instead_of_claiming_safety() -> None:
    codemap = WorkContextProjection()
    packet = codemap.work(_action(), token_budget=1)
    assert packet["safe"] is False
    assert packet["items"] == []
    assert packet["missing_roles"] == ["edit", "verify", "contract"]


def test_budget_sweep_finds_smallest_safe_budget_and_density() -> None:
    codemap = WorkContextProjection()
    sweep = codemap.budget_sweep(_action(), budgets=(64, 128, 192, 256, 384, 512))
    assert sweep["mandatory_monotonic"] is True
    assert sweep["smallest_safe_budget"] is not None
    rows = assert_records(sweep["rows"])
    assert [row["budget"] for row in rows] == [64, 128, 192, 256, 384, 512]
    assert all(row["duplicate_evidence_bytes"] == 0 for row in rows)
    assert all(0.0 <= assert_number(row["useful_bytes_ratio"]) <= 1.0 for row in rows)
    safe_rows = [row for row in rows if row["safe"]]
    assert safe_rows
    assert all(
        row["tokens_per_safe_packet"] == row["estimated_tokens"] for row in safe_rows
    )


def test_same_path_can_cover_multiple_mandatory_roles_without_false_unsafe() -> None:
    codemap = WorkContextProjection()
    shared = _row("pkg/policy.py", 1, "edit")
    action = {
        "edit": shared,
        "verify": _row("tests/test_policy.py", 2, "verify"),
        "contract": dict(shared),
        "related": [],
        "inspect": [],
    }
    packet = codemap.work(action, token_budget=512)
    assert packet["safe"] is True
    assert packet["missing_roles"] == []
    assert packet["role_coverage"] == {"edit": True, "verify": True, "contract": True}
    shared_items = [
        item
        for item in assert_records(packet["items"])
        if item["path"] == "pkg/policy.py"
    ]
    assert len(shared_items) == 1
    assert shared_items[0]["covered_roles"] == ["edit", "contract"]
    assert assert_object(packet["evidence_metrics"])["duplicate_evidence_bytes"] == 0


def test_optional_duplicate_of_mandatory_path_cannot_change_role_authority() -> None:
    codemap = WorkContextProjection()
    action = _action()
    action["related"] = [
        _row("pkg/engine.py", 99, "related"),
        _row("pkg/new_helper.py", 7, "related"),
    ]
    packet = codemap.work(action, token_budget=1800)
    engine = [
        item
        for item in assert_records(packet["items"])
        if item["path"] == "pkg/engine.py"
    ]
    assert len(engine) == 1
    assert engine[0]["role"] == "edit"
    assert engine[0]["mandatory"] is True
    assert engine[0]["covered_roles"] == ["edit"]


def test_shared_mandatory_path_reports_all_uncovered_roles_when_budget_is_tiny() -> (
    None
):
    codemap = WorkContextProjection()
    shared = _row("pkg/policy.py", 1, "edit")
    action = {
        "edit": shared,
        "verify": _row("tests/test_policy.py", 2, "verify"),
        "contract": dict(shared),
        "related": [],
        "inspect": [],
    }
    packet = codemap.work(action, token_budget=1)
    assert packet["safe"] is False
    assert packet["items"] == []
    assert packet["missing_roles"] == ["edit", "verify", "contract"]
    assert packet["role_coverage"] == {
        "edit": False,
        "verify": False,
        "contract": False,
    }
