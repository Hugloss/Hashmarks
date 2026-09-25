from __future__ import annotations

import threading
import time

import pytest
from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap
from hashmarks.codemap.freshness_map import FreshnessMapOptions
from hashmarks.codemap.repository_intelligence_query import (
    RepositoryIntelligenceQueryOptions,
)
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> str:
    (root / "src" / "case").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "case" / "__init__.py").write_text("")
    (root / "src" / "case" / "engine.py").write_text(
        "def ember(v): return v + '-old'\n"
    )
    (root / "src" / "case" / "route.py").write_text(
        "from .engine import ember\ndef handle(v): return ember(v)\n"
    )
    (root / "tests" / "test_ember.py").write_text(
        "from src.case.route import handle\ndef test_ember(): assert handle('x') == 'x-new'\n"
    )
    (root / "tests" / "test_other.py").write_text("def test_other(): assert True\n")
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath=['.']\n"
    )
    return "Fix ember implementation and verify behavior"


def _row_key(row: dict[str, object]) -> tuple[str, str | None]:
    kind = str(row["kind"])
    member = (
        str(row["member"])
        if kind == "negative-verification-evidence" and row.get("member") is not None
        else None
    )
    return kind, member


def _by_key(
    freshness: dict[str, object],
) -> dict[tuple[str, str | None], dict[str, object]]:
    return {_row_key(row): row for row in freshness["entries"]}


def test_freshness_map_is_derived_bounded_repository_truth(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        freshness = codemap.evidence_freshness_map(
            task,
            ["src/case/engine.py"],
            negative_members=["tests/test_other.py"],
        )

    entries = _by_key(freshness)
    assert freshness["schema"] == "hashmarks.evidence-freshness-map.v1"
    assert freshness["authority"] == "repository-intelligence-only"
    assert freshness["storage"] == "derived-not-persisted"
    assert freshness["execution_effect"] == "none"
    assert freshness["freshness_map_identity"].startswith("sha256:")
    assert entries[("ownership", None)]["state"] in {"current", "unknown"}
    assert entries[("impact", None)]["changed_revisions"][0]["revision"]
    assert entries[("verification-membership", None)]["member"] == "tests/test_ember.py"
    negative = entries[("negative-verification-evidence", "tests/test_other.py")]
    assert negative["state"] in {"current", "unknown"}
    assert negative["reason"] in {
        "lower-bounded-verification-evidence",
        "canonical-selection-retained",
        "not-in-bounded-candidate-set",
    }


def test_freshness_map_identity_includes_typed_bounds(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        default = codemap.evidence_freshness_map(task, ["src/case/engine.py"])
        bounded = codemap.evidence_freshness_map(
            task,
            ["src/case/engine.py"],
            options=FreshnessMapOptions(
                limit=2,
                per_role=1,
                impact_limit_per_surface=2,
                max_depth=1,
            ),
        )

    default_impact = _by_key(default)[("impact", None)]
    bounded_impact = _by_key(bounded)[("impact", None)]
    assert bounded_impact["evidence_identity"] != default_impact["evidence_identity"]


def test_prior_map_invalidates_only_changed_evidence_identity(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.evidence_freshness_map(
            task,
            ["src/case/engine.py"],
            negative_members=["tests/test_other.py"],
        )
        (tmp_path / "src" / "case" / "engine.py").write_text(
            "def ember(v): return v + '-new'\n"
        )
        codemap.sync()
        after = codemap.evidence_freshness_map(
            task,
            ["src/case/engine.py"],
            negative_members=["tests/test_other.py"],
            previous_map=before,
        )

    prior = {_row_key(row): row for row in after["prior"]}
    assert prior[("impact", None)]["state"] == "stale"
    assert prior[("ownership", None)]["state"] == "current"
    assert prior[("verification-membership", None)]["state"] == "current"
    assert (
        prior[("negative-verification-evidence", "tests/test_other.py")]["state"]
        == "current"
    )


def test_prior_map_rejects_tampered_retained_evidence(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.evidence_freshness_map(task, ["src/case/engine.py"])
        before["entries"][0]["state"] = "stale"

        with pytest.raises(ValueError, match="freshness identity mismatch"):
            codemap.evidence_freshness_map(
                task,
                ["src/case/engine.py"],
                previous_map=before,
            )


def test_prior_map_rejects_foreign_repository(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    task = _repo(left)
    _repo(right)
    with CodeMap(left) as codemap:
        codemap.sync()
        before = codemap.evidence_freshness_map(task, ["src/case/engine.py"])
    with CodeMap(right) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="repository-mismatch"):
            codemap.evidence_freshness_map(
                task,
                ["src/case/engine.py"],
                previous_map=before,
            )


def test_selected_member_invalidates_prior_negative_claim(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        freshness = codemap.evidence_freshness_map(
            task,
            ["src/case/engine.py"],
            negative_members=["tests/test_ember.py"],
        )

    row = _by_key(freshness)[("negative-verification-evidence", "tests/test_ember.py")]
    assert row["state"] == "stale"
    assert row["reason"] == "member-is-selected"


def test_cross_repository_freshness_is_dependency_bound(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend" / "package.json").write_text('{"name":"backend"}')
    (tmp_path / "frontend" / "package.json").write_text('{"name":"frontend"}')
    (tmp_path / "backend" / "value.ts").write_text("export const value = 1\n")
    (tmp_path / ".hashmarks-project-links.toml").write_text(
        "[[link]]\nsource='npm:frontend'\ntarget='npm:backend'\nkind='consumer'\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        freshness = codemap.evidence_freshness_map(
            "backend value change", ["backend/value.ts"]
        )

    rows = _by_key(freshness)
    cross = rows[("cross-repository", None)]
    assert cross["state"] == "dependent"
    assert cross["dependency_state"] == "current"
    assert any(
        row["producer"] == "declared-project-links" for row in cross["dependencies"]
    )


def _wait(client: CodeMapServiceClient) -> None:
    for _ in range(100):
        try:
            client.status()
            return
        except OSError:
            time.sleep(0.01)
    raise AssertionError("service did not start")


def test_service_exposes_freshness_map(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    socket_path = tmp_path / "hm.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        freshness = client.repository_intelligence_query(
            "freshness",
            task,
            ["src/case/engine.py"],
            options=RepositoryIntelligenceQueryOptions(
                negative_members=("tests/test_other.py",)
            ),
        )["result"]
        assert freshness["schema"] == "hashmarks.evidence-freshness-map.v1"
    finally:
        client.stop()
        thread.join(timeout=5)


def test_negative_evidence_invalidates_when_reference_evidence_changes(
    tmp_path: Path,
) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.evidence_freshness_map(
            task,
            ["src/case/engine.py"],
            negative_members=["tests/test_other.py"],
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.case.route import handle\ndef test_other(): assert handle('x')\n"
        )
        codemap.sync()
        after = codemap.evidence_freshness_map(
            task,
            ["src/case/engine.py"],
            negative_members=["tests/test_other.py"],
            previous_map=before,
        )

    prior = {_row_key(row): row for row in after["prior"]}
    assert (
        prior[("negative-verification-evidence", "tests/test_other.py")]["state"]
        == "stale"
    )


def test_cross_repository_prior_invalidates_on_declared_dependency_change(
    tmp_path: Path,
) -> None:
    for name in ("backend", "frontend", "mobile"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "package.json").write_text(f'{{"name":"{name}"}}')
    (tmp_path / "backend" / "value.ts").write_text("export const value = 1\n")
    links = tmp_path / ".hashmarks-project-links.toml"
    links.write_text(
        "[[link]]\nsource='npm:frontend'\ntarget='npm:backend'\nkind='consumer'\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        before = codemap.evidence_freshness_map(
            "backend value change", ["backend/value.ts"]
        )
        links.write_text(
            "[[link]]\nsource='npm:frontend'\ntarget='npm:backend'\nkind='consumer'\n"
            "[[link]]\nsource='npm:mobile'\ntarget='npm:backend'\nkind='consumer'\n"
        )
        codemap.sync()
        after = codemap.evidence_freshness_map(
            "backend value change",
            ["backend/value.ts"],
            previous_map=before,
        )

    prior = {_row_key(row): row for row in after["prior"]}
    assert prior[("cross-repository", None)]["state"] == "stale"
