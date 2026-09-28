from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hashmarks.codemap import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderResult,
)
from hashmarks.codemap.engine import CodeMap


@dataclass
class _IndependentOwnerProvider:
    name: str
    path: str

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        value = context.read_text(self.path).strip().split(":", 1)[1].strip()
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": f"{self.name}-owner",
                    "concept": {
                        "kind": "ownership",
                        "identity": "component-a",
                    },
                    "scope": {"environment": "all"},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "rule": "provider-local-owner",
                        },
                    },
                    "declarations": [
                        {
                            "declaration_id": "owner",
                            "semantic_role": {"kind": "repository-owner"},
                            "value_state": "resolved",
                            "value": value,
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
                        "expected_declaration_ids": ["owner"],
                        "scope": {"environment": "all"},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={"provider": self.name, "version": "1"},
        )


@dataclass
class _CrossProviderCorrespondenceProvider:
    correspondence_state: str = "declared"
    name: str = "correlation-provider"
    left_path: str = "owner-a.txt"
    right_path: str = "owner-b.txt"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    @staticmethod
    def _declaration(
        *,
        declaration_id: str,
        semantic_role: str,
        source_provider: str,
        path: str,
        value: str,
    ) -> dict[str, object]:
        return {
            "declaration_id": declaration_id,
            "semantic_role": {"kind": semantic_role},
            "value_state": "resolved",
            "value": value,
            "producer": {
                "provider": "correlation-provider",
                "source_provider": source_provider,
            },
            "evidence": [
                {
                    "path": path,
                    "start_line": 1,
                    "end_line": 1,
                }
            ],
        }

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        left = context.read_text(self.left_path).strip().split(":", 1)[1].strip()
        right = context.read_text(self.right_path).strip().split(":", 1)[1].strip()
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": "cross-provider-owner",
                    "concept": {
                        "kind": "ownership-correspondence",
                        "identity": "component-a",
                    },
                    "scope": {"environment": "all"},
                    "correspondence": {
                        "state": self.correspondence_state,
                        "basis": {
                            "provider": self.name,
                            "left_provider": "provider-a",
                            "right_provider": "provider-b",
                            "rule": "explicit-cross-provider-owner-correspondence",
                        },
                    },
                    "declarations": [
                        self._declaration(
                            declaration_id="left-owner",
                            semantic_role="left-source",
                            source_provider="provider-a",
                            path=self.left_path,
                            value=left,
                        ),
                        self._declaration(
                            declaration_id="right-owner",
                            semantic_role="right-source",
                            source_provider="provider-b",
                            path=self.right_path,
                            value=right,
                        ),
                    ],
                    "coverage": {
                        "state": "complete",
                        "truncation": "complete",
                        "expected_declaration_ids": [
                            "left-owner",
                            "right-owner",
                        ],
                        "scope": {"environment": "all"},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={"provider": self.name, "version": "1"},
        )


def _groups(packet: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        row["group_id"]: row
        for row in packet["declarations"]["groups"]
    }


def _bindings(packet: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        row["binding_id"]: row
        for row in packet["declarations"]["repository_evidence"]["bindings"]
    }


def _correlation_declarations(
    packet: dict[str, object],
) -> dict[str, dict[str, object]]:
    group = _groups(packet)["cross-provider-owner"]
    return {row["declaration_id"]: row for row in group["declarations"]}


def _cross_provider_packets(
    tmp_path: Path,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner-a.txt").write_text("owner: team-a\n", encoding="utf-8")
    (repo / "owner-b.txt").write_text("owner: team-a\n", encoding="utf-8")
    provider_a = _IndependentOwnerProvider("provider-a", "owner-a.txt")
    provider_b = _IndependentOwnerProvider("provider-b", "owner-b.txt")
    correlation = _CrossProviderCorrespondenceProvider()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        baseline = codemap.discover_repository_declarations(
            [provider_a, provider_b, correlation]
        )

        (repo / "owner-b.txt").write_text("owner: team-b\n", encoding="utf-8")
        codemap.sync(["owner-b.txt"])
        differing = codemap.discover_repository_declarations(
            [provider_a, provider_b, correlation],
            previous_observation=baseline,
        )

        ambiguous = codemap.discover_repository_declarations(
            [
                provider_a,
                provider_b,
                _CrossProviderCorrespondenceProvider(
                    correspondence_state="ambiguous"
                ),
            ],
            previous_observation=differing,
        )

        removed = codemap.discover_repository_declarations(
            [provider_a, provider_b],
            previous_observation=ambiguous,
        )

    return baseline, differing, ambiguous, removed


def _assert_baseline_identity_separation(packet: dict[str, object]) -> None:
    groups = _groups(packet)
    source_a = groups["provider-a-owner"]
    source_b = groups["provider-b-owner"]
    correlation = groups["cross-provider-owner"]

    assert source_a["semantic_namespace"] == "provider-a"
    assert source_b["semantic_namespace"] == "provider-b"
    assert correlation["semantic_namespace"] == "correlation-provider"
    assert len(
        {
            source_a["semantic_subject_identity"],
            source_b["semantic_subject_identity"],
            correlation["semantic_subject_identity"],
        }
    ) == 3

    source_roles = {
        source_a["declarations"][0]["semantic_declaration_identity"],
        source_b["declarations"][0]["semantic_declaration_identity"],
    }
    correlation_roles = {
        row["semantic_declaration_identity"]
        for row in correlation["declarations"]
    }
    assert len(source_roles) == 2
    assert source_roles.isdisjoint(correlation_roles)
    assert correlation["comparison"] == {
        "state": "equivalent",
        "distinct_values": ["team-a"],
    }
    assert packet["declarations"]["winner"] == "not-selected"


def _assert_cross_provider_value_change_is_local(
    baseline: dict[str, object],
    differing: dict[str, object],
) -> None:
    before = _groups(baseline)
    after = _groups(differing)
    assert (
        before["provider-a-owner"]["group_observation_identity"]
        == after["provider-a-owner"]["group_observation_identity"]
    )
    assert (
        before["provider-b-owner"]["semantic_subject_identity"]
        == after["provider-b-owner"]["semantic_subject_identity"]
    )
    assert (
        before["cross-provider-owner"]["semantic_subject_identity"]
        == after["cross-provider-owner"]["semantic_subject_identity"]
    )
    assert after["cross-provider-owner"]["comparison"] == {
        "state": "differing",
        "distinct_values": ["team-a", "team-b"],
    }

    provider_delta = differing["delta_from_previous"]["providers"]
    assert provider_delta == {
        "added": [],
        "removed": [],
        "changed": ["correlation-provider", "provider-b"],
    }
    changed_groups = {
        row["group_id"]: row
        for row in differing["delta_from_previous"]["declarations"]["changed_groups"]
    }
    assert set(changed_groups) == {
        "cross-provider-owner",
        "provider-b-owner",
    }
    assert changed_groups["provider-b-owner"]["value_changed_declaration_ids"] == [
        "owner"
    ]
    assert changed_groups["cross-provider-owner"][
        "value_changed_declaration_ids"
    ] == ["right-owner"]


def _assert_correspondence_ambiguity_does_not_rewrite_sources(
    differing: dict[str, object],
    ambiguous: dict[str, object],
) -> None:
    before = _groups(differing)
    after = _groups(ambiguous)
    for group_id in ("provider-a-owner", "provider-b-owner"):
        assert (
            before[group_id]["group_observation_identity"]
            == after[group_id]["group_observation_identity"]
        )

    correlation = after["cross-provider-owner"]
    assert correlation["correspondence"]["state"] == "ambiguous"
    assert correlation["comparison"] == {
        "state": "ambiguous",
        "reason": "correspondence-not-uniquely-declared",
        "distinct_values": [],
    }
    assert ambiguous["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": [],
    }
    changed = ambiguous["delta_from_previous"]["declarations"]["changed_groups"]
    assert [row["group_id"] for row in changed] == ["cross-provider-owner"]
    assert changed[0]["correspondence_changed"] is True
    assert changed[0]["comparison_changed"] is True
    assert changed[0]["value_changed_declaration_ids"] == []


def _assert_removing_correlation_preserves_source_authority(
    ambiguous: dict[str, object],
    removed: dict[str, object],
) -> None:
    before = _groups(ambiguous)
    after = _groups(removed)
    assert set(after) == {"provider-a-owner", "provider-b-owner"}
    for group_id in after:
        assert (
            before[group_id]["group_observation_identity"]
            == after[group_id]["group_observation_identity"]
        )

    delta = removed["delta_from_previous"]
    assert delta["providers"] == {
        "added": [],
        "removed": ["correlation-provider"],
        "changed": [],
    }
    declaration_delta = delta["declarations"]
    assert declaration_delta["removed_group_ids"] == ["cross-provider-owner"]
    assert declaration_delta["added_group_ids"] == []
    assert declaration_delta["changed_groups"] == []
    subjects = declaration_delta["semantic_subjects"]
    assert subjects["removed"] == [
        before["cross-provider-owner"]["semantic_subject_identity"]
    ]
    assert subjects["added"] == []
    assert subjects["changed"] == []
    assert subjects["ambiguous"] == []

    old_correlation = _correlation_declarations(ambiguous)
    source_binding_ids = {
        after["provider-a-owner"]["declarations"][0]["binding_id"],
        after["provider-b-owner"]["declarations"][0]["binding_id"],
    }
    binding_delta = declaration_delta["repository_evidence"]["bindings"]
    assert set(binding_delta["preserved"]) == source_binding_ids
    assert set(binding_delta["removed"]) == {
        old_correlation["left-owner"]["binding_id"],
        old_correlation["right-owner"]["binding_id"],
    }
    assert binding_delta["added"] == []
    assert binding_delta["changed"] == []


def test_explicit_cross_provider_correspondence_never_merges_namespaces(
    tmp_path: Path,
) -> None:
    baseline, differing, ambiguous, removed = _cross_provider_packets(tmp_path)
    _assert_baseline_identity_separation(baseline)
    _assert_cross_provider_value_change_is_local(baseline, differing)
    _assert_correspondence_ambiguity_does_not_rewrite_sources(
        differing,
        ambiguous,
    )
    _assert_removing_correlation_preserves_source_authority(ambiguous, removed)
