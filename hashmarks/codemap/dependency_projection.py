"""Bounded dependency projections and read-only retained evidence qualification."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hashmarks.file_store import UnstableFileError
from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path

from .dependency_resolution_evidence import _identity
from .dependency_resolution_query import _package_selector, dependency_package_query

if TYPE_CHECKING:
    from .repository_dependencies import RepositoryDependencies

_MAX_PACKAGES = 64
_MAX_PATHS = 64
_MAX_RESULTS = 256
_MAX_NODE_IDS = 64
_MAX_ENVELOPE_BYTES = 4_194_304
_MAX_SOURCE_BYTES = 1_048_576
_MEMBER_REVISION = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset(
    {
        "schema",
        "request",
        "observation",
        "derivation",
        "assessment",
        "packages",
        "source_scope",
        "consumer_evidence",
        "repository",
        "completeness",
        "truncation",
        "negative_evidence",
        "limits",
        "authority",
        "producer_authority",
        "execution_authority",
        "result_authority",
        "certification_authority",
        "storage",
        "projection_identity",
    }
)


def _encoded(packet: object) -> bytes:
    try:
        encoded = json.dumps(
            packet,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("dependency projection must be JSON-compatible") from exc
    if len(encoded) > _MAX_ENVELOPE_BYTES:
        raise ValueError("dependency projection exceeds the 4 MiB envelope limit")
    return encoded


@dataclass(frozen=True)
class _Request:
    packages: list[dict[str, str]]
    source_paths: list[str]
    limit: int
    max_depth: int

    def packet(self) -> dict[str, object]:
        return {
            "packages": self.packages,
            "source_paths": self.source_paths,
            "limit": self.limit,
            "max_depth": self.max_depth,
        }


def _request(
    observation: Mapping[str, object],
    packages: object,
    source_paths: object,
    limit: object,
    max_depth: object,
) -> _Request:
    if type(limit) is not int or not 1 <= limit <= _MAX_RESULTS:
        raise ValueError("dependency projection limit must be between 1 and 256")
    if type(max_depth) is not int or not 1 <= max_depth <= 12:
        raise ValueError("dependency projection max_depth must be between 1 and 12")
    if (
        not isinstance(packages, Sequence)
        or isinstance(packages, (str, bytes, bytearray))
        or not 1 <= len(packages) <= _MAX_PACKAGES
    ):
        raise ValueError("dependency projection requires between 1 and 64 packages")
    selectors: dict[bytes, dict[str, str]] = {}
    for value in packages:
        if not isinstance(value, Mapping):
            raise ValueError("dependency package selector must be an object")
        selector = _package_selector(observation, value)
        selectors[_encoded(selector)] = selector
    return _Request(
        [selectors[key] for key in sorted(selectors)],
        _source_paths(source_paths),
        limit,
        max_depth,
    )


def _source_paths(source_paths: object) -> list[str]:
    if (
        not isinstance(source_paths, Sequence)
        or isinstance(source_paths, (str, bytes, bytearray))
        or len(source_paths) > _MAX_PATHS
    ):
        raise ValueError(
            "dependency projection source_paths must contain at most 64 paths"
        )
    paths = set()
    for path in source_paths:
        if not isinstance(path, str) or not path or len(path) > 4096:
            raise ValueError("dependency projection source path must be bounded text")
        paths.add(normalize_relative_path(path, allow_root=False))
    return sorted(paths)


def _retained_members(value: object, paths: Sequence[str]) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) != len(paths):
        raise ValueError("retained dependency source members must match request paths")
    members: list[dict[str, object]] = []
    for path, member in zip(paths, value, strict=True):
        if not isinstance(member, Mapping) or member.get("path") != path:
            raise ValueError("retained dependency source member path mismatch")
        state = member.get("state")
        if not isinstance(state, str) or state not in {
            "known-present",
            "known-absent",
            "unknown",
            "unsupported",
        }:
            raise ValueError("invalid retained dependency source member state")
        revision = member.get("member_revision")
        if revision is not None and (
            not isinstance(revision, str)
            or _MEMBER_REVISION.fullmatch(revision) is None
        ):
            raise ValueError("invalid retained dependency source member revision")
        if state == "known-present" and (
            revision is None or member.get("evidence_visibility") != "source"
        ):
            raise ValueError("retained source member requires native source revision")
        if state == "known-absent" and revision is not None:
            raise ValueError("absent retained source member cannot carry a revision")
        members.append(dict(member))
    return members


def _correspondence(before: Mapping[str, object], after: Mapping[str, object]) -> str:
    known = {"known-present", "known-absent"}
    if before["state"] not in known or after["state"] not in known:
        return "unknown"
    return (
        "matched"
        if (before["state"], before.get("member_revision"))
        == (after["state"], after.get("member_revision"))
        else "mismatch"
    )


def _source_scope(
    retained: list[dict[str, object]], observations: list[dict[str, object]]
) -> dict[str, object]:
    correspondence = [
        {
            "path": before["path"],
            "state": _correspondence(
                before, cast("Mapping[str, object]", after["member"])
            ),
        }
        for before, after in zip(retained, observations, strict=True)
    ]
    matched = bool(correspondence) and all(
        row["state"] == "matched" for row in correspondence
    )
    available = bool(observations) and all(
        row["availability"] == "observed" for row in observations
    )
    return {
        "retained_members": retained,
        "observations": observations,
        "correspondence": correspondence,
        "freshness": "stale"
        if any(row["state"] == "mismatch" for row in correspondence)
        else "current"
        if matched
        else "unknown",
        "completeness": "complete" if matched and available else "incomplete",
        "negative_evidence": "not-admissible",
    }


def _inputs_current(assessment: Mapping[str, object]) -> bool:
    scope = cast("Mapping[str, object]", assessment["source_scope"])
    return (
        scope["freshness"] == "current"
        and scope["source_equivalence"] == "proven"
        and scope["availability"] == "available"
    )


def _packages(
    observation: Mapping[str, object],
    request: _Request,
    assessment: Mapping[str, object],
) -> list[dict[str, object]]:
    current = _inputs_current(assessment)
    scope = cast("Mapping[str, object]", assessment["source_scope"])
    packages = [
        dependency_package_query(observation, selector, max_results=request.limit)
        for selector in request.packages
    ]
    for package in packages:
        package["current_inventory"] = [
            {
                "context": row["context"],
                "membership": row["membership"] if current else "unknown",
                "negative_evidence": row["negative_evidence"]
                if current
                else "not-admissible",
                "freshness": scope["freshness"],
                "source_equivalence": scope["source_equivalence"],
                "availability": scope["availability"],
                "scope": "declared-resolved-inventory-with-current-input-correspondence",
            }
            for row in cast("Sequence[Mapping[str, object]]", package["contexts"])
        ]
    return packages


class DependencyProjectionMixin:
    """Project existing dependency and Source owners without rebinding old claims."""

    @operation_response("dependency_projection")
    def projection(
        self,
        observation: Mapping[str, object],
        *,
        packages: Sequence[Mapping[str, object]],
        source_paths: Sequence[str] = (),
        limit: int = 100,
        max_depth: int = 8,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        self._require_qualified_dependency_observation_v3(observation)
        retained = cast("dict[str, object]", json.loads(_encoded(observation)))
        request = _request(retained, packages, source_paths, limit, max_depth)
        return self._dependency_projection(retained, request, retained_members=None)

    @operation_response("dependency_projection")
    def requalify(self, projection: Mapping[str, object]) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        # Validate all caller claims before consulting current repository source.
        packet = json.loads(_encoded(projection))
        if (
            not isinstance(packet, dict)
            or set(packet) != _FIELDS
            or packet.get("schema") != operation_schema("dependency_projection")
        ):
            raise ValueError("invalid retained dependency projection envelope")
        identity = packet.pop("projection_identity")
        if identity != _identity(operation_schema("dependency_projection"), packet):
            raise ValueError("retained dependency projection identity mismatch")
        observation = packet["observation"]
        self._require_qualified_dependency_observation_v3(observation)
        requested = packet["request"]
        if not isinstance(requested, Mapping) or set(requested) != {
            "packages",
            "source_paths",
            "limit",
            "max_depth",
        }:
            raise ValueError("invalid retained dependency projection request")
        request = _request(observation, **requested)
        if request.packet() != requested:
            raise ValueError("retained dependency projection request is not canonical")
        scope = packet["source_scope"]
        if not isinstance(scope, Mapping):
            raise ValueError("invalid retained dependency projection source scope")
        retained = _retained_members(
            scope.get("retained_members"), request.source_paths
        )
        return self._dependency_projection(
            observation, request, retained_members=retained
        )

    def _dependency_projection_binding(self) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        return {
            "repository_identity": self.reads.repository_identity(),
            "codemap_generation": int(self.store.generation()),
        }

    def _dependency_projection_sources(
        self, paths: Sequence[str]
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        return [
            self.source.observe(path, max_bytes=_MAX_SOURCE_BYTES) for path in paths
        ]

    def _dependency_projection_consumers(
        self,
        observation: Mapping[str, object],
        request: _Request,
        packages: Sequence[Mapping[str, object]],
        *,
        assessment: Mapping[str, object],
        source_scope: Mapping[str, object],
        binding_current: bool,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        nodes = sorted(
            {
                str(cast("Mapping[str, object]", row["selection"])["node_id"])
                for package in packages
                for row in cast("Sequence[Mapping[str, object]]", package["matches"])
            }
        )
        packet: dict[str, object] = {
            "state": "unavailable",
            "reason": None,
            "observation": None,
            "node_ids": nodes[:_MAX_NODE_IDS],
            "omitted_node_count": max(0, len(nodes) - _MAX_NODE_IDS),
            "selection_scope": "returned-package-matches",
            "context_scope": "all-declared-contexts-for-selected-nodes",
        }
        if not request.source_paths:
            packet.update(state="not-requested", reason="no-source-paths")
        elif not nodes:
            packet.update(
                state="no-matching-selection", reason="no-returned-package-matches"
            )
        elif not binding_current:
            packet["reason"] = "retained-repository-binding-stale"
        elif not _inputs_current(assessment):
            packet["reason"] = "dependency-input-correspondence-not-proven"
        elif (
            source_scope["freshness"] != "current"
            or source_scope["completeness"] != "complete"
        ):
            packet["reason"] = "retained-source-correspondence-not-proven"
        elif (index_reason := self._dependency_projection_index_reason()) is not None:
            packet["reason"] = index_reason
        else:
            packet.update(
                state="observed",
                observation=self.consumers(
                    observation,
                    source_paths=request.source_paths,
                    node_ids=nodes[:_MAX_NODE_IDS],
                    limit=request.limit,
                    max_depth=request.max_depth,
                ),
            )
        return packet

    def _dependency_projection_index_reason(self) -> str | None:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        if (
            self.store.meta("sync.build_state") != "COMPLETE"
            or not self.store.has_files()
        ):
            return "codemap-not-ready"
        if self.source.index._analysis_scope_conformance().identity != self.store.meta(
            "analysis_scope_conformance_identity", ""
        ):
            return "codemap-scope-stale"
        return None

    def _dependency_projection(
        self,
        observation: dict[str, object],
        request: _Request,
        *,
        retained_members: list[dict[str, object]] | None,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        binding = self._dependency_projection_binding()
        assessment = self.assessment(observation)
        sources = self._dependency_projection_sources(request.source_paths)
        if retained_members is None:
            retained_members = [
                dict(cast("Mapping[str, object]", row["member"])) for row in sources
            ]
        source_scope = _source_scope(retained_members, sources)
        packages = _packages(observation, request, assessment)
        binding_current = observation["repository_binding"] == binding
        consumers = self._dependency_projection_consumers(
            observation,
            request,
            packages,
            assessment=assessment,
            source_scope=source_scope,
            binding_current=binding_current,
        )
        # Close every nominated input, including paths omitted by output bounds.
        if (
            self.assessment(observation) != assessment
            or self._dependency_projection_sources(request.source_paths) != sources
            or self._dependency_projection_binding() != binding
        ):
            raise UnstableFileError(
                "dependency projection inputs changed during observation"
            )
        consumer_observation = cast(
            "Mapping[str, object] | None", consumers["observation"]
        )
        producer = cast("Mapping[str, object]", observation["producer"])
        packet: dict[str, object] = {
            "schema": operation_schema("dependency_projection"),
            "request": request.packet(),
            "observation": observation,
            "derivation": self.derivation_authority(observation)
            if producer.get("adapter_semantics")
            else None,
            "assessment": assessment,
            "packages": packages,
            "source_scope": source_scope,
            "consumer_evidence": consumers,
            "repository": {
                "retained_binding": dict(
                    cast("Mapping[str, object]", observation["repository_binding"])
                ),
                "current_binding": binding,
                "binding_state": "current" if binding_current else "stale",
            },
            # Inventory coverage never qualifies the graph, module owners or the
            # consumer universe. Keep completeness on each canonical domain.
            "completeness": "incomplete",
            "truncation": "truncated"
            if consumers["omitted_node_count"]
            or any(row["truncation"] == "truncated" for row in packages)
            or any(row["truncation"] == "truncated" for row in sources)
            or consumer_observation is not None
            and consumer_observation["truncation"] == "truncated"
            else "complete",
            "negative_evidence": "not-admissible",
            "limits": {
                "packages": _MAX_PACKAGES,
                "source_paths": _MAX_PATHS,
                "source_bytes": _MAX_SOURCE_BYTES,
                "consumer_node_ids": _MAX_NODE_IDS,
                "results": request.limit,
                "max_depth": request.max_depth,
                "envelope_bytes": _MAX_ENVELOPE_BYTES,
            },
            "authority": "repository-intelligence-only",
            "producer_authority": "caller-claimed",
            "execution_authority": "external",
            "result_authority": "external",
            "certification_authority": "external",
            "storage": "request-scoped-not-persisted",
        }
        packet["projection_identity"] = _identity(
            operation_schema("dependency_projection"), packet
        )
        _encoded(packet)
        return packet
