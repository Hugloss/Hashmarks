from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import decision_scoped
from .evidence_freshness import freshness_state

if TYPE_CHECKING:
    from .engine import CodeMap


_MAX_BINDINGS = 256
_MAX_EVIDENCE_PER_BINDING = 256
_MAX_DEPENDENCIES_PER_BINDING = 512
_MAX_UNIQUE_PATHS = 2048
_MAX_RELATIONSHIPS_PER_PATH = 1000


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


class RepositoryEvidenceBindingsMixin:
    """Observe opaque consumer bindings to exact repository evidence.

    This surface owns repository facts only. Binding identifiers are opaque;
    Hashmarks never interprets consumer policy or gives the result execution
    authority.
    """

    @staticmethod
    def _binding_span(raw: Mapping[str, object]) -> EvidenceSpan:
        path = normalize_relative_path(str(raw.get("path") or ""), allow_root=False)
        try:
            start = int(raw["start_line"])
            end = int(raw["end_line"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("evidence span requires integer start_line/end_line") from exc
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

    @staticmethod
    def _physical_lines(raw: bytes) -> list[bytes]:
        """Split physical repository lines only on LF while preserving exact bytes."""
        if not raw:
            return []
        parts = raw.split(b"\n")
        lines = [part + b"\n" for part in parts[:-1]]
        if parts[-1]:
            lines.append(parts[-1])
        return lines

    def _observe_span(self, span: EvidenceSpan) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        member, raw = self._repository_member_observation(
            span.path, include_bytes=True
        )
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

        lines = self._physical_lines(raw)
        if span.end_line > len(lines):
            return {
                **base,
                "state": "known-absent",
                "locator_state": "known-absent",
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
        member, _raw = self._repository_member_observation(ref.path)
        return {
            "scope": "member",
            **member,
            "member_state": member["state"],
        }

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
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        paths = sorted(
            {
                str(row.get("path") or "")
                for row in evidence
                if row.get("state") == "known-present" and row.get("path")
            }
        )
        edges = self._session_edges_for_paths_many(
            paths, limit_per_path=limit_per_path
        )
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
                        "identity": self._evidence_identity(
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
                int(row.get("line") or 0),
                str(row.get("kind") or ""),
                str(row.get("target") or ""),
            )
        )
        return {
            "state": "observed",
            "relationships": relationships,
            "bounds": {
                "paths": len(paths),
                "limit_per_path": limit_per_path,
            },
            "completeness": "bounded-not-claimed",
        }

    @decision_scoped
    def repository_evidence_bindings(
        self,
        bindings: Sequence[Mapping[str, object]],
        *,
        dependency_paths: Mapping[str, Sequence[str]] | None = None,
        relationship_limit_per_path: int = 100,
        include_relationships: bool = True,
    ) -> dict[str, object]:
        """Return deterministic exact-span evidence for opaque consumer bindings."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
        unknown_dependency_bindings = (
            set(dependency_paths or {}) - declared_ids
        )
        if unknown_dependency_bindings:
            raise ValueError(
                "dependency_paths contains unknown binding ids: "
                + ", ".join(sorted(unknown_dependency_bindings))
            )

        generation, identity_generation, stale = self._generation_status()
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        unique_paths: set[str] = set()
        for raw_binding in bindings:
            assert isinstance(raw_binding, Mapping)
            binding_id = str(raw_binding.get("binding_id") or "").strip()
            if not binding_id:
                raise ValueError("binding_id must not be empty")
            if binding_id in seen:
                raise ValueError(f"duplicate binding_id: {binding_id}")
            seen.add(binding_id)
            raw_evidence = raw_binding.get("evidence")
            if not isinstance(raw_evidence, Sequence) or isinstance(
                raw_evidence, (str, bytes)
            ):
                raise ValueError("binding evidence must be a sequence")
            if len(raw_evidence) > _MAX_EVIDENCE_PER_BINDING:
                raise ValueError(
                    "binding evidence exceeds "
                    f"{_MAX_EVIDENCE_PER_BINDING} entries"
                )
            references = [
                self._binding_reference(raw)
                for raw in raw_evidence
                if isinstance(raw, Mapping)
            ]
            if len(references) != len(raw_evidence):
                raise ValueError("each evidence item must be an object")
            references.sort(key=self._reference_sort_key)
            evidence = [self._observe_reference(ref) for ref in references]
            declared_dependencies = sorted(
                {
                    normalize_relative_path(path, allow_root=False)
                    for path in (dependency_paths or {}).get(binding_id, ())
                }
            )
            if len(declared_dependencies) > _MAX_DEPENDENCIES_PER_BINDING:
                raise ValueError(
                    "binding dependencies exceeds "
                    f"{_MAX_DEPENDENCIES_PER_BINDING} entries"
                )
            unique_paths.update(ref.path for ref in references)
            unique_paths.update(declared_dependencies)
            if len(unique_paths) > _MAX_UNIQUE_PATHS:
                raise ValueError(
                    f"binding request exceeds {_MAX_UNIQUE_PATHS} unique paths"
                )

            dependencies = []
            for path in declared_dependencies:
                member, _raw = self._repository_member_observation(path)
                dependencies.append(member)

            definition_payload = {
                "binding_id": binding_id,
                "evidence": [
                    self._reference_definition(ref) for ref in references
                ],
                "dependencies": declared_dependencies,
                "include_relationships": include_relationships,
                "relationship_limit_per_path": relationship_limit_per_path,
            }
            binding_payload = {
                "binding_id": binding_id,
                "evidence": evidence,
                "dependencies": dependencies,
                "relationships": (
                    self._binding_relationships(
                        evidence, limit_per_path=relationship_limit_per_path
                    )
                    if include_relationships
                    else {
                        "state": "not-requested",
                        "relationships": [],
                        "bounds": {"paths": 0, "limit_per_path": relationship_limit_per_path},
                        "completeness": "not-observed",
                    }
                ),
            }
            rows.append(
                {
                    **binding_payload,
                    "binding_definition_identity": "sha256:"
                    + self._packet_digest(
                        "hashmarks.repository-evidence-binding-definition.v1",
                        definition_payload,
                    ),
                    "binding_observation_identity": "sha256:"
                    + self._packet_digest(
                        "hashmarks.repository-evidence-binding-observation.v1",
                        binding_payload,
                    ),
                }
            )
        rows.sort(key=lambda row: str(row["binding_id"]))
        payload: dict[str, object] = {
            "schema": "hashmarks.repository-evidence-bindings.v1",
            "repository": {
                "repository_identity": self._repository_packet_identity(),
                "codemap_generation": generation,
                "identity_generation": identity_generation,
                "freshness": freshness_state(stale),
            },
            "bindings": rows,
            "completeness": {
                "state": "known-present",
                "scope": "explicit-declared-evidence",
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        payload["bindings_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.repository-evidence-bindings.v1", payload
        )
        return payload
