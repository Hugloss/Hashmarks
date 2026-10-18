from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hashmarks.file_store import UnstableFileError
from hashmarks.freshness import freshness_state
from hashmarks.operation_contract import operation_schema
from hashmarks.paths import normalize_relative_path

from .decision_session import ReadScopeOwner, decision_scoped
from .repository_evidence_binding_delta import RepositoryEvidenceBindingDeltaMixin
from .repository_evidence_coverage import RepositoryEvidenceCoverageMixin
from .repository_observation import (
    evidence_identity,
    packet_digest,
    repository_observer_packet,
)

if TYPE_CHECKING:
    from .decision_session import DecisionScope
    from .repository_source import RepositorySource


_MAX_BINDINGS = 256
_MAX_EVIDENCE_PER_BINDING = 256
_MAX_DEPENDENCIES_PER_BINDING = 512
_MAX_UNIQUE_PATHS = 2048
_MAX_RELATIONSHIPS_PER_PATH = 1000


def _binding_coordinate(value: object) -> int:
    if not isinstance(value, (int, str, float, bytes, bytearray)):
        raise TypeError("repository evidence coordinates must be numeric")
    return int(value)


def _binding_member_stamp(path: Path) -> tuple[int, ...] | None:
    """Request-local reuse check only; member digests remain content authority."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    """One exact repository-text span, expressed as one-based inclusive lines."""

    path: str
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class EvidenceMember:
    """One whole repository member with no text-locator assumption."""

    path: str


EvidenceReference = EvidenceSpan | EvidenceMember


@dataclass(slots=True)
class _BindingObservationRequest:
    dependency_paths: Mapping[str, Sequence[str]]
    relationship_limit_per_path: int
    include_relationships: bool
    seen: set[str] = field(default_factory=set)
    unique_paths: set[str] = field(default_factory=set)
    observations: dict[EvidenceSpan, dict[str, object]] = field(default_factory=dict)
    stamps: dict[str, tuple[int, ...]] = field(default_factory=dict)


class RepositoryBindings(
    RepositoryEvidenceBindingDeltaMixin, RepositoryEvidenceCoverageMixin, ReadScopeOwner
):
    """Observe opaque consumer bindings to exact repository evidence.

    This surface owns repository facts only. Binding identifiers are opaque;
    Hashmarks never interprets consumer policy or gives the result execution
    authority.
    """

    def __init__(self, source: RepositorySource) -> None:
        self.source = source
        self.workspace = source.workspace

    @property
    def reads(self) -> DecisionScope:
        return self.source.reads

    @staticmethod
    def _binding_span(raw: Mapping[str, object]) -> EvidenceSpan:
        path = normalize_relative_path(str(raw.get("path") or ""), allow_root=False)
        try:
            start = _binding_coordinate(raw["start_line"])
            end = _binding_coordinate(raw["end_line"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "evidence span requires integer start_line/end_line"
            ) from exc
        if start < 1 or end < start:
            raise ValueError("evidence span requires 1 <= start_line <= end_line")
        return EvidenceSpan(path, start, end)

    @staticmethod
    def _reference_sort_key(ref: EvidenceReference) -> tuple[str, str, int, int]:
        if isinstance(ref, EvidenceSpan):
            return ("lines", ref.path, ref.start_line, ref.end_line)
        return ("member", ref.path, 0, 0)

    @classmethod
    def _binding_reference(cls, raw: Mapping[str, object]) -> EvidenceReference:
        scope = str(raw.get("scope") or "lines")
        if scope == "member":
            if "start_line" in raw or "end_line" in raw:
                raise ValueError("member evidence must not declare line bounds")
            return EvidenceMember(
                normalize_relative_path(str(raw.get("path") or ""), allow_root=False)
            )
        if scope != "lines":
            raise ValueError("evidence scope must be 'lines' or 'member'")
        return cls._binding_span(raw)

    def _observe_span(self, span: EvidenceSpan) -> dict[str, object]:
        member, raw = self.source.member(span.path, include_bytes=True)
        base: dict[str, object] = {
            "scope": "lines",
            "path": span.path,
            "start_line": span.start_line,
            "end_line": span.end_line,
            "member_state": member["state"],
        }
        for key in ("member_revision", "evidence_visibility"):
            if key in member:
                base[key] = member[key]

        if member["state"] != "known-present" or raw is None:
            state = str(member["state"])
            return {
                **base,
                "state": state,
                "locator_state": state,
                "content_state": state,
                **({"reason": member["reason"]} if member.get("reason") else {}),
            }

        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            return {
                **base,
                "state": "unsupported",
                "locator_state": "unsupported",
                "content_state": "unsupported",
                "reason": "member-not-utf8-text",
            }

        lines = self.source._physical_lines(raw)
        if span.end_line > len(lines):
            return {
                **base,
                "state": "known-absent",
                "locator_state": "outside-member",
                "content_state": "known-absent",
                "reason": "declared-span-outside-member",
            }

        selected = b"".join(lines[span.start_line - 1 : span.end_line])
        digest = hashlib.sha256(
            b"hashmarks.repository-evidence-span.v1\0" + selected
        ).hexdigest()
        return {
            **base,
            "state": "known-present",
            "locator_state": "known-present",
            "content_state": "known-present",
            "span_identity": "sha256:" + digest,
            "byte_length": len(selected),
        }

    def _observe_reference(self, ref: EvidenceReference) -> dict[str, object]:
        if isinstance(ref, EvidenceSpan):
            return self._observe_span(ref)
        member, _raw = self.source.member(ref.path)
        return {
            "scope": "member",
            **member,
            "member_state": member["state"],
        }

    def _observe_reference_once(
        self, ref: EvidenceReference, request: _BindingObservationRequest
    ) -> dict[str, object]:
        if not isinstance(ref, EvidenceSpan):
            return self._observe_reference(ref)
        source = self.source._repository_member_source(ref.path)
        if isinstance(source, dict):
            return self._observe_reference(ref)
        stamp = _binding_member_stamp(source.path)
        if ref.path in request.stamps and stamp != request.stamps[ref.path]:
            raise UnstableFileError(
                f"binding source changed during observation: {ref.path}"
            )
        cached = request.observations.get(ref)
        if (
            cached is not None
            and cached.get("member_revision") == source.indexed_revision
        ):
            return deepcopy(cached)
        observed = self._observe_reference(ref)
        if stamp is not None and observed.get("state") == "known-present":
            request.stamps[ref.path] = stamp
            request.observations[ref] = deepcopy(observed)
        return observed

    def _validate_binding_snapshot(self, request: _BindingObservationRequest) -> None:
        for path, stamp in request.stamps.items():
            if _binding_member_stamp(self.workspace / path) != stamp:
                raise UnstableFileError(
                    f"binding source changed during observation: {path}"
                )

    @staticmethod
    def _reference_definition(ref: EvidenceReference) -> dict[str, object]:
        if isinstance(ref, EvidenceSpan):
            return {
                "scope": "lines",
                "path": ref.path,
                "start_line": ref.start_line,
                "end_line": ref.end_line,
            }
        return {"scope": "member", "path": ref.path}

    def _binding_relationships(
        self, evidence: Sequence[Mapping[str, object]], *, limit_per_path: int
    ) -> dict[str, object]:
        """Project bounded indexed relationships without inventing dependency authority."""
        paths = sorted(
            {
                str(row.get("path") or "")
                for row in evidence
                if row.get("state") == "known-present" and row.get("path")
            }
        )
        edges = self.reads.edges_for_paths_many(paths, limit_per_path=limit_per_path)
        relationships: list[dict[str, object]] = []
        for path in paths:
            for edge in edges.get(path, ()):
                fact = {
                    "path": path,
                    **{
                        key: edge[key]
                        for key in ("source", "kind", "target", "confidence")
                        if edge.get(key) is not None
                    },
                }
                relationships.append(
                    {
                        **fact,
                        **(
                            {"line": edge["line"]}
                            if edge.get("line") is not None
                            else {}
                        ),
                        "identity": evidence_identity(
                            "hashmarks.relationship-evidence.v1", fact
                        ),
                        "provenance": {
                            "source": "codemap-edge-index",
                            "path": path,
                        },
                    }
                )
        relationships.sort(
            key=lambda row: (
                str(row.get("path") or ""),
                _binding_coordinate(row.get("line") or 0),
                str(row.get("kind") or ""),
                str(row.get("target") or ""),
            )
        )
        return {
            "state": "observed",
            "scope_paths": paths,
            "relationships": relationships,
            "bounds": {
                "paths": len(paths),
                "limit_per_path": limit_per_path,
            },
            "completeness": "bounded-not-claimed",
        }

    @classmethod
    def _binding_references(cls, value: object) -> list[EvidenceReference]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError("binding evidence must be a sequence")
        if len(value) > _MAX_EVIDENCE_PER_BINDING:
            raise ValueError(
                f"binding evidence exceeds {_MAX_EVIDENCE_PER_BINDING} entries"
            )
        references = [
            cls._binding_reference(raw) for raw in value if isinstance(raw, Mapping)
        ]
        if len(references) != len(value):
            raise ValueError("each evidence item must be an object")
        references.sort(key=cls._reference_sort_key)
        return references

    def _observe_binding(
        self,
        raw_binding: Mapping[str, object],
        request: _BindingObservationRequest,
    ) -> dict[str, object]:
        binding_id = str(raw_binding.get("binding_id") or "").strip()
        if not binding_id:
            raise ValueError("binding_id must not be empty")
        if binding_id in request.seen:
            raise ValueError(f"duplicate binding_id: {binding_id}")
        request.seen.add(binding_id)
        references = self._binding_references(raw_binding.get("evidence"))
        evidence = [self._observe_reference_once(ref, request) for ref in references]
        declared_dependencies = sorted(
            {
                normalize_relative_path(path, allow_root=False)
                for path in request.dependency_paths.get(binding_id, ())
            }
        )
        if len(declared_dependencies) > _MAX_DEPENDENCIES_PER_BINDING:
            raise ValueError(
                f"binding dependencies exceeds {_MAX_DEPENDENCIES_PER_BINDING} entries"
            )
        request.unique_paths.update(ref.path for ref in references)
        request.unique_paths.update(declared_dependencies)
        if len(request.unique_paths) > _MAX_UNIQUE_PATHS:
            raise ValueError(
                f"binding request exceeds {_MAX_UNIQUE_PATHS} unique paths"
            )
        dependencies = [self.source.member(path)[0] for path in declared_dependencies]
        definition_payload = {
            "binding_id": binding_id,
            "evidence": [self._reference_definition(ref) for ref in references],
            "dependencies": declared_dependencies,
            "include_relationships": request.include_relationships,
            "relationship_limit_per_path": (
                request.relationship_limit_per_path
                if request.include_relationships
                else None
            ),
        }
        relationships = (
            self._binding_relationships(
                evidence, limit_per_path=request.relationship_limit_per_path
            )
            if request.include_relationships
            else {
                "state": "not-requested",
                "scope_paths": [],
                "relationships": [],
                "bounds": {
                    "paths": 0,
                    "limit_per_path": request.relationship_limit_per_path,
                },
                "completeness": "not-observed",
            }
        )
        binding_payload = {
            "binding_id": binding_id,
            "evidence": evidence,
            "dependencies": dependencies,
            "relationships": relationships,
        }
        return {
            **binding_payload,
            "binding_definition_identity": "sha256:"
            + packet_digest(
                "hashmarks.repository-evidence-binding-definition.v1",
                definition_payload,
            ),
            "binding_observation_identity": "sha256:"
            + packet_digest(
                "hashmarks.repository-evidence-binding-observation.v1",
                binding_payload,
            ),
        }

    @decision_scoped
    def observe(
        self,
        bindings: Sequence[Mapping[str, object]],
        *,
        dependency_paths: Mapping[str, Sequence[str]] | None = None,
        relationship_limit_per_path: int = 100,
        include_relationships: bool = True,
    ) -> dict[str, object]:
        """Return deterministic exact-span evidence for opaque consumer bindings."""
        if not isinstance(bindings, Sequence) or isinstance(bindings, (str, bytes)):
            raise ValueError("bindings must be a sequence")
        if len(bindings) > _MAX_BINDINGS:
            raise ValueError(f"bindings exceeds {_MAX_BINDINGS} entries")
        if not 1 <= relationship_limit_per_path <= _MAX_RELATIONSHIPS_PER_PATH:
            raise ValueError(
                "relationship_limit_per_path must be between 1 and "
                f"{_MAX_RELATIONSHIPS_PER_PATH}"
            )
        if any(not isinstance(raw, Mapping) for raw in bindings):
            raise ValueError("each binding must be an object")

        declared_ids = {
            str(raw.get("binding_id") or "").strip()
            for raw in bindings
            if isinstance(raw, Mapping)
        }
        unknown_dependency_bindings = set(dependency_paths or {}) - declared_ids
        if unknown_dependency_bindings:
            raise ValueError(
                "dependency_paths contains unknown binding ids: "
                + ", ".join(sorted(unknown_dependency_bindings))
            )

        generation, identity_generation, stale = self.reads.generation_status()
        request = _BindingObservationRequest(
            dependency_paths=dependency_paths or {},
            relationship_limit_per_path=relationship_limit_per_path,
            include_relationships=include_relationships,
        )
        rows: list[dict[str, object]] = []
        for raw_binding in bindings:
            assert isinstance(raw_binding, Mapping)
            rows.append(self._observe_binding(raw_binding, request))
        self._validate_binding_snapshot(request)
        rows.sort(key=lambda row: str(row["binding_id"]))
        payload: dict[str, object] = {
            "schema": operation_schema("repository_evidence", "observation"),
            "observer": repository_observer_packet(),
            "repository": {
                "repository_identity": self.reads.repository_identity(),
                "source_identity": self.source.packet_identity(
                    generation=generation,
                    identity_generation=identity_generation,
                    stale=stale,
                ),
                "codemap_generation": generation,
                "identity_generation": identity_generation,
                "freshness": freshness_state(stale),
            },
            "bindings": rows,
            "completeness": {
                "state": "complete",
                "scope": "explicit-declared-evidence",
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        payload["bindings_identity"] = "sha256:" + packet_digest(
            operation_schema("repository_evidence", "observation"), payload
        )
        return payload
