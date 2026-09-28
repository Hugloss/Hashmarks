from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from hashmarks import CodeMap
from hashmarks.codemap import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderError,
    RepositoryDeclarationProviderResult,
)


def _value(context: RepositoryDeclarationProviderContext, path: str) -> str:
    text = context.read_text(path).strip()
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

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return self.detected

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        declarations = []
        for index, path in enumerate(self.paths):
            declarations.append(
                {
                    "declaration_id": f"value-{index}",
                    "value_state": "resolved",
                    "value": _value(context, path),
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

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return self.detected

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
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
                            "value": _value(context, self.path),
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


@dataclass
class _FixedSubjectProvider:
    name: str
    path: str
    override_namespace: bool = False

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        group: dict[str, object] = {
            "group_id": self.name,
            "concept": {"kind": "shared-fixture", "identity": "subject"},
            "scope": {"environment": "all"},
            "correspondence": {
                "state": "declared",
                "basis": {"provider": self.name},
            },
            "declarations": [
                {
                    "declaration_id": "value",
                    "value_state": "resolved",
                    "value": _value(context, self.path),
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
        }
        if self.override_namespace:
            group["semantic_namespace"] = "spoofed-provider"
        return RepositoryDeclarationProviderResult(
            groups=(group,),
            provenance={"provider": self.name},
        )


@dataclass
class _SemanticRoleProvider:
    name: str = "runtime-provider"
    group_id: str = "runtime-request"
    project_declaration_id: str = "project-intent"
    runtime_declaration_id: str = "container-runtime"
    project_path: str = "pyproject.toml"
    runtime_path: str = "Dockerfile"
    provenance_version: str = "1"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": self.group_id,
                    "concept": {
                        "kind": "runtime-compatibility",
                        "identity": "python",
                    },
                    "scope": {"environment": "application"},
                    "correspondence": {
                        "state": "declared",
                        "basis": {
                            "provider": self.name,
                            "rule": "explicit-runtime-correspondence",
                        },
                    },
                    "declarations": [
                        {
                            "declaration_id": self.project_declaration_id,
                            "semantic_role": {"kind": "project-intent"},
                            "value_state": "resolved",
                            "value": _value(context, self.project_path),
                            "producer": {
                                "provider": self.name,
                                "source": "project-intent",
                            },
                            "evidence": [
                                {
                                    "path": self.project_path,
                                    "start_line": 1,
                                    "end_line": 1,
                                }
                            ],
                        },
                        {
                            "declaration_id": self.runtime_declaration_id,
                            "semantic_role": {"kind": "container-runtime"},
                            "value_state": "resolved",
                            "value": _value(context, self.runtime_path),
                            "producer": {
                                "provider": self.name,
                                "source": "container-runtime",
                            },
                            "evidence": [
                                {
                                    "path": self.runtime_path,
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
                            self.project_declaration_id,
                            self.runtime_declaration_id,
                        ],
                        "scope": {"environment": "application"},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={
                "provider": self.name,
                "version": self.provenance_version,
            },
        )


@dataclass
class _NamespacedOwnershipProvider:
    name: str
    path: str = "owner.txt"
    semantic_scope: str = "all"
    provenance_version: str = "1"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        value = _value(context, self.path)
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


class _FailingProvider:
    name = "failing-provider"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
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
    assert packet["execution_effect"] == {
        "hashmarks": "none",
        "provider_contract": "read-only",
        "provider_sandboxed": False,
    }
    provider_row = packet["providers"][0]
    assert provider_row["name"] == "fixture-provider"
    assert provider_row["state"] == "collected"
    assert provider_row["provenance"] == {
        "provider": "fixture-provider",
        "version": "1",
    }
    assert provider_row["warnings"] == []
    assert provider_row["group_ids"] == ["fixture-group"]
    assert [row["path"] for row in provider_row["inputs"]] == sorted(paths)
    assert all(
        row["state"] == "known-present" and row.get("member_revision")
        for row in provider_row["inputs"]
    )
    group = packet["declarations"]["groups"][0]
    assert group["semantic_namespace"] == "fixture-provider"
    assert group["concept"] == concept
    assert group["comparison"]["state"] == "equivalent"
    assert packet["observation_identity"].startswith("sha256:")


def _semantic_role_rows(packet: dict[str, object]) -> dict[str, dict[str, object]]:
    group = packet["declarations"]["groups"][0]
    return {row["semantic_role"]["kind"]: row for row in group["declarations"]}


def _binding_rows(packet: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        row["binding_id"]: row
        for row in packet["declarations"]["repository_evidence"]["bindings"]
    }


def _provider_role_churn_packets(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('python = "3.12"\n', encoding="utf-8")
    (repo / "Dockerfile").write_text("python: 3.12\n", encoding="utf-8")
    before_provider = _SemanticRoleProvider(
        group_id="runtime-request-v1",
        project_declaration_id="intent-v1",
        runtime_declaration_id="container-v1",
        provenance_version="1",
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.discover_repository_declarations([before_provider])

        moved = repo / "deploy" / "runtime.meta"
        moved.parent.mkdir()
        (repo / "Dockerfile").replace(moved)
        moved.write_text("python: 3.13\n", encoding="utf-8")
        codemap.sync(["Dockerfile", "deploy/runtime.meta"])

        after = codemap.discover_repository_declarations(
            [
                _SemanticRoleProvider(
                    group_id="runtime-request-v2",
                    project_declaration_id="intent-v2",
                    runtime_declaration_id="container-v2",
                    runtime_path="deploy/runtime.meta",
                    provenance_version="2",
                )
            ],
            previous_observation=before,
        )
    return before, after


def _assert_provider_role_semantics(
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    assert before["providers"][0]["provenance"]["version"] == "1"
    assert after["providers"][0]["provenance"]["version"] == "2"
    assert after["delta_from_previous"]["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["runtime-provider"],
    }

    before_group = before["declarations"]["groups"][0]
    after_group = after["declarations"]["groups"][0]
    assert (
        before_group["semantic_subject_identity"]
        == after_group["semantic_subject_identity"]
    )

    before_by_role = _semantic_role_rows(before)
    after_by_role = _semantic_role_rows(after)
    for role in ("project-intent", "container-runtime"):
        assert (
            before_by_role[role]["semantic_declaration_identity"]
            == after_by_role[role]["semantic_declaration_identity"]
        )

    subject = after["delta_from_previous"]["declarations"]["semantic_subjects"][
        "changed"
    ][0]
    assert subject["previous_group_id"] == "runtime-request-v1"
    assert subject["current_group_id"] == "runtime-request-v2"
    assert subject["group_id_changed"] is True

    semantic = subject["semantic_declarations"]
    assert semantic["added"] == []
    assert semantic["removed"] == []
    assert semantic["ambiguous"] == []
    changes = {row["semantic_role"]["kind"]: row for row in semantic["changed"]}
    assert changes["project-intent"] == {
        "semantic_declaration_identity": before_by_role["project-intent"][
            "semantic_declaration_identity"
        ],
        "semantic_role": {"kind": "project-intent"},
        "previous_declaration_id": "intent-v1",
        "current_declaration_id": "intent-v2",
        "declaration_id_changed": True,
    }
    assert changes["container-runtime"]["value_transition"] == {
        "before": {"value_state": "resolved", "value": "3.12"},
        "after": {"value_state": "resolved", "value": "3.13"},
    }
    assert changes["container-runtime"]["previous_declaration_id"] == "container-v1"
    assert changes["container-runtime"]["current_declaration_id"] == "container-v2"
    assert changes["container-runtime"]["declaration_id_changed"] is True
    assert "producer_transition" not in changes["container-runtime"]

    assert subject["coverage_transition"]["before"]["expected_declaration_ids"] == [
        "container-v1",
        "intent-v1",
    ]
    assert subject["coverage_transition"]["after"]["expected_declaration_ids"] == [
        "container-v2",
        "intent-v2",
    ]


def _assert_provider_binding_authority_separation(
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    before_by_role = _semantic_role_rows(before)
    after_by_role = _semantic_role_rows(after)
    assert (
        before_by_role["container-runtime"]["declaration_definition_identity"]
        != after_by_role["container-runtime"]["declaration_definition_identity"]
    )

    binding_delta = after["delta_from_previous"]["declarations"]["repository_evidence"][
        "bindings"
    ]
    assert binding_delta["changed"] == []
    assert binding_delta["preserved"] == []
    assert binding_delta["removed"] == sorted(
        row["binding_id"] for row in before_by_role.values()
    )
    assert binding_delta["added"] == sorted(
        row["binding_id"] for row in after_by_role.values()
    )

    before_bindings = _binding_rows(before)
    after_bindings = _binding_rows(after)
    assert (
        before_bindings[before_by_role["container-runtime"]["binding_id"]]["evidence"][
            0
        ]["path"]
        == "Dockerfile"
    )
    assert (
        after_bindings[after_by_role["container-runtime"]["binding_id"]]["evidence"][0][
            "path"
        ]
        == "deploy/runtime.meta"
    )


def test_discovery_preserves_semantic_roles_across_provider_request_churn(
    tmp_path: Path,
) -> None:
    before, after = _provider_role_churn_packets(tmp_path)
    _assert_provider_role_semantics(before, after)
    _assert_provider_binding_authority_separation(before, after)


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


def test_discovery_namespaces_equal_opaque_subjects_by_provider(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("value: same\n", encoding="utf-8")
    (repo / "b.txt").write_text("value: same\n", encoding="utf-8")
    providers = [
        _FixedSubjectProvider("provider-a", "a.txt"),
        _FixedSubjectProvider("provider-b", "b.txt"),
    ]

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.discover_repository_declarations(providers)

    groups = packet["declarations"]["groups"]
    assert [row["semantic_namespace"] for row in groups] == [
        "provider-a",
        "provider-b",
    ]
    assert groups[0]["concept"] == groups[1]["concept"]
    assert groups[0]["scope"] == groups[1]["scope"]
    assert (
        groups[0]["semantic_subject_identity"] != groups[1]["semantic_subject_identity"]
    )


def test_discovery_rejects_provider_semantic_namespace_spoofing(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("value: same\n", encoding="utf-8")
    provider = _FixedSubjectProvider(
        "provider-a",
        "value.txt",
        override_namespace=True,
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="must not override semantic_namespace",
        ):
            codemap.discover_repository_declarations([provider])


def _ownership_group(packet: dict[str, object]) -> dict[str, object]:
    return packet["declarations"]["groups"][0]


def _ownership_declaration(packet: dict[str, object]) -> dict[str, object]:
    return _ownership_group(packet)["declarations"][0]


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

    provider_a = _NamespacedOwnershipProvider("provider-a")
    provider_b_v1 = _NamespacedOwnershipProvider("provider-b")
    provider_b_v2 = _NamespacedOwnershipProvider(
        "provider-b",
        provenance_version="2",
    )
    provider_b_prod = _NamespacedOwnershipProvider(
        "provider-b",
        semantic_scope="production",
        provenance_version="2",
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        provider_a_packet = codemap.discover_repository_declarations([provider_a])
        provider_b_packet = codemap.discover_repository_declarations(
            [provider_b_v1],
            previous_observation=provider_a_packet,
        )
        provider_b_version_packet = codemap.discover_repository_declarations(
            [provider_b_v2],
            previous_observation=provider_b_packet,
        )
        provider_b_scope_packet = codemap.discover_repository_declarations(
            [provider_b_prod],
            previous_observation=provider_b_version_packet,
        )

    return (
        provider_a_packet,
        provider_b_packet,
        provider_b_version_packet,
        provider_b_scope_packet,
    )


def _assert_cross_provider_namespace_isolation(
    provider_a: dict[str, object],
    provider_b: dict[str, object],
) -> None:
    group_a = _ownership_group(provider_a)
    group_b = _ownership_group(provider_b)
    declaration_a = _ownership_declaration(provider_a)
    declaration_b = _ownership_declaration(provider_b)

    assert group_a["concept"] == group_b["concept"]
    assert group_a["scope"] == group_b["scope"]
    assert declaration_a["semantic_role"] == declaration_b["semantic_role"]
    assert declaration_a["value"] == declaration_b["value"] == "team-a"
    assert declaration_a["binding_id"] == declaration_b["binding_id"]
    assert group_a["semantic_namespace"] == "provider-a"
    assert group_b["semantic_namespace"] == "provider-b"
    assert (
        group_a["semantic_subject_identity"]
        != group_b["semantic_subject_identity"]
    )
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
    subjects = delta["declarations"]["semantic_subjects"]
    assert subjects["added"] == [group_b["semantic_subject_identity"]]
    assert subjects["removed"] == [group_a["semantic_subject_identity"]]
    assert subjects["ambiguous"] == []
    assert subjects["changed"] == []

    changed_group = delta["declarations"]["changed_groups"][0]
    assert changed_group["group_id"] == "ownership-request"
    assert changed_group["semantic_subject_changed"] is True
    assert changed_group["value_changed_declaration_ids"] == []
    assert changed_group["definition_changed_declaration_ids"] == ["owner"]

    bindings = delta["declarations"]["repository_evidence"]["bindings"]
    assert bindings["changed"] == []
    assert bindings["added"] == []
    assert bindings["removed"] == []
    assert bindings["preserved"] == [declaration_b["binding_id"]]


def _assert_provider_version_is_not_semantic_identity(
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    before_group = _ownership_group(before)
    after_group = _ownership_group(after)
    before_declaration = _ownership_declaration(before)
    after_declaration = _ownership_declaration(after)

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
    assert before["declarations"]["observation_identity"] == after["declarations"][
        "observation_identity"
    ]
    assert after["delta_from_previous"]["declarations"]["changed_groups"] == []
    assert after["delta_from_previous"]["declarations"]["semantic_subjects"] == {
        "added": [],
        "removed": [],
        "ambiguous": [],
        "changed": [],
    }


def _assert_scope_change_is_semantic_remove_add(
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    before_group = _ownership_group(before)
    after_group = _ownership_group(after)
    before_declaration = _ownership_declaration(before)
    after_declaration = _ownership_declaration(after)

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
    subjects = delta["declarations"]["semantic_subjects"]
    assert subjects["added"] == [after_group["semantic_subject_identity"]]
    assert subjects["removed"] == [before_group["semantic_subject_identity"]]
    assert subjects["ambiguous"] == []
    assert subjects["changed"] == []

    changed_group = delta["declarations"]["changed_groups"][0]
    assert changed_group["semantic_subject_changed"] is True
    assert changed_group["value_changed_declaration_ids"] == []
    assert changed_group["definition_changed_declaration_ids"] == ["owner"]

    bindings = delta["declarations"]["repository_evidence"]["bindings"]
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
        {
            "name": "optional-provider",
            "state": "not-detected",
            "inputs": [],
            "enumerations": [],
        }
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
        before["declarations"]["groups"][0]["semantic_subject_identity"]
        == after["declarations"]["groups"][0]["semantic_subject_identity"]
    )
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


def test_previous_discovery_from_foreign_repository_fails_before_providers_run(
    tmp_path: Path,
) -> None:
    first_repo = tmp_path / "first"
    second_repo = tmp_path / "second"
    first_repo.mkdir()
    second_repo.mkdir()
    (first_repo / "value.txt").write_text("value: same\n", encoding="utf-8")
    (second_repo / "value.txt").write_text("value: same\n", encoding="utf-8")
    provider = _SingleProvider("fixture-provider", "value.txt")

    with CodeMap(first_repo, state_dir=tmp_path / "first-state") as first:
        first.sync()
        previous = first.discover_repository_declarations([provider])

    with CodeMap(second_repo, state_dir=tmp_path / "second-state") as second:
        second.sync()
        with pytest.raises(
            ValueError,
            match="previous declaration discovery repository-mismatch",
        ):
            second.discover_repository_declarations(
                [provider],
                previous_observation=previous,
            )


def test_discovery_has_no_ambient_default_providers(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Chart.yaml").write_text("owner: team-a\n", encoding="utf-8")
    (repo / "catalog-info.yaml").write_text("owner: team-a\n", encoding="utf-8")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.discover_repository_declarations([])

    assert packet["providers"] == []
    assert packet["declarations"]["groups"] == []


def test_cross_provider_group_identity_collision_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("value: a\n", encoding="utf-8")
    (repo / "b.txt").write_text("value: a\n", encoding="utf-8")
    first = _PairProvider(
        name="first-provider",
        group_id="same-group",
        concept={"kind": "fixture", "identity": "value"},
        paths=("a.txt", "b.txt"),
    )
    second = _PairProvider(
        name="second-provider",
        group_id="same-group",
        concept={"kind": "fixture", "identity": "value"},
        paths=("a.txt", "b.txt"),
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="duplicate group_id"):
            codemap.discover_repository_declarations([first, second])


@dataclass
class _DuplicateGroupProvider(_SingleProvider):
    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        result = super().discover(context)
        return RepositoryDeclarationProviderResult(
            groups=(result.groups[0], result.groups[0]),
            provenance={"provider": self.name},
        )


def test_duplicate_group_identity_from_one_provider_fails_at_provider_boundary(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("value: stable\n", encoding="utf-8")
    provider = _DuplicateGroupProvider("duplicate-provider", "value.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="returned duplicate group_id values",
        ):
            codemap.discover_repository_declarations([provider])


class _UnreadEvidenceProvider:
    name = "unread-evidence"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": "unread",
                    "concept": {"kind": "fixture", "identity": "value"},
                    "scope": {},
                    "correspondence": {
                        "state": "declared",
                        "basis": {"provider": self.name},
                    },
                    "declarations": [
                        {
                            "declaration_id": "value",
                            "value_state": "resolved",
                            "value": "claimed-without-read",
                            "producer": {"provider": self.name},
                            "evidence": [
                                {
                                    "path": "value.txt",
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


@dataclass
class _MutatingProvider(_SingleProvider):
    mutation_root: Path | None = None

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        result = super().discover(context)
        if self.mutation_root is None:
            raise AssertionError("mutation root is required")
        (self.mutation_root / self.path).write_text(
            "value: changed\n",
            encoding="utf-8",
        )
        return result


def test_provider_cannot_bind_semantic_value_to_unread_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("value: actual\n", encoding="utf-8")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="evidence was not read through the provider context",
        ):
            codemap.discover_repository_declarations([_UnreadEvidenceProvider()])


def test_provider_input_change_after_parse_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("value: before\n", encoding="utf-8")
    provider = _MutatingProvider(
        "mutating-provider",
        "value.txt",
        mutation_root=repo,
    )

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="input changed during discovery",
        ):
            codemap.discover_repository_declarations([provider])


class _ManyInputsProvider:
    name = "many-inputs"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        for index in range(257):
            context.exists(f"input-{index}.txt")
        return False

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        raise AssertionError("discovery must not run")


def test_provider_repository_input_reads_are_bounded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="inputs exceed 256 paths",
        ):
            codemap.discover_repository_declarations([_ManyInputsProvider()])


def test_provider_context_cannot_read_pruned_repository_scope(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    hidden = repo / "node_modules" / "pkg"
    hidden.mkdir(parents=True)
    (hidden / "metadata.txt").write_text("value: hidden\n", encoding="utf-8")
    provider = _SingleProvider("pruned-provider", "node_modules/pkg/metadata.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="pruned-provider discovery failed",
        ) as exc_info:
            codemap.discover_repository_declarations([provider])

    assert "cannot read current repository bytes" in str(exc_info.value)
    assert "unsupported" in str(exc_info.value)


@dataclass
class _HelperInputProvider(_SingleProvider):
    helper_path: str = "helper.txt"

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        context.read_text(self.helper_path)
        return super().discover(context)


def test_helper_input_delta_does_not_masquerade_as_declaration_delta(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("value: stable\n", encoding="utf-8")
    (repo / "helper.txt").write_text("mode: first\n", encoding="utf-8")
    provider = _HelperInputProvider("helper-provider", "value.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.discover_repository_declarations([provider])
        (repo / "helper.txt").write_text("mode: second\n", encoding="utf-8")
        codemap.sync(["helper.txt"])
        after = codemap.discover_repository_declarations(
            [provider],
            previous_observation=before,
        )

    delta = after["delta_from_previous"]
    assert delta["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["helper-provider"],
    }
    assert delta["declarations"]["changed_groups"] == []
    assert (
        before["declarations"]["groups"][0]["group_observation_identity"]
        == after["declarations"]["groups"][0]["group_observation_identity"]
    )
    assert (
        before["declarations"]["observation_identity"]
        != after["declarations"]["observation_identity"]
    )


@dataclass
class _EnumeratingHelperProvider(_SingleProvider):
    enumeration_prefix: str = "helpers"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        assert not hasattr(context, "workspace")
        context.paths(self.enumeration_prefix)
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        context.paths(self.enumeration_prefix)
        return super().discover(context)


def test_provider_path_enumeration_is_bounded_tracked_and_has_no_raw_workspace(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    helpers = repo / "helpers"
    helpers.mkdir()
    (helpers / "a.meta").write_text("helper: one\n", encoding="utf-8")
    (helpers / "b.meta").write_text("helper: two\n", encoding="utf-8")
    (repo / "value.txt").write_text("value: stable\n", encoding="utf-8")
    provider = _EnumeratingHelperProvider("enumerating-provider", "value.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.discover_repository_declarations([provider])

    provider_row = packet["providers"][0]
    assert provider_row["enumerations"] == [
        {
            "prefix": "helpers",
            "paths": ["helpers/a.meta", "helpers/b.meta"],
        }
    ]
    assert packet["bounds"]["max_path_enumerations_per_provider"] == 32
    assert packet["bounds"]["max_enumerated_paths_per_provider"] == 256


def test_provider_path_enumeration_delta_is_separate_from_declaration_delta(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    helpers = repo / "helpers"
    helpers.mkdir()
    (helpers / "a.meta").write_text("helper: one\n", encoding="utf-8")
    (repo / "value.txt").write_text("value: stable\n", encoding="utf-8")
    provider = _EnumeratingHelperProvider("enumerating-provider", "value.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.discover_repository_declarations([provider])
        (helpers / "b.meta").write_text("helper: two\n", encoding="utf-8")
        codemap.sync(["helpers/b.meta"])
        after = codemap.discover_repository_declarations(
            [provider],
            previous_observation=before,
        )

    delta = after["delta_from_previous"]
    assert delta["providers"] == {
        "added": [],
        "removed": [],
        "changed": ["enumerating-provider"],
    }
    assert delta["declarations"]["changed_groups"] == []
    assert (
        before["providers"][0]["enumerations"] != after["providers"][0]["enumerations"]
    )


class _TooBroadEnumerationProvider:
    name = "too-broad-enumeration"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        context.paths("many")
        return False

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        raise AssertionError("discovery must not run")


def test_provider_path_enumeration_fails_closed_above_bound(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    many = repo / "many"
    many.mkdir(parents=True)
    for index in range(257):
        (many / f"{index:03}.txt").write_text("value\n", encoding="utf-8")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="path enumeration exceeds 256 paths",
        ):
            codemap.discover_repository_declarations([_TooBroadEnumerationProvider()])


class _RootEnumerationProvider:
    name = "root-enumeration"

    def __init__(self) -> None:
        self.paths: tuple[str, ...] = ()

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        self.paths = context.paths()
        return False

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        raise AssertionError("discovery must not run")


def test_provider_path_enumeration_respects_pruned_repository_scope(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "visible.meta").write_text("value\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=value\n", encoding="utf-8")
    hidden = repo / "node_modules" / "pkg"
    hidden.mkdir(parents=True)
    (hidden / "hidden.txt").write_text("hidden\n", encoding="utf-8")
    provider = _RootEnumerationProvider()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.discover_repository_declarations([provider])

    assert provider.paths == ("visible.meta",)
    assert packet["providers"][0]["enumerations"] == [
        {"prefix": "", "paths": ["visible.meta"]}
    ]


class _UnstableEnumerationProvider:
    name = "unstable-enumeration"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        context.paths()
        return False

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        raise AssertionError("discovery must not run")


def test_provider_path_enumeration_requires_deterministic_repository_order(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "z.meta").write_text("z\n", encoding="utf-8")
    (repo / "a.meta").write_text("a\n", encoding="utf-8")
    provider = _UnstableEnumerationProvider()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        original = codemap._declaration_provider_paths
        codemap._declaration_provider_paths = lambda prefix: tuple(
            reversed(original(prefix))
        )
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="deterministically ordered",
        ):
            codemap.discover_repository_declarations([provider])


class _OversizedGroupProvider:
    name = "oversized-groups"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        group = {
            "group_id": "placeholder",
            "concept": {"kind": "fixture"},
            "scope": {},
            "correspondence": {"state": "declared", "basis": {"provider": self.name}},
            "declarations": [],
            "coverage": {
                "state": "unknown",
                "truncation": "unknown",
                "expected_declaration_ids": [],
                "scope": {},
                "provenance": {"provider": self.name},
            },
        }
        return RepositoryDeclarationProviderResult(
            groups=tuple(
                {**group, "group_id": f"group-{index}"} for index in range(129)
            ),
            provenance={"provider": self.name},
        )


def test_single_provider_output_is_bounded_before_aggregate_qualification(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="groups exceed 128 entries",
        ):
            codemap.discover_repository_declarations([_OversizedGroupProvider()])


class _OversizedDeclarationProvider:
    name = "oversized-declarations"

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return True

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        declarations = tuple(
            {
                "declaration_id": f"value-{index}",
                "value_state": "unresolved",
                "producer": {"provider": self.name},
                "evidence": [{"path": "value.txt", "start_line": 1, "end_line": 1}],
            }
            for index in range(257)
        )
        context.read_text("value.txt")
        return RepositoryDeclarationProviderResult(
            groups=(
                {
                    "group_id": "many-values",
                    "concept": {"kind": "fixture"},
                    "scope": {},
                    "correspondence": {
                        "state": "unresolved",
                        "basis": {"provider": self.name},
                    },
                    "declarations": declarations,
                    "coverage": {
                        "state": "unknown",
                        "truncation": "unknown",
                        "expected_declaration_ids": [],
                        "scope": {},
                        "provenance": {"provider": self.name},
                    },
                },
            ),
            provenance={"provider": self.name},
        )


def test_single_provider_declarations_are_bounded_before_qualification(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("value\n", encoding="utf-8")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="declarations exceed 256 entries",
        ):
            codemap.discover_repository_declarations([_OversizedDeclarationProvider()])


def test_provider_evidence_validation_rejects_duplicate_input_index_rows(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("value: stable\n", encoding="utf-8")
    provider = _SingleProvider("fixture-provider", "value.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.discover_repository_declarations([provider])
        provider_row = packet["providers"][0]
        provider_row["inputs"].append(dict(provider_row["inputs"][0]))
        try:
            from hashmarks.codemap.repository_declaration_discovery import (
                _validate_provider_evidence_revisions,
            )

            _validate_provider_evidence_revisions(
                packet["providers"], packet["declarations"]
            )
        except ValueError as exc:
            assert "provider input paths are duplicated" in str(exc)
        else:
            raise AssertionError("duplicate provider input index must fail closed")


def test_provider_revalidation_rejects_duplicate_input_rows_before_reread(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("value: stable\n", encoding="utf-8")
    provider = _SingleProvider("fixture-provider", "value.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.discover_repository_declarations([provider])
        observation = packet["providers"][0]
        observation["inputs"].append(dict(observation["inputs"][0]))
        from hashmarks.codemap.repository_declaration_provider import (
            validate_repository_declaration_provider_inputs,
        )

        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="input paths are duplicated or malformed",
        ):
            validate_repository_declaration_provider_inputs(
                codemap._declaration_provider_member_read,
                codemap._declaration_provider_paths,
                packet["providers"],
            )


def test_provider_revalidation_rejects_duplicate_enumeration_prefixes(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    helpers = repo / "helpers"
    helpers.mkdir()
    (helpers / "a.meta").write_text("a\n", encoding="utf-8")
    (repo / "value.txt").write_text("value: stable\n", encoding="utf-8")
    provider = _EnumeratingHelperProvider("enumerating-provider", "value.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        packet = codemap.discover_repository_declarations([provider])
        observation = packet["providers"][0]
        observation["enumerations"].append(dict(observation["enumerations"][0]))
        from hashmarks.codemap.repository_declaration_provider import (
            validate_repository_declaration_provider_inputs,
        )

        with pytest.raises(
            RepositoryDeclarationProviderError,
            match="enumeration prefixes are duplicated",
        ):
            validate_repository_declaration_provider_inputs(
                codemap._declaration_provider_member_read,
                codemap._declaration_provider_paths,
                packet["providers"],
            )


def test_previous_discovery_rejects_authenticated_nested_repository_divergence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("value: same\n", encoding="utf-8")
    provider = _SingleProvider("fixture-provider", "value.txt")

    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        previous = codemap.discover_repository_declarations([provider])
        previous["declarations"]["repository"] = dict(
            previous["declarations"]["repository"]
        )
        previous["declarations"]["repository"]["repository_identity"] = "sha256:foreign"
        previous["declarations"]["observation_identity"] = (
            "sha256:"
            + codemap._packet_digest(
                "hashmarks.repository-declarations.v1",
                {
                    key: value
                    for key, value in previous["declarations"].items()
                    if key not in {"observation_identity", "delta_from_previous"}
                },
            )
        )
        previous["observation_identity"] = codemap._declaration_discovery_identity(
            previous
        )

        with pytest.raises(
            ValueError,
            match="nested repository-mismatch",
        ):
            codemap.discover_repository_declarations(
                [provider],
                previous_observation=previous,
            )
