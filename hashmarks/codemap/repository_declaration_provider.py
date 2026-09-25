from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .repository_declaration_contract import encoded_json_bytes, json_value

MAX_DECLARATION_PROVIDERS = 32
MAX_PROVIDER_PROVENANCE_BYTES = 4_096
MAX_PROVIDER_WARNINGS = 32
MAX_PROVIDER_WARNING_CHARS = 1_024
MAX_DISCOVERY_PACKET_BYTES = 1_572_864


class RepositoryDeclarationProviderError(ValueError):
    """A declaration provider violated the discovery contract."""


@dataclass(frozen=True, slots=True)
class RepositoryDeclarationProviderResult:
    """Producer-owned declaration discovery result.

    Providers own parsing, semantic extraction, normalization, scope,
    correspondence, coverage, and their provenance. Hashmarks qualifies the
    returned claims against canonical repository evidence afterwards.
    """

    groups: tuple[Mapping[str, object], ...]
    provenance: Mapping[str, object]
    warnings: tuple[str, ...] = ()


class RepositoryDeclarationProvider(Protocol):
    """Explicit read-only producer for repository declaration claims."""

    name: str

    def detect(self, workspace: Path) -> bool:
        """Return whether this provider applies to the workspace."""

    def discover(self, workspace: Path) -> RepositoryDeclarationProviderResult:
        """Return producer-normalized declaration groups for the workspace."""


def _provider_name(provider: RepositoryDeclarationProvider) -> str:
    name = getattr(provider, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise RepositoryDeclarationProviderError(
            "declaration provider name must be a non-empty string"
        )
    return name.strip()


def _provider_provenance(
    value: Mapping[str, object],
    *,
    provider_name: str,
) -> dict[str, object]:
    normalized = json_value(
        value,
        name=f"declaration provider {provider_name} provenance",
    )
    if not isinstance(normalized, dict) or not normalized:
        raise RepositoryDeclarationProviderError(
            f"declaration provider {provider_name} provenance must be a non-empty object"
        )
    if (
        encoded_json_bytes(
            normalized,
            name=f"declaration provider {provider_name} provenance",
        )
        > MAX_PROVIDER_PROVENANCE_BYTES
    ):
        raise RepositoryDeclarationProviderError(
            f"declaration provider {provider_name} provenance exceeds "
            f"{MAX_PROVIDER_PROVENANCE_BYTES} encoded bytes"
        )
    return normalized


def _provider_warnings(
    warnings: Sequence[str],
    *,
    provider_name: str,
) -> list[str]:
    if len(warnings) > MAX_PROVIDER_WARNINGS:
        raise RepositoryDeclarationProviderError(
            f"declaration provider {provider_name} warnings exceed "
            f"{MAX_PROVIDER_WARNINGS} entries"
        )
    normalized: list[str] = []
    for warning in warnings:
        if not isinstance(warning, str) or not warning.strip():
            raise RepositoryDeclarationProviderError(
                f"declaration provider {provider_name} warnings must be non-empty strings"
            )
        clean = warning.strip()
        if len(clean) > MAX_PROVIDER_WARNING_CHARS:
            raise RepositoryDeclarationProviderError(
                f"declaration provider {provider_name} warning exceeds "
                f"{MAX_PROVIDER_WARNING_CHARS} characters"
            )
        normalized.append(clean)
    return normalized


def _provider_groups(
    groups: Sequence[Mapping[str, object]],
    *,
    provider_name: str,
) -> list[dict[str, object]]:
    normalized = json_value(
        list(groups),
        name=f"declaration provider {provider_name} groups",
    )
    if not isinstance(normalized, list) or any(
        not isinstance(group, dict) for group in normalized
    ):
        raise RepositoryDeclarationProviderError(
            f"declaration provider {provider_name} groups must be objects"
        )
    return [group for group in normalized if isinstance(group, dict)]


def _provider_result(
    provider_name: str,
    result: object,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if not isinstance(result, RepositoryDeclarationProviderResult):
        raise RepositoryDeclarationProviderError(
            f"declaration provider {provider_name} must return "
            "RepositoryDeclarationProviderResult"
        )
    groups = _provider_groups(result.groups, provider_name=provider_name)
    provenance = _provider_provenance(
        result.provenance,
        provider_name=provider_name,
    )
    warnings = _provider_warnings(
        result.warnings,
        provider_name=provider_name,
    )
    group_ids: list[str] = []
    for group in groups:
        group_id = group.get("group_id")
        if not isinstance(group_id, str) or not group_id.strip():
            raise RepositoryDeclarationProviderError(
                f"declaration provider {provider_name} returned a group "
                "without a non-empty group_id"
            )
        group_ids.append(group_id.strip())
    return groups, {
        "name": provider_name,
        "state": "collected",
        "provenance": provenance,
        "warnings": warnings,
        "group_ids": sorted(group_ids),
    }


def collect_repository_declaration_providers(
    workspace: Path,
    providers: Sequence[RepositoryDeclarationProvider],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Run explicit providers deterministically and fail closed on provider errors."""
    if not isinstance(providers, Sequence) or isinstance(providers, (str, bytes)):
        raise RepositoryDeclarationProviderError("providers must be a sequence")
    if len(providers) > MAX_DECLARATION_PROVIDERS:
        raise RepositoryDeclarationProviderError(
            f"providers exceeds {MAX_DECLARATION_PROVIDERS} entries"
        )

    named = [(_provider_name(provider), provider) for provider in providers]
    names = [name for name, _provider in named]
    if len(set(names)) != len(names):
        raise RepositoryDeclarationProviderError(
            "declaration provider names must be unique"
        )

    groups: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    for name, provider in sorted(named, key=lambda item: item[0]):
        try:
            detected = provider.detect(workspace)
        except Exception as exc:
            raise RepositoryDeclarationProviderError(
                f"declaration provider {name} detection failed: {exc}"
            ) from exc
        if not isinstance(detected, bool):
            raise RepositoryDeclarationProviderError(
                f"declaration provider {name} detect() must return bool"
            )
        if not detected:
            observations.append({"name": name, "state": "not-detected"})
            continue
        try:
            result = provider.discover(workspace)
        except Exception as exc:
            raise RepositoryDeclarationProviderError(
                f"declaration provider {name} discovery failed: {exc}"
            ) from exc
        provider_groups, observation = _provider_result(name, result)
        groups.extend(provider_groups)
        observations.append(observation)

    return groups, observations
