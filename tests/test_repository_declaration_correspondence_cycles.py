from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hashmarks.codemap import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderResult,
)
from hashmarks.codemap.engine import CodeMap


@dataclass
class _SourceProvider:
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
                    "concept": {"kind": "ownership", "identity": self.name},
                    "scope": {"environment": "all"},
                    "correspondence": {
                        "state": "declared",
                        "basis": {"provider": self.name, "rule": "source-owner"},
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
class _PairProvider:
    name: str
    group_id: str
    left_provider: str
    right_provider: str
    left_path: str
    right_path: str

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        left = context.read_text(self.left_path).strip().split(":", 1)[1].strip()
        right = context.read_text(self.right_path).strip().split(":", 1)[1].strip()
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": self.group_id,
                    "concept": {
                        "kind": "ownership-correspondence",
                        "identity": self.group_id,
                    },
                    "scope": {"environment": "all"},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "left_provider": self.left_provider,
                            "right_provider": self.right_provider,
                            "rule": "explicit-pair-correspondence",
                        },
                    },
                    "declarations": [
                        {
                            "declaration_id": "left-owner",
                            "semantic_role": {"kind": "left-source"},
                            "value_state": "resolved",
                            "value": left,
                            "producer": {"provider": self.name},
                            "evidence": [
                                {
                                    "path": self.left_path,
                                    "start_line": 1,
                                    "end_line": 1,
                                }
                            ],
                        },
                        {
                            "declaration_id": "right-owner",
                            "semantic_role": {"kind": "right-source"},
                            "value_state": "resolved",
                            "value": right,
                            "producer": {"provider": self.name},
                            "evidence": [
                                {
                                    "path": self.right_path,
                                    "start_line": 1,
                                    "end_line": 1,
                                }
                            ],
                        },
                    ],
                    "coverage": {
                        "state": "complete",
                        "truncation": "complete",
                        "expected_declaration_ids": ["left-owner", "right-owner"],
                        "scope": {"environment": "all"},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={"provider": self.name, "version": "1"},
        )


@dataclass
class _ExplicitSummaryProvider:
    name: str = "correlation-abc-summary"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        declarations = []
        for role, provider, path in (
            ("a-source", "provider-a", "owner-a.txt"),
            ("b-source", "provider-b", "owner-b.txt"),
            ("c-source", "provider-c", "owner-c.txt"),
        ):
            value = context.read_text(path).strip().split(":", 1)[1].strip()
            declarations.append(
                {
                    "declaration_id": role,
                    "semantic_role": {"kind": role},
                    "value_state": "resolved",
                    "value": value,
                    "producer": {
                        "provider": self.name,
                        "source_provider": provider,
                    },
                    "evidence": [{"path": path, "start_line": 1, "end_line": 1}],
                }
            )
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": "explicit-abc-summary",
                    "concept": {
                        "kind": "ownership-correspondence-summary",
                        "identity": "abc",
                    },
                    "scope": {"environment": "all"},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "rule": "explicit-three-way-summary",
                        },
                    },
                    "declarations": declarations,
                    "coverage": {
                        "state": "complete",
                        "truncation": "complete",
                        "expected_declaration_ids": [
                            "a-source",
                            "b-source",
                            "c-source",
                        ],
                        "scope": {"environment": "all"},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={"provider": self.name, "version": "1"},
        )


def _groups(packet: dict[str, object]) -> dict[str, dict[str, object]]:
    return {row["group_id"]: row for row in packet["declarations"]["groups"]}


def _cycle_packets(
    tmp_path: Path,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("a", "b", "c"):
        (repo / f"owner-{name}.txt").write_text(
            "owner: team-a\n",
            encoding="utf-8",
        )

    provider_a = _SourceProvider("provider-a", "owner-a.txt")
    provider_b = _SourceProvider("provider-b", "owner-b.txt")
    provider_c = _SourceProvider("provider-c", "owner-c.txt")
    ab = _PairProvider(
        "correlation-ab",
        "correspondence-ab",
        "provider-a",
        "provider-b",
        "owner-a.txt",
        "owner-b.txt",
    )
    bc = _PairProvider(
        "correlation-bc",
        "correspondence-bc",
        "provider-b",
        "provider-c",
        "owner-b.txt",
        "owner-c.txt",
    )
    ca = _PairProvider(
        "correlation-ca",
        "correspondence-ca",
        "provider-c",
        "provider-a",
        "owner-c.txt",
        "owner-a.txt",
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        cycle = codemap.discover_repository_declarations(
            [provider_a, provider_b, provider_c, ab, bc, ca]
        )

        (repo / "owner-c.txt").write_text("owner: team-b\n", encoding="utf-8")
        codemap.sync(["owner-c.txt"])
        changed = codemap.discover_repository_declarations(
            [provider_a, provider_b, provider_c, ab, bc, ca],
            previous_observation=cycle,
        )

        explicit_summary = codemap.discover_repository_declarations(
            [
                provider_a,
                provider_b,
                provider_c,
                ab,
                bc,
                ca,
                _ExplicitSummaryProvider(),
            ],
            previous_observation=changed,
        )

    return cycle, changed, explicit_summary


def _assert_cycle_has_no_component_authority(packet: dict[str, object]) -> None:
    groups = _groups(packet)
    assert set(groups) == {
        "provider-a-owner",
        "provider-b-owner",
        "provider-c-owner",
        "correspondence-ab",
        "correspondence-bc",
        "correspondence-ca",
    }
    assert "explicit-abc-summary" not in groups
    for group_id in ("correspondence-ab", "correspondence-bc", "correspondence-ca"):
        assert groups[group_id]["comparison"] == {
            "state": "equivalent",
            "distinct_values": ["team-a"],
        }
    assert packet["declarations"]["winner"] == "not-selected"


def _assert_cycle_change_stays_pair_local(
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    before_groups = _groups(before)
    after_groups = _groups(after)
    assert set(after_groups) == set(before_groups)
    assert "explicit-abc-summary" not in after_groups

    for group_id in (
        "provider-a-owner",
        "provider-b-owner",
        "correspondence-ab",
    ):
        assert (
            before_groups[group_id]["group_observation_identity"]
            == after_groups[group_id]["group_observation_identity"]
        )

    assert after_groups["correspondence-ab"]["comparison"] == {
        "state": "equivalent",
        "distinct_values": ["team-a"],
    }
    for group_id in ("correspondence-bc", "correspondence-ca"):
        assert after_groups[group_id]["comparison"] == {
            "state": "differing",
            "distinct_values": ["team-a", "team-b"],
        }

    assert after["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["correlation-bc", "correlation-ca", "provider-c"],
    }
    changed_groups = {
        row["group_id"]
        for row in after["delta_from_previous"]["declarations"]["changed_groups"]
    }
    assert changed_groups == {
        "correspondence-bc",
        "correspondence-ca",
        "provider-c-owner",
    }
    assert after["declarations"]["winner"] == "not-selected"


def _assert_summary_exists_only_when_explicitly_owned(
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    before_groups = _groups(before)
    after_groups = _groups(after)
    assert set(after_groups) == set(before_groups) | {"explicit-abc-summary"}
    for group_id in before_groups:
        assert (
            before_groups[group_id]["group_observation_identity"]
            == after_groups[group_id]["group_observation_identity"]
        )

    summary = after_groups["explicit-abc-summary"]
    assert summary["semantic_namespace"] == "correlation-abc-summary"
    assert summary["comparison"] == {
        "state": "differing",
        "distinct_values": ["team-a", "team-b"],
    }
    assert after["declarations"]["winner"] == "not-selected"
    assert after["delta_from_previous"]["providers"] == {
        "added": ["correlation-abc-summary"],
        "removed": [],
        "changed": [],
    }

    delta = after["delta_from_previous"]["declarations"]
    assert delta["added_group_ids"] == ["explicit-abc-summary"]
    assert delta["removed_group_ids"] == []
    assert delta["changed_groups"] == []
    assert delta["semantic_subjects"]["added"] == [summary["semantic_subject_identity"]]
    assert delta["semantic_subjects"]["removed"] == []
    assert delta["semantic_subjects"]["changed"] == []
    assert delta["semantic_subjects"]["ambiguous"] == []


def test_correspondence_cycle_never_creates_component_consensus(
    tmp_path: Path,
) -> None:
    cycle, changed, explicit_summary = _cycle_packets(tmp_path)
    _assert_cycle_has_no_component_authority(cycle)
    _assert_cycle_change_stays_pair_local(cycle, changed)
    _assert_summary_exists_only_when_explicitly_owned(changed, explicit_summary)
