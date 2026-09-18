from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.repository_delta import RepositoryDeltaMixin
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> tuple[Path, str]:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    source = root / "src" / "owner.py"
    source.write_text("def widget(): return 'old'\n", encoding="utf-8")
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget
def test_widget(): assert widget() == 'new'
",
        encoding="utf-8",
    )
    return source, "change widget behavior and verify widget test"


def _apply(previous: dict[str, object], delta: dict[str, object]) -> dict[str, object]:
    out = json.loads(json.dumps(previous))
    for change in delta["changes"]:
        path = change["path"]
        current = out
        for part in path[:-1]:
            current = current[part]
        key = path[-1]
        if change.get("delete"):
            del current[key]
        else:
            current[key] = change["value"]
    out["snapshot_identity"] = delta["to"]["snapshot_identity"]
    return out


def test_snapshot_contains_path_symbols_dependencies_and_repository_evidence(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        snapshot = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
    assert snapshot["schema"] == "hashmarks.repository-intelligence-snapshot.v1"
    assert "src/owner.py" in snapshot["paths"]
    assert any(
        row.get("name") == "widget"
        for row in snapshot["paths"]["src/owner.py"]["symbols"]
    )
    assert isinstance(snapshot["paths"]["src/owner.py"]["dependencies"], list)
    assert snapshot["verification"]["member"] == "tests/test_owner.py"
    assert snapshot["freshness"]
    assert snapshot["storage"] == "derived-not-persisted"


def test_repository_delta_is_smaller_and_exactly_reconstructs_current_snapshot(
    tmp_path: Path,
) -> None:
    source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        codemap.sync(["src/owner.py"])
        delta = codemap.repository_intelligence_delta(
            task, ["src/owner.py"], previous_snapshot=previous
        )
        current = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])

    assert delta["schema"] == "hashmarks.repository-intelligence-delta.v1"
    assert delta["storage"] == "derived-not-persisted"
    assert delta["authority"] == "repository-intelligence-only"
    assert delta["execution_effect"] == "none"
    assert _apply(previous, delta) == current
    assert len(json.dumps(delta, sort_keys=True)) < len(
        json.dumps(current, sort_keys=True)
    )
    assert "paths" in delta["changed_sections"]
    assert "impact_changed" not in delta["semantic"]
    assert "verification_changed" not in delta["semantic"]
    assert delta["semantic"]["freshness_changed"] is True


def test_repository_delta_reports_dependency_change(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text(
        "def widget(): return 'a'\n", encoding="utf-8"
    )
    (tmp_path / "src" / "b.py").write_text(
        "def widget(): return 'b'\n", encoding="utf-8"
    )
    route = tmp_path / "src" / "route.py"
    route.write_text(
        "from src.a import widget\n"
        "def route(): return widget()\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_route.py").write_text(
        "from src.route import route\n"
        "def test_route(): assert route() == 'b'\n",
        encoding="utf-8",
    )
    task = "change route widget behavior and verify route test"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(task, ["src/route.py"])
        route.write_text(
            "from src.b import widget\n"
            "def route(): return widget()\n", encoding="utf-8"
        )
        codemap.sync(["src/route.py"])
        delta = codemap.repository_intelligence_delta(
            task, ["src/route.py"], previous_snapshot=previous
        )
        current = codemap.repository_intelligence_snapshot(task, ["src/route.py"])
    assert _apply(previous, delta) == current
    assert any(
        row.get("target") == "src.b.widget"
        for row in delta["semantic"]["dependencies_added"]
    )
    assert any(
        row.get("target") == "src.a.widget"
        for row in delta["semantic"]["dependencies_removed"]
    )


def test_repository_delta_does_not_promote_name_similarity_to_move_identity(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    left = tmp_path / "src" / "left.py"
    right = tmp_path / "src" / "right.py"
    left.write_text("def widget(): return 1\n", encoding="utf-8")
    right.write_text("def helper(): return 2\n", encoding="utf-8")
    (tmp_path / "tests" / "test_left.py").write_text(
        "from src.left import widget\n"
        "def test_widget(): assert widget()==1\n",
        encoding="utf-8",
    )
    task = "change widget and verify widget test"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(
            task, ["src/left.py", "src/right.py"]
        )
        left.write_text("", encoding="utf-8")
        right.write_text(
            "def helper(): return 2\n"
            "def widget(): return 1\n", encoding="utf-8"
        )
        codemap.sync(["src/left.py", "src/right.py"])
        delta = codemap.repository_intelligence_delta(
            task, ["src/left.py", "src/right.py"], previous_snapshot=previous
        )
    assert any(
        row.get("name") == "widget" and row["path"] == "src/right.py"
        for row in delta["semantic"]["symbols_added"]
    )
    assert any(
        row.get("name") == "widget" and row["path"] == "src/left.py"
        for row in delta["semantic"]["symbols_removed"]
    )
    assert any(
        row.get("name") == "widget"
        and row["from"] == "src/left.py"
        and row["to"] == "src/right.py"
        and row["state"] == "possible"
        and row["identity_authority"] is False
        for row in delta["semantic"]["possible_symbol_moves"]
    )


def test_repository_delta_rejects_foreign_repository_other_task_and_wrong_schema(
    tmp_path: Path,
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _source_a, task = _repo(a)
    _source_b, _ = _repo(b)
    with CodeMap(a) as ca:
        ca.sync()
        previous = ca.repository_intelligence_snapshot(task, ["src/owner.py"])
    with CodeMap(b) as cb:
        cb.sync()
        with pytest.raises(ValueError, match="repository-mismatch"):
            cb.repository_intelligence_delta(
                task, ["src/owner.py"], previous_snapshot=previous
            )
    with CodeMap(a) as ca:
        ca.sync()
        with pytest.raises(ValueError, match="task-mismatch"):
            ca.repository_intelligence_delta(
                "different task", ["src/owner.py"], previous_snapshot=previous
            )
        with pytest.raises(ValueError, match="repository-intelligence-snapshot"):
            ca.repository_intelligence_delta(
                task, ["src/owner.py"], previous_snapshot={"schema": "wrong"}
            )


def _wait(client: CodeMapServiceClient) -> None:
    for _ in range(100):
        try:
            client.status()
            return
        except OSError:
            time.sleep(0.01)
    raise AssertionError("service did not start")


def test_repository_snapshot_and_delta_service_surface(tmp_path: Path) -> None:
    source, task = _repo(tmp_path)
    socket = tmp_path / "delta.sock"
    service = CodeMapService(tmp_path, socket_path=socket)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket)
    _wait(client)
    try:
        client.sync()
        previous = client.repository_intelligence_query(
            "snapshot", task, ["src/owner.py"]
        )["result"]
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        client.sync()
        delta = client.repository_intelligence_query(
            "delta", task, ["src/owner.py"], previous_snapshot=previous
        )["result"]
        assert delta["schema"] == "hashmarks.repository-intelligence-delta.v1"
        assert delta["execution_effect"] == "none"
    finally:
        client.stop()
        thread.join(timeout=5)


def test_repository_snapshot_exposes_observer_and_explicit_completeness(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        snapshot = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])

    assert snapshot["observer"]["identity"].startswith("sha256:")
    assert snapshot["observer"]["producer"] == "hashmarks"
    assert snapshot["completeness"] == {
        "state": "known-present",
        "scope": "bounded-explicit-change-set",
        "dynamic_runtime_relationships": "unknown",
    }


def test_repository_delta_keeps_observer_change_separate_from_repository_change(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
        previous["observer"] = {
            **previous["observer"],
            "identity": "sha256:older-observer",
        }
        previous["snapshot_identity"] = "sha256:caller-retained-older-observer"
        delta = codemap.repository_intelligence_delta(
            task, ["src/owner.py"], previous_snapshot=previous
        )

    assert delta["observer"]["changed"] is True
    assert delta["observer"]["before"] == "sha256:older-observer"
    assert delta["repository_identity"]


def test_snapshot_relationship_rows_have_stable_identity_and_provenance(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
        second = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])

    symbol = first["paths"]["src/owner.py"]["symbols"][0]
    assert symbol["identity"].startswith("sha256:")
    assert symbol["provenance"] == {
        "source": "codemap-symbol-index",
        "path": "src/owner.py",
    }
    assert second["paths"]["src/owner.py"]["symbols"][0]["identity"] == symbol["identity"]


def test_relationship_identity_does_not_turn_provenance_into_semantic_delta(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
        dependencies = previous["paths"]["src/owner.py"]["dependencies"]
        if dependencies:
            dependencies[0]["provenance"] = {
                "source": "older-compatible-observer",
                "path": "src/owner.py",
            }
        previous["snapshot_identity"] = "sha256:caller-retained-provenance-variant"
        delta = codemap.repository_intelligence_delta(
            task, ["src/owner.py"], previous_snapshot=previous
        )

    assert not delta["semantic"].get("dependencies_added")
    assert not delta["semantic"].get("dependencies_removed")


def test_diagnostic_delta_uses_identity_not_aggregate_count() -> None:
    before = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        repository_identity="sha256:repo-a",
        codemap_generation=41,
        outcome="fail",
        diagnostics=[
            {"tool": "pyright", "rule": "a", "path": "src/a.py", "message": "old"},
            {"tool": "pyright", "rule": "b", "path": "src/b.py", "message": "stable"},
        ],
    )
    after = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        repository_identity="sha256:repo-b",
        codemap_generation=42,
        outcome="fail",
        diagnostics=[
            {"tool": "pyright", "rule": "c", "path": "src/a.py", "message": "new"},
            {"tool": "pyright", "rule": "b", "path": "src/b.py", "message": "stable"},
        ],
    )

    delta = RepositoryDeltaMixin.diagnostic_observation_delta(
        before, after, changed_paths=["src/a.py"]
    )

    assert delta["diagnostics"]["before_count"] == 2
    assert delta["diagnostics"]["after_count"] == 2
    assert len(delta["diagnostics"]["added"]) == 1
    assert len(delta["diagnostics"]["removed"]) == 1
    assert len(delta["diagnostics"]["added_in_changed_scope"]) == 1
    assert delta["diagnostics"]["unchanged_count"] == 1


def test_blocked_environment_is_observation_not_repository_failure() -> None:
    observation = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pytest",
        repository_identity="sha256:repo",
        codemap_generation=42,
        outcome="blocked-permission",
        environment_identity="sha256:sandbox",
        diagnostics=[],
    )

    assert observation["outcome"] == "blocked-permission"
    assert observation["authority"] == "observation-only"
    assert observation["execution_effect"] == "none"


def test_external_diagnostic_identity_is_order_stable() -> None:
    rows = [
        {"tool": "ruff", "rule": "A", "path": "a.py", "message": "a"},
        {"tool": "ruff", "rule": "B", "path": "b.py", "message": "b"},
    ]
    first = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="ruff",
        repository_identity="sha256:repo",
        codemap_generation=1,
        outcome="fail",
        diagnostics=rows,
    )
    second = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="ruff",
        repository_identity="sha256:repo",
        codemap_generation=1,
        outcome="fail",
        diagnostics=list(reversed(rows)),
    )

    assert first["diagnostics"] == second["diagnostics"]


def test_external_observation_stales_on_relevant_edit() -> None:
    observation = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pytest",
        repository_identity="sha256:repo-a",
        codemap_generation=41,
        outcome="pass",
        scope_paths=["src/owner.py", "tests/test_owner.py"],
        diagnostics=[],
    )

    freshness = RepositoryDeltaMixin.external_observation_freshness(
        observation,
        current_repository_identity="sha256:repo-b",
        current_generation=42,
        changed_paths=["src/owner.py"],
    )

    assert freshness["state"] == "stale"
    assert freshness["reason"] == "relevant-repository-evidence-changed"
    assert freshness["intersection"] == ["src/owner.py"]


def test_unrelated_edit_does_not_destroy_scoped_observation_freshness() -> None:
    observation = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pytest",
        repository_identity="sha256:repo-a",
        codemap_generation=41,
        outcome="pass",
        scope_paths=["src/owner.py", "tests/test_owner.py"],
        diagnostics=[],
    )

    freshness = RepositoryDeltaMixin.external_observation_freshness(
        observation,
        current_repository_identity="sha256:repo-b",
        current_generation=42,
        changed_paths=["docs/guide.md"],
    )

    assert freshness["state"] == "fresh"
    assert freshness["reason"] == "changed-paths-proven-outside-observation-scope"
    assert freshness["intersection"] == []


def test_unscoped_external_observation_fails_closed_after_repository_change() -> None:
    observation = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="ruff",
        repository_identity="sha256:repo-a",
        codemap_generation=41,
        outcome="pass",
        diagnostics=[],
    )

    freshness = RepositoryDeltaMixin.external_observation_freshness(
        observation,
        current_repository_identity="sha256:repo-b",
        current_generation=42,
        changed_paths=["docs/guide.md"],
    )

    assert freshness["state"] == "stale"
    assert freshness["reason"] == "repository-changed-without-declared-observation-scope"


def test_dependency_scope_invalidates_observation_without_direct_path_overlap() -> None:
    observation = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pytest",
        repository_identity="sha256:repo-a",
        codemap_generation=41,
        outcome="pass",
        scope_paths=["tests/test_owner.py"],
        diagnostics=[],
    )

    freshness = RepositoryDeltaMixin.external_observation_freshness(
        observation,
        current_repository_identity="sha256:repo-b",
        current_generation=42,
        changed_paths=["src/owner.py"],
        dependency_paths=["src/owner.py"],
    )

    assert freshness["state"] == "stale"
    assert freshness["intersection"] == ["src/owner.py"]


def test_verification_relationship_has_provider_identity_without_sufficiency_claim(
    tmp_path: Path,
) -> None:
    _source, _task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relationship = codemap.verification_relationship_evidence(
            relation_kind="behavioral-verification",
            source="src/owner.py",
            target="tests/test_owner.py",
            classification="direct",
            provenance="static-reference",
        )

    assert relationship["evidence_identity"].startswith("sha256:")
    assert relationship["classification"] == "direct"
    assert "boundary" not in relationship
    assert relationship["relation_kind"] == "behavioral-verification"
    assert relationship["authority"] == "repository-relationship-only"
    assert relationship["execution_effect"] == "none"


def test_verification_relationship_identity_is_deterministic_and_policy_free(
    tmp_path: Path,
) -> None:
    _source, _task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.verification_relationship_evidence(
            source="src/owner.py", target="tests/test_owner.py",
            classification="direct", relation_kind="behavioral-verification",
            provenance="static-reference",
        )
        second = codemap.verification_relationship_evidence(
            source="src/owner.py", target="tests/test_owner.py",
            classification="direct", relation_kind="behavioral-verification",
            provenance="static-reference",
        )
    assert first == second
    assert "boundary" not in first
    assert "sufficient" not in first
    assert "recommended" not in first


def test_verification_relationship_rejects_blank_relation_kind(tmp_path: Path) -> None:
    _source, _task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="relationship kind must be nonblank"):
            codemap.verification_relationship_evidence(
                source="src/owner.py", target="tests/test_owner.py",
                classification="direct", relation_kind=" ",
                provenance="static-reference",
            )


def test_verification_relationship_rejects_policy_classifications(
    tmp_path: Path,
) -> None:
    _source, _task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="unsupported verification relationship"):
            codemap.verification_relationship_evidence(
                relation_kind="behavioral-verification",
                source="src/owner.py",
                target="tests/test_owner.py",
                classification="sufficient",
                provenance="agent-claim",
            )
