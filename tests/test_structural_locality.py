from __future__ import annotations

from pathlib import Path

from hashmarks.codemap import CodeMap, structural_locality_delta


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _codemap(root: Path) -> CodeMap:
    return CodeMap(
        root,
        state_dir=root / ".hashmarks-test-state",
        artifact_db=root / ".hashmarks-test-artifacts.sqlite3",
    )


def test_structural_locality_reports_exact_bounded_facts(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/core.py",
        """
def helper(value):
    return value + 1


def wrapper(value):
    return helper(value)


def authority(value):
    if value < 0:
        raise ValueError(value)
    return wrapper(value)
""".lstrip(),
    )
    _write(
        tmp_path,
        "tests/test_core.py",
        """
from pkg.core import authority


def test_authority():
    assert authority(1) == 2
""".lstrip(),
    )

    with _codemap(tmp_path) as codemap:
        packet = codemap.structural_locality(
            "pkg/core.py::authority",
            max_depth=3,
        )

    assert packet["schema"] == "hashmarks.structural-locality.v1"
    assert packet["freshness"]["state"] == "current"
    assert packet["freshness"]["basis"] == "explicit-sync"
    assert packet["claims"] == {
        "refactor_recommendation": False,
        "semantic_responsibility_inferred": False,
        "ambiguous_calls_promoted_to_exact": False,
        "execution_authority": False,
    }
    nodes = {row["symbol_id"]: row for row in packet["nodes"]}
    assert set(nodes) == {
        "pkg/core.py::authority",
        "pkg/core.py::wrapper",
        "pkg/core.py::helper",
    }
    assert nodes["pkg/core.py::authority"]["forwarding_only"] is False
    assert nodes["pkg/core.py::wrapper"]["forwarding_only"] is True
    assert nodes["pkg/core.py::wrapper"]["exact_caller_count"] == 1
    assert nodes["pkg/core.py::helper"]["exact_caller_count"] == 1
    assert packet["dimensions"]["file_count"] == 1
    assert packet["dimensions"]["max_navigation_depth"] == 2
    assert packet["dimensions"]["forwarding_only_symbol_count"] == 1
    assert packet["dimensions"]["unresolved_call_count"] == 0
    assert packet["dimensions"]["external_or_unindexed_call_count"] == 1
    assert packet["external_or_unindexed_calls"][0]["target_text"] == "ValueError"
    assert "tests/test_core.py" in packet["verification_paths"]
    assert str(packet["provider_implementation_identity"]).startswith("sha256:")
    assert str(packet["repository_identity"]).startswith("sha256:")
    assert str(packet["source_identity"]).startswith("sha256:")
    assert str(packet["measurement_configuration_identity"]).startswith("sha256:")
    assert str(packet["evidence_identity"]).startswith("sha256:")


def test_structural_locality_keeps_ambiguous_call_unresolved(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/core.py",
        """
def helper(value):
    return value + 1


def wrapper(value):
    return helper(value)


def authority(value):
    return wrapper(value)
""".lstrip(),
    )
    _write(
        tmp_path,
        "pkg/other.py",
        """
def helper(value):
    return value - 1
""".lstrip(),
    )

    with _codemap(tmp_path) as codemap:
        packet = codemap.structural_locality(
            "pkg/core.py::authority",
            max_depth=3,
        )

    nodes = {row["symbol_id"] for row in packet["nodes"]}
    assert "pkg/core.py::wrapper" in nodes
    assert "pkg/core.py::helper" not in nodes
    assert "pkg/other.py::helper" not in nodes
    unresolved = packet["unresolved_calls"]
    assert any(row.get("target_text") == "helper" for row in unresolved)
    helper_row = next(row for row in unresolved if row.get("target_text") == "helper")
    assert helper_row["candidate_symbol_ids"] == [
        "pkg/core.py::helper",
        "pkg/other.py::helper",
    ]
    assert packet["claims"]["ambiguous_calls_promoted_to_exact"] is False


def test_structural_locality_delta_reports_facts_without_policy(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/core.py",
        """
def authority(value):
    if value < 0:
        raise ValueError(value)
    return value + 1
""".lstrip(),
    )
    with _codemap(tmp_path) as codemap:
        before = codemap.structural_locality(
            "pkg/core.py::authority",
            max_depth=3,
        )
        _write(
            tmp_path,
            "pkg/core.py",
            """
def helper(value):
    return value + 1


def authority(value):
    if value < 0:
        raise ValueError(value)
    return helper(value)
""".lstrip(),
        )
        after = codemap.structural_locality(
            "pkg/core.py::authority",
            max_depth=3,
        )

    delta = structural_locality_delta(before, after)
    assert delta["schema"] == "hashmarks.structural-locality-delta.v1"
    assert delta["comparable"] is True
    assert delta["incomparability_reasons"] == []
    assert delta["introduced_symbol_ids"] == ["pkg/core.py::helper"]
    assert delta["removed_symbol_ids"] == []
    assert delta["dimension_delta"]["symbol_count"] == 1
    assert delta["claims"] == {
        "architectural_improvement": False,
        "refactor_recommendation": False,
        "consumer_policy_applied": False,
    }


def test_structural_locality_requires_exact_symbol_identity(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/core.py", "def authority():\n    return 1\n")
    with _codemap(tmp_path) as codemap:
        try:
            codemap.structural_locality("authority")
        except ValueError as exc:
            assert "path::qualname" in str(exc)
        else:
            raise AssertionError("plain symbol name was accepted as structural-locality authority")


def test_structural_locality_does_not_short_name_resolve_qualified_call(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/core.py",
        """
def helper(value):
    return value + 1


def authority(client, value):
    return client.helper(value)
""".lstrip(),
    )

    with _codemap(tmp_path) as codemap:
        packet = codemap.structural_locality(
            "pkg/core.py::authority",
            max_depth=2,
        )

    assert [row["symbol_id"] for row in packet["nodes"]] == [
        "pkg/core.py::authority"
    ]
    assert packet["dimensions"]["unresolved_call_count"] == 1
    row = packet["unresolved_calls"][0]
    assert row["target_text"] == "client.helper"
    assert row["candidate_symbol_ids"] == ["pkg/core.py::helper"]


def test_structural_locality_does_not_resolve_shadowed_plain_call(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/core.py",
        """
def helper(value):
    return value + 1


def authority(helper, value):
    return helper(value)
""".lstrip(),
    )

    with _codemap(tmp_path) as codemap:
        packet = codemap.structural_locality(
            "pkg/core.py::authority",
            max_depth=2,
        )

    assert [row["symbol_id"] for row in packet["nodes"]] == [
        "pkg/core.py::authority"
    ]
    assert packet["dimensions"]["unresolved_call_count"] == 1
    assert packet["unresolved_calls"][0]["candidate_symbol_ids"] == [
        "pkg/core.py::helper"
    ]


def test_structural_locality_delta_rejects_tampered_packet_identity(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/core.py", "def authority():\n    return 1\n")
    with _codemap(tmp_path) as codemap:
        before = codemap.structural_locality("pkg/core.py::authority")
        _write(tmp_path, "pkg/core.py", "def authority():\n    return 2\n")
        after = codemap.structural_locality("pkg/core.py::authority")

    tampered = dict(after)
    tampered["repository_identity"] = "sha256:tampered"
    delta = structural_locality_delta(before, tampered)

    assert delta["comparable"] is False
    assert "after-evidence-identity" in delta["incomparability_reasons"]


def test_structural_locality_exact_callers_are_positive_reuse_evidence(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/shared.py", "def helper(value):\n    return value + 1\n")
    _write(
        tmp_path,
        "pkg/a.py",
        "from pkg.shared import helper\n"
        "def use_a(value):\n"
        "    return helper(value)\n",
    )
    _write(
        tmp_path,
        "pkg/b.py",
        "from pkg.shared import helper\n"
        "def use_b(value):\n"
        "    return helper(value)\n",
    )

    with _codemap(tmp_path) as codemap:
        packet = codemap.structural_locality(
            "pkg/shared.py::helper",
            max_depth=0,
        )

    target = packet["nodes"][0]
    assert target["symbol_id"] == "pkg/shared.py::helper"
    assert target["exact_caller_count"] == 2
    assert {
        (row["path"], row["source"]) for row in target["exact_callers"]
    } == {
        ("pkg/a.py", "use_a"),
        ("pkg/b.py", "use_b"),
    }
    assert packet["dimensions"]["target_exact_caller_count"] == 2
