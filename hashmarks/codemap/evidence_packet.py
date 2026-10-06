from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hashmarks.digest import hash_file
from hashmarks.evidence_context import evidence_context_identity
from hashmarks.operation_contract import (
    operation_response,
    operation_schema,
    validate_operation_response,
)

from .configuration_evidence import ConfigurationEvidenceMixin
from .decision_session import decision_scoped
from .evidence_decision_packet import (
    TASK_DECISION_DEFAULT_OPTIONS,
    DecisionPacketMixin,
)
from .evidence_freshness import freshness_state
from .model import EvidenceVisibility, SearchHit
from .python_ast import estimate_tokens
from .task_action_projection import TASK_ACTION_DEFAULT_OPTIONS

if TYPE_CHECKING:
    from .engine import CodeMap


TASK_DECISION_BRIEF_BUDGET_SWEEP_DEFAULTS = (64, 128, 192, 256, 384, 512)


@dataclass(frozen=True, slots=True)
class TaskActionBriefBudgetOptions:
    """Adaptive budget defaults for the model-facing task-action brief."""

    token_budget: int | None = None
    candidate_budgets: tuple[int, ...] = (
        32,
        64,
        96,
        128,
        192,
        256,
        384,
        512,
        768,
        1024,
    )


TASK_ACTION_BRIEF_BUDGET_DEFAULT_OPTIONS = TaskActionBriefBudgetOptions()


@dataclass(frozen=True, slots=True)
class TaskEvidenceOptions:
    """Default bounds for one public task-evidence request."""

    limit: int = 20
    per_role: int = 3
    token_budget: int = 1536


TASK_EVIDENCE_DEFAULT_OPTIONS = TaskEvidenceOptions()


@dataclass(frozen=True, slots=True)
class _TaskEvidenceRange:
    path: str
    role: str
    qualname: str | None
    name: str | None
    signature: str
    start: int | None
    end: int | None


class TaskEvidencePacketMixin(ConfigurationEvidenceMixin, DecisionPacketMixin):
    @staticmethod
    def _task_decision_anchor(value: object) -> dict[str, object] | None:
        if not isinstance(value, dict) or not value.get("path"):
            return None
        row: dict[str, object] = {"path": str(value["path"])}
        symbol = value.get("name") or value.get("qualname")
        if symbol:
            row["symbol"] = str(symbol)
        return row

    @operation_response("task_decision_brief")
    @decision_scoped
    def task_decision_brief(
        self,
        task: str,
        *,
        limit: int = TASK_DECISION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_DECISION_DEFAULT_OPTIONS.per_role,
        token_budget: int = TASK_DECISION_DEFAULT_OPTIONS.token_budget,
    ) -> dict[str, object]:
        """Return the minimal trustworthy first-stage action projection.

        The full decision packet remains available for diagnostics. Stage 1
        intentionally carries only the action anchors needed to inspect, edit, and
        verify plus safety/freshness signals.
        """
        packet = self.task_decision_packet(
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )

        edit = self._task_decision_anchor(packet.get("edit"))
        candidate = self._task_decision_anchor(packet.get("candidate"))
        verify = self._task_decision_anchor(packet.get("verify"))
        contract = self._task_decision_anchor(packet.get("contract"))
        used = {row["path"] for row in (edit, verify) if row is not None}
        if contract is not None and contract["path"] in used:
            contract = None
        plan = (
            packet.get("verification_plan")
            if isinstance(packet.get("verification_plan"), dict)
            else {}
        )
        context = (
            packet.get("context_budget")
            if isinstance(packet.get("context_budget"), dict)
            else {}
        )
        discrimination = (
            packet.get("discrimination")
            if isinstance(packet.get("discrimination"), dict)
            else {}
        )
        identity = (
            packet.get("identity") if isinstance(packet.get("identity"), dict) else {}
        )
        ownership = (
            packet.get("ownership_resolution")
            if isinstance(packet.get("ownership_resolution"), dict)
            else {}
        )
        owner_path = (
            ownership.get("owner_path")
            if isinstance(ownership.get("owner_path"), list)
            else []
        )
        result: dict[str, object] = {
            "schema": operation_schema("task_decision_brief"),
            "edit": edit,
            "candidate": candidate,
            "verify": verify,
            "verification_argv": list(plan.get("argv") or [])
            if plan.get("available")
            else None,
            "safe": bool(context.get("safe")) and edit is not None,
            "stale": identity.get("stale"),
            "decision_generation": identity.get("decision_generation"),
            "evidence_receipt": dict(packet.get("evidence_receipt") or {}),
            "full_packet_available": True,
        }
        if owner_path:
            result["owner_path"] = [
                {
                    "from": str(edge.get("from") or ""),
                    "to": str(edge.get("to") or ""),
                    "relation": str(edge.get("relation") or ""),
                }
                for edge in owner_path
            ]
        if contract is not None:
            result["contract"] = contract
        missing = list(context.get("missing_roles") or [])
        if missing:
            result["missing_roles"] = missing
        if bool(discrimination.get("needed")):
            result["discrimination"] = {
                "needed": True,
                "reason": str(discrimination.get("reason") or "unresolved"),
            }
        return result

    def _minimum_safe_action_budget(self, action: dict[str, object]) -> int:
        """Return exact tokens required by the mandatory action skeleton.

        ``work_context`` admits unique edit/verify/contract anchors before any
        discretionary evidence, so the minimum safe budget is simply the sum of
        those unique mandatory anchor costs. This is the production fast path;
        exhaustive budget sweeps remain a QA/diagnostic surface.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        used = 0
        seen: set[str] = set()
        for role in ("edit", "verify", "contract"):
            row = action.get(role)
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "")
            if not path or path in seen:
                continue
            seen.add(path)
            used += int(self._work_context_anchor(row, role=role)["estimated_tokens"])
        return used

    @staticmethod
    def _owner_path_text(action: Mapping[str, object]) -> str | None:
        """Render the already-selected ownership path without changing ownership."""
        ownership = action.get("ownership_resolution")
        ownership = ownership if isinstance(ownership, dict) else {}
        owner_path = ownership.get("owner_path")
        if not isinstance(owner_path, list) or not owner_path:
            return None
        first = owner_path[0] if isinstance(owner_path[0], dict) else {}
        chain = str(first.get("from") or "")
        for edge in owner_path:
            if not isinstance(edge, dict):
                continue
            target = str(edge.get("to") or "")
            if target:
                chain += f" --{str(edge.get('relation') or 'relates')}--> {target}"
        return chain or None

    @staticmethod
    def _task_action_selected_rows(
        action: Mapping[str, object],
    ) -> tuple[
        dict[str, object] | None, dict[str, object] | None, dict[str, object] | None
    ]:
        """Consume the action map's canonical Stage-1 edit projection."""
        selected = []
        for role in ("action_edit", "verify", "contract"):
            value = action.get(role)
            selected.append(value if isinstance(value, dict) else None)
        return selected[0], selected[1], selected[2]

    def _task_action_verification_plan(
        self,
        verify: Mapping[str, object] | None,
    ) -> dict[str, object]:
        """Project the selected verification evidence into its existing plan contract."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if verify is None or not verify.get("path"):
            return {
                "schema": "hashmarks.verification-plan.v1",
                "available": False,
                "reason": "no-verification-surface",
            }
        symbol = (
            str(verify.get("verification_test_symbol"))
            if verify.get("verification_test_symbol") is not None
            else str(verify.get("name"))
            if verify.get("name") is not None
            else None
        )
        return self.verification_plan(
            str(verify["path"]),
            symbol=symbol,
            qualname=str(verify.get("qualname"))
            if verify.get("qualname") is not None
            else None,
        )

    @staticmethod
    def _task_action_brief_verification(
        result: dict[str, object],
        verification: Mapping[str, object],
        verify: Mapping[str, object] | None,
    ) -> None:
        if not verification.get("available"):
            return
        argv = verification.get("argv")
        if isinstance(argv, list) and argv:
            result["verify"] = list(argv)
        if verify is not None and verify.get("path"):
            result["verify_path"] = str(verify["path"])

    def _task_action_brief_from_action(
        self,
        action: dict[str, object],
        *,
        task: str,
        token_budget: int,
        limit: int,
    ) -> dict[str, object]:
        """Project one already-resolved action map into model-facing evidence.

        This is intentionally a projection only.  Ranking, ownership, and
        verification authority remain owned by ``task_action_map`` and
        ``verification_plan``; the helper avoids recomputing repository
        retrieval merely to strip authority/debug metadata from the model view.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        del limit
        context = self.work_context(action, token_budget=token_budget)
        edit, verify, contract = self._task_action_selected_rows(action)
        verification = self._task_action_verification_plan(verify)
        evidence_receipt = self._decision_evidence_receipt(task, action, verification)
        stale = evidence_receipt.get("stale")

        safe = (
            bool(context.get("safe"))
            and edit is not None
            and bool(verification.get("available"))
        )
        result: dict[str, object] = {
            "schema": operation_schema("task_action_brief"),
            "status": (
                "unsafe"
                if not safe
                else "safe-stale"
                if stale is True
                else "safe-fresh"
                if stale is False
                else "safe-unknown"
            ),
            "candidate": action.get("candidate_path"),
            "authority_proof_identity": str(
                (
                    action.get("ownership_authority")
                    if isinstance(action.get("ownership_authority"), Mapping)
                    else {}
                ).get("authority_proof_identity")
                or ""
            ),
            "evidence_receipt": evidence_receipt,
        }
        if edit and edit.get("path"):
            result["edit"] = str(edit["path"])
        self._task_action_brief_verification(result, verification, verify)

        owner_path_text = self._owner_path_text(action)
        if owner_path_text is not None:
            result["owner_path"] = owner_path_text

        used_paths = {
            str(row.get("path"))
            for row in (edit, verify)
            if isinstance(row, dict) and row.get("path")
        }
        if (
            contract
            and contract.get("path")
            and str(contract["path"]) not in used_paths
        ):
            result["contract"] = str(contract["path"])

        missing = list(context.get("missing_roles") or [])
        if missing:
            result["missing"] = missing

        action_discrimination = action.get("action_discrimination")
        if not isinstance(action_discrimination, Mapping):
            raise AssertionError(
                "task action map must provide canonical action_discrimination"
            )
        if bool(action_discrimination.get("needed")):
            result["discrimination"] = str(
                action_discrimination.get("reason") or "unresolved"
            )
        return result

    def _task_evidence_current_symbol(
        self,
        path: str,
        *,
        qualname: str | None,
        name: str | None,
    ) -> Mapping[str, object] | None:
        """Rebind a selected evidence row to its unique current indexed symbol."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        current = self.store.symbol_at(path, qualname) if qualname else None
        if current is not None or not name:
            return current
        matches = [
            symbol
            for symbol in self._session_symbols_for_path(path)
            if str(symbol.get("name") or "") == name
        ]
        return matches[0] if len(matches) == 1 else None

    def _task_evidence_outline_item(
        self,
        *,
        path: str,
        role: str,
        symbol: str | None,
        signature: str,
        token_budget: int,
        pending: Mapping[str, object] | None,
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        """Return the smallest policy-safe structural fallback for selected evidence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        content = signature
        representation = "signature"
        if not content:
            outline = self.store.outline(path)
            if (
                outline is not None
                and EvidenceVisibility(str(outline["evidence_visibility"]))
                is not EvidenceVisibility.DENY
            ):
                content = str(outline.get("outline") or "").strip()
                representation = "outline"
        if content:
            estimated_tokens = estimate_tokens(content)
            if estimated_tokens <= token_budget:
                return {
                    "role": role,
                    "path": path,
                    "symbol": symbol,
                    "representation": representation,
                    "content": content,
                    "estimated_tokens": estimated_tokens,
                }, None if pending is None else dict(pending)
        return None, None if pending is None else dict(pending)

    def _task_evidence_visibility(self, path: str) -> EvidenceVisibility | None:
        """Return current source-disclosure policy for one already-selected path."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        file_row = self._session_file_row(path)
        if file_row is None:
            return None
        try:
            return EvidenceVisibility(str(file_row["evidence_visibility"]))
        except ValueError:
            return EvidenceVisibility.DENY

    def _task_evidence_current_range(
        self,
        path: str,
        row: Mapping[str, object],
    ) -> tuple[str | None, str | None, str, int | None, int | None]:
        """Rebind selected symbol/range evidence to the current repository index."""
        qualname = str(row.get("qualname") or "") or None
        name = str(row.get("name") or "") or None
        signature = str(row.get("signature") or "").strip()
        start_raw, end_raw = row.get("start_line"), row.get("end_line")
        start = int(start_raw) if isinstance(start_raw, int) and start_raw > 0 else None
        end = int(end_raw) if isinstance(end_raw, int) and end_raw > 0 else None
        current = self._task_evidence_current_symbol(path, qualname=qualname, name=name)
        if current is None:
            return qualname, name, signature, start, end
        qualname = str(current.get("qualname") or qualname or "") or None
        name = str(current.get("name") or name or "") or None
        signature = str(current.get("signature") or signature).strip()
        current_start, current_end = current.get("start_line"), current.get("end_line")
        start = (
            int(current_start)
            if isinstance(current_start, int) and current_start > 0
            else start
        )
        end = (
            int(current_end)
            if isinstance(current_end, int) and current_end > 0
            else end
        )
        return qualname, name, signature, start, end

    def _task_evidence_source_range(
        self,
        evidence: _TaskEvidenceRange,
        token_budget: int,
    ) -> tuple[dict[str, object] | None, dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        assert evidence.start is not None and evidence.end is not None
        try:
            body = self._source_slice(
                evidence.path,
                evidence.start,
                evidence.end,
                qualname=evidence.qualname,
            )
        except (OSError, PermissionError, FileNotFoundError):
            body = ""
        body_tokens = estimate_tokens(body) if body else 0
        common: dict[str, object] = {
            "role": evidence.role,
            "path": evidence.path,
            "symbol": evidence.qualname or evidence.name,
            "lines": [evidence.start, evidence.end],
        }
        if body and body_tokens <= token_budget:
            return {
                **common,
                "representation": "source-range",
                "content": body,
                "estimated_tokens": body_tokens,
            }, {}
        return None, {
            **common,
            "reason": "exact-source-range-exceeds-start-budget"
            if body
            else "exact-source-range-unavailable",
            **({"estimated_tokens": body_tokens} if body else {}),
        }

    def _task_evidence_path_admission(
        self, path: str, role: str
    ) -> tuple[EvidenceVisibility | None, dict[str, object] | None]:
        visibility = self._task_evidence_visibility(path)
        if visibility is None:
            return None, {
                "role": role,
                "path": path,
                "reason": "path-no-longer-indexed",
            }
        if visibility is EvidenceVisibility.DENY:
            return None, {
                "role": role,
                "path": path,
                "reason": "source-evidence-denied",
            }
        return visibility, None

    def _task_evidence_source_or_outline(
        self, evidence: _TaskEvidenceRange, token_budget: int
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        item, pending = self._task_evidence_source_range(evidence, token_budget)
        if item is not None:
            return item, None
        return self._task_evidence_outline_item(
            path=evidence.path,
            role=evidence.role,
            symbol=evidence.qualname or evidence.name,
            signature=evidence.signature,
            token_budget=token_budget,
            pending=pending,
        )

    def _task_evidence_evidence_item(
        self,
        row: dict[str, object],
        *,
        role: str,
        token_budget: int,
        task: str = "",
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        """Project one already-selected action row into bounded source evidence.

        The action map remains the authority for *which* path matters.  This
        helper only decides how much of that already-selected path can be shown
        under the repository's agent-visibility policy and the caller's budget.
        It never searches for a replacement owner and never invents a partial
        source body when the exact symbol range does not fit.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if token_budget < 0:
            raise ValueError("token_budget must be >= 0")
        path = str(row.get("path") or "")
        if not path:
            return None, None
        visibility, denied = self._task_evidence_path_admission(path, role)
        if denied is not None:
            return None, denied
        assert visibility is not None

        qualname, name, signature, start, end = self._task_evidence_current_range(
            path, row
        )
        evidence = _TaskEvidenceRange(
            path=path,
            role=role,
            qualname=qualname,
            name=name,
            signature=signature,
            start=start,
            end=end,
        )
        symbol = evidence.qualname or evidence.name
        if (
            visibility is EvidenceVisibility.SOURCE
            and evidence.start is not None
            and evidence.end is not None
        ):
            return self._task_evidence_source_or_outline(evidence, token_budget)
        elif visibility is EvidenceVisibility.SOURCE:
            config_item, config_pending = self._task_evidence_config_evidence(
                path,
                task=task,
                role=role,
                token_budget=token_budget,
            )
            if config_item is not None or config_pending is not None:
                return config_item, config_pending
            pending = {
                "role": role,
                "path": path,
                "symbol": symbol,
                "reason": "no-exact-symbol-range",
            }
        else:
            pending = {
                "role": role,
                "path": path,
                "symbol": symbol,
                "reason": "source-body-not-authorized",
            }

        # Preserve the smallest policy-safe structural evidence when the exact
        # source body cannot be included. The pending exact read stays explicit.
        return self._task_evidence_outline_item(
            path=path,
            role=role,
            symbol=symbol,
            signature=signature,
            token_budget=token_budget,
            pending=pending,
        )

    @staticmethod
    def _task_evidence_selection_reason(
        action: dict[str, object],
        edit: dict[str, object] | None,
    ) -> str:
        """Explain *why* the already-selected edit evidence is present.

        This is provenance over existing action authority only.  It never
        ranks candidates or changes ownership; the label simply records which
        mechanical projection selected the current edit path.
        """
        if edit is None:
            return "unresolved"
        path = str(edit.get("path") or "")
        ownership = action.get("ownership_resolution")
        if isinstance(ownership, dict) and str(ownership.get("selected") or "") == path:
            via = str(ownership.get("via") or "").strip()
            return (
                "literal-reference"
                if via == "references"
                else f"structural-{via}"
                if via
                else "structural-owner"
            )
        projection_reason = next(
            (
                reason
                for field, reason in (
                    ("locality_projection", "config-locality"),
                    ("literal_reference_projection", "literal-reference"),
                    ("structural_projection", "structural-owner"),
                )
                if edit.get(field)
            ),
            None,
        )
        if projection_reason is not None:
            return projection_reason
        domains = {str(value) for value in (edit.get("domains") or [])}
        roles = {str(value) for value in (edit.get("roles") or [])}
        reason = "canonical-edit-role"
        if "contract" in roles and domains.intersection({"contract", "ownership"}):
            reason = "contract-authority"
        elif domains.intersection({"config", "build", "plan"}):
            reason = "config-role"
        return reason

    @staticmethod
    def _task_evidence_freshness(
        generation: int,
        selection_generation: int,
        stale: bool | None,
        verification_stale: bool,
    ) -> tuple[str, str | None]:
        if generation != selection_generation:
            return "stale", "generation-changed-during-start"
        if verification_stale:
            return "stale", "verification-changed-since-selection"
        freshness = freshness_state(stale)
        reason = {
            "stale": "continuity-reported-change",
            "unknown": "filesystem-continuity-unproven",
        }.get(freshness)
        return freshness, reason

    def _task_evidence_provenance(
        self,
        action: dict[str, object],
        *,
        selection_generation: int,
        verification_stale: bool = False,
    ) -> dict[str, object]:
        """Return compact source-revision and freshness evidence for a start packet."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        edit = action.get("edit") if isinstance(action.get("edit"), dict) else None
        generation, identity_generation, stale = self._generation_status()
        freshness, freshness_reason = self._task_evidence_freshness(
            generation, selection_generation, stale, verification_stale
        )

        result: dict[str, object] = {
            "why": self._task_evidence_selection_reason(action, edit),
            "freshness": freshness,
        }
        if freshness == "current":
            result["freshness_proof"] = "proven"
        if edit is not None and edit.get("path"):
            file_row = self._session_file_row(str(edit["path"]))
            if file_row is not None and file_row["file_digest"]:
                # This is Hashmarks' domain-separated canonical file-content
                # digest, not an ad-hoc mtime or raw filesystem revision.
                result["revision"] = str(file_row["file_digest"])
        # Routine proven/unknown packets stay compact. Detailed generation
        # diagnostics are useful only when the packet is stale and needs a
        # refresh before the external agent acts.
        if freshness == "stale":
            result["freshness_reason"] = freshness_reason or "stale"
            result["generation"] = generation
            if identity_generation is not None:
                result["identity_generation"] = identity_generation
            if generation != selection_generation:
                result["selection_generation"] = selection_generation
        return result

    def _bind_task_evidence_evidence_context(
        self,
        provenance: dict[str, object],
        evidence_receipt: Mapping[str, object],
    ) -> dict[str, object]:
        """Bind compact start evidence to its exact repository/selection context.

        The decision-authority receipt already binds repository, task, generation,
        ownership and verification selection.  This context identity composes that
        existing authority with the selected source revision, explicit freshness
        state and native Hashmarks producer identity.  It adds no new authority.
        """
        bound = dict(provenance)
        bound["context_identity"] = evidence_context_identity(
            evidence_receipt, provenance
        )
        return bound

    @staticmethod
    def _task_evidence_base_result(
        task: str,
        action: Mapping[str, object],
        evidence_receipt: Mapping[str, object],
        verification_plan: Mapping[str, object],
    ) -> dict[str, object]:
        """Project task evidence into role-separated repository observations."""
        authority = (
            action.get("ownership_authority")
            if isinstance(action.get("ownership_authority"), Mapping)
            else {}
        )
        ambiguity = (
            action.get("ambiguity")
            if isinstance(action.get("ambiguity"), Mapping)
            else {}
        )
        candidate = (
            action.get("edit") if isinstance(action.get("edit"), Mapping) else None
        )
        owner = (
            action.get("admitted_edit")
            if isinstance(action.get("admitted_edit"), Mapping)
            else None
        )
        basis = str(action.get("owner_basis") or "") or None
        explicit_target_basis = (
            str(candidate.get("explicit_target_basis") or "")
            if isinstance(candidate, Mapping)
            else ""
        ) or basis
        explicit_bases = {
            "literal-path",
            "qualified-symbol",
            "unique-exact-symbol",
            "exact-symbol",
            "explicit-test-edit",
        }
        explicit_target = (
            {
                "status": "resolved",
                "basis": explicit_target_basis,
                "path": str(candidate.get("path") or ""),
                "symbol": candidate.get("qualname") or candidate.get("name"),
            }
            if candidate is not None and explicit_target_basis in explicit_bases
            else {
                "status": "not-explicit",
                "basis": None,
                "path": None,
                "symbol": None,
            }
        )
        verify = (
            action.get("verify") if isinstance(action.get("verify"), Mapping) else None
        )
        contract = (
            action.get("contract")
            if isinstance(action.get("contract"), Mapping)
            else None
        )
        return {
            "schema": operation_schema("task_evidence"),
            "task": task,
            "evidence_receipt": dict(evidence_receipt),
            "retrieval": {
                "results": list(action.get("canonical") or []),
                "bounds": dict(action.get("bounds") or {}),
                "ordering": "retrieval-relevance-only",
                "ownership_authority": False,
            },
            "explicit_target": explicit_target,
            "ownership": {
                "status": str(authority.get("status") or "unresolved"),
                "authority_proof_identity": str(
                    authority.get("authority_proof_identity") or ""
                ),
                "proof_scope": authority.get("proof_scope"),
                "proof_scope_complete": bool(authority.get("proof_scope_complete")),
                "owner": None if owner is None else dict(owner),
                "candidate": None if candidate is None else dict(candidate),
                "basis": basis if owner is not None else None,
                "candidate_basis": explicit_target_basis or basis,
                "ambiguity": dict(ambiguity),
                "authority": "repository-ownership-only",
                "source_evidence": None,
                "next_read": None,
                "source_budget": None,
            },
            "verification": {
                "selected": None if verify is None else dict(verify),
                "relevance": action.get("verification_relevance"),
                "plan": dict(verification_plan),
                "authority": "repository-verification-evidence-only",
            },
            "related": {
                "contract": None if contract is None else dict(contract),
                "inspect": list(action.get("inspect") or []),
                "candidates": list(action.get("related") or []),
            },
            "consumer_action": "external",
        }

    @staticmethod
    def _task_evidence_retrieval_locator(
        row: Mapping[str, object],
        *,
        rank: int | None = None,
    ) -> dict[str, object]:
        """Project one retrieval candidate into a compact non-authoritative locator."""
        result: dict[str, object] = {"path": str(row.get("path") or "")}

        if rank is not None:
            result["rank"] = rank

        symbol = row.get("qualname") or row.get("name")
        if symbol:
            result["symbol"] = str(symbol)

        roles = row.get("roles")
        if isinstance(roles, list) and roles:
            result["roles"] = [str(role) for role in roles if str(role)]

        start = row.get("start_line")
        end = row.get("end_line")
        if isinstance(start, int) and start > 0:
            result["start_line"] = start
        if isinstance(end, int) and end > 0:
            result["end_line"] = end

        visibility = row.get("evidence_visibility")
        if visibility:
            result["evidence_visibility"] = str(visibility)

        supplement = row.get("retrieval_supplement")
        if supplement:
            result["supplement"] = str(supplement)
        return result

    def _task_evidence_compact_retrieval(
        self,
        result: dict[str, object],
    ) -> None:
        """Compact retrieval presentation without changing ranking or ownership."""
        retrieval = result.get("retrieval")
        if not isinstance(retrieval, dict):
            raise AssertionError("task evidence retrieval projection must be a mapping")
        current = retrieval.get("results")
        if not isinstance(current, list):
            raise AssertionError("task evidence retrieval results must be a list")
        retrieval["results"] = [
            self._task_evidence_retrieval_locator(row, rank=rank)
            for rank, row in enumerate(current, 1)
            if isinstance(row, Mapping)
        ]
        retrieval["presentation"] = "compact-locators-v1"

    @staticmethod
    def _task_evidence_retrieval_query(task: str) -> str:
        """Exclude a separate output-format sentence from retrieval vocabulary."""
        directive = re.search(
            r"[.!?]\s+(?:return|output|respond with)\s+exactly\s+"
            r"(?:(?:one|an?|the)\s+)?"
            r"(?:JSON|YAML|XML|Markdown)\b",
            task,
            flags=re.IGNORECASE,
        )
        return task[: directive.start()].strip() if directive else task

    def _task_evidence_natural_candidate_paths(
        self,
        task: str,
        existing: Sequence[Mapping[str, object]],
        terms: Sequence[str],
        bound_reasons: set[str],
    ) -> list[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        paths = list(
            dict.fromkeys(
                str(row.get("path"))
                for row in existing
                if isinstance(row.get("path"), str) and row.get("path")
            )
        )[:16]
        salient = self._task_salient_natural_terms(
            task,
            limit=6,
            bound_reasons=bound_reasons,
        )
        rare_paths: list[str] = []
        for term in salient:
            hits = self._task_component_hits(
                term,
                bound_reasons,
                include_signature=True,
            )
            if not hits or len(hits) > 8:
                continue
            for hit in hits[:2]:
                if (
                    self.policy.decide(hit.path).evidence_visibility
                    is EvidenceVisibility.DENY
                ):
                    continue
                if hit.path not in rare_paths:
                    rare_paths.append(hit.path)
            if len(rare_paths) >= 4:
                break
        paths.extend(path for path in rare_paths[:4] if path not in paths)
        lexical = self._session_lexical_file_candidates(terms, limit=64)
        code_paths = [
            str(row["path"])
            for row in lexical
            if row.get("path") and row.get("language") not in {"text", "markdown"}
        ][:12]
        paths.extend(path for path in code_paths if path not in paths)
        return paths

    @staticmethod
    def _task_evidence_identifier_parts(name: str) -> tuple[str, ...]:
        parts: list[str] = []
        for piece in name.replace("-", "_").split("_"):
            parts.extend(
                part.lower()
                for part in re.findall(
                    r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", piece
                )
                if len(part) >= 2
            )
        return tuple(parts)

    @staticmethod
    def _task_evidence_phrase_relevance(
        parts: Sequence[str], query_tokens: Sequence[tuple[str, ...]]
    ) -> float:
        def matches(part: str, variant: str) -> bool:
            return variant == part or (len(part) >= 5 and variant.startswith(part))

        phrase_length = 0
        phrase_position = 0
        for start in range(len(parts)):
            for position in range(len(query_tokens)):
                length = 0
                while (
                    start + length < len(parts)
                    and position + length < len(query_tokens)
                    and any(
                        matches(parts[start + length], variant)
                        for variant in query_tokens[position + length]
                    )
                ):
                    length += 1
                if length > phrase_length or (
                    length == phrase_length and position > phrase_position
                ):
                    phrase_length, phrase_position = length, position
        return 2 * phrase_length + (
            12 * phrase_position / len(query_tokens) if phrase_length >= 2 else 0
        )

    @classmethod
    def _task_evidence_symbol_relevance(
        cls,
        name: str,
        query_tokens: Sequence[tuple[str, ...]],
        frequencies: Mapping[str, int],
        total: int,
    ) -> float:
        parts = cls._task_evidence_identifier_parts(name)
        if not parts:
            return 0.0

        def matches(part: str, variant: str) -> bool:
            return variant == part or (len(part) >= 5 and variant.startswith(part))

        weighted = 0.0
        matched_parts = 0
        for part in parts:
            options = [
                (variant, position)
                for position, variants in enumerate(query_tokens)
                for variant in variants
                if matches(part, variant)
            ]
            if not options:
                continue
            variant, position = max(options, key=lambda row: row[1])
            matched_parts += 1
            weighted += math.log((total + 1) / (frequencies.get(variant, 0) + 1)) * (
                1 + 0.5 * position / len(query_tokens)
            )
        if not matched_parts:
            return 0.0
        return (
            weighted
            + cls._task_evidence_phrase_relevance(parts, query_tokens)
            + 2 * matched_parts / len(parts)
        )

    def _task_evidence_scored_symbols(
        self,
        path: str,
        query_tokens: Sequence[tuple[str, ...]],
        frequencies: Mapping[str, int],
        total: int,
    ) -> list[tuple[float, Mapping[str, object]]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        scored: list[tuple[float, str, Mapping[str, object]]] = []
        for symbol in self._session_symbols_for_path(path):
            score = self._task_evidence_symbol_relevance(
                str(symbol.get("name") or ""), query_tokens, frequencies, total
            )
            if score > 0:
                scored.append(
                    (
                        score,
                        str(symbol.get("qualname") or symbol.get("name") or ""),
                        symbol,
                    )
                )
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [(row[0], row[2]) for row in scored[:8]]

    @staticmethod
    def _task_evidence_supplement_row(
        path: str,
        symbol: Mapping[str, object],
        *,
        score: float,
        visibility: EvidenceVisibility,
    ) -> dict[str, object]:
        def optional_text(key: str) -> str | None:
            value = symbol.get(key)
            return None if value is None else str(value)

        def optional_line(key: str) -> int | None:
            value = symbol.get(key)
            return value if isinstance(value, int) and value > 0 else None

        row = SearchHit(
            path=path,
            score=float(score),
            kind=str(symbol.get("kind") or "symbol"),
            name=optional_text("name"),
            qualname=optional_text("qualname"),
            signature=optional_text("signature"),
            start_line=optional_line("start_line"),
            end_line=optional_line("end_line"),
            evidence_visibility=visibility,
        ).as_dict()
        row["retrieval_supplement"] = "bounded-natural-language"
        row["score_basis"] = "natural-identifier-phrase-relevance"
        return row

    def _task_evidence_natural_retrieval_supplements(
        self,
        task: str,
        existing: Sequence[Mapping[str, object]],
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        """Add bounded retrieval-only evidence without changing action authority."""
        if limit < 10:
            return []
        existing_keys = {
            (
                str(row.get("path") or ""),
                str(row.get("symbol") or row.get("qualname") or row.get("name") or ""),
            )
            for row in existing
        }
        query = self._task_evidence_retrieval_query(task)
        terms, _truncated = self._task_natural_term_candidates(query)
        if not terms:
            return []
        term_set = set(terms)
        query_tokens = tuple(
            tuple(
                variant
                for variant in self._task_natural_term_variants(word)
                if variant in term_set
            )
            for word in re.findall(r"[A-Za-z]+", query.lower())
        )
        total, frequencies = self._session_lexical_document_frequencies(terms)
        bound_reasons: set[str] = set()
        paths = self._task_evidence_natural_candidate_paths(
            query, existing, terms, bound_reasons
        )
        eligible: list[tuple[str, EvidenceVisibility]] = []
        for path in paths:
            visibility = self._task_evidence_visibility(path)
            if (
                visibility is None
                or visibility is EvidenceVisibility.DENY
                or self.policy.decide(path).evidence_visibility
                is EvidenceVisibility.DENY
                or not self._indexed_path_current(path)
            ):
                continue
            eligible.append((path, visibility))
        self._session_preload_symbols([path for path, _ in eligible])
        scored_rows: list[tuple[float, int, str, dict[str, object]]] = []
        for path_rank, (path, visibility) in enumerate(eligible):
            for score, symbol in self._task_evidence_scored_symbols(
                path, query_tokens, frequencies, total
            ):
                key = (
                    path,
                    str(symbol.get("qualname") or symbol.get("name") or ""),
                )
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                scored_rows.append(
                    (
                        score,
                        path_rank,
                        str(symbol.get("qualname") or symbol.get("name") or ""),
                        self._task_evidence_supplement_row(
                            path, symbol, score=score, visibility=visibility
                        ),
                    )
                )
        scored_rows.sort(key=lambda row: (-row[0], row[1], row[2]))
        return [row[3] for row in scored_rows[:2]]

    def _task_evidence_attach_retrieval_supplements(
        self,
        result: dict[str, object],
        task: str,
        *,
        limit: int,
    ) -> None:
        retrieval = result.get("retrieval")
        if not isinstance(retrieval, dict):
            return
        current = retrieval.get("results")
        if not isinstance(current, list):
            return
        rows = [row for row in current if isinstance(row, Mapping)]
        supplements = self._task_evidence_natural_retrieval_supplements(
            task,
            rows,
            limit=limit,
        )
        if not supplements:
            return
        keep = max(0, limit - len(supplements))
        retrieval["results"] = [
            *current[:keep],
            *[self._task_evidence_retrieval_locator(row) for row in supplements],
        ]
        retrieval["canonical_omitted_results"] = max(0, len(current) - keep)
        retrieval["supplemental_results"] = len(supplements)
        retrieval["supplemental_authority"] = False
        retrieval["ordering"] = "canonical-then-bounded-natural-language"

    @staticmethod
    def _task_evidence_compact_evidence(
        item: Mapping[str, object] | None,
        pending: Mapping[str, object] | None,
        *,
        token_budget: int,
    ) -> tuple[dict[str, object] | None, dict[str, object] | None, dict[str, object]]:
        """Compact one already-selected evidence projection without changing selection."""
        compact_item = None
        used = 0
        complete = False
        if item is not None:
            compact_item = {
                key: value for key, value in item.items() if key not in {"role", "path"}
            }
            used = int(item.get("estimated_tokens") or 0)
            complete = item.get("representation") in {
                "source-range",
                "config-key-range",
            }
        compact_pending = (
            None
            if pending is None
            else {key: value for key, value in pending.items() if key != "role"}
        )
        return (
            compact_item,
            compact_pending,
            {
                "requested_tokens": token_budget,
                "estimated_tokens": used,
                "complete": complete,
            },
        )

    def _task_evidence_verification_stale(self, action: Mapping[str, object]) -> bool:
        """Check only the selected verification file against its indexed revision.

        This is a bounded closing fence, not a repository rescan. Selection still
        belongs to the action map; the fence only prevents a stale verification
        target from being emitted as safe-fresh after selection.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        verify = action.get("verify")
        if not isinstance(verify, Mapping) or not verify.get("path"):
            return False
        path = str(verify["path"])
        indexed = self._session_file_row(path)
        if indexed is None or not indexed["file_digest"]:
            return True
        try:
            current = hash_file(self.workspace / path).hash
        except (OSError, PermissionError, FileNotFoundError):
            return True
        return current != str(indexed["file_digest"])

    def _task_evidence_attach_provenance(
        self,
        result: dict[str, object],
        action: Mapping[str, object],
        *,
        selection_generation: int,
        verification_stale: bool = False,
    ) -> None:
        """Attach freshness independently from owner-resolution authority."""
        provenance = self._task_evidence_provenance(
            dict(action),
            selection_generation=selection_generation,
            verification_stale=verification_stale,
        )
        receipt = result.get("evidence_receipt")
        if not isinstance(receipt, Mapping):
            raise ValueError("task evidence is missing its evidence receipt")
        provenance = self._bind_task_evidence_evidence_context(
            provenance,
            receipt,
        )
        result["provenance"] = provenance
        result["freshness"] = {
            "state": str(provenance.get("freshness") or "unknown"),
            "reason": provenance.get("freshness_reason"),
        }

    def _task_evidence_attach_owner_source(
        self,
        result: dict[str, object],
        action: Mapping[str, object],
        *,
        task: str,
        token_budget: int,
    ) -> None:
        ownership = result["ownership"]
        if not isinstance(ownership, dict):
            raise AssertionError("task evidence ownership projection must be a mapping")
        owner_row = action.get("edit")
        item = pending = None
        if (
            ownership.get("status") == "resolved"
            and isinstance(owner_row, dict)
            and owner_row.get("path")
        ):
            item, pending = self._task_evidence_evidence_item(
                owner_row,
                role="owner",
                token_budget=token_budget,
                task=task,
            )
        compact_item, compact_pending, source_budget = (
            self._task_evidence_compact_evidence(
                item,
                pending,
                token_budget=token_budget,
            )
        )
        ownership["source_evidence"] = compact_item
        ownership["next_read"] = compact_pending
        ownership["source_budget"] = source_budget

    def task_evidence(
        self,
        task: str,
        *,
        limit: int = TASK_EVIDENCE_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_EVIDENCE_DEFAULT_OPTIONS.per_role,
        token_budget: int = TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
    ) -> dict[str, object]:
        """Return role-separated repository evidence for an external consumer."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if token_budget < 1:
            raise ValueError("token_budget must be >= 1")
        reconciled_task_paths = set(self._reconcile_cached_task_paths(task, limit))
        with self.decision_session():
            action = self.task_action_map(
                task,
                limit=limit,
                per_role=per_role,
            )
            selection_generation = self.store.generation()
            verify_row = (
                action.get("verify")
                if isinstance(action.get("verify"), Mapping)
                else None
            )
            verification_plan = self._task_action_verification_plan(verify_row)
            evidence_receipt = self._decision_evidence_receipt(
                task, action, verification_plan
            )
            result = self._task_evidence_base_result(
                task,
                action,
                evidence_receipt,
                verification_plan,
            )
            self._task_evidence_compact_retrieval(result)
            self._task_evidence_attach_retrieval_supplements(
                result,
                task,
                limit=limit,
            )

        self._task_evidence_attach_owner_source(
            result,
            action,
            task=task,
            token_budget=token_budget,
        )

        selected_verify = action.get("verify")
        selected_verify_path = (
            str(selected_verify.get("path"))
            if isinstance(selected_verify, Mapping) and selected_verify.get("path")
            else None
        )
        verification_stale = (
            selected_verify_path in reconciled_task_paths
            or self._task_evidence_verification_stale(action)
        )
        self._task_evidence_attach_provenance(
            result,
            action,
            selection_generation=selection_generation,
            verification_stale=verification_stale,
        )
        result["evidence_packet_identity"] = "sha256:" + self._packet_digest(
            operation_schema("task_evidence"),
            result,
        )
        return validate_operation_response("task_evidence", result)

    @operation_response("task_action_brief")
    @decision_scoped
    def task_action_brief(
        self,
        task: str,
        *,
        limit: int = TASK_ACTION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_ACTION_DEFAULT_OPTIONS.per_role,
        token_budget: int
        | None = TASK_ACTION_BRIEF_BUDGET_DEFAULT_OPTIONS.token_budget,
        candidate_budgets: Sequence[int] = (
            TASK_ACTION_BRIEF_BUDGET_DEFAULT_OPTIONS.candidate_budgets
        ),
    ) -> dict[str, object]:
        """Return the smallest model-facing Stage-1 action contract.

        The canonical action map is computed exactly once.  Authority/debug
        metadata remains available through ``task_decision_brief`` and the full
        packet, but producing the model projection must not repeat repository
        archaeology simply to discard that metadata again.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        action = self.task_action_map(
            task,
            limit=limit,
            per_role=per_role,
        )
        selected_budget = token_budget
        if selected_budget is None:
            normalized_budgets = sorted({int(value) for value in candidate_budgets})
            if not normalized_budgets or normalized_budgets[0] < 1:
                raise ValueError("candidate_budgets must contain positive integers")
            required = self._minimum_safe_action_budget(action)
            selected_budget = next(
                (budget for budget in normalized_budgets if budget >= required),
                normalized_budgets[-1],
            )
        return self._task_action_brief_from_action(
            action,
            task=task,
            token_budget=int(selected_budget),
            limit=limit,
        )

    @operation_response("task_decision_brief_budget_sweep")
    def task_decision_brief_budget_sweep(
        self,
        task: str,
        *,
        budgets: Sequence[int] = TASK_DECISION_BRIEF_BUDGET_SWEEP_DEFAULTS,
        limit: int = TASK_DECISION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_DECISION_DEFAULT_OPTIONS.per_role,
    ) -> dict[str, object]:
        """Measure the smallest worker-visible decision budget that stays safe.

        This evaluates the actual Stage-1 brief contract rather than only the
        internal work-context allocator. A budget qualifies only when the brief
        remains safe and therefore carries every mandatory role required by the
        current task. Visible JSON bytes are recorded as a tokenizer-independent
        evidence-size proxy; exact model-token accounting remains a harness metric.
        """
        normalized = sorted({int(value) for value in budgets})
        if not normalized or normalized[0] < 1:
            raise ValueError("budgets must contain positive integers")
        rows: list[dict[str, object]] = []
        for budget in normalized:
            brief = self.task_decision_brief(
                task,
                limit=limit,
                per_role=per_role,
                token_budget=budget,
            )
            encoded = json.dumps(brief, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
            missing = list(brief.get("missing_roles") or [])
            rows.append(
                {
                    "budget": budget,
                    "safe": bool(brief.get("safe")),
                    "missing_roles": missing,
                    "visible_brief_bytes": len(encoded),
                    "edit_available": isinstance(brief.get("edit"), dict),
                    "verify_available": isinstance(brief.get("verify"), dict),
                    "verification_argv_available": isinstance(
                        brief.get("verification_argv"), list
                    ),
                }
            )
        safe = [row for row in rows if bool(row["safe"])]
        smallest = int(safe[0]["budget"]) if safe else None
        smallest_row = safe[0] if safe else None
        return {
            "schema": operation_schema("task_decision_brief_budget_sweep"),
            "rows": rows,
            "smallest_safe_budget": smallest,
            "smallest_safe_visible_brief_bytes": (
                int(smallest_row["visible_brief_bytes"]) if smallest_row else None
            ),
            "optimization_target": "minimum-safe-agent-visible-evidence",
            "token_accounting": "visible-bytes-proxy-exact-model-tokens-harness-owned",
        }
