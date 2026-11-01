"""Bounded verifier context over existing source, import-root and project owners.

Ancestor manifest observations describe repository scope, never a process cwd.
Missing retained project evidence stays unknown even when a manifest is current.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .repository_observation import evidence_identity
from .verification_plan import _UnqualifiedNominationMember

if TYPE_CHECKING:
    from .evidence_verification import RepositoryVerification


MAX_CONTEXT_ANCESTORS = 32
MAX_CONTEXT_PROJECTS = 32


def _context_manifest_names(path: str) -> tuple[str, ...]:
    target = PurePosixPath(path)
    if target.suffix in {".py", ".pyi"} or target.name == "pyproject.toml":
        return ("pyproject.toml",)
    if (
        target.suffix in {".ts", ".tsx", ".mts", ".cts"}
        or target.name == "tsconfig.json"
    ):
        return ("package.json", "tsconfig.json")
    if (
        target.suffix in {".js", ".jsx", ".mjs", ".cjs"}
        or target.name == "package.json"
    ):
        return ("package.json",)
    return ()


class VerificationContextMixin:
    def _verification_manifest(
        self, path: str, filename: str, members: list[dict[str, object]]
    ) -> tuple[str | None, bytes | None]:
        """Observe the nearest manifest and every nearer absence that supports it.

        A denied/unreadable candidate cannot be skipped to promote an ancestor.
        The ledger makes adding a nearer declaration invalidate retained evidence.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        parent = PurePosixPath(path).parent
        ancestors = (parent, *parent.parents)
        for ancestor in ancestors[:MAX_CONTEXT_ANCESTORS]:
            candidate = (ancestor / filename).as_posix()
            raw = self._nomination_source_member(candidate, members)
            if raw is not None:
                return candidate, raw
        if len(ancestors) > MAX_CONTEXT_ANCESTORS:
            raise _UnqualifiedNominationMember("manifest-ancestor-limit")
        return None, None

    def _verification_manifest_context(
        self, path: str, members: list[dict[str, object]]
    ) -> tuple[list[dict[str, object]], list[str]]:
        contexts: list[dict[str, object]] = []
        reasons: list[str] = []
        for filename in _context_manifest_names(path):
            try:
                manifest, _ = self._verification_manifest(path, filename, members)
            except _UnqualifiedNominationMember as exc:
                reason = (
                    "manifest-ancestor-limit"
                    if str(exc) == "manifest-ancestor-limit"
                    else "manifest-source-unqualified"
                )
                reasons.append(reason)
                contexts.append({"kind": filename, "state": "unknown"})
            else:
                contexts.append(
                    {
                        "kind": filename,
                        "state": "known-present" if manifest else "known-absent",
                        "manifest": manifest,
                        "root": PurePosixPath(manifest).parent.as_posix()
                        if manifest
                        else None,
                    }
                )
        return contexts, sorted(set(reasons))

    def _verification_python_context_inputs(
        self, path: str, members: list[dict[str, object]]
    ) -> list[str]:
        """Requalify packaging and root workspace inputs before projecting roots."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if "pyproject.toml" not in _context_manifest_names(path):
            return []
        observed = {row["path"] for row in members}
        parent = PurePosixPath(path).parent
        ancestors = (parent, *parent.parents)
        reasons: list[str] = []
        for ancestor in ancestors[:MAX_CONTEXT_ANCESTORS]:
            manifest = (ancestor / "pyproject.toml").as_posix()
            if manifest in observed:
                continue
            try:
                self._nomination_source_member(manifest, members)
            except _UnqualifiedNominationMember:
                reasons.append("workspace-source-unqualified")
        if len(ancestors) > MAX_CONTEXT_ANCESTORS:
            reasons.append("manifest-ancestor-limit")
        return reasons

    def _verification_project_context(self, path: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        projects = self.native._fresh_projects_for_path(path)
        nearest_depth = max(
            (len(PurePosixPath(row["root"]).parts) for row in projects), default=-1
        )
        nearest = [
            row
            for row in projects
            if len(PurePosixPath(row["root"]).parts) == nearest_depth
        ]
        ambiguous = len(nearest) > 1 or any(
            isinstance(row.get("metadata"), dict)
            and row["metadata"].get("name_resolution") == "ambiguous"
            for row in nearest
        )
        return {
            "state": "ambiguous"
            if ambiguous
            else "resolved-unique"
            if nearest
            else "unknown",
            "project_id": nearest[0]["project_id"]
            if len(nearest) == 1 and not ambiguous
            else None,
            "projects": projects[:MAX_CONTEXT_PROJECTS],
            "project_count": len(projects),
            "omitted_projects": max(0, len(projects) - MAX_CONTEXT_PROJECTS),
            "freshness": "current" if projects else "unknown",
            "completeness": "unknown",
            "authority": "retained-qualified-project-evidence",
        }

    def _verification_context(self, path: str) -> dict[str, object]:
        """Compose current ancestor metadata and qualified retained project facts.

        Python roots are projected from Index's existing packaging interpretation.
        Manifest proximity is not promoted into native project identity.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        rel = normalize_relative_path(path, allow_root=False)
        members: list[dict[str, object]] = []
        manifests, reasons = self._verification_manifest_context(rel, members)
        reasons = sorted(
            set(reasons + self._verification_python_context_inputs(rel, members))
        )
        projects = self._verification_project_context(rel)
        roots = [
            root
            for root in self.source.index.python_import_roots
            if not reasons
            and "pyproject.toml" in _context_manifest_names(rel)
            and (rel == root or rel.startswith(root.rstrip("/") + "/"))
        ]
        roots.sort(key=lambda root: (-len(root), root))
        bounded = bool(
            "manifest-ancestor-limit" in reasons
            or projects["omitted_projects"]
            or len(roots) > MAX_CONTEXT_PROJECTS
        )
        payload: dict[str, object] = {
            "schema": "hashmarks.verification-context.v1",
            "path": rel,
            "repository_identity": self.reads.repository_identity(),
            **self.reads.freshness_fields(),
            "manifests": manifests,
            "supporting_source_members": members,
            "python_source_roots": roots[:MAX_CONTEXT_PROJECTS],
            "source_root_state": "qualified" if roots and not reasons else "unknown",
            "project": projects,
            "completeness": "incomplete" if reasons or bounded else "complete",
            "truncation": "truncated" if bounded else "complete",
            "scope": "ancestor-manifests-and-retained-project-evidence",
            "reasons": reasons,
            "bounds": {
                "manifest_ancestors": MAX_CONTEXT_ANCESTORS,
                "projects": MAX_CONTEXT_PROJECTS,
                "source_roots": MAX_CONTEXT_PROJECTS,
            },
            "authority": "repository-context-only",
            "execution_effect": "none",
        }
        payload["context_identity"] = evidence_identity(
            "hashmarks.verification-context.v1", payload
        )
        return payload
