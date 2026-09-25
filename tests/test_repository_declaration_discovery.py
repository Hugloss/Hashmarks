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

