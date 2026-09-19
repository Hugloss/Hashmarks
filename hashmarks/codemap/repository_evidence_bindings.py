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

    def _observe_span(self, span: EvidenceSpan) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        path = self.workspace / span.path
        # Evidence identity is lexical repository evidence. Never follow a symlink
        # leaf or a symlinked ancestor into another filesystem authority.
        cursor = self.workspace
        symlinked = False
        for part in span.path.split("/"):
            cursor = cursor / part
            if cursor.is_symlink():
                symlinked = True
                break
        if symlinked:
            return {
                "path": span.path,
                "start_line": span.start_line,
                "end_line": span.end_line,
                "state": "unsupported",
                "reason": "symlink-evidence-not-observed",
            }
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return {
                "path": span.path,
                "start_line": span.start_line,
                "end_line": span.end_line,
                "state": "known-absent",
                "reason": "member-not-present",
            }
        except OSError:
            return {
                "path": span.path,
                "start_line": span.start_line,
                "end_line": span.end_line,
                "state": "unknown",
                "reason": "member-unreadable",
            }
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "path": span.path,
                "start_line": span.start_line,
                "end_line": span.end_line,
                "state": "unsupported",
                "reason": "member-not-utf8-text",
                "member_identity": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
        lines = text.splitlines(keepends=True)
        if span.end_line > len(lines):
            return {
                "path": span.path,
                "start_line": span.start_line,
                "end_line": span.end_line,
                "state": "known-absent",
                "reason": "declared-span-outside-member",
                "member_identity": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
        # splitlines(keepends=True) plus UTF-8 re-encoding preserves the exact
        # selected bytes for valid UTF-8, including CRLF/LF and a missing final newline.
        selected = b"".join(
            line.encode("utf-8") for line in lines[span.start_line - 1 : span.end_line]
        )
        return {
            "path": span.path,
            "start_line": span.start_line,
            "end_line": span.end_line,
            "state": "known-present",
            "member_identity": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "span_identity": "sha256:" + hashlib.sha256(selected).hexdigest(),
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
                relationships.append(
                    {
                        key: edge[key]
                        for key in ("path", "source", "kind", "target", "line", "confidence")
                        if edge.get(key) is not None
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
            dependency_rows = self._session_file_rows(declared_dependencies)
            dependencies = [
                {
                    "path": path,
                    "state": "known-present" if path in dependency_rows else "known-absent",
                    **(
                        {"member_identity": str(dependency_rows[path].get("file_digest") or "")}
                        if path in dependency_rows
                        else {}
                    ),
                }
                for path in declared_dependencies
            ]
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
                    "binding_identity": "sha256:"
                    + self._packet_digest(
                        "hashmarks.repository-evidence-binding.v1", binding_payload
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
                "stale": stale is not False,
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
