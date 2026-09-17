from scripts.agent_evaluation.decision_qa import (
    evaluate_decision_packet,
    packet_consistency,
    summarize_decision_qa,
)


def _packet(
    *, safe=True, edit="src/owner.py", verify="tests/test_owner.py", shared=False
):
    items = [
        {
            "path": edit,
            "role": "edit",
            "covered_roles": ["edit", "contract"] if shared else ["edit"],
        },
        {"path": verify, "role": "verify", "covered_roles": ["verify"]},
    ]
    if not shared:
        items.append(
            {
                "path": "src/contract.py",
                "role": "contract",
                "covered_roles": ["contract"],
            }
        )
    missing = [] if safe else ["contract"]
    if not safe:
        items = items[:2]
    return {
        "edit": {"path": edit},
        "verify": {"path": verify},
        "contract": {"path": edit if shared else "src/contract.py"},
        "work_context": {"items": items, "safe": safe, "missing_roles": missing},
        "context_budget": {"safe": safe, "missing_roles": missing},
        "discrimination": {"needed": not safe},
        "identity": {"task_identity": "task-1"},
    }


def test_consistency_accepts_shared_multi_role_evidence():
    result = packet_consistency(_packet(shared=True))
    assert result["consistent"] is True
    assert result["missing_roles"] == []
    assert result["secret_knowledge_used"] is False


def test_consistency_detects_false_role_safety_claim():
    packet = _packet(safe=True)
    packet["work_context"]["items"] = packet["work_context"]["items"][:2]
    result = packet_consistency(packet)
    assert result["consistent"] is False
    assert "context-safety-role-coverage-mismatch" in result["issues"]


def test_authority_grading_classifies_correct_safe_without_leaking_expected_paths():
    result = evaluate_decision_packet(
        _packet(),
        expected_edit_path="src/owner.py",
        expected_verify_path="tests/test_owner.py",
        expected_safe=True,
    )
    assert result["safety_class"] == "correct-safe"
    assert result["fully_correct"] is True
    assert "expected_edit_path" not in result
    assert "expected_verify_path" not in result
    assert result["grading_scope"] == "authority-side-after-freeze"


def test_authority_grading_classifies_false_safe():
    result = evaluate_decision_packet(
        _packet(safe=True),
        expected_edit_path="src/owner.py",
        expected_verify_path="tests/test_owner.py",
        expected_safe=False,
    )
    assert result["safety_class"] == "false-safe"
    assert result["fully_correct"] is False


def test_authority_grading_classifies_false_unsafe():
    result = evaluate_decision_packet(
        _packet(safe=False),
        expected_edit_path="src/owner.py",
        expected_verify_path="tests/test_owner.py",
        expected_safe=True,
    )
    assert result["safety_class"] == "false-unsafe"
    assert result["fully_correct"] is False


def test_authority_grading_marks_wrong_decision_even_when_safety_is_correct():
    result = evaluate_decision_packet(
        _packet(edit="src/decoy.py"),
        expected_edit_path="src/owner.py",
        expected_verify_path="tests/test_owner.py",
        expected_safe=True,
    )
    assert result["edit_correct"] is False
    assert result["verify_correct"] is True
    assert result["fully_correct"] is False


def test_summary_reports_false_safe_and_false_unsafe_rates():
    rows = [
        {
            "safety_class": "correct-safe",
            "fully_correct": True,
            "edit_correct": True,
            "verify_correct": True,
            "packet_consistent": True,
        },
        {
            "safety_class": "false-safe",
            "fully_correct": False,
            "edit_correct": True,
            "verify_correct": True,
            "packet_consistent": True,
        },
        {
            "safety_class": "false-unsafe",
            "fully_correct": False,
            "edit_correct": True,
            "verify_correct": True,
            "packet_consistent": True,
        },
        {
            "safety_class": "correct-unsafe",
            "fully_correct": True,
            "edit_correct": True,
            "verify_correct": True,
            "packet_consistent": True,
        },
    ]
    summary = summarize_decision_qa(rows)
    assert summary["tasks"] == 4
    assert summary["fully_correct"] == 2
    assert summary["safety"]["false-safe"] == 1
    assert summary["safety"]["false-unsafe"] == 1
    assert summary["false_safe_rate"] == 0.25
    assert summary["false_unsafe_rate"] == 0.25
