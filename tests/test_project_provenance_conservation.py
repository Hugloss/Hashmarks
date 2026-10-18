"""Distinct admitted project links survive bounded impact and public projections."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import ChangeImpactOptions, CodeMap, expand_project_impact
from hashmarks.evidence_presentation import FORMATS, present_repository_evidence


def _repository(root: Path, shape: str) -> set[tuple[str, str, str]]:
    for name in ("root", "left", "right", "client"):
        (root / name).mkdir()
        (root / name / "package.json").write_text(json.dumps({"name": name}))
        (root / name / "value.ts").write_text("export const value = 1;\n")
    links = {
        "parallel": [("client", "root", "api"), ("client", "root", "contract")],
        "diamond": [
            ("left", "root", "left-root"),
            ("right", "root", "right-root"),
            ("client", "left", "client-left"),
            ("client", "right", "client-right"),
        ],
        "cycle": [("client", "root", "client-root"), ("root", "client", "root-client")],
    }[shape]
    (root / ".hashmarks-project-links.toml").write_text(
        "".join(
            f"[[link]]\nsource='npm:{source}'\ntarget='npm:{target}'\nkind='{kind}'\n"
            for source, target, kind in links
        )
    )
    return {(f"npm:{source}", f"npm:{target}", kind) for source, target, kind in links}


@pytest.mark.parametrize("shape", ["parallel", "diamond"])
@pytest.mark.parametrize("encoding", ["verbose", "compact"])
def test_distinct_declared_links_survive_public_impact_and_cross_repository_views(
    tmp_path: Path, shape: str, encoding: str
) -> None:
    expected = _repository(tmp_path, shape)
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as repository:
        repository.index.sync()
        repository.native.enrich_projects(
            ("npm-package-graph", "declared-project-links")
        )
        admitted = {
            (row["source"], row["target"], row["kind"])
            for row in repository.store.project_edges()
            if row["producer"] == "declared-project-links"
        }
        impact = repository.changes.task_impact(
            "Update root value",
            ["root/value.ts"],
            options=ChangeImpactOptions(
                project_impact_limit=20, project_impact_encoding=encoding
            ),
        )
        packet = repository.cross_repository.packet(
            "Update root value", ["root/value.ts"]
        )
    assert admitted == expected
    fragment = expand_project_impact(assert_object(impact["project_impact"]))
    assert {
        (row["from"], row["to"], row["kind"])
        for row in assert_records(fragment["edges"])
    } == expected
    assert {
        (row["from"], row["to"], row["kind"])
        for row in assert_records(packet["relationships"])
    } == expected
    depths = {
        row["project"]: row["depth"] for row in assert_records(fragment["affected"])
    }
    assert depths == (
        {"npm:client": 1}
        if shape == "parallel"
        else {"npm:left": 1, "npm:right": 1, "npm:client": 2}
    )
    for format in FORMATS:
        if format == "none":
            continue
        projection = present_repository_evidence(packet, format=format)
        assert projection["supported"] is True
        displayed = [
            finding["details"]
            for group in assert_records(projection["groups"])
            if group["family"] == "relationship"
            for finding in assert_records(group["findings"])
        ]
        assert {
            (row["from"], row["to"], row["kind"]) for row in assert_records(displayed)
        } == expected


@pytest.mark.parametrize("limit", [1, 3])
def test_parallel_provenance_does_not_consume_the_project_membership_limit(
    tmp_path: Path, limit: int
) -> None:
    _repository(tmp_path, "parallel")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as repository:
        repository.index.sync()
        repository.native.enrich_projects(
            ("npm-package-graph", "declared-project-links")
        )
        impact = repository.changes.task_impact(
            "Update root value",
            ["root/value.ts"],
            options=ChangeImpactOptions(project_impact_limit=limit),
        )
    fragment = assert_object(impact["project_impact"])
    assert fragment["affected"] == [{"project": "npm:client", "depth": 1}]
    assert len(assert_records(fragment["edges"])) == 2
    assert fragment["reported_affected"] == fragment["total_affected"] == 1
    assert fragment["complete"] is True


def test_cycles_do_not_expand_the_selected_project_set(tmp_path: Path) -> None:
    _repository(tmp_path, "cycle")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as repository:
        repository.index.sync()
        repository.native.enrich_projects(
            ("npm-package-graph", "declared-project-links")
        )
        packet = repository.cross_repository.packet(
            "Update root value", ["root/value.ts"]
        )
    assert packet["dependents"] == [{"project_identity": "npm:client", "depth": 1}]
    assert packet["execution_effect"] == "none"


def test_full_membership_limit_keeps_both_declared_diamond_paths(
    tmp_path: Path,
) -> None:
    expected = _repository(tmp_path, "diamond")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as repository:
        repository.index.sync()
        repository.native.enrich_projects(
            ("npm-package-graph", "declared-project-links")
        )
        impact = repository.changes.task_impact(
            "Update root value",
            ["root/value.ts"],
            options=ChangeImpactOptions(project_impact_limit=3),
        )
    fragment = assert_object(impact["project_impact"])
    assert len(assert_records(fragment["affected"])) == 3
    assert {
        (row["from"], row["to"], row["kind"])
        for row in assert_records(fragment["edges"])
    } == expected
    assert fragment["complete"] is True


def test_provenance_cannot_admit_an_unselected_project(tmp_path: Path) -> None:
    _repository(tmp_path, "parallel")
    links = tmp_path / ".hashmarks-project-links.toml"
    links.write_text(
        links.read_text()
        + "[[link]]\nsource='npm:left'\ntarget='npm:root'\nkind='other'\n"
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as repository:
        repository.index.sync()
        repository.native.enrich_projects(
            ("npm-package-graph", "declared-project-links")
        )
        impact = repository.changes.task_impact(
            "Update root value",
            ["root/value.ts"],
            options=ChangeImpactOptions(project_impact_limit=1),
        )
    fragment = assert_object(impact["project_impact"])
    assert fragment["affected"] == [{"project": "npm:client", "depth": 1}]
    assert {
        (row["from"], row["to"], row["kind"])
        for row in assert_records(fragment["edges"])
    } == {
        ("npm:client", "npm:root", "api"),
        ("npm:client", "npm:root", "contract"),
    }
    assert fragment["reported_affected"] == 1
    assert fragment["total_affected"] == 2
    assert fragment["complete"] is False
