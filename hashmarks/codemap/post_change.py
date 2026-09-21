from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hashmarks.evidence_context import validate_evidence_context
from hashmarks.paths import normalize_relative_path

from .change_impact import ChangeImpactMixin

if TYPE_CHECKING:
    from pathlib import Path

    from .engine import CodeMap


@dataclass(frozen=True, slots=True)
class PostChangeOptions:
    """Previous anchors and bounds for one post-change projection."""

    previous_edit_path: str | None = None
    previous_verify_path: str | None = None
    limit: int = 20
    per_role: int = 3
    token_budget: int = 512


class PostChangeMixin(ChangeImpactMixin):
    @staticmethod
    def _post_change_previous_value(packet: Mapping[str, object], key: str) -> object:
        ownership = (
            packet.get("ownership")
            if isinstance(packet.get("ownership"), Mapping)
            else {}
        )
        verification = (
            packet.get("verification")
            if isinstance(packet.get("verification"), Mapping)
            else {}
        )
        if key == "candidate_path":
            candidate = (
                ownership.get("candidate")
                if isinstance(ownership.get("candidate"), Mapping)
                else {}
            )
            return str(candidate.get("path") or "") or None
        if key == "candidate_basis":
            return str(ownership.get("candidate_basis") or "") or None
        if key == "owner_path":
            owner = (
                ownership.get("owner")
                if isinstance(ownership.get("owner"), Mapping)
                else {}
            )
            return str(owner.get("path") or "") or None
        if key == "owner_basis":
            return str(ownership.get("basis") or "") or None
        if key == "verification_path":
            selected = (
                verification.get("selected")
                if isinstance(verification.get("selected"), Mapping)
                else {}
            )
            return str(selected.get("path") or "") or None
        if key == "verification_argv":
            plan = (
                verification.get("plan")
                if isinstance(verification.get("plan"), Mapping)
                else {}
            )
            argv = plan.get("argv")
            return tuple(str(item) for item in argv) if isinstance(argv, list) else None
        return packet.get(key)

    def _post_change_revision_snapshot(
        self, paths: Sequence[str]
    ) -> dict[str, str | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        revisions: dict[str, str | None] = {}
        for path in paths:
            row = self._session_file_row(path)
            revisions[path] = (
                None
                if row is None or not row["file_digest"]
                else str(row["file_digest"])
            )
        return revisions

    def _post_change_path_changes(
        self,
        paths: Sequence[str],
        before_revisions: Mapping[str, str | None],
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        changes: list[dict[str, object]] = []
        for path in paths:
            row = self._session_file_row(path)
            after_revision = (
                None
                if row is None or not row["file_digest"]
                else str(row["file_digest"])
            )
            before_revision = before_revisions[path]
            if before_revision is None and after_revision is None:
                state = "unindexed"
            elif before_revision is None:
                state = "added"
            elif after_revision is None:
                state = "removed"
            elif before_revision == after_revision:
                state = "unchanged"
            else:
                state = "changed"
            item: dict[str, object] = {"path": path, "state": state}
            if state in {"added", "changed"} and after_revision is not None:
                item["revision"] = after_revision
            changes.append(item)
        return changes

    def _validate_post_change_previous_evidence(
        self,
        task: str,
        previous_evidence: Mapping[str, object],
        *,
        generation_before: int,
    ) -> None:
        """Fail closed unless previous evidence belongs to this exact continuity cut."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        receipt = previous_evidence.get("evidence_receipt")
        provenance = previous_evidence.get("provenance")
        if not isinstance(receipt, Mapping) or not isinstance(provenance, Mapping):
            raise ValueError(
                "previous_evidence must contain bound authority receipt and provenance"
            )

        reasons: list[str] = []
        if (
            str(receipt.get("repository_identity") or "")
            != self._repository_packet_identity()
        ):
            reasons.append("repository-mismatch")
        expected_task = self._packet_digest("hashmarks.task.v1", {"task": task})
        if str(receipt.get("task_identity") or "") != expected_task:
            reasons.append("task-mismatch")
        if receipt.get("codemap_generation") != generation_before:
            reasons.append("codemap-generation-mismatch")
        context = validate_evidence_context(receipt, provenance)
        if not context["valid"]:
            reasons.extend(str(reason) for reason in context["reasons"])
        if reasons:
            raise ValueError(
                "previous_evidence continuity mismatch: "
                + ", ".join(dict.fromkeys(reasons))
            )

    def _post_change_previous_index_binding(
        self,
        previous_evidence: dict[str, object],
        previous_provenance: Mapping[str, object],
    ) -> tuple[str, str | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        previous_candidate = self._post_change_previous_value(
            previous_evidence, "candidate_path"
        )
        previous_revision = (
            str(previous_provenance.get("revision"))
            if previous_provenance.get("revision")
            else None
        )
        if not isinstance(previous_candidate, str) or not previous_revision:
            return "unbound", previous_revision
        row = self._session_file_row(previous_candidate)
        indexed_before = (
            None if row is None or not row["file_digest"] else str(row["file_digest"])
        )
        return (
            "current" if indexed_before == previous_revision else "mismatch"
        ), previous_revision

    def _post_change_current_evidence(
        self,
        task: str,
        *,
        limit: int,
        per_role: int,
        token_budget: int,
    ) -> tuple[dict[str, object], Mapping[str, object], str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        current = self.task_evidence(
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )
        provenance = (
            current.get("provenance")
            if isinstance(current.get("provenance"), Mapping)
            else {}
        )
        ownership = (
            current.get("ownership")
            if isinstance(current.get("ownership"), Mapping)
            else {}
        )
        return current, provenance, str(ownership.get("status") or "unresolved")

    def _post_change_evidence_diff(
        self,
        previous_evidence: dict[str, object],
        current: dict[str, object],
        previous_provenance: Mapping[str, object],
        provenance: Mapping[str, object],
        *,
        generation_changed: bool,
        previous_revision: str | None,
    ) -> tuple[list[str], list[str], dict[str, object]]:
        invalidated: list[str] = (
            ["previous-evidence-generation"] if generation_changed else []
        )
        reused: list[str] = []
        replacement: dict[str, object] = {}
        ownership_changed = False
        verification_changed = False
        for key, label, domain in (
            ("candidate_path", "task-candidate", "ownership"),
            ("candidate_basis", "candidate-basis", "ownership"),
            ("owner_path", "owner", "ownership"),
            ("owner_basis", "owner-basis", "ownership"),
            ("verification_path", "verification-surface", "verification"),
            ("verification_argv", "verification-plan", "verification"),
        ):
            previous_value = self._post_change_previous_value(previous_evidence, key)
            current_value = self._post_change_previous_value(current, key)
            if previous_value == current_value:
                if current_value not in (None, "", (), []):
                    reused.append(label)
                continue
            invalidated.append(label)
            if domain == "ownership":
                ownership_changed = True
            else:
                verification_changed = True

        if ownership_changed and isinstance(current.get("ownership"), Mapping):
            replacement["ownership"] = dict(current["ownership"])
        if verification_changed and isinstance(current.get("verification"), Mapping):
            replacement["verification"] = dict(current["verification"])

        previous_why = (
            str(previous_provenance.get("why"))
            if previous_provenance.get("why")
            else None
        )
        current_why = str(provenance.get("why")) if provenance.get("why") else None
        if previous_why == current_why and current_why is not None:
            reused.append("selection-provenance")
        elif previous_why != current_why:
            invalidated.append("selection-provenance")

        current_revision = (
            str(provenance.get("revision")) if provenance.get("revision") else None
        )
        if (
            previous_revision
            and current_revision
            and previous_revision == current_revision
        ):
            reused.append("candidate-source-revision")
        elif previous_revision != current_revision:
            invalidated.append("candidate-source-revision")

        if (
            previous_why != current_why
            or self._post_change_previous_value(previous_evidence, "candidate_path")
            != self._post_change_previous_value(current, "candidate_path")
        ):
            replacement["provenance"] = {
                key: provenance[key] for key in ("why", "revision") if key in provenance
            }
        return invalidated, reused, replacement

    def task_post_change_delta(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        previous_evidence: dict[str, object],
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 1536,
    ) -> dict[str, object]:
        """Refresh changed paths and report role-separated evidence invalidation."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if token_budget < 1:
            raise ValueError("token_budget must be >= 1")
        if (
            not isinstance(previous_evidence, dict)
            or previous_evidence.get("schema") != "hashmarks.task-evidence.v2"
        ):
            raise ValueError(
                "previous_evidence must be a hashmarks.task-evidence.v2 packet"
            )
        normalized = tuple(
            dict.fromkeys(
                normalize_relative_path(path, allow_root=False)
                for path in changed_paths
            )
        )
        if not normalized:
            raise ValueError(
                "changed_paths must contain at least one repository-relative path"
            )

        generation_before = self.store.generation()
        self._validate_post_change_previous_evidence(
            task,
            previous_evidence,
            generation_before=generation_before,
        )
        before_revisions = self._post_change_revision_snapshot(normalized)
        previous_provenance = (
            previous_evidence.get("provenance")
            if isinstance(previous_evidence.get("provenance"), Mapping)
            else {}
        )
        previous_index_binding, previous_revision = (
            self._post_change_previous_index_binding(
                previous_evidence,
                previous_provenance,
            )
        )
        sync_result = self.sync(normalized)
        path_changes = self._post_change_path_changes(normalized, before_revisions)
        current, provenance, ownership_status = self._post_change_current_evidence(
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )
        invalidated, reused, replacement = self._post_change_evidence_diff(
            previous_evidence,
            current,
            previous_provenance,
            provenance,
            generation_changed=sync_result.generation != generation_before,
            previous_revision=previous_revision,
        )
        freshness = (
            current.get("freshness")
            if isinstance(current.get("freshness"), Mapping)
            else {}
        )
        result: dict[str, object] = {
            "schema": "hashmarks.task-post-change-delta.v2",
            "change": "changed" if invalidated else "unchanged",
            "ownership_status": ownership_status,
            "path_changes": path_changes,
            "generation_before": generation_before,
            "generation_after": sync_result.generation,
            "invalidated": invalidated,
            "reused": reused,
            "freshness": str(freshness.get("state") or "unknown"),
            "scope": "changed-paths-only",
            "consumer_owner": "external",
        }
        if previous_index_binding != "current":
            result["previous_index_binding"] = previous_index_binding
        if any(
            (
                sync_result.derived_surfaces_changed,
                sync_result.derived_surfaces_preserved,
                sync_result.semantic_invalidation_shields,
            )
        ):
            result["semantic_invalidation"] = {
                "changed": sync_result.derived_surfaces_changed,
                "preserved": sync_result.derived_surfaces_preserved,
                "shields": sync_result.semantic_invalidation_shields,
            }
        if replacement:
            result["replacement"] = replacement
        return result

    def refresh_after_change_delta(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        options: PostChangeOptions = PostChangeOptions(),
    ) -> dict[str, object]:
        """Refresh changed paths and expose only changed action anchors."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        normalized = tuple(
            dict.fromkeys(
                normalize_relative_path(path, allow_root=False)
                for path in changed_paths
            )
        )
        if not normalized:
            raise ValueError(
                "changed_paths must contain at least one repository-relative path"
            )
        before = self.store.generation()
        sync_result = self.sync(normalized)
        brief = self.task_decision_brief(
            task,
            limit=options.limit,
            per_role=options.per_role,
            token_budget=options.token_budget,
        )
        edit = brief.get("edit") if isinstance(brief.get("edit"), dict) else None
        verify = brief.get("verify") if isinstance(brief.get("verify"), dict) else None
        current_edit = str(edit.get("path")) if edit and edit.get("path") else None
        current_verify = (
            str(verify.get("path")) if verify and verify.get("path") else None
        )
        prior_edit = (
            normalize_relative_path(options.previous_edit_path, allow_root=False)
            if options.previous_edit_path
            else None
        )
        prior_verify = (
            normalize_relative_path(options.previous_verify_path, allow_root=False)
            if options.previous_verify_path
            else None
        )
        result: dict[str, object] = {
            "schema": "hashmarks.refresh-delta.v1",
            "changed_paths": list(normalized),
            "generation": sync_result.generation,
        }
        if edit is not None and current_edit != prior_edit:
            result["edit"] = dict(edit)
            owner_path = brief.get("owner_path")
            if isinstance(owner_path, list) and owner_path:
                result["owner_path"] = list(owner_path)
        if verify is not None and current_verify != prior_verify:
            result["verify"] = dict(verify)
            argv = brief.get("verification_argv")
            if isinstance(argv, list):
                result["verification_argv"] = list(argv)
        if bool(brief.get("stale")):
            result["stale"] = True
        if not bool(brief.get("safe", True)):
            result["safe"] = False
        return result

    def refresh_after_change_brief(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 512,
    ) -> dict[str, object]:
        """Refresh changed paths and return a compact post-refresh decision."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        normalized = tuple(
            dict.fromkeys(
                normalize_relative_path(path, allow_root=False)
                for path in changed_paths
            )
        )
        if not normalized:
            raise ValueError(
                "changed_paths must contain at least one repository-relative path"
            )
        before = self.store.generation()
        started = time.perf_counter()
        sync_result = self.sync(normalized)
        refresh_ms = (time.perf_counter() - started) * 1000.0
        brief = self.task_decision_brief(
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )
        return {
            "schema": "hashmarks.post-change-refresh-brief.v1",
            "changed_paths": list(normalized),
            "generation_before": before,
            "generation_after": sync_result.generation,
            "refresh_ms": refresh_ms,
            "decision_brief": brief,
            "scope": "changed-paths-only",
            "consumer_owner": "external",
        }

    def refresh_after_change(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 512,
    ) -> dict[str, object]:
        """Refresh only changed repository paths, then emit fresh repository task evidence.

        The external consumer owns the change and reports changed paths. Hashmarks
        owns only incremental repository evidence refresh and evidence regeneration.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        normalized = tuple(
            dict.fromkeys(
                normalize_relative_path(path, allow_root=False)
                for path in changed_paths
            )
        )
        if not normalized:
            raise ValueError(
                "changed_paths must contain at least one repository-relative path"
            )
        before = self.store.generation()
        started = time.perf_counter()
        sync_result = self.sync(normalized)
        refresh_ms = (time.perf_counter() - started) * 1000.0
        packet = self.task_decision_packet(
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )
        return {
            "schema": "hashmarks.post-change-refresh.v1",
            "changed_paths": list(normalized),
            "generation_before": before,
            "generation_after": sync_result.generation,
            "refresh_ms": refresh_ms,
            "sync": sync_result.as_dict(),
            "packet": packet,
            "scope": "changed-paths-only",
            "consumer_owner": "external",
        }
