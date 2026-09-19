from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import decision_scoped

if TYPE_CHECKING:
    from .engine import CodeMap


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    """One exact repository-text span, expressed as one-based inclusive lines."""

    path: str
    start_line: int
    end_line: int


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
            "path": span.path,
            "start_line": span.start_line,
            "end_line": span.end_line,
            "member_state": member["state"],
        }
        for key in ("member_identity", "evidence_visibility"):
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
        if relationship_limit_per_path < 1:
            raise ValueError("relationship_limit_per_path must be >= 1")
        generation, identity_generation, stale = self._generation_status()
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        for raw_binding in bindings:
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
            evidence = [
                self._observe_span(self._binding_span(raw))
                for raw in raw_evidence
                if isinstance(raw, Mapping)
            ]
            if len(evidence) != len(raw_evidence):
                raise ValueError("each evidence item must be an object")
            declared_dependencies = sorted(
                {
                    normalize_relative_path(path, allow_root=False)
                    for path in (dependency_paths or {}).get(binding_id, ())
                }
            )
            dependencies = []
            for path in declared_dependencies:
                member, _raw = self._repository_member_observation(path)
                dependencies.append(member)

            definition_payload = {
                "binding_id": binding_id,
                "evidence": [
                    {
                        "path": row.path,
                        "start_line": row.start_line,
                        "end_line": row.end_line,
                    }
                    for row in (
                        self._binding_span(raw)
                        for raw in raw_evidence
                        if isinstance(raw, Mapping)
                    )
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
                "freshness": (
                    "stale"
                    if stale is True
                    else "current"
                    if stale is False
                    else "unknown"
                ),
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
