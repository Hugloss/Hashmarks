from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

if TYPE_CHECKING:
    from .engine import CodeMap


class RepositoryEvidenceCoverageMixin:
    """Classify an explicit repository change set against opaque evidence bindings."""

    @staticmethod
    def _coverage_binding_paths(packet: Mapping[str, object]) -> tuple[set[str], set[str]]:
        evidence_paths: set[str] = set()
        dependency_paths: set[str] = set()
        rows = packet.get("bindings")
        if not isinstance(rows, list):
            return evidence_paths, dependency_paths
        for binding in rows:
            if not isinstance(binding, Mapping):
                continue
            evidence = binding.get("evidence")
            if isinstance(evidence, list):
                evidence_paths.update(
                    str(row.get("path") or "")
                    for row in evidence
                    if isinstance(row, Mapping) and row.get("path")
                )
            dependencies = binding.get("dependencies")
            if isinstance(dependencies, list):
                dependency_paths.update(
                    str(row.get("path") or "")
                    for row in dependencies
                    if isinstance(row, Mapping) and row.get("path")
                )
        return evidence_paths, dependency_paths

    def repository_evidence_coverage(
        self,
        bindings_packet: Mapping[str, object],
        *,
        changed_paths: Sequence[str],
        change_set_complete: bool,
        binding_delta: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Classify explicit changed paths without overstating incomplete observations."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if bindings_packet.get("schema") != "hashmarks.repository-evidence-bindings.v1":
            raise ValueError("bindings_packet must be repository evidence bindings")
        changed = sorted(
            {
                normalize_relative_path(path, allow_root=False)
                for path in changed_paths
            }
        )
        if (
            binding_delta is not None
            and binding_delta.get("schema")
            != "hashmarks.repository-evidence-binding-delta.v1"
        ):
            raise ValueError("binding_delta must be a repository evidence binding delta")
        evidence_paths, dependency_paths = self._coverage_binding_paths(bindings_packet)
        bound_members = sorted(set(changed) & evidence_paths)
        dependency_affected = sorted(
            (set(changed) & dependency_paths) - set(bound_members)
        )
        outside = sorted(
            set(changed) - evidence_paths - dependency_paths
        )
        direct_changed: set[str] = set()
        member_only: set[str] = set()
        if binding_delta is not None:
            delta_bindings = binding_delta.get("bindings")
            changed_bindings = (
                delta_bindings.get("changed")
                if isinstance(delta_bindings, Mapping)
                else []
            )
            if isinstance(changed_bindings, list):
                for binding in changed_bindings:
                    direct = binding.get("direct_evidence") if isinstance(binding, Mapping) else None
                    changes = direct.get("changes") if isinstance(direct, Mapping) else None
                    if not isinstance(changes, list):
                        continue
                    for change in changes:
                        if not isinstance(change, Mapping):
                            continue
                        evidence = change.get("evidence")
                        if not isinstance(evidence, list) or not evidence:
                            continue
                        path = str(evidence[0])
                        if change.get("direct_content_changed") is True:
                            direct_changed.add(path)
                        elif change.get("member_changed") is True:
                            member_only.add(path)
        direct_changed &= set(bound_members)
        member_only = (member_only & set(bound_members)) - direct_changed
        precision_unknown = set(bound_members) - direct_changed - member_only
        classification = {
            "changed_inside_bound_evidence": sorted(direct_changed),
            "changed_elsewhere_in_bound_member": sorted(member_only),
            "bound_member_precision_unknown": sorted(precision_unknown),
            "dependency_affected": dependency_affected,
            "outside_declared_bindings": outside if change_set_complete else [],
            "outside_declared_bindings_candidates": outside if not change_set_complete else [],
        }
        payload: dict[str, object] = {
            "schema": "hashmarks.repository-evidence-coverage.v1",
            "changed_paths": changed,
            "classification": classification,
            "precision": {
                "bound_range": "known" if binding_delta is not None else "unknown",
                "reason": (
                    "binding-delta-supplied"
                    if binding_delta is not None
                    else "path-change-set-cannot-prove-range-impact"
                ),
            },
            "coverage": {
                "state": "complete" if change_set_complete else "incomplete",
                "outside_classification": (
                    "known" if change_set_complete else "unknown"
                ),
                "reason": (
                    "caller-declared-complete-change-set"
                    if change_set_complete
                    else "caller-change-set-completeness-not-proven"
                ),
            },
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        payload["coverage_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.repository-evidence-coverage.v1", payload
        )
        return payload
