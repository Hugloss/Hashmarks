from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from hashmarks.paths import normalize_relative_path

from .repository_declaration_contract import encoded_json_bytes, json_value

MAX_DECLARATION_PROVIDERS = 32
MAX_PROVIDER_INPUTS = 256
MAX_PROVIDER_ENUMERATIONS = 32
MAX_PROVIDER_ENUMERATED_PATHS = 256
MAX_PROVIDER_NAME_CHARS = 256
MAX_PROVIDER_PROVENANCE_BYTES = 4_096
MAX_PROVIDER_WARNINGS = 32
MAX_PROVIDER_WARNING_CHARS = 1_024
MAX_DISCOVERY_PACKET_BYTES = 1_572_864

_MemberReader = Callable[
    [str, bool],
    tuple[dict[str, object], bytes | None],
]
_PathEnumerator = Callable[[str], tuple[str, ...]]


class RepositoryDeclarationProviderError(ValueError):
    """A declaration provider violated the discovery contract."""


@dataclass(frozen=True, slots=True)
class RepositoryDeclarationProviderResult:
    """Producer-owned declaration discovery result."""

    groups: tuple[Mapping[str, object], ...]
    provenance: Mapping[str, object]
    warnings: tuple[str, ...] = ()


class RepositoryDeclarationProviderContext(Protocol):
    """Read-only, revision-bound repository input surface for providers."""

    def paths(self, prefix: str = "") -> tuple[str, ...]:
        """Return bounded admitted indexed paths under a repository prefix."""
        ...

    def exists(self, path: str) -> bool:
        """Return whether an admitted repository member is currently present."""
        ...

    def read_bytes(self, path: str) -> bytes:
        """Read stable admitted repository bytes and bind their revision."""
        ...

    def read_text(self, path: str, *, encoding: str = "utf-8") -> str:
        """Read stable admitted repository text and bind its revision."""
        ...


class _RepositoryDeclarationProviderContext:
    """Concrete Hashmarks-owned provider input tracker."""

    def __init__(
        self,
        read_member: _MemberReader,
        enumerate_paths: _PathEnumerator,
    ) -> None:
        self._read_member = read_member
        self._enumerate_paths = enumerate_paths
        self._inputs: dict[str, dict[str, object]] = {}
        self._enumerations: dict[str, tuple[str, ...]] = {}

    def paths(self, prefix: str = "") -> tuple[str, ...]:
        try:
            normalized = normalize_relative_path(prefix, allow_root=True)
        except ValueError as exc:
            raise RepositoryDeclarationProviderError(
                "declaration provider path-enumeration prefix is invalid"
            ) from exc
        if normalized not in self._enumerations and (
            len(self._enumerations) >= MAX_PROVIDER_ENUMERATIONS
        ):
            raise RepositoryDeclarationProviderError(
                "declaration provider path enumerations exceed "
                f"{MAX_PROVIDER_ENUMERATIONS} queries"
            )
        paths = self._enumerate_paths(normalized)
        if len(paths) > MAX_PROVIDER_ENUMERATED_PATHS:
            raise RepositoryDeclarationProviderError(
                "declaration provider path enumeration exceeds "
                f"{MAX_PROVIDER_ENUMERATED_PATHS} paths for prefix {normalized!r}"
            )
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise RepositoryDeclarationProviderError(
                "declaration provider path enumeration must be unique and "
                f"deterministically ordered for prefix {normalized!r}"
            )
        previous = self._enumerations.get(normalized)
        if previous is not None and previous != paths:
            raise RepositoryDeclarationProviderError(
                "declaration provider path enumeration changed while reading: "
                f"{normalized!r}"
            )
        total_paths = set(paths)
        for observed in self._enumerations.values():
            total_paths.update(observed)
        if len(total_paths) > MAX_PROVIDER_ENUMERATED_PATHS:
            raise RepositoryDeclarationProviderError(
                "declaration provider enumerated path set exceeds "
                f"{MAX_PROVIDER_ENUMERATED_PATHS} distinct paths"
            )
        self._enumerations[normalized] = paths
        return paths

    @staticmethod
    def _signature(observation: Mapping[str, object]) -> dict[str, object]:
        keys = (
            "path",
            "state",
            "member_revision",
            "evidence_visibility",
            "index_state",
            "reason",
        )
        return {
            key: observation[key] for key in keys if observation.get(key) is not None
        }

    def _record(
        self,
        path: str,
        observation: Mapping[str, object],
        *,
        content: bool,
    ) -> None:
        signature = self._signature(observation)
        previous = self._inputs.get(path)
        if previous is not None:
            previous_signature = {
                key: value
                for key, value in previous.items()
                if key != "observation_kind"
            }
            if previous_signature != signature:
                raise RepositoryDeclarationProviderError(
                    f"declaration provider input changed while reading: {path}"
                )
            content = content or previous.get("observation_kind") == "content"
        if path not in self._inputs and len(self._inputs) >= MAX_PROVIDER_INPUTS:
            raise RepositoryDeclarationProviderError(
                f"declaration provider inputs exceed {MAX_PROVIDER_INPUTS} paths"
            )
        self._inputs[path] = {
            **signature,
            "observation_kind": "content" if content else "existence",
        }

    def exists(self, path: str) -> bool:
        observation, _raw = self._read_member(path, False)
        normalized = str(observation.get("path") or path)
        self._record(normalized, observation, content=False)
        state = observation.get("state")
        if state == "known-present":
            return True
        if state == "known-absent":
            return False
        raise RepositoryDeclarationProviderError(
            f"declaration provider cannot qualify existence for {normalized}: {state}"
        )

    def read_bytes(self, path: str) -> bytes:
        observation, raw = self._read_member(path, True)
        normalized = str(observation.get("path") or path)
        self._record(normalized, observation, content=True)
        if observation.get("state") != "known-present" or raw is None:
            raise RepositoryDeclarationProviderError(
                "declaration provider cannot read current repository bytes for "
                f"{normalized}: {observation.get('state')}"
            )
        return raw

    def read_text(self, path: str, *, encoding: str = "utf-8") -> str:
        raw = self.read_bytes(path)
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError as exc:
            raise RepositoryDeclarationProviderError(
                f"declaration provider cannot decode {path} as {encoding}"
            ) from exc

    def input_observations(self) -> list[dict[str, object]]:
        return [self._inputs[path] for path in sorted(self._inputs)]

    def enumeration_observations(self) -> list[dict[str, object]]:
        return [
            {"prefix": prefix, "paths": list(self._enumerations[prefix])}
            for prefix in sorted(self._enumerations)
        ]

    def content_paths(self) -> frozenset[str]:
        return frozenset(
            path
            for path, observation in self._inputs.items()
            if observation.get("observation_kind") == "content"
        )


class RepositoryDeclarationProvider(Protocol):
    """Explicit read-only producer for repository declaration claims."""

    name: str

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        """Return whether this provider applies to the workspace."""
        ...

    def discover(
        self,
        context: RepositoryDeclarationProviderContext,
    ) -> RepositoryDeclarationProviderResult:
        """Return producer-normalized declaration groups for the workspace."""
        ...


def _provider_name(provider: RepositoryDeclarationProvider) -> str:
    name = getattr(provider, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise RepositoryDeclarationProviderError(
            "declaration provider name must be a non-empty string"
        )
    normalized = name.strip()
    if len(normalized) > MAX_PROVIDER_NAME_CHARS:
        raise RepositoryDeclarationProviderError(
            f"declaration provider name exceeds {MAX_PROVIDER_NAME_CHARS} characters"
        )
    return normalized


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


def _provider_evidence_path(item: object) -> str | None:
    if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
        return None
    try:
        return normalize_relative_path(str(item["path"]), allow_root=False)
    except ValueError as exc:
        raise RepositoryDeclarationProviderError(
            "declaration provider evidence path is invalid"
        ) from exc


def _declaration_evidence_paths(declaration: object) -> set[str]:
    if not isinstance(declaration, Mapping):
        return set()
    evidence = declaration.get("evidence")
    if not isinstance(evidence, list):
        return set()
    return {
        path for item in evidence if (path := _provider_evidence_path(item)) is not None
    }


def _declared_evidence_paths(groups: Sequence[Mapping[str, object]]) -> set[str]:
    paths: set[str] = set()
    for group in groups:
        declarations = group.get("declarations")
        if not isinstance(declarations, list):
            continue
        for declaration in declarations:
            paths.update(_declaration_evidence_paths(declaration))
    return paths


def _provider_result(
    provider_name: str,
    result: object,
    context: _RepositoryDeclarationProviderContext,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if not isinstance(result, RepositoryDeclarationProviderResult):
        raise RepositoryDeclarationProviderError(
            f"declaration provider {provider_name} must return "
            "RepositoryDeclarationProviderResult"
        )
    groups = _provider_groups(result.groups, provider_name=provider_name)
    evidence_paths = _declared_evidence_paths(groups)
    unread = sorted(evidence_paths - set(context.content_paths()))
    if unread:
        raise RepositoryDeclarationProviderError(
            f"declaration provider {provider_name} evidence was not read through "
            f"the provider context: {', '.join(unread)}"
        )

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
    if len(set(group_ids)) != len(group_ids):
        raise RepositoryDeclarationProviderError(
            f"declaration provider {provider_name} returned duplicate group_id values"
        )
    return groups, {
        "name": provider_name,
        "state": "collected",
        "provenance": provenance,
        "warnings": warnings,
        "group_ids": sorted(group_ids),
        "inputs": context.input_observations(),
        "enumerations": context.enumeration_observations(),
    }


def _named_providers(
    providers: Sequence[RepositoryDeclarationProvider],
) -> list[tuple[str, RepositoryDeclarationProvider]]:
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
    return sorted(named, key=lambda item: item[0])


def _collect_provider(
    read_member: _MemberReader,
    enumerate_paths: _PathEnumerator,
    name: str,
    provider: RepositoryDeclarationProvider,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    context = _RepositoryDeclarationProviderContext(read_member, enumerate_paths)
    try:
        detected = provider.detect(context)
    except Exception as exc:
        raise RepositoryDeclarationProviderError(
            f"declaration provider {name} detection failed: {exc}"
        ) from exc
    if not isinstance(detected, bool):
        raise RepositoryDeclarationProviderError(
            f"declaration provider {name} detect() must return bool"
        )
    if not detected:
        return [], {
            "name": name,
            "state": "not-detected",
            "inputs": context.input_observations(),
            "enumerations": context.enumeration_observations(),
        }
    try:
        result = provider.discover(context)
    except Exception as exc:
        raise RepositoryDeclarationProviderError(
            f"declaration provider {name} discovery failed: {exc}"
        ) from exc
    return _provider_result(name, result, context)


def collect_repository_declaration_providers(
    read_member: _MemberReader,
    enumerate_paths: _PathEnumerator,
    providers: Sequence[RepositoryDeclarationProvider],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Run explicit providers deterministically and fail closed on provider errors."""
    groups: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    for name, provider in _named_providers(providers):
        provider_groups, observation = _collect_provider(
            read_member,
            enumerate_paths,
            name,
            provider,
        )
        groups.extend(provider_groups)
        observations.append(observation)
    return groups, observations


def _validate_provider_enumerations(
    enumerate_paths: _PathEnumerator,
    provider_name: str,
    raw: object,
) -> None:
    if not isinstance(raw, list):
        raise RepositoryDeclarationProviderError(
            f"declaration provider {provider_name} enumerations are malformed"
        )
    for previous in raw:
        if not isinstance(previous, Mapping):
            raise RepositoryDeclarationProviderError(
                f"declaration provider {provider_name} enumeration is malformed"
            )
        prefix = previous.get("prefix")
        paths = previous.get("paths")
        if (
            not isinstance(prefix, str)
            or not isinstance(paths, list)
            or any(not isinstance(path, str) for path in paths)
        ):
            raise RepositoryDeclarationProviderError(
                f"declaration provider {provider_name} enumeration is malformed"
            )
        current = list(enumerate_paths(prefix))
        if current != paths:
            raise RepositoryDeclarationProviderError(
                "declaration provider "
                f"{provider_name} path enumeration changed during discovery: {prefix!r}"
            )


def validate_repository_declaration_provider_inputs(
    read_member: _MemberReader,
    enumerate_paths: _PathEnumerator,
    provider_observations: Sequence[Mapping[str, object]],
) -> None:
    """Revalidate every provider input after declaration qualification."""
    for provider in provider_observations:
        name = str(provider.get("name") or "")
        inputs = provider.get("inputs")
        _validate_provider_enumerations(
            enumerate_paths,
            name,
            provider.get("enumerations"),
        )
        if not isinstance(inputs, list):
            raise RepositoryDeclarationProviderError(
                f"declaration provider {name} inputs are malformed"
            )
        for previous in inputs:
            if not isinstance(previous, Mapping):
                raise RepositoryDeclarationProviderError(
                    f"declaration provider {name} input observation is malformed"
                )
            path = previous.get("path")
            if not isinstance(path, str) or not path:
                raise RepositoryDeclarationProviderError(
                    f"declaration provider {name} input path is malformed"
                )
            observation_kind = previous.get("observation_kind")
            if observation_kind not in {"content", "existence"}:
                raise RepositoryDeclarationProviderError(
                    f"declaration provider {name} input kind is malformed"
                )
            current, _raw = read_member(path, observation_kind == "content")
            current_signature = _RepositoryDeclarationProviderContext._signature(
                current
            )
            current_signature["observation_kind"] = observation_kind
            if current_signature != dict(previous):
                raise RepositoryDeclarationProviderError(
                    f"declaration provider {name} input changed during discovery: {path}"
                )
