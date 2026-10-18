from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from contract_assertions import assert_object, assert_records, assert_text

from hashmarks.codemap import (
    RepositoryDeclarationProvider,
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
class _CorrelationProvider:
    name: str = "correlation-ab"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        left = context.read_text("owner-a.txt").strip().split(":", 1)[1].strip()
        right = context.read_text("owner-b.txt").strip().split(":", 1)[1].strip()
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": "correspondence-ab",
                    "concept": {
                        "kind": "ownership-correspondence",
                        "identity": "ab",
                    },
                    "scope": {"environment": "all"},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "left_provider": "provider-a",
                            "right_provider": "provider-b",
                            "rule": "explicit-ab-correspondence",
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
                                    "path": "owner-a.txt",
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
                                    "path": "owner-b.txt",
                                    "start_line": 1,
                                    "end_line": 1,
                                }
                            ],
                        },
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


def _groups(packet: Mapping[str, object]) -> dict[str, dict[str, object]]:
    return {
        assert_text(row["group_id"]): row
        for row in assert_records(assert_object(packet["declarations"])["groups"])
    }


def _source_providers() -> list[RepositoryDeclarationProvider]:
    return [
        _SourceProvider("provider-a", "owner-a.txt"),
        _SourceProvider("provider-b", "owner-b.txt"),
    ]


def _initial_correspondence_packet(
    repo: Path,
    state_dir: Path,
) -> dict[str, object]:
    providers = [*_source_providers(), _CorrelationProvider()]
    with CodeMap(repo, state_dir=state_dir) as codemap:
        codemap.index.sync()
        packet = codemap.declarations.discover(providers)

    assert packet["storage"] == "derived-not-persisted"
    assert assert_object(packet["declarations"])["storage"] == "derived-not-persisted"
    assert set(_groups(packet)) == {
        "provider-a-owner",
        "provider-b-owner",
        "correspondence-ab",
    }
    assert "delta_from_previous" not in packet
    return packet


def _assert_reopen_removes_only_explicit_correspondence(
    repo: Path,
    state_dir: Path,
    previous: dict[str, object],
) -> dict[str, object]:
    with CodeMap(repo, state_dir=state_dir) as codemap:
        current = codemap.declarations.discover(
            _source_providers(),
            previous_observation=previous,
        )

    assert set(_groups(current)) == {"provider-a-owner", "provider-b-owner"}
    assert current["storage"] == "derived-not-persisted"
    assert assert_object(current["delta_from_previous"])["providers"] == {
        "added": [],
        "removed": ["correlation-ab"],
        "changed": [],
    }
    delta = assert_object(assert_object(current["delta_from_previous"])["declarations"])
    assert delta["removed_group_ids"] == ["correspondence-ab"]
    assert delta["added_group_ids"] == []
    assert delta["changed_groups"] == []
    assert assert_object(delta["semantic_subjects"])["removed"] == [
        _groups(previous)["correspondence-ab"]["semantic_subject_identity"]
    ]
    return current


def _assert_reopen_has_no_hidden_correspondence(
    repo: Path,
    state_dir: Path,
) -> dict[str, object]:
    with CodeMap(repo, state_dir=state_dir) as codemap:
        current = codemap.declarations.discover(_source_providers())

    assert set(_groups(current)) == {"provider-a-owner", "provider-b-owner"}
    assert "correspondence-ab" not in _groups(current)
    assert "delta_from_previous" not in current
    return current


def _assert_old_packet_replay_is_one_call_only(
    repo: Path,
    state_dir: Path,
    old_correspondence: dict[str, object],
    expected_current: dict[str, object],
) -> None:
    with CodeMap(repo, state_dir=state_dir) as codemap:
        replayed = codemap.declarations.discover(
            _source_providers(),
            previous_observation=old_correspondence,
        )
        fresh = codemap.declarations.discover(_source_providers())

    assert set(_groups(replayed)) == {"provider-a-owner", "provider-b-owner"}
    assert assert_object(assert_object(replayed["delta_from_previous"])["providers"])[
        "removed"
    ] == ["correlation-ab"]
    assert (
        assert_object(replayed["declarations"])["observation_identity"]
        == assert_object(expected_current["declarations"])["observation_identity"]
    )

    assert set(_groups(fresh)) == {"provider-a-owner", "provider-b-owner"}
    assert "delta_from_previous" not in fresh
    assert fresh["observation_identity"] == expected_current["observation_identity"]
    assert (
        assert_object(fresh["declarations"])["observation_identity"]
        == assert_object(expected_current["declarations"])["observation_identity"]
    )


def test_correspondence_never_persists_or_replays_as_hidden_graph_state(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    state_dir = tmp_path / "state"
    repo.mkdir()
    (repo / "owner-a.txt").write_text("owner: team-a\n", encoding="utf-8")
    (repo / "owner-b.txt").write_text("owner: team-a\n", encoding="utf-8")

    initial = _initial_correspondence_packet(repo, state_dir)
    removed = _assert_reopen_removes_only_explicit_correspondence(
        repo,
        state_dir,
        initial,
    )
    fresh = _assert_reopen_has_no_hidden_correspondence(repo, state_dir)
    assert fresh["observation_identity"] == removed["observation_identity"]

    _assert_old_packet_replay_is_one_call_only(
        repo,
        state_dir,
        initial,
        fresh,
    )
