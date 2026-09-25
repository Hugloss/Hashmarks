from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from hashmarks import CodeMap
from hashmarks.codemap import (
    RepositoryDeclarationProviderError,
    RepositoryDeclarationProviderResult,
)


def _value(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if "=" in text:
        return text.split("=", 1)[1].strip().strip('"')
    if ":" in text:
        return text.split(":", 1)[1].strip().strip('"')
    return text


@dataclass
class _PairProvider:
    name: str
    group_id: str
    concept: dict[str, object]
    paths: tuple[str, str]
    provenance_version: str = "1"
    detected: bool = True
    warning: str | None = None

    def detect(self, workspace: Path) -> bool:
        return self.detected

    def discover(self, workspace: Path) -> RepositoryDeclarationProviderResult:
        declarations = []
        for index, path in enumerate(self.paths):
            declarations.append(
                {
                    "declaration_id": f"value-{index}",
                    "value_state": "resolved",
                    "value": _value(workspace / path),
                    "producer": {
                        "provider": self.name,
                        "path_kind": Path(path).suffix or Path(path).name,
                    },
                    "evidence": [
                        {
                            "path": path,
                            "start_line": 1,
                            "end_line": 1,
                        }
                    ],
                }
            )
        warnings = () if self.warning is None else (self.warning,)
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": self.group_id,
                    "concept": self.concept,
                    "scope": {"fixture": self.group_id},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "rule": "fixture-explicit-correspondence",
                        },
                    },
                    "declarations": declarations,
                    "coverage": {
                        "state": "complete",
                        "truncation": "complete",
                        "expected_declaration_ids": ["value-0", "value-1"],
                        "scope": {"fixture": self.group_id},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={
                "provider": self.name,
                "version": self.provenance_version,
            },
            warnings=warnings,
        )


@dataclass
class _SingleProvider:
    name: str
    path: str
    detected: bool = True

    def detect(self, workspace: Path) -> bool:
        return self.detected

    def discover(self, workspace: Path) -> RepositoryDeclarationProviderResult:
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": self.name,
                    "concept": {"kind": "fixture", "identity": self.name},
                    "scope": {},
                    "correspondence": {
                        "state": "declared",
                        "basis": {"provider": self.name},
                    },
                    "declarations": [
                        {
                            "declaration_id": "value",
                            "value_state": "resolved",
                            "value": _value(workspace / self.path),
                            "producer": {"provider": self.name},
                            "evidence": [
                                {
                                    "path": self.path,
                                    "start_line": 1,
                                    "end_line": 1,
                                }
                            ],
                        }
                    ],
                    "coverage": {
                        "state": "complete",
                        "truncation": "complete",
                        "expected_declaration_ids": ["value"],
                        "scope": {},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={"provider": self.name},
        )


class _FailingProvider:
    name = "failing-provider"

    def detect(self, workspace: Path) -> bool:
        return True

    def discover(self, workspace: Path) -> RepositoryDeclarationProviderResult:
        raise RuntimeError("fixture discovery failure")


@pytest.mark.parametrize(
    ("paths", "contents", "concept"),
    [
        (
            ("pyproject.toml", "Dockerfile"),
            ('python = "3.12"\n', "python: 3.12\n"),
            {"kind": "runtime-compatibility", "identity": "python"},
        ),
        (
            ("manifest.toml", "resolved.lock"),
            ('version = "4.2"\n', "version: 4.2\n"),
            {"kind": "dependency-version", "identity": "example"},
        ),
        (
            ("CODEOWNERS", "component.metadata"),
            ("owner: team-a\n", "owner: team-a\n"),
            {"kind": "ownership", "identity": "component"},
        ),
        (
            ("source.metadata", "generated.metadata"),
            ("lifecycle: production\n", "lifecycle: production\n"),
            {"kind": "generated-source-fact", "identity": "lifecycle"},
        ),
        (
            ("Chart.yaml", "catalog-info.yaml"),
            ("owner: team-platform\n", "owner: team-platform\n"),
            {"kind": "catalog-correspondence", "identity": "owner"},
        ),
    ],
)
def test_discovery_is_format_and_domain_neutral(
    tmp_path: Path,
    paths: tuple[str, str],
    contents: tuple[str, str],
    concept: dict[str, object],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for path, body in zip(paths, contents, strict=True):
        (repo / path).write_text(body, encoding="utf-8")
    provider = _PairProvider(
        name="fixture-provider",
        group_id="fixture-group",
        concept=concept,
        paths=paths,
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.discover_repository_declarations([provider])

    assert packet["schema"] == "hashmarks.repository-declaration-discovery.v1"
    assert packet["execution_effect"] == "none"
    assert packet["providers"] == [
        {
            "name": "fixture-provider",
            "state": "collected",
            "provenance": {"provider": "fixture-provider", "version": "1"},
            "warnings": [],
            "group_ids": ["fixture-group"],
        }
    ]
    group = packet["declarations"]["groups"][0]
    assert group["concept"] == concept
    assert group["comparison"]["state"] == "equivalent"
    assert packet["observation_identity"].startswith("sha256:")


def test_provider_order_is_not_discovery_identity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("value: a\n", encoding="utf-8")
    (repo / "b.txt").write_text("value: b\n", encoding="utf-8")
    a = _SingleProvider("a-provider", "a.txt")
    b = _SingleProvider("b-provider", "b.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        first = codemap.discover_repository_declarations([b, a])
        second = codemap.discover_repository_declarations([a, b])

    assert first["observation_identity"] == second["observation_identity"]
    assert [row["name"] for row in first["providers"]] == [
        "a-provider",
        "b-provider",
    ]


def test_not_detected_provider_is_observable_without_claiming_absence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("value: a\n", encoding="utf-8")
    provider = _SingleProvider("optional-provider", "a.txt", detected=False)

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.discover_repository_declarations([provider])

    assert packet["providers"] == [
        {"name": "optional-provider", "state": "not-detected"}
    ]
    assert packet["declarations"]["groups"] == []


def test_detected_provider_failure_fails_closed_instead_of_returning_partial_data(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="failing-provider discovery failed",
        ):
            codemap.discover_repository_declarations([_FailingProvider()])


def test_duplicate_provider_names_fail_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("value: a\n", encoding="utf-8")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="names must be unique",
        ):
            codemap.discover_repository_declarations(
                [
                    _SingleProvider("same", "a.txt"),
                    _SingleProvider("same", "a.txt"),
                ]
            )


def test_discovery_delta_separates_provider_provenance_from_declaration_change(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("value: same\n", encoding="utf-8")
    (repo / "b.txt").write_text("value: same\n", encoding="utf-8")
    first_provider = _PairProvider(
        name="fixture-provider",
        group_id="group",
        concept={"kind": "fixture", "identity": "value"},
        paths=("a.txt", "b.txt"),
        provenance_version="1",
    )
    second_provider = _PairProvider(
        name="fixture-provider",
        group_id="group",
        concept={"kind": "fixture", "identity": "value"},
        paths=("a.txt", "b.txt"),
        provenance_version="2",
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.discover_repository_declarations([first_provider])
        after = codemap.discover_repository_declarations(
            [second_provider],
            previous_observation=before,
        )

    delta = after["delta_from_previous"]
    assert delta["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["fixture-provider"],
    }
    assert delta["declarations"]["changed_groups"] == []
    assert (
        before["declarations"]["observation_identity"]
        == after["declarations"]["observation_identity"]
    )
    assert before["observation_identity"] != after["observation_identity"]


def test_discovery_delta_reuses_nested_repository_evidence_delta(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("value: one\n", encoding="utf-8")
    (repo / "b.txt").write_text("value: one\n", encoding="utf-8")
    provider = _PairProvider(
        name="fixture-provider",
        group_id="group",
        concept={"kind": "fixture", "identity": "value"},
        paths=("a.txt", "b.txt"),
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.discover_repository_declarations([provider])
        (repo / "b.txt").write_text("value: two\n", encoding="utf-8")
        codemap.sync(["b.txt"])
        after = codemap.discover_repository_declarations(
            [provider],
            previous_observation=before,
        )

    nested = after["delta_from_previous"]["declarations"]
    assert nested["changed_groups"][0]["value_changed_declaration_ids"] == ["value-1"]
    assert nested["changed_groups"][0]["comparison_changed"] is True
    changed_bindings = nested["repository_evidence"]["bindings"]["changed"]
    assert len(changed_bindings) == 1
    assert changed_bindings[0]["binding_id"].endswith("value-1")


def test_previous_discovery_packet_is_tamper_checked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("value: a\n", encoding="utf-8")
    provider = _SingleProvider("fixture-provider", "a.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        previous = codemap.discover_repository_declarations([provider])
        previous["providers"][0]["state"] = "tampered"
        with pytest.raises(
            ValueError,
            match="previous declaration discovery identity mismatch",
        ):
            codemap.discover_repository_declarations(
                [provider],
                previous_observation=previous,
            )
