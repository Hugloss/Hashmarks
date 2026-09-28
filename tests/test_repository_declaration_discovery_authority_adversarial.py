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
            "expected_declaration_ids": (["value"] if expected is None else expected),
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


@dataclass
class _GeneratedOwnershipProvider:
    name: str = "generated-owner-provider"
    source_path: str = "owners/source.meta"
    generated_path: str = "owners/generated.meta"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return context.exists(self.source_path)

    @staticmethod
    def _declaration(
        *,
        declaration_id: str,
        semantic_role: str,
        path: str,
        value: str,
    ) -> dict[str, object]:
        return {
            "declaration_id": declaration_id,
            "semantic_role": {"kind": semantic_role},
            "value_state": "resolved",
            "value": value,
            "producer": {"provider": "generated-owner-provider"},
            "evidence": [{"path": path, "start_line": 1, "end_line": 1}],
        }

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        source = context.read_text(self.source_path).strip()
        declarations = [
            self._declaration(
                declaration_id="source-owner",
                semantic_role="source",
                path=self.source_path,
                value=source,
            )
        ]
        if context.exists(self.generated_path):
            generated = context.read_text(self.generated_path).strip()
            declarations.append(
                self._declaration(
                    declaration_id="generated-owner",
                    semantic_role="generated-copy",
                    path=self.generated_path,
                    value=generated,
                )
            )
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": "component-owner",
                    "concept": {"kind": "ownership", "identity": "component-a"},
                    "scope": {"environment": "all"},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "rule": "source-generated-correspondence",
                        },
                    },
                    "declarations": declarations,
                    "coverage": {
                        "state": "complete",
                        "truncation": "complete",
                        "expected_declaration_ids": [
                            "source-owner",
                            "generated-owner",
                        ],
                        "scope": {"repository": "fixture"},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={"provider": self.name, "version": "1"},
        )


@dataclass
class _OwnershipUncertaintyProvider:
    coverage_state: str = "complete"
    truncation: str = "complete"
    name: str = "ownership-uncertainty-provider"
    source_path: str = "owners/source.meta"
    generated_path: str = "owners/catalog.meta"
    policy_path: str = ".github/CODEOWNERS"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return context.exists(self.source_path)

    @staticmethod
    def _resolved(
        *,
        declaration_id: str,
        semantic_role: str,
        path: str,
        value: str,
    ) -> dict[str, object]:
        return {
            "declaration_id": declaration_id,
            "semantic_role": {"kind": semantic_role},
            "value_state": "resolved",
            "value": value,
            "producer": {"provider": "ownership-uncertainty-provider"},
            "evidence": [{"path": path, "start_line": 1, "end_line": 1}],
        }

    def _generated_declaration(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> dict[str, object]:
        raw = context.read_text(self.generated_path).strip()
        base = {
            "declaration_id": "generated-owner",
            "semantic_role": {"kind": "generated-catalog"},
            "producer": {"provider": self.name},
            "evidence": [
                {
                    "path": self.generated_path,
                    "start_line": 1,
                    "end_line": 1,
                }
            ],
        }
        candidates = [value.strip() for value in raw.split("|") if value.strip()]
        if len(candidates) > 1:
            return {
                **base,
                "value_state": "ambiguous",
                "candidate_values": candidates,
            }
        return {**base, "value_state": "resolved", "value": raw}

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        source = context.read_text(self.source_path).strip()
        declarations = [
            self._resolved(
                declaration_id="source-owner",
                semantic_role="source-metadata",
                path=self.source_path,
                value=source,
            ),
            self._generated_declaration(context),
        ]
        if context.exists(self.policy_path):
            declarations.append(
                self._resolved(
                    declaration_id="policy-owner",
                    semantic_role="repository-policy",
                    path=self.policy_path,
                    value=context.read_text(self.policy_path).strip(),
                )
            )
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": "component-owner",
                    "concept": {"kind": "ownership", "identity": "component-a"},
                    "scope": {"environment": "all"},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "rule": "explicit-owner-correspondence",
                        },
                    },
                    "declarations": declarations,
                    "coverage": {
                        "state": self.coverage_state,
                        "truncation": self.truncation,
                        "expected_declaration_ids": [
                            "source-owner",
                            "generated-owner",
                            "policy-owner",
                        ],
                        "scope": {"repository": "fixture"},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={"provider": self.name, "version": "1"},
        )


@dataclass
class _PolicyMultiplicityProvider:
    name: str = "policy-multiplicity-provider"
    source_path: str = "owners/source.meta"
    policy_path: str = ".github/CODEOWNERS"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return context.exists(self.source_path)

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        source = context.read_text(self.source_path).strip()
        declarations: list[dict[str, object]] = [
            {
                "declaration_id": "source-owner",
                "semantic_role": {"kind": "source-metadata"},
                "value_state": "resolved",
                "value": source,
                "producer": {"provider": self.name, "source": "metadata"},
                "evidence": [
                    {
                        "path": self.source_path,
                        "start_line": 1,
                        "end_line": 1,
                    }
                ],
            }
        ]
        expected = ["source-owner"]
        for line_number, raw in enumerate(
            context.read_text(self.policy_path).splitlines(),
            start=1,
        ):
            line = raw.strip()
            if not line:
                continue
            pattern, owner = line.split(maxsplit=1)
            declaration_id = f"policy-rule-{line_number}"
            expected.append(declaration_id)
            declarations.append(
                {
                    "declaration_id": declaration_id,
                    "semantic_role": {"kind": "repository-policy"},
                    "value_state": "resolved",
                    "value": owner,
                    "producer": {
                        "provider": self.name,
                        "pattern": pattern,
                        "ordinal": line_number,
                        "specificity": len(pattern),
                    },
                    "evidence": [
                        {
                            "path": self.policy_path,
                            "start_line": line_number,
                            "end_line": line_number,
                        }
                    ],
                }
            )
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": "component-owner",
                    "concept": {"kind": "ownership", "identity": "component-a"},
                    "scope": {"component": "component-a"},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "rule": "explicit-policy-correspondence",
                        },
                    },
                    "declarations": declarations,
                    "coverage": {
                        "state": "complete",
                        "truncation": "complete",
                        "expected_declaration_ids": expected,
                        "scope": {"repository": "fixture"},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={"provider": self.name, "version": "1"},
        )


@dataclass
class _NamespacedOwnershipProvider:
    name: str
    semantic_scope: str = "all"
    provenance_version: str = "1"
    path: str = "owner.txt"

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
                    "group_id": "ownership-request",
                    "concept": {
                        "kind": "ownership",
                        "identity": "component-a",
                    },
                    "scope": {"environment": self.semantic_scope},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "rule": "explicit-ownership-correspondence",
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
                        "scope": {"environment": self.semantic_scope},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={
                "provider": self.name,
                "version": self.provenance_version,
            },
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


def _role_rows(packet: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        row["semantic_role"]["kind"]: row
        for row in _nested_group(packet)["declarations"]
    }


def _generated_ownership_lifecycle(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    repo = tmp_path / "repo"
    source = repo / "owners" / "source.meta"
    generated = repo / "owners" / "generated.meta"
    source.parent.mkdir(parents=True)
    source.write_text("team-a\n", encoding="utf-8")
    generated.write_text("team-a\n", encoding="utf-8")
    provider = _GeneratedOwnershipProvider()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        present = codemap.discover_repository_declarations([provider])

        generated.unlink()
        codemap.sync(["owners/generated.meta"])
        absent = codemap.discover_repository_declarations(
            [provider],
            previous_observation=present,
        )

        generated.write_text("team-b\n", encoding="utf-8")
        codemap.sync(["owners/generated.meta"])
        restored = codemap.discover_repository_declarations(
            [provider],
            previous_observation=absent,
        )

    return present, absent, restored


def _assert_generated_role_absence(
    present: dict[str, object],
    absent: dict[str, object],
) -> str:
    present_group = _nested_group(present)
    absent_group = _nested_group(absent)
    generated_identity = _role_rows(present)["generated-copy"][
        "semantic_declaration_identity"
    ]

    assert present_group["comparison"]["state"] == "equivalent"
    assert present_group["absence"]["state"] == "known-present"
    assert absent_group["comparison"]["state"] == "insufficient"
    assert absent_group["absence"] == {
        "state": "known-absent",
        "missing_declaration_ids": ["generated-owner"],
        "unseen_expected_declaration_ids": [],
        "unexpected_declaration_ids": [],
    }
    assert _provider(absent)["state"] == "collected"
    assert absent["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["generated-owner-provider"],
    }

    delta = _nested_delta(absent)
    changed = delta["changed_groups"][0]
    assert changed["removed_declaration_ids"] == ["generated-owner"]
    assert changed["added_declaration_ids"] == []
    assert changed["comparison_changed"] is True
    assert changed["absence_changed"] is True
    assert changed["coverage_changed"] is False

    subject = delta["semantic_subjects"]["changed"][0]
    assert subject["semantic_declarations"] == {
        "added": [],
        "removed": [generated_identity],
        "ambiguous": [],
        "changed": [],
    }
    bindings = delta["repository_evidence"]["bindings"]
    assert bindings["changed"] == []
    assert bindings["removed"] == [_role_rows(present)["generated-copy"]["binding_id"]]
    assert bindings["preserved"] == [_role_rows(present)["source"]["binding_id"]]
    return generated_identity


def _assert_generated_role_reappearance(
    present: dict[str, object],
    absent: dict[str, object],
    restored: dict[str, object],
    generated_identity: str,
) -> None:
    restored_group = _nested_group(restored)
    restored_roles = _role_rows(restored)
    assert restored_group["comparison"] == {
        "state": "differing",
        "distinct_values": ["team-a", "team-b"],
    }
    assert restored_group["absence"]["state"] == "known-present"
    assert (
        restored_roles["generated-copy"]["semantic_declaration_identity"]
        == generated_identity
    )
    assert (
        restored_group["semantic_subject_identity"]
        == _nested_group(present)["semantic_subject_identity"]
        == _nested_group(absent)["semantic_subject_identity"]
    )

    delta = _nested_delta(restored)
    subject = delta["semantic_subjects"]["changed"][0]
    assert subject["semantic_declarations"] == {
        "added": [generated_identity],
        "removed": [],
        "ambiguous": [],
        "changed": [],
    }
    assert subject["comparison_transition"]["before"]["state"] == "insufficient"
    assert subject["comparison_transition"]["after"]["state"] == "differing"
    assert subject["absence_transition"]["before"]["state"] == "known-absent"
    assert subject["absence_transition"]["after"]["state"] == "known-present"

    bindings = delta["repository_evidence"]["bindings"]
    assert bindings["added"] == [restored_roles["generated-copy"]["binding_id"]]
    assert bindings["changed"] == []
    assert bindings["preserved"] == [restored_roles["source"]["binding_id"]]

    original_generated = _role_rows(present)["generated-copy"]
    restored_generated = restored_roles["generated-copy"]
    assert (
        original_generated["declaration_definition_identity"]
        == restored_generated["declaration_definition_identity"]
    )
    assert (
        original_generated["declaration_observation_identity"]
        != restored_generated["declaration_observation_identity"]
    )


def test_generated_role_reappears_without_history_or_invented_continuity(
    tmp_path: Path,
) -> None:
    present, absent, restored = _generated_ownership_lifecycle(tmp_path)
    generated_identity = _assert_generated_role_absence(present, absent)
    _assert_generated_role_reappearance(
        present,
        absent,
        restored,
        generated_identity,
    )


def _ownership_uncertainty_packets(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    repo = tmp_path / "repo"
    source = repo / "owners" / "source.meta"
    generated = repo / "owners" / "catalog.meta"
    policy = repo / ".github" / "CODEOWNERS"
    source.parent.mkdir(parents=True)
    policy.parent.mkdir(parents=True)
    source.write_text("team-a\n", encoding="utf-8")
    generated.write_text("team-a\n", encoding="utf-8")
    policy.write_text("team-a\n", encoding="utf-8")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        baseline = codemap.discover_repository_declarations(
            [_OwnershipUncertaintyProvider()]
        )

        generated.write_text("team-a | team-b\n", encoding="utf-8")
        policy.unlink()
        codemap.sync(["owners/catalog.meta", ".github/CODEOWNERS"])
        stressed = codemap.discover_repository_declarations(
            [
                _OwnershipUncertaintyProvider(
                    coverage_state="incomplete",
                    truncation="unknown",
                )
            ],
            previous_observation=baseline,
        )
    return baseline, stressed


def _assert_ownership_uncertainty_current_state(
    baseline: dict[str, object],
    stressed: dict[str, object],
) -> None:
    baseline_group = _nested_group(baseline)
    stressed_group = _nested_group(stressed)
    assert baseline_group["comparison"] == {
        "state": "equivalent",
        "distinct_values": ["team-a"],
    }
    assert baseline_group["absence"]["state"] == "known-present"
    assert stressed_group["comparison"] == {
        "state": "ambiguous",
        "reason": "one-or-more-values-not-resolved",
        "ambiguous_declaration_ids": ["generated-owner"],
        "distinct_values": [],
    }
    assert stressed_group["absence"] == {
        "state": "unknown",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": ["policy-owner"],
        "unexpected_declaration_ids": [],
        "reason": "coverage-does-not-authorize-negative-evidence",
    }
    assert stressed["declarations"]["winner"] == "not-selected"
    assert "preferred" not in stressed_group["comparison"]
    assert "authoritative_value" not in stressed_group["comparison"]

    baseline_roles = _role_rows(baseline)
    stressed_roles = _role_rows(stressed)
    for role in ("source-metadata", "generated-catalog"):
        assert (
            baseline_roles[role]["semantic_declaration_identity"]
            == stressed_roles[role]["semantic_declaration_identity"]
        )


def _assert_ownership_uncertainty_semantic_delta(
    baseline: dict[str, object],
    stressed: dict[str, object],
) -> None:
    baseline_roles = _role_rows(baseline)
    delta = _nested_delta(stressed)
    changed = delta["changed_groups"][0]
    assert changed["definition_changed"] is True
    assert changed["removed_declaration_ids"] == ["policy-owner"]
    assert changed["added_declaration_ids"] == []
    assert changed["value_changed_declaration_ids"] == ["generated-owner"]
    assert changed["comparison_changed"] is True
    assert changed["absence_changed"] is True
    assert changed["coverage_changed"] is True

    subject = delta["semantic_subjects"]["changed"][0]
    semantic = subject["semantic_declarations"]
    assert semantic["added"] == []
    assert semantic["ambiguous"] == []
    assert semantic["removed"] == [
        baseline_roles["repository-policy"]["semantic_declaration_identity"]
    ]
    assert semantic["changed"] == [
        {
            "semantic_declaration_identity": baseline_roles["generated-catalog"][
                "semantic_declaration_identity"
            ],
            "semantic_role": {"kind": "generated-catalog"},
            "previous_declaration_id": "generated-owner",
            "current_declaration_id": "generated-owner",
            "declaration_id_changed": False,
            "value_transition": {
                "before": {"value_state": "resolved", "value": "team-a"},
                "after": {
                    "value_state": "ambiguous",
                    "candidate_values": ["team-a", "team-b"],
                },
            },
        }
    ]
    assert subject["comparison_transition"]["before"]["state"] == "equivalent"
    assert subject["comparison_transition"]["after"]["state"] == "ambiguous"
    assert subject["absence_transition"]["before"]["state"] == "known-present"
    assert subject["absence_transition"]["after"]["state"] == "unknown"
    assert subject["coverage_transition"]["before"]["state"] == "complete"
    assert subject["coverage_transition"]["after"]["state"] == "incomplete"


def _assert_ownership_uncertainty_binding_separation(
    baseline: dict[str, object],
    stressed: dict[str, object],
) -> None:
    baseline_roles = _role_rows(baseline)
    stressed_roles = _role_rows(stressed)
    bindings = _nested_delta(stressed)["repository_evidence"]["bindings"]
    assert bindings["removed"] == [baseline_roles["repository-policy"]["binding_id"]]
    assert bindings["added"] == []
    assert stressed_roles["source-metadata"]["binding_id"] in bindings["preserved"]
    assert (
        stressed_roles["generated-catalog"]["binding_id"]
        == baseline_roles["generated-catalog"]["binding_id"]
    )


def test_ownership_value_ambiguity_and_incomplete_coverage_remain_orthogonal(
    tmp_path: Path,
) -> None:
    baseline, stressed = _ownership_uncertainty_packets(tmp_path)
    _assert_ownership_uncertainty_current_state(baseline, stressed)
    _assert_ownership_uncertainty_semantic_delta(baseline, stressed)
    _assert_ownership_uncertainty_binding_separation(baseline, stressed)


def _policy_role_rows(packet: dict[str, object]) -> list[dict[str, object]]:
    return [
        row
        for row in _nested_group(packet)["declarations"]
        if row.get("semantic_role") == {"kind": "repository-policy"}
    ]


def _policy_multiplicity_packets(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    repo = tmp_path / "repo"
    source = repo / "owners" / "source.meta"
    policy = repo / ".github" / "CODEOWNERS"
    source.parent.mkdir(parents=True)
    policy.parent.mkdir(parents=True)
    source.write_text("team-a\n", encoding="utf-8")
    policy.write_text("* team-a\n", encoding="utf-8")
    provider = _PolicyMultiplicityProvider()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        baseline = codemap.discover_repository_declarations([provider])

        policy.write_text(
            "* team-a\n/components/* team-a\n/components/specific team-b\n",
            encoding="utf-8",
        )
        codemap.sync([".github/CODEOWNERS"])
        stressed = codemap.discover_repository_declarations(
            [provider],
            previous_observation=baseline,
        )
    return baseline, stressed


def _assert_policy_multiplicity_current_state(
    baseline: dict[str, object],
    stressed: dict[str, object],
) -> str:
    baseline_group = _nested_group(baseline)
    stressed_group = _nested_group(stressed)
    assert baseline_group["comparison"] == {
        "state": "equivalent",
        "distinct_values": ["team-a"],
    }
    assert stressed_group["comparison"] == {
        "state": "differing",
        "distinct_values": ["team-a", "team-b"],
    }
    assert baseline_group["absence"]["state"] == "known-present"
    assert stressed_group["absence"]["state"] == "known-present"
    assert stressed["declarations"]["winner"] == "not-selected"
    assert "preferred" not in stressed_group["comparison"]
    assert "authoritative_value" not in stressed_group["comparison"]

    baseline_policy = _policy_role_rows(baseline)
    stressed_policy = _policy_role_rows(stressed)
    assert len(baseline_policy) == 1
    assert len(stressed_policy) == 3
    policy_identity = baseline_policy[0]["semantic_declaration_identity"]
    assert {row["semantic_declaration_identity"] for row in stressed_policy} == {
        policy_identity
    }
    assert [row["producer"]["ordinal"] for row in stressed_policy] == [1, 2, 3]
    assert [row["producer"]["specificity"] for row in stressed_policy] == [
        1,
        13,
        20,
    ]
    assert [row["value"] for row in stressed_policy] == [
        "team-a",
        "team-a",
        "team-b",
    ]
    return policy_identity


def _assert_policy_multiplicity_semantic_delta(
    stressed: dict[str, object],
    policy_identity: str,
) -> None:
    semantic = _nested_delta(stressed)["semantic_subjects"]["changed"][0][
        "semantic_declarations"
    ]
    assert semantic["added"] == []
    assert semantic["removed"] == []
    assert semantic["changed"] == []
    assert semantic["ambiguous"] == [
        {
            "semantic_declaration_identity": policy_identity,
            "previous_declaration_ids": ["policy-rule-1"],
            "current_declaration_ids": [
                "policy-rule-1",
                "policy-rule-2",
                "policy-rule-3",
            ],
            "reason": "semantic-declaration-not-unique",
        }
    ]


def _assert_policy_multiplicity_binding_separation(
    baseline: dict[str, object],
    stressed: dict[str, object],
) -> None:
    baseline_group = _nested_group(baseline)
    baseline_policy = _policy_role_rows(baseline)
    source = next(
        row
        for row in baseline_group["declarations"]
        if row.get("semantic_role") == {"kind": "source-metadata"}
    )
    bindings = _nested_delta(stressed)["repository_evidence"]["bindings"]
    assert bindings["preserved"] == [source["binding_id"]]
    assert len(bindings["added"]) == 2
    assert bindings["removed"] == []

    policy_binding = next(
        row
        for row in bindings["changed"]
        if row["binding_id"] == baseline_policy[0]["binding_id"]
    )
    assert policy_binding["definition"]["state"] == "preserved"
    assert policy_binding["direct_evidence"]["state"] == "preserved"
    assert policy_binding["locator_evidence"]["state"] == "preserved"
    assert policy_binding["member_evidence"] == {
        "state": "changed",
        "changes": [
            {
                "scope": "lines",
                "evidence": [".github/CODEOWNERS", 1, 1],
                "state": "changed",
                "revision_changed": True,
                "observation_state_changed": False,
                "before_state": "known-present",
                "after_state": "known-present",
            }
        ],
    }


def test_provider_duplicate_policy_role_preserves_multiplicity_without_precedence(
    tmp_path: Path,
) -> None:
    baseline, stressed = _policy_multiplicity_packets(tmp_path)
    policy_identity = _assert_policy_multiplicity_current_state(
        baseline,
        stressed,
    )
    _assert_policy_multiplicity_semantic_delta(stressed, policy_identity)
    _assert_policy_multiplicity_binding_separation(baseline, stressed)


def _namespace_isolation_packets(
    tmp_path: Path,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.txt").write_text("owner: team-a\n", encoding="utf-8")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        provider_a = codemap.discover_repository_declarations(
            [_NamespacedOwnershipProvider("provider-a")]
        )
        provider_b = codemap.discover_repository_declarations(
            [_NamespacedOwnershipProvider("provider-b")],
            previous_observation=provider_a,
        )
        provider_b_version = codemap.discover_repository_declarations(
            [
                _NamespacedOwnershipProvider(
                    "provider-b",
                    provenance_version="2",
                )
            ],
            previous_observation=provider_b,
        )
        provider_b_scope = codemap.discover_repository_declarations(
            [
                _NamespacedOwnershipProvider(
                    "provider-b",
                    semantic_scope="production",
                    provenance_version="2",
                )
            ],
            previous_observation=provider_b_version,
        )

    return provider_a, provider_b, provider_b_version, provider_b_scope


def _single_role_declaration(packet: dict[str, object]) -> dict[str, object]:
    return _nested_group(packet)["declarations"][0]


def _assert_cross_provider_namespace_isolation(
    provider_a: dict[str, object],
    provider_b: dict[str, object],
) -> None:
    group_a = _nested_group(provider_a)
    group_b = _nested_group(provider_b)
    declaration_a = _single_role_declaration(provider_a)
    declaration_b = _single_role_declaration(provider_b)

    assert group_a["concept"] == group_b["concept"]
    assert group_a["scope"] == group_b["scope"]
    assert declaration_a["semantic_role"] == declaration_b["semantic_role"]
    assert declaration_a["value"] == declaration_b["value"] == "team-a"
    assert declaration_a["binding_id"] == declaration_b["binding_id"]
    assert group_a["semantic_namespace"] == "provider-a"
    assert group_b["semantic_namespace"] == "provider-b"
    assert group_a["semantic_subject_identity"] != group_b["semantic_subject_identity"]
    assert (
        declaration_a["semantic_declaration_identity"]
        != declaration_b["semantic_declaration_identity"]
    )

    delta = provider_b["delta_from_previous"]
    assert delta["providers"] == {
        "added": ["provider-b"],
        "removed": ["provider-a"],
        "changed": [],
    }
    subjects = _nested_delta(provider_b)["semantic_subjects"]
    assert subjects["added"] == [group_b["semantic_subject_identity"]]
    assert subjects["removed"] == [group_a["semantic_subject_identity"]]
    assert subjects["ambiguous"] == []
    assert subjects["changed"] == []

    changed_group = _nested_delta(provider_b)["changed_groups"][0]
    assert changed_group["group_id"] == "ownership-request"
    assert changed_group["semantic_subject_changed"] is True
    assert changed_group["value_changed_declaration_ids"] == []
    assert changed_group["definition_changed_declaration_ids"] == ["owner"]

    bindings = _nested_delta(provider_b)["repository_evidence"]["bindings"]
    assert bindings["changed"] == []
    assert bindings["added"] == []
    assert bindings["removed"] == []
    assert bindings["preserved"] == [declaration_b["binding_id"]]


def _assert_provider_version_is_not_semantic_identity(
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    before_group = _nested_group(before)
    after_group = _nested_group(after)
    before_declaration = _single_role_declaration(before)
    after_declaration = _single_role_declaration(after)

    assert before["providers"][0]["provenance"]["version"] == "1"
    assert after["providers"][0]["provenance"]["version"] == "2"
    assert after["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["provider-b"],
    }
    assert (
        before_group["semantic_subject_identity"]
        == after_group["semantic_subject_identity"]
    )
    assert (
        before_declaration["semantic_declaration_identity"]
        == after_declaration["semantic_declaration_identity"]
    )
    assert (
        before["declarations"]["observation_identity"]
        == after["declarations"]["observation_identity"]
    )
    assert _nested_delta(after)["changed_groups"] == []
    assert _nested_delta(after)["semantic_subjects"] == {
        "added": [],
        "removed": [],
        "ambiguous": [],
        "changed": [],
    }


def _assert_scope_change_is_semantic_remove_add(
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    before_group = _nested_group(before)
    after_group = _nested_group(after)
    before_declaration = _single_role_declaration(before)
    after_declaration = _single_role_declaration(after)

    assert before_group["semantic_namespace"] == after_group["semantic_namespace"]
    assert before_group["concept"] == after_group["concept"]
    assert before_group["scope"] == {"environment": "all"}
    assert after_group["scope"] == {"environment": "production"}
    assert (
        before_group["semantic_subject_identity"]
        != after_group["semantic_subject_identity"]
    )
    assert (
        before_declaration["semantic_declaration_identity"]
        != after_declaration["semantic_declaration_identity"]
    )

    delta = after["delta_from_previous"]
    assert delta["providers"] == {
        "added": [],
        "removed": [],
        "changed": [],
    }
    subjects = _nested_delta(after)["semantic_subjects"]
    assert subjects["added"] == [after_group["semantic_subject_identity"]]
    assert subjects["removed"] == [before_group["semantic_subject_identity"]]
    assert subjects["ambiguous"] == []
    assert subjects["changed"] == []

    changed_group = _nested_delta(after)["changed_groups"][0]
    assert changed_group["semantic_subject_changed"] is True
    assert changed_group["value_changed_declaration_ids"] == []
    assert changed_group["definition_changed_declaration_ids"] == ["owner"]

    bindings = _nested_delta(after)["repository_evidence"]["bindings"]
    assert bindings["changed"] == []
    assert bindings["added"] == []
    assert bindings["removed"] == []
    assert bindings["preserved"] == [after_declaration["binding_id"]]


def test_provider_namespace_version_and_scope_identity_boundaries(
    tmp_path: Path,
) -> None:
    provider_a, provider_b, provider_b_version, provider_b_scope = (
        _namespace_isolation_packets(tmp_path)
    )
    _assert_cross_provider_namespace_isolation(provider_a, provider_b)
    _assert_provider_version_is_not_semantic_identity(
        provider_b,
        provider_b_version,
    )
    _assert_scope_change_is_semantic_remove_add(
        provider_b_version,
        provider_b_scope,
    )
