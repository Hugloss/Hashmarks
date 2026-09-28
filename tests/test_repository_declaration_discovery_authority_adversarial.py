from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hashmarks.codemap import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderResult,
)
from hashmarks.codemap.engine import CodeMap


def _group(
    *,
    provider: str,
    path: str,
    value: str,
    coverage_state: str = "complete",
    truncation: str = "complete",
    expected: list[str] | None = None,
) -> dict[str, object]:
    return {
        "group_id": provider,
        "concept": {"kind": "ownership", "identity": "component-a"},
        "scope": {"environment": "all"},
        "correspondence": {
            "state": "declared",
            "basis": {"provider": provider},
        },
        "declarations": [
            {
                "declaration_id": "value",
                "value_state": "resolved",
                "value": value,
                "producer": {"provider": provider},
                "evidence": [
                    {
                        "path": path,
                        "start_line": 1,
                        "end_line": 1,
                    }
                ],
            }
        ],
        "coverage": {
            "state": coverage_state,
            "truncation": truncation,
            "expected_declaration_ids": (
                ["value"] if expected is None else expected
            ),
            "scope": {"repository": "fixture"},
            "provenance": {"provider": provider},
        },
    }


@dataclass
class _MarkerProvider:
    name: str = "marker-provider"
    marker: str = "provider.marker"
    value_path: str = "value.meta"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return context.exists(self.marker)

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        value = context.read_text(self.value_path).strip()
        return RepositoryDeclarationProviderResult(
            groups=(
                _group(
                    provider=self.name,
                    path=self.value_path,
                    value=value,
                ),
            ),
            provenance={"provider": self.name},
        )


@dataclass
class _WarningCoverageProvider:
    warning: str | None
    coverage_state: str = "complete"
    truncation: str = "complete"
    name: str = "warning-provider"
    value_path: str = "value.meta"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        value = context.read_text(self.value_path).strip()
        warnings = () if self.warning is None else (self.warning,)
        return RepositoryDeclarationProviderResult(
            groups=(
                _group(
                    provider=self.name,
                    path=self.value_path,
                    value=value,
                    coverage_state=self.coverage_state,
                    truncation=self.truncation,
                    expected=["value", "missing"],
                ),
            ),
            provenance={"provider": self.name},
            warnings=warnings,
        )


@dataclass
class _EnumeratingProvider:
    name: str = "enumerating-owner-provider"
    prefix: str = "owners"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        paths = context.paths(self.prefix)
        if len(paths) != 1:
            raise ValueError("fixture requires exactly one owner source")
        path = paths[0]
        value = context.read_text(path).strip()
        return RepositoryDeclarationProviderResult(
            groups=(
                _group(
                    provider=self.name,
                    path=path,
                    value=value,
                ),
            ),
            provenance={"provider": self.name},
        )


def _provider(packet: dict[str, object]) -> dict[str, object]:
    return packet["providers"][0]


def _nested_group(packet: dict[str, object]) -> dict[str, object]:
    return packet["declarations"]["groups"][0]


def _nested_delta(packet: dict[str, object]) -> dict[str, object]:
    return packet["delta_from_previous"]["declarations"]


def test_detection_lifecycle_adds_and_removes_claims_without_inventing_absence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    marker = repo / "provider.marker"
    (repo / "value.meta").write_text("team-a\n", encoding="utf-8")
    provider = _MarkerProvider()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        not_detected = codemap.discover_repository_declarations([provider])

        marker.write_text("enabled\n", encoding="utf-8")
        codemap.sync(["provider.marker"])
        collected = codemap.discover_repository_declarations(
            [provider],
            previous_observation=not_detected,
        )

        marker.unlink()
        codemap.sync(["provider.marker"])
        removed = codemap.discover_repository_declarations(
            [provider],
            previous_observation=collected,
        )

    assert _provider(not_detected)["state"] == "not-detected"
    assert _provider(not_detected)["inputs"][0]["state"] == "known-absent"
    assert not_detected["declarations"]["groups"] == []

    assert _provider(collected)["state"] == "collected"
    assert {row["path"] for row in _provider(collected)["inputs"]} == {
        "provider.marker",
        "value.meta",
    }
    assert collected["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["marker-provider"],
    }
    assert _nested_delta(collected)["added_group_ids"] == ["marker-provider"]
    assert _nested_group(collected)["absence"]["state"] == "known-present"

    assert _provider(removed)["state"] == "not-detected"
    assert _provider(removed)["inputs"][0]["state"] == "known-absent"
    assert removed["declarations"]["groups"] == []
    assert removed["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["marker-provider"],
    }
    assert _nested_delta(removed)["removed_group_ids"] == ["marker-provider"]


def test_warning_text_is_wrapper_provenance_until_coverage_explicitly_downgrades(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.meta").write_text("team-a\n", encoding="utf-8")

    base_provider = _WarningCoverageProvider(warning=None)
    warning_provider = _WarningCoverageProvider(warning="enumeration may be partial")
    incomplete_provider = _WarningCoverageProvider(
        warning="enumeration may be partial",
        coverage_state="incomplete",
        truncation="unknown",
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        base = codemap.discover_repository_declarations([base_provider])
        warned = codemap.discover_repository_declarations(
            [warning_provider],
            previous_observation=base,
        )
        incomplete = codemap.discover_repository_declarations(
            [incomplete_provider],
            previous_observation=warned,
        )

    assert _provider(base)["warnings"] == []
    assert _provider(warned)["warnings"] == ["enumeration may be partial"]
    assert warned["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["warning-provider"],
    }
    assert _nested_delta(warned)["changed_groups"] == []
    assert (
        base["declarations"]["observation_identity"]
        == warned["declarations"]["observation_identity"]
    )

    assert incomplete["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": [],
    }
    changed = _nested_delta(incomplete)["changed_groups"][0]
    assert changed["definition_changed"] is False
    assert changed["value_changed_declaration_ids"] == []
    assert changed["observation_changed_declaration_ids"] == []
    assert changed["coverage_changed"] is True
    assert changed["absence_changed"] is True
    assert _nested_group(warned)["absence"]["state"] == "known-absent"
    assert _nested_group(incomplete)["absence"] == {
        "state": "unknown",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": ["missing"],
        "unexpected_declaration_ids": [],
        "reason": "coverage-does-not-authorize-negative-evidence",
    }


def test_enumerated_source_move_changes_definition_without_value_churn(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "owners" / "a.meta"
    source.parent.mkdir(parents=True)
    source.write_text("team-a\n", encoding="utf-8")
    provider = _EnumeratingProvider()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.discover_repository_declarations([provider])

        moved = repo / "owners" / "b.meta"
        source.replace(moved)
        codemap.sync(["owners/a.meta", "owners/b.meta"])
        after = codemap.discover_repository_declarations(
            [provider],
            previous_observation=before,
        )

    assert _provider(before)["enumerations"] == [
        {"prefix": "owners", "paths": ["owners/a.meta"]}
    ]
    assert _provider(after)["enumerations"] == [
        {"prefix": "owners", "paths": ["owners/b.meta"]}
    ]
    assert after["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["enumerating-owner-provider"],
    }

    changed = _nested_delta(after)["changed_groups"][0]
    assert changed["definition_changed"] is True
    assert changed["definition_changed_declaration_ids"] == ["value"]
    assert changed["value_changed_declaration_ids"] == []
    assert changed["comparison_changed"] is False
    assert changed["absence_changed"] is False

    nested_binding_changes = _nested_delta(after)["repository_evidence"]["bindings"][
        "changed"
    ]
    assert len(nested_binding_changes) == 1
    binding = nested_binding_changes[0]
    assert binding["definition"]["state"] == "changed"
    assert binding["direct_evidence"]["state"] == "preserved"
    assert binding["member_evidence"]["state"] == "preserved"
